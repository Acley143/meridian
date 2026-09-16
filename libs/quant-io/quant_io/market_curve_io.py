"""The `market.curves` producer, and the shared curve validator (ADR-0027).

`validate_market_curve` is the single validator used by the producer here
and, later, by the consumer (ADR-0027 Decision 3) -- a record failing it is
rejected in both directions, never silently accepted by one side only.
"""
from __future__ import annotations

import math
import re
from collections.abc import Sequence
from decimal import Decimal

from meridian_contracts import market_curves as market_curve_schema
from meridian_contracts import market_curves_key as market_curve_key_schema
from meridian_contracts.market_curves import CurveKind, MarketCurve
from meridian_contracts.market_curves_key import CurveKind as KeyCurveKind
from meridian_contracts.market_curves_key import MarketCurveKey

from quant_io.consumer import AvroConsumer, OnAssign
from quant_io.producer import AvroProducer, DeliveryError
from quant_io.topic_admin import ensure_compacted_topic

MARKET_CURVES_TOPIC = "market.curves"

_CURVE_ID_PATTERNS = {
    CurveKind.RISK_FREE_RATE: re.compile(r"^[A-Z]{3}$"),
    CurveKind.FX_RATE: re.compile(r"^[A-Z]{6}$"),
}
_FLOAT_KINDS = (CurveKind.RISK_FREE_RATE, CurveKind.VOLATILITY, CurveKind.DIVIDEND_YIELD)
_NON_EMPTY_CURVE_ID_KINDS = (CurveKind.VOLATILITY, CurveKind.DIVIDEND_YIELD)

# decimal(38,8), the wire type for FX_RATE's value_decimal (ADR-0027
# Decision 3, ADR-0013): at most 30 integer digits and 8 fractional digits.
_MAX_INTEGER_DIGITS = 30
_MAX_FRACTIONAL_DIGITS = 8


class InvalidMarketCurveError(ValueError):
    """A `MarketCurve` (or a batch of them) violates ADR-0027's shape
    invariants."""


def _fits_decimal_38_8(value: Decimal) -> bool:
    """Whether `value` is finite and representable as decimal(38,8) --
    checked directly against `Decimal.as_tuple()` rather than by quantizing
    (quant_core.numeric.to_money quantizes silently, which would accept and
    round away exactly the shapes this must reject)."""
    if not value.is_finite():
        return False
    _sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        return False  # only reachable for Inf/NaN, already excluded above
    fractional_digits = max(0, -exponent)
    integer_digits = max(0, len(digits) + exponent)
    return fractional_digits <= _MAX_FRACTIONAL_DIGITS and integer_digits <= _MAX_INTEGER_DIGITS


def validate_market_curve(curve: MarketCurve) -> None:
    """The single validator shared by the producer (this module) and,
    later, the consumer (ADR-0027 Decision 3). Raises
    `InvalidMarketCurveError`, naming the curve's `scenario_id`, `kind`,
    and `curve_id`, on any violation."""

    def _fail(reason: str) -> None:
        raise InvalidMarketCurveError(
            f"invalid MarketCurve scenario_id={curve.scenario_id!r} "
            f"kind={curve.kind.value} curve_id={curve.curve_id!r}: {reason}"
        )

    if curve.scenario_id == "":
        _fail("scenario_id must not be empty")

    if curve.kind is CurveKind.FX_RATE:
        if not (curve.value_decimal is not None and curve.value_float is None):
            _fail("FX_RATE must set value_decimal and leave value_float unset")
    elif curve.kind in _FLOAT_KINDS and not (
        curve.value_float is not None and curve.value_decimal is None
    ):
        _fail(f"{curve.kind.value} must set value_float and leave value_decimal unset")

    if curve.value_float is not None and not math.isfinite(curve.value_float):
        _fail("value_float must be finite")

    if curve.value_decimal is not None and not _fits_decimal_38_8(curve.value_decimal):
        _fail("value_decimal must be finite and representable at precision 38, scale 8")

    if curve.kind in _CURVE_ID_PATTERNS:
        if not _CURVE_ID_PATTERNS[curve.kind].match(curve.curve_id):
            _fail(f"curve_id does not match the pattern required for {curve.kind.value}")
    elif curve.kind in _NON_EMPTY_CURVE_ID_KINDS and curve.curve_id == "":
        _fail("curve_id must not be empty")

    for field_name, value in (("event_time", curve.event_time), ("ingest_time", curve.ingest_time)):
        offset = value.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            _fail(f"{field_name} must be UTC-aware (utcoffset() == 0)")


