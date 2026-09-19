"""Orchestrates hydration, tick-driven repricing, and snapshot production.

Startup sequence (Task 1, extended by ADR-0027): `hydrate()` blocks,
consuming `portfolio.state` to the end of every assigned partition, then
`market.curves` to the end of every assigned partition, before
`start_tick_consumption()` ever subscribes to `market.ticks`. Nothing in
this class touches the tick topic until hydration is complete -- a tick
"arriving" before then is not buffered or specially handled, it simply
isn't fetched yet, because the consumer group for it doesn't exist yet.
This is the "paused" strategy Task 1 allows, chosen over in-memory
buffering because it can't leak: there is no buffer to overflow or lose on
a crash between hydration and the first tick. `market.curves` hydration
uses a fresh consumer group every run, exactly like `portfolio.state`, so
its compacted history is replayed from the start rather than resumed.

Per-tick flow (Tasks 3, 5, 6, 7): update the last-known price/event_time for
the ticked instrument, find every portfolio holding it (the reverse index,
keyed by underlying_id -- see `pricer.portfolio_view`), price and aggregate
each one (one snapshot per affected portfolio, Task 6's Q1 fan-out policy),
flush all of them to the broker, and only then commit the tick's offset --
never before every snapshot it produced is durably delivered. Pending
`market.curves` updates are drained the same way pending `portfolio.state`
updates are, before polling for the next tick.

Unpriceable-portfolio reporting (ADR-0018, extended by ADR-0027): a
portfolio that cannot be priced -- missing reference data, no observed
price yet for an underlying, missing a required `market.curves` value, or
an instrument type with no pricer -- is never silently skipped. Every skip
goes through `_report_unpriceable`, which logs a structured WARNING
(`event=portfolio_unpriceable`) and increments `unpriceable_counts`.
`_price_portfolio` evaluates the whole portfolio before reporting: at most
one event is reported per portfolio per tick, in fixed precedence --
`UNKNOWN_BASE_CURRENCY` (ADR-0028 Decision 2: a portfolio-wide fact, so it
comes before anything per-position; an empty `base_currency` on
`portfolio.state` is never treated as any particular currency), then
`NO_REFERENCE_DATA`, then `NO_PRICE`, then `MISSING_CURVE`, then
`INSTRUMENT_NOT_PRICEABLE` (ADR-0027 Decision 9) -- each naming every
affected id, not just the first one found. The published `RiskSnapshot`
carries the portfolio's `base_currency`.

Currency conversion (ADR-0028 Decisions 3 to 5, 7): each position's cash
contribution is computed in its instrument's own currency and, when that
differs from the portfolio's `base_currency`, converted per position --
before contributions are summed -- with the direct `FX_RATE` curve for the
pair `<position currency><base currency>` (never inverted), decimal
throughout and rounded once per field at scale 8. A same-currency position
is untouched: no curve lookup, no multiplication, no re-rounding. Every
position type needs its FX curve, not only options; a missing one is
`MISSING_CURVE` listing `FX_RATE:<pair>`. A non-positive `FX_RATE` never
enters the view: the shared validator rejects it at the producer and again
in `CurveView.apply` (`market_curve_rejected`), so the pair is simply
missing; the per-position `ValueError` catch in `_price_portfolio` is defence
in depth (it fails that position as `INSTRUMENT_NOT_PRICEABLE` naming the
pair and value) rather than a path reachable through Kafka. A tick
whose currency disagrees with its instrument's reference currency is
rejected before it is cached (`tick_currency_mismatch`). `var_95` is still
0.0; its currency treatment is decided when VaR is built.
"""
from __future__ import annotations

import time
import uuid
from collections import Counter
from datetime import datetime
from decimal import Decimal
from logging import Logger

from meridian_contracts.market_curves import CurveKind
from meridian_contracts.risk_snapshot import RiskSnapshot
from meridian_contracts.tick import Tick
from quant_core import PRICER_VERSION
from quant_io.clock import now_utc
from quant_io.consumer import PartitionEOF
from quant_io.market_curve_io import MARKET_CURVES_TOPIC, make_market_curve_consumer
from quant_io.portfolio_state_io import (
    PORTFOLIO_STATE_TOPIC,
    make_portfolio_state_consumer,
)
from quant_io.risk_snapshot_io import RISK_SNAPSHOTS_TOPIC, RiskSnapshotProducer
from quant_io.tick_producer import MARKET_TICKS_TOPIC, make_tick_consumer

