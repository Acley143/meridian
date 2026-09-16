"""Unit tests for `validate_market_curve` (ADR-0027 Decision 3). No Kafka --
pure function, tested as one."""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from meridian_contracts.market_curves import CurveKind, MarketCurve
from quant_io.market_curve_io import InvalidMarketCurveError, validate_market_curve

_EVENT_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_INGEST_TIME = datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)

_VALID_CURVE_ID = {
    CurveKind.RISK_FREE_RATE: "USD",
    CurveKind.VOLATILITY: "AAPL",
    CurveKind.DIVIDEND_YIELD: "AAPL",
    CurveKind.FX_RATE: "EURUSD",
}
_FLOAT_KINDS = (CurveKind.RISK_FREE_RATE, CurveKind.VOLATILITY, CurveKind.DIVIDEND_YIELD)


def _curve(
    *,
    kind: CurveKind,
    scenario_id: str = "scenario-1",
    curve_id: str | None = None,
    value_float: float | None = None,
    value_decimal: Decimal | None = None,
    event_time: datetime = _EVENT_TIME,
    ingest_time: datetime = _INGEST_TIME,
) -> MarketCurve:
    return MarketCurve(
        scenario_id=scenario_id,
        kind=kind,
        curve_id=curve_id if curve_id is not None else _VALID_CURVE_ID[kind],
        value_float=value_float,
        value_decimal=value_decimal,
        event_time=event_time,
        ingest_time=ingest_time,
    )


def _valid(kind: CurveKind) -> MarketCurve:
    if kind is CurveKind.FX_RATE:
        return _curve(kind=kind, value_decimal=Decimal("1.08000000"))
    return _curve(kind=kind, value_float=0.05)


@pytest.mark.parametrize("kind", list(CurveKind))
def test_valid_curve_accepted(kind: CurveKind) -> None:
    validate_market_curve(_valid(kind))  # must not raise


@pytest.mark.parametrize("kind", _FLOAT_KINDS)
def test_float_kind_rejects_decimal_only(kind: CurveKind) -> None:
    curve = _curve(kind=kind, value_decimal=Decimal("1.00000000"))
    with pytest.raises(InvalidMarketCurveError, match=kind.value):
        validate_market_curve(curve)


@pytest.mark.parametrize("kind", _FLOAT_KINDS)
def test_float_kind_rejects_both_set(kind: CurveKind) -> None:
    curve = _curve(kind=kind, value_float=0.05, value_decimal=Decimal("1.00000000"))
    with pytest.raises(InvalidMarketCurveError, match=kind.value):
        validate_market_curve(curve)


@pytest.mark.parametrize("kind", _FLOAT_KINDS)
def test_float_kind_rejects_neither_set(kind: CurveKind) -> None:
    curve = _curve(kind=kind)
    with pytest.raises(InvalidMarketCurveError, match=kind.value):
        validate_market_curve(curve)


def test_fx_rate_rejects_float_only() -> None:
    curve = _curve(kind=CurveKind.FX_RATE, value_float=1.08)
    with pytest.raises(InvalidMarketCurveError, match=CurveKind.FX_RATE.value):
        validate_market_curve(curve)


def test_fx_rate_rejects_both_set() -> None:
    curve = _curve(kind=CurveKind.FX_RATE, value_float=1.08, value_decimal=Decimal("1.08000000"))
    with pytest.raises(InvalidMarketCurveError, match=CurveKind.FX_RATE.value):
        validate_market_curve(curve)


def test_fx_rate_rejects_neither_set() -> None:
    curve = _curve(kind=CurveKind.FX_RATE)
    with pytest.raises(InvalidMarketCurveError, match=CurveKind.FX_RATE.value):
        validate_market_curve(curve)


def test_empty_scenario_id_rejected() -> None:
    curve = _curve(kind=CurveKind.RISK_FREE_RATE, scenario_id="", value_float=0.05)
    with pytest.raises(InvalidMarketCurveError, match=CurveKind.RISK_FREE_RATE.value):
        validate_market_curve(curve)


@pytest.mark.parametrize(
    ("kind", "bad_curve_id"),
    [
        (CurveKind.RISK_FREE_RATE, "US"),
        (CurveKind.RISK_FREE_RATE, "usd"),
        (CurveKind.FX_RATE, "EURUS"),
        (CurveKind.FX_RATE, "eurusd"),
        (CurveKind.VOLATILITY, ""),
        (CurveKind.DIVIDEND_YIELD, ""),
    ],
)
def test_bad_curve_id_rejected(kind: CurveKind, bad_curve_id: str) -> None:
    curve = _valid(kind)
    curve = _curve(
        kind=kind,
        curve_id=bad_curve_id,
        value_float=curve.value_float,
        value_decimal=curve.value_decimal,
    )
    with pytest.raises(InvalidMarketCurveError, match=kind.value):
        validate_market_curve(curve)


def test_nan_value_float_rejected() -> None:
    curve = _curve(kind=CurveKind.RISK_FREE_RATE, value_float=math.nan)
    with pytest.raises(InvalidMarketCurveError, match=CurveKind.RISK_FREE_RATE.value):
        validate_market_curve(curve)


def test_positive_infinity_value_float_rejected() -> None:
    curve = _curve(kind=CurveKind.VOLATILITY, value_float=math.inf)
    with pytest.raises(InvalidMarketCurveError, match=CurveKind.VOLATILITY.value):
        validate_market_curve(curve)


def test_naive_event_time_rejected() -> None:
    curve = _curve(
        kind=CurveKind.RISK_FREE_RATE,
        value_float=0.05,
        event_time=datetime(2026, 1, 1),  # noqa: DTZ001 -- deliberately naive, this is what's under test
    )
    with pytest.raises(InvalidMarketCurveError, match=CurveKind.RISK_FREE_RATE.value):
        validate_market_curve(curve)


def test_non_utc_ingest_time_rejected() -> None:
    curve = _curve(
        kind=CurveKind.RISK_FREE_RATE,
        value_float=0.05,
        ingest_time=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1))),
    )
    with pytest.raises(InvalidMarketCurveError, match=CurveKind.RISK_FREE_RATE.value):
        validate_market_curve(curve)