class MarketCurveProducer:
    """Produces `MarketCurve` messages to `market.curves`, keyed by
    `(scenario_id, kind, curve_id)`. The constructor provisions the topic
    (ADR-0027 Decision 10, `quant_io.topic_admin`) before constructing the
    underlying producer, so a misconfigured pre-existing topic fails at
    construction rather than on first produce."""

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        schema_registry_url: str,
        topic: str = MARKET_CURVES_TOPIC,
        max_queue_size: int = 10_000,
    ) -> None:
        ensure_compacted_topic(bootstrap_servers, topic)
        self._producer = AvroProducer(
            bootstrap_servers=bootstrap_servers,
            schema_registry_url=schema_registry_url,
            topic=topic,
            value_schema_str=market_curve_schema.SCHEMA_JSON,
            value_to_dict=MarketCurve.to_dict,
            key_schema_str=market_curve_key_schema.SCHEMA_JSON,
            key_to_dict=MarketCurveKey.to_dict,
            max_queue_size=max_queue_size,
        )

    def produce_curve(self, curve: MarketCurve) -> None:
        validate_market_curve(curve)
        key = MarketCurveKey(
            scenario_id=curve.scenario_id,
            kind=KeyCurveKind(curve.kind.value),
            curve_id=curve.curve_id,
        )
        self._producer.produce(key=key, value=curve)

    def flush(self, timeout: float = 30.0) -> int:
        return self._producer.flush(timeout)

    def publish_scenario_curves(self, curves: Sequence[MarketCurve], *, timeout: float = 30.0) -> None:
        """Publish one scenario's entire set of curves as one batch (ADR-0027
        Decision 4: every curve key a scenario needs is published exactly
        once, before that scenario's first tick). Every curve in the batch
        is validated -- and the batch checked for a single `scenario_id`
        and no duplicate `(kind, curve_id)` -- before anything is produced:
        a batch that fails validation produces nothing. A delivery failure
        after validation (e.g. a broker rejection) can still leave a
        partial batch, surfaced as `DeliveryError` -- republishing the same
        scenario afterwards is safe, because `market.curves` is compacted
        and every curve's value is identical on retry."""
        if not curves:
            raise InvalidMarketCurveError("publish_scenario_curves requires at least one curve")

        scenario_ids = {curve.scenario_id for curve in curves}
        if len(scenario_ids) > 1:
            raise InvalidMarketCurveError(
                f"publish_scenario_curves received more than one scenario_id: {sorted(scenario_ids)}"
            )

        seen: set[tuple[CurveKind, str]] = set()
        for curve in curves:
            dup_key = (curve.kind, curve.curve_id)
            if dup_key in seen:
                raise InvalidMarketCurveError(
                    f"duplicate (kind, curve_id) in batch: {curve.kind.value}:{curve.curve_id}"
                )
            seen.add(dup_key)
            validate_market_curve(curve)

        for curve in curves:
            self.produce_curve(curve)
        outstanding = self.flush(timeout)
        if outstanding != 0:
            raise DeliveryError(f"{outstanding} market.curves message(s) not delivered after flush")


def make_market_curve_consumer(
    *,
    bootstrap_servers: str,
    schema_registry_url: str,
    group_id: str,
    topic: str = MARKET_CURVES_TOPIC,
    enable_partition_eof: bool = False,
    on_assign: OnAssign | None = None,
) -> AvroConsumer:
    return AvroConsumer(
        bootstrap_servers=bootstrap_servers,
        schema_registry_url=schema_registry_url,
        topic=topic,
        group_id=group_id,
        value_schema_str=market_curve_schema.SCHEMA_JSON,
        value_from_dict=MarketCurve.from_dict,
        key_schema_str=market_curve_key_schema.SCHEMA_JSON,
        key_from_dict=MarketCurveKey.from_dict,
        enable_partition_eof=enable_partition_eof,
        on_assign=on_assign,
    )
