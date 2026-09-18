"""In-memory materialized view over `market.curves` (ADR-0027).

An invalid record supersedes and removes the previous value rather than
leaving it in place: the producer has already superseded it (a new,
invalid version was published to the same key), and pricing from a stale
value the producer no longer stands behind would be a wrong number, not a
conservative fallback (ADR-0018, ADR-0027 Decision 3).
"""
from __future__ import annotations

from meridian_contracts.market_curves import CurveKind, MarketCurve
from meridian_contracts.market_curves_key import MarketCurveKey
from quant_io.market_curve_io import InvalidMarketCurveError, validate_market_curve

_CurveMapKey = tuple[str, CurveKind, str]


class CurveView:
    """`(scenario_id, kind, curve_id) -> MarketCurve`, rebuilt by hydration
    and kept current by live updates -- the same shape as
    `pricer.portfolio_view.PortfolioView` for `portfolio.state`."""

    def __init__(self) -> None:
        self._curves: dict[_CurveMapKey, MarketCurve] = {}

    def apply(self, key: MarketCurveKey, value: MarketCurve | None) -> str | None:
        """Apply one `market.curves` message. Returns `None` on success, or
        an error string describing why the record was rejected -- callers
        are responsible for logging/counting the rejection."""
        map_key: _CurveMapKey = (key.scenario_id, CurveKind(key.kind.value), key.curve_id)

        if value is None:
            self._curves.pop(map_key, None)
            return None

        if (
            key.scenario_id != value.scenario_id
            or key.kind.value != value.kind.value
            or key.curve_id != value.curve_id
        ):
            self._curves.pop(map_key, None)
            return (
                f"key/value mismatch: key=(scenario_id={key.scenario_id!r}, "
                f"kind={key.kind.value}, curve_id={key.curve_id!r}) "
                f"value=(scenario_id={value.scenario_id!r}, kind={value.kind.value}, "
                f"curve_id={value.curve_id!r})"
            )

        try:
            validate_market_curve(value)
        except InvalidMarketCurveError as exc:
            self._curves.pop(map_key, None)
            return str(exc)

        self._curves[map_key] = value
        return None

    def get(self, scenario_id: str, kind: CurveKind, curve_id: str) -> MarketCurve | None:
        return self._curves.get((scenario_id, kind, curve_id))

    def __len__(self) -> int:
        return len(self._curves)
