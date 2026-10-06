"""ADR-0029: the published `RiskSnapshot.var_95` is the 1-day 95% delta-normal
VaR -- per position `|cash_delta| * Z_95 * (vol / sqrt(365)) / 0.01`, summed by
magnitude -- built from the post-conversion cash delta, with `VOLATILITY`
required for every position type.

Expected numbers are worked out by hand and stated as literals, never derived
by calling `quant_core.risk` or any pricer code. Throughout:

    Z_95                 = 1.6448536269514722
    sqrt(365)            = 19.104973174542800179...
    Z_95 / sqrt(365) / 0.01 = 8.6095573750567963354...   (call it K)

so a position's VaR is `K * |cash_delta| * vol`. Every position here is an
equity (delta 1, contract_size 1), so `cash_delta = price * 0.01 * quantity`.
"""
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from loader import PortfolioFixture, TickFixture
from meridian_contracts.market_curves import CurveKind, MarketCurve
from meridian_contracts.portfolio_state import Position
from pricer.pricing import UnpriceableReason
from pricer.reference_data import InstrumentReference, ReferenceData
from pricer_test_helpers import (
    consume_all_snapshots,
    make_service,
    process_n_real_ticks,
    produce_ticks,
    seed_portfolios,
    unique_topics,
)

_SCENARIO = "var-test"
_T0 = datetime(2026, 1, 2, 9, 30, 0, tzinfo=UTC)
# The hand values are exact to far more digits than a float64 holds; this only
# absorbs float64 rounding, not any modelling difference.
_REL = 1e-12


def _at(seconds: int) -> datetime:
    return datetime(2026, 1, 2, 9, 30, seconds, tzinfo=UTC)


def _equity(instrument_id: str, underlying_id: str, currency: str) -> InstrumentReference:
    return InstrumentReference(
        instrument_id=instrument_id,
        instrument_type="EQUITY",
        underlying_id=underlying_id,
        currency=currency,
        contract_size=Decimal(1),
    )


def _position(portfolio_id: str, instrument_id: str, quantity: str) -> Position:
    return Position(
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        quantity=Decimal(quantity),
        average_cost=Decimal(1),
        as_of_event_time=_T0,
    )


def _portfolio(portfolio_id: str, positions: list[Position]) -> PortfolioFixture:
    return PortfolioFixture(
        portfolio_id=portfolio_id, base_currency="USD", positions=positions, event_time=_T0
    )


def _vol(underlying_id: str, value: float) -> MarketCurve:
    return MarketCurve(
        scenario_id=_SCENARIO,
        kind=CurveKind.VOLATILITY,
        curve_id=underlying_id,
        value_float=value,
        value_decimal=None,
        event_time=_T0,
        ingest_time=_T0,
    )


def _fx(pair: str, rate: str) -> MarketCurve:
    return MarketCurve(
        scenario_id=_SCENARIO,
        kind=CurveKind.FX_RATE,
        curve_id=pair,
        value_float=None,
        value_decimal=Decimal(rate),
        event_time=_T0,
        ingest_time=_T0,
    )


def _drive(kafka_stack, reference_data, portfolios, curves, ticks):
    topics = unique_topics()
    seed_portfolios(kafka_stack, topics, portfolios)
    service = make_service(kafka_stack, topics, reference_data, curves=curves)
    service.hydrate()
    service.start_tick_consumption()
    produce_ticks(kafka_stack, topics, _SCENARIO, ticks)
    per_tick = process_n_real_ticks(service, len(ticks))
    return service, topics, per_tick