from pricer.curve_view import CurveView
from pricer.logging_config import get_logger
from pricer.portfolio_view import PortfolioView
from pricer.pricing import (
    OptionMarketInputs,
    UnpricableInstrumentError,
    UnpriceableReason,
    aggregate_portfolio,
    aggregate_position,
    convert_contribution,
    oldest_input_event_time,
    price_instrument,
)
from pricer.reference_data import ReferenceData

_DEFAULT_HYDRATION_TIMEOUT_SECONDS = 30.0


class PricerService:
    def __init__(
        self,
        *,
        bootstrap_servers: str,
        schema_registry_url: str,
        reference_data: ReferenceData,
        tick_group_id: str,
        portfolio_state_topic: str = PORTFOLIO_STATE_TOPIC,
        tick_topic: str = MARKET_TICKS_TOPIC,
        risk_snapshot_topic: str = RISK_SNAPSHOTS_TOPIC,
        market_curve_topic: str = MARKET_CURVES_TOPIC,
        logger: Logger | None = None,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._schema_registry_url = schema_registry_url
        self.reference_data = reference_data
        self._tick_group_id = tick_group_id
        self._portfolio_state_topic = portfolio_state_topic
        self._tick_topic = tick_topic
        self._market_curve_topic = market_curve_topic
        self._log = logger or get_logger()

        self.view = PortfolioView(reference_data)
        self.curves = CurveView()
        self._last_price: dict[str, Decimal] = {}
        self._last_event_time: dict[str, datetime] = {}
        self._unpriceable_counts: Counter[UnpriceableReason] = Counter()
        self._rejected_curve_count = 0
        self._tick_currency_mismatch_count = 0
        self.ready = False

        self._portfolio_consumer = None
        self._curve_consumer = None
        self._tick_consumer = None
        self._risk_producer = RiskSnapshotProducer(
            bootstrap_servers=bootstrap_servers,
            schema_registry_url=schema_registry_url,
            topic=risk_snapshot_topic,
        )

    @property
    def unpriceable_counts(self) -> Counter[UnpriceableReason]:
        """A copy of the running per-reason unpriceable-event counts
        (ADR-0018). Counts *events* (one per skip), not distinct
        portfolios -- a portfolio skipped on every tick increments its
        reason's count once per tick, not once total."""
        return Counter(self._unpriceable_counts)

    @property
    def rejected_curve_count(self) -> int:
        """A count of `market.curves` messages rejected by `CurveView.apply`
        (ADR-0027 Decision 3) -- invalid records, or a key/value mismatch."""
        return self._rejected_curve_count

    @property
    def tick_currency_mismatch_count(self) -> int:
        """A count of ticks rejected because their currency disagrees with
        their instrument's reference-data currency (ADR-0028 Decision 7)."""
        return self._tick_currency_mismatch_count

    def _report_unpriceable(
        self,
        *,
        portfolio_id: str,
        reason: UnpriceableReason,
        trigger: str,
        missing: list[str],
        detail: str = "",
    ) -> None:
        missing_sorted = sorted(set(missing))
        self._unpriceable_counts[reason] += 1
        message = (
            "portfolio_unpriceable portfolio_id=%s reason=%s trigger=%s missing=%s"
        )
        args = [portfolio_id, reason.value, trigger, ",".join(missing_sorted)]
        if detail:
            message += " detail=%s"
            args.append(detail)
        self._log.warning(
            message,
            *args,
            extra={
                "event": "portfolio_unpriceable",
                "portfolio_id": portfolio_id,
                "reason": reason,
                "trigger": trigger,
                "missing": missing_sorted,
                "detail": detail,
            },
        )

    # -- Task 1: hydration gate ------------------------------------------

    def _hydrate_to_end(
        self,
        *,
        topic_name: str,
        timeout: float,
        make_consumer,
        apply_message,
    ) -> None:
        """Shared hydration loop: consume `make_consumer`'s consumer to the
        end of every partition it gets assigned, applying each message
        through `apply_message`, against one deadline. `make_consumer` is
        responsible for stashing the consumer it builds wherever the caller
        needs it (e.g. `self._portfolio_consumer`) *before* returning, since
        `apply_message` callbacks may need it (to `commit()`) while this
        loop is still running."""
        state: dict[str, object] = {"assigned": False, "pending": set()}

        def on_assign(_consumer: object, partitions: list) -> None:
            state["pending"] = {(p.topic, p.partition) for p in partitions}
            state["assigned"] = True
            self._log.info("hydration: assigned %d partition(s) of %s", len(partitions), topic_name)

        consumer = make_consumer(on_assign)

        deadline = time.monotonic() + timeout
        while not (state["assigned"] and not state["pending"]):
            if time.monotonic() > deadline:
                if not state["assigned"]:
                    raise TimeoutError(
                        f"{topic_name} hydration did not complete within {timeout}s: "
                        "no partitions were assigned (topic may not exist)"
                    )
                raise TimeoutError(
                    f"{topic_name} hydration did not complete within {timeout}s "
                    f"(still pending: {state['pending']})"
                )
            msg = consumer.poll(1.0)
            if isinstance(msg, PartitionEOF):
                state["pending"].discard((msg.topic, msg.partition))
            elif msg is not None:
                apply_message(msg)

    def hydrate(self, timeout: float = _DEFAULT_HYDRATION_TIMEOUT_SECONDS) -> None:
        """Block until `portfolio.state`, then `market.curves`, have each
        been read to the end of every assigned partition (ADR-0018,
        ADR-0027 Decision 9). Must be called before
        `start_tick_consumption`."""
        self._log.info("hydration: starting (readiness=HYDRATING)")

        # A fresh group id every hydration run, for both topics: the local
        # view is rebuilt from scratch each start (ADR-0003 -- "a new
        # pricer instance can rebuild its view by replaying the topic from
        # the start"), never resumed from a previously committed offset.
        def make_portfolio_consumer(on_assign):
            self._portfolio_consumer = make_portfolio_state_consumer(
                bootstrap_servers=self._bootstrap_servers,
                schema_registry_url=self._schema_registry_url,
                group_id=f"pricer-portfolio-view-{uuid.uuid4()}",
                topic=self._portfolio_state_topic,
                enable_partition_eof=True,
                on_assign=on_assign,
            )
            return self._portfolio_consumer

        self._hydrate_to_end(
            topic_name=self._portfolio_state_topic,
            timeout=timeout,
            make_consumer=make_portfolio_consumer,
            apply_message=self._apply_portfolio_message,
        )

        def make_curve_consumer(on_assign):
            self._curve_consumer = make_market_curve_consumer(
                bootstrap_servers=self._bootstrap_servers,
                schema_registry_url=self._schema_registry_url,
                group_id=f"pricer-curve-view-{uuid.uuid4()}",
                topic=self._market_curve_topic,
                enable_partition_eof=True,
                on_assign=on_assign,
            )
            return self._curve_consumer

        self._hydrate_to_end(
            topic_name=self._market_curve_topic,
            timeout=timeout,
            make_consumer=make_curve_consumer,
            apply_message=self._apply_curve_message,
        )

        self.ready = True
        self._log.info(
            "hydration: complete (readiness=READY), %d portfolio(s) in view, %d curve(s) in view",
            len(self.view),
            len(self.curves),
        )

    def _apply_portfolio_message(self, msg: object) -> None:
        key = msg.key()
        value = msg.value()
        if value is None:
            removed = self.view.remove(key.portfolio_id)
            self._log.info("portfolio.state tombstone: portfolio_id=%s removed=%s", key.portfolio_id, removed)
        else:
            self.view.apply(
                key.portfolio_id, value.positions, value.event_time, value.base_currency
            )
            self._log.info(
                "portfolio.state applied: portfolio_id=%s positions=%d",
                key.portfolio_id,
                len(value.positions),
            )
            unknown = sorted(
                {
                    position.instrument_id
                    for position in value.positions
                    if position.instrument_id not in self.reference_data
                }
            )
            if unknown:
                self._report_unpriceable(
                    portfolio_id=key.portfolio_id,
                    reason=UnpriceableReason.NO_REFERENCE_DATA,
                    trigger="portfolio_update",
                    missing=unknown,
                )
        self._portfolio_consumer.commit(msg)

    def _drain_portfolio_updates(self) -> None:
        while True:
            msg = self._portfolio_consumer.poll(0.0)
            if msg is None or isinstance(msg, PartitionEOF):
                return
            self._apply_portfolio_message(msg)

    def _apply_curve_message(self, msg: object) -> None:
        key = msg.key()
        value = msg.value()
        error = self.curves.apply(key, value)
        if error is not None:
            self._rejected_curve_count += 1
            self._log.warning(
                "market_curve_rejected scenario_id=%s kind=%s curve_id=%s error=%s",
                key.scenario_id,
                key.kind.value,
                key.curve_id,
                error,
                extra={
                    "event": "market_curve_rejected",
                    "scenario_id": key.scenario_id,
                    "kind": key.kind.value,
                    "curve_id": key.curve_id,
                    "error": error,
                },
            )
        self._curve_consumer.commit(msg)

    def _drain_curve_updates(self) -> None:
        while True:
            msg = self._curve_consumer.poll(0.0)
            if msg is None or isinstance(msg, PartitionEOF):
                return
            self._apply_curve_message(msg)

    # -- Tasks 3/5/6/7: tick-driven repricing ----------------------------

    def start_tick_consumption(self) -> None:
        if not self.ready:
            raise RuntimeError("start_tick_consumption called before hydrate() completed")
        self._tick_consumer = make_tick_consumer(
            bootstrap_servers=self._bootstrap_servers,
            schema_registry_url=self._schema_registry_url,
            group_id=self._tick_group_id,
            topic=self._tick_topic,
        )
        self._log.info("tick consumption started: group_id=%s", self._tick_group_id)

    def process_one_tick(self, timeout: float = 5.0) -> list[RiskSnapshot] | None:
        """Poll for one tick and, if one arrives within `timeout`, reprice
        every affected portfolio and produce a snapshot for each. Returns
        `None` on a poll timeout (no tick arrived), else the list of
        snapshots produced for that tick (possibly empty, if every
        affected portfolio was unpricable)."""
        if self._tick_consumer is None:
            raise RuntimeError("start_tick_consumption() was not called")

        self._drain_portfolio_updates()
        self._drain_curve_updates()

        msg = self._tick_consumer.poll(timeout)
        if msg is None or isinstance(msg, PartitionEOF):
            return None

        tick: Tick = msg.value()

        # ADR-0028 Decision 7: reference data is authoritative for an
        # instrument's currency, so a tick quoted in a different one is the
        # suspect value. Its price and event time are never cached, so
        # nothing is priced from it; the offset is still committed, or the
        # same tick would be redelivered forever. A tick for an instrument
        # reference data does not know is cached as before -- there is no
        # basis to judge it.
        if tick.instrument_id in self.reference_data:
            reference_currency = self.reference_data.get(tick.instrument_id).currency
            if tick.currency != reference_currency:
                self._reject_tick_currency_mismatch(tick, reference_currency)
                self._tick_consumer.commit(msg)
                return []

        self._last_price[tick.instrument_id] = tick.price
        self._last_event_time[tick.instrument_id] = tick.event_time

        affected = self.view.portfolios_for_underlying(tick.instrument_id)
        produced: list[RiskSnapshot] = []
        for portfolio_id in sorted(affected):
            snapshot = self._price_portfolio(portfolio_id, tick)
            if snapshot is not None:
                self._risk_producer.produce_snapshot(snapshot)
                produced.append(snapshot)

        # Flush (durably deliver) every snapshot this tick produced before
        # committing the tick's own offset (Task 7) -- never the reverse.
        self._risk_producer.flush()
        self._tick_consumer.commit(msg)

        self._log.info(
            "tick processed: instrument_id=%s affected=%d snapshots=%d",
            tick.instrument_id,
            len(affected),
            len(produced),
        )
        return produced

    def _reject_tick_currency_mismatch(self, tick: Tick, reference_currency: str) -> None:
        self._tick_currency_mismatch_count += 1
        self._log.warning(
            "tick_currency_mismatch instrument_id=%s tick_currency=%s reference_currency=%s",
            tick.instrument_id,
            tick.currency,
            reference_currency,
            extra={
                "event": "tick_currency_mismatch",
                "instrument_id": tick.instrument_id,
                "tick_currency": tick.currency,
                "reference_currency": reference_currency,
            },
        )

    def _price_portfolio(self, portfolio_id: str, triggering_tick: Tick) -> RiskSnapshot | None:
        positions = self.view.positions(portfolio_id)

        # (0) The portfolio's reporting currency must be known (ADR-0028
        # Decision 2). An empty value is the wire default for a message
        # written before the field existed, never "USD"; it is a fact about
        # the whole portfolio, so it is checked before anything per-position.
        base_currency = self.view.base_currency(portfolio_id)
        if not base_currency:
            self._report_unpriceable(
                portfolio_id=portfolio_id,
                reason=UnpriceableReason.UNKNOWN_BASE_CURRENCY,
                trigger="tick",
                missing=[portfolio_id],
            )
            return None

        # (a) Every held instrument must have reference data before anything
        # else is checked -- collected across all positions, not just the
        # first missing one.
        no_reference_data = sorted(
            {p.instrument_id for p in positions if p.instrument_id not in self.reference_data}
        )
        if no_reference_data:
            self._report_unpriceable(
                portfolio_id=portfolio_id,
                reason=UnpriceableReason.NO_REFERENCE_DATA,
                trigger="tick",
                missing=no_reference_data,
            )
            return None

        # (b) Every underlying must have an observed price -- again, every
        # missing one, not just the first.
        no_price = sorted(
            {
                self.reference_data.get(p.instrument_id).underlying_id
                for p in positions
                if self.reference_data.get(p.instrument_id).underlying_id not in self._last_price
            }
        )
        if no_price:
            self._report_unpriceable(
                portfolio_id=portfolio_id,
                reason=UnpriceableReason.NO_PRICE,
                trigger="tick",
                missing=no_price,
            )
            return None

        # (c) Every required market.curves value must be present under the
        # triggering tick's scenario_id (ADR-0027 Decisions 6, 8, 9) -- every
        # missing key, not just the first. A VANILLA_EUROPEAN_OPTION needs its
        # three option curves; and EVERY position, of any type, whose currency
        # differs from the portfolio's base currency needs the direct FX_RATE
        # pair (position currency followed by base currency, e.g. EURUSD --
        # ADR-0028 Decisions 3 and 4). A same-currency position needs no FX
        # curve. A rate is never inverted or derived (ADR-0027 Decision 2).
        required_curves: dict[tuple[CurveKind, str], None] = {}
        for position in positions:
            reference = self.reference_data.get(position.instrument_id)
            if reference.currency != base_currency:
                required_curves[(CurveKind.FX_RATE, reference.currency + base_currency)] = None
            if reference.instrument_type != "VANILLA_EUROPEAN_OPTION":
                continue
            required_curves[(CurveKind.RISK_FREE_RATE, reference.currency)] = None
            required_curves[(CurveKind.VOLATILITY, reference.underlying_id)] = None
            required_curves[(CurveKind.DIVIDEND_YIELD, reference.underlying_id)] = None

        missing_curves = sorted(
            f"{kind.value}:{curve_id}"
            for kind, curve_id in required_curves
            if self.curves.get(triggering_tick.scenario_id, kind, curve_id) is None
        )
        if missing_curves:
            self._report_unpriceable(
                portfolio_id=portfolio_id,
                reason=UnpriceableReason.MISSING_CURVE,
                trigger="tick",
                missing=missing_curves,
            )
            return None

        # (d) Price every position, collecting every pricing failure (not
        # just the first) before reporting.
        contributions = []
        underlyings_used: set[str] = set()
        failures: list[tuple[str, str]] = []

        for position in positions:
            reference = self.reference_data.get(position.instrument_id)
            underlying_id = reference.underlying_id
            spot = self._last_price[underlying_id]

            market = None
            if reference.instrument_type == "VANILLA_EUROPEAN_OPTION":
                rate_curve = self.curves.get(
                    triggering_tick.scenario_id, CurveKind.RISK_FREE_RATE, reference.currency
                )
                vol_curve = self.curves.get(
                    triggering_tick.scenario_id, CurveKind.VOLATILITY, underlying_id
                )
                div_curve = self.curves.get(
                    triggering_tick.scenario_id, CurveKind.DIVIDEND_YIELD, underlying_id
                )
                market = OptionMarketInputs(
                    volatility=vol_curve.value_float,
                    risk_free_rate=rate_curve.value_float,
                    dividend_yield=div_curve.value_float,
                )

            try:
                pricing_result = price_instrument(reference, spot, triggering_tick.event_time, market)
            except UnpricableInstrumentError as exc:
                failures.append((position.instrument_id, str(exc)))
                continue

            contribution = aggregate_position(
                pricing_result, position.quantity, reference.contract_size, spot
            )

            # ADR-0028 Decisions 3 and 5: convert this position into the
            # reporting currency now, before contributions are summed. A
            # same-currency position is left exactly as computed: no lookup,
            # no multiplication, no re-rounding.
            if reference.currency != base_currency:
                pair = reference.currency + base_currency
                fx_curve = self.curves.get(triggering_tick.scenario_id, CurveKind.FX_RATE, pair)
                try:
                    contribution = convert_contribution(contribution, fx_curve.value_decimal)
                except ValueError:
                    # A rate that is not finite and strictly positive must
                    # not escape and kill the tick loop: it is this
                    # position's failure, reported like any other. With
                    # validation at both the producer and the consumer
                    # (`validate_market_curve`, ADR-0027 Decision 3), a
                    # non-positive FX_RATE can no longer reach this point
                    # through Kafka; the catch remains for any future caller
                    # that puts a curve into the view another way, and is
                    # covered by the `convert_contribution` unit test in
                    # `tests/test_aggregation.py`.
                    detail = (
                        f"the FX rate for {pair} is invalid: {fx_curve.value_decimal} "
                        "(must be finite and strictly positive)"
                    )
                    failures.append((position.instrument_id, detail))
                    continue

            contributions.append(contribution)
            underlyings_used.add(underlying_id)

        if failures:
            failures.sort(key=lambda f: f[0])
            self._report_unpriceable(
                portfolio_id=portfolio_id,
                reason=UnpriceableReason.INSTRUMENT_NOT_PRICEABLE,
                trigger="tick",
                missing=[instrument_id for instrument_id, _ in failures],
                detail="; ".join(message for _, message in failures),
            )
            return None

        aggregate = aggregate_portfolio(contributions)
        oldest = oldest_input_event_time(underlyings_used, self._last_event_time)

        return RiskSnapshot(
            portfolio_id=portfolio_id,
            base_currency=base_currency,
            as_of=triggering_tick.event_time,
            pricer_version=PRICER_VERSION,
            price=aggregate.price,
            cash_delta=aggregate.cash_delta,
            cash_gamma=aggregate.cash_gamma,
            cash_vega=aggregate.cash_vega,
            cash_theta=aggregate.cash_theta,
            cash_rho=aggregate.cash_rho,
            var_95=0.0,
            scenario_id=triggering_tick.scenario_id,
            oldest_input_event_time=oldest,
            ingest_time=now_utc(),
        )

    def run(self) -> None:
        self.hydrate()
        self.start_tick_consumption()
        while True:
            self.process_one_tick()

    def close(self) -> None:
        if self._portfolio_consumer is not None:
            self._portfolio_consumer.close()
        if self._curve_consumer is not None:
            self._curve_consumer.close()
        if self._tick_consumer is not None:
            self._tick_consumer.close()