def test_published_var_95_matches_a_hand_computed_value_in_the_base_currency(
    kafka_stack,
) -> None:
    """PF (base USD) holds 10 AAPL (USD, 150.00, vol 0.25) and 3 SAP (EUR,
    100.03, vol 0.40), EURUSD = 1.08123457.

      AAPL cash_delta = 150.00 * 0.01 * 10            = 15.00000000 USD
      SAP  cash_delta = 100.03 * 0.01 * 3             = 3.00090000 EUR
                      * 1.08123457 = 3.244676821113  -> 3.24467682 USD
      sum of |cash_delta| * vol = 15.00 * 0.25 + 3.24467682 * 0.40
                                = 3.75 + 1.297870728 = 5.047870728
      var_95 = K * 5.047870728 = 43.459932654585719558...

    Had the unconverted EUR cash delta been used instead, the figure would be
    K * (3.75 + 3.0009 * 0.40) = 42.620408447186162306..., so this also pins
    that VaR is built after FX conversion (ADR-0029 Decision 6)."""
    reference_data = ReferenceData(
        {"AAPL": _equity("AAPL", "AAPL", "USD"), "SAP": _equity("SAP", "SAP", "EUR")}
    )
    portfolio = _portfolio("PF", [_position("PF", "AAPL", "10"), _position("PF", "SAP", "3")])
    curves = [_vol("AAPL", 0.25), _vol("SAP", 0.40), _fx("EURUSD", "1.08123457")]
    ticks = [
        TickFixture("AAPL", Decimal("150.00"), "USD", _at(0)),
        TickFixture("SAP", Decimal("100.03"), "EUR", _at(1)),
    ]
    service, topics, per_tick = _drive(kafka_stack, reference_data, [portfolio], curves, ticks)
    try:
        assert per_tick[0] == [], "SAP has no price yet on the first tick"
        consumed = consume_all_snapshots(kafka_stack, topics, expected_count=1)
        assert len(consumed) == 1
        snapshot = consumed[0]
        assert snapshot.base_currency == "USD"
        assert snapshot.cash_delta == Decimal("18.24467682")
        assert snapshot.var_95 == pytest.approx(43.459932654585719558, rel=_REL)
    finally:
        service.close()


def test_equity_without_a_volatility_curve_is_missing_curve_and_no_snapshot(
    kafka_stack, caplog
) -> None:
    """An equity needs its underlying's VOLATILITY curve too (ADR-0029
    Decision 7): with none published, the portfolio is MISSING_CURVE naming
    exactly VOLATILITY:AAPL, and nothing is produced."""
    caplog.set_level(logging.WARNING, logger="pricer")
    service, _topics, per_tick = _drive(
        kafka_stack,
        ReferenceData({"AAPL": _equity("AAPL", "AAPL", "USD")}),
        [_portfolio("PF", [_position("PF", "AAPL", "10")])],
        [],
        [TickFixture("AAPL", Decimal("150.00"), "USD", _at(0))],
    )
    try:
        assert per_tick == [[]], "no snapshot"
        records = [
            r
            for r in caplog.records
            if getattr(r, "event", None) == "portfolio_unpriceable" and r.portfolio_id == "PF"
        ]
        assert [r.reason for r in records] == [UnpriceableReason.MISSING_CURVE]
        assert records[0].missing == ["VOLATILITY:AAPL"]
        assert service.unpriceable_counts[UnpriceableReason.MISSING_CURVE] == 1
    finally:
        service.close()


def test_opposite_positions_on_one_underlying_add_by_magnitude_not_net(kafka_stack) -> None:
    """Two distinct instruments on underlying AAPL (150.00, vol 0.25): long 10
    of AAPL and short 4 of AAPL-BLOCK.

      cash_delta: +15.00 and -6.00, portfolio cash_delta +9.00
      no netting:  K * (|15| + |-6|) * 0.25 = K * 5.25 = 45.200176219048180760...
      netted (must NOT be the answer): K * |9| * 0.25 = 19.371504093877791754...
    """
    reference_data = ReferenceData(
        {
            "AAPL": _equity("AAPL", "AAPL", "USD"),
            "AAPL-BLOCK": _equity("AAPL-BLOCK", "AAPL", "USD"),
        }
    )
    portfolio = _portfolio(
        "PF", [_position("PF", "AAPL", "10"), _position("PF", "AAPL-BLOCK", "-4")]
    )
    service, _topics, per_tick = _drive(
        kafka_stack,
        reference_data,
        [portfolio],
        [_vol("AAPL", 0.25)],
        [TickFixture("AAPL", Decimal("150.00"), "USD", _at(0))],
    )
    try:
        assert len(per_tick[0]) == 1
        snapshot = per_tick[0][0]
        assert snapshot.cash_delta == Decimal("9.00000000")
        assert snapshot.var_95 == pytest.approx(45.200176219048180760, rel=_REL)
        assert snapshot.var_95 != pytest.approx(19.371504093877791754, rel=_REL)
    finally:
        service.close()
