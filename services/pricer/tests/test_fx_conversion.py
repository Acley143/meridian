"""ADR-0028 Decisions 3, 4, 5 and 7: position contributions are converted into
the portfolio's reporting currency per position, before they are summed, with
the direct FX_RATE curve for `<position currency><base currency>`; every
position type needs its FX curve, a same-currency position needs none, a
published rate that cannot be applied fails that position rather than the
pricer, and a tick quoted in a currency other than its instrument's reference
currency is rejected before it is cached.

Mixed-currency reference data is built in the test, in the same style as
`test_unpriceable_reporting.py`'s American-option case; the shared fixtures
stay single-currency USD. Expected numbers are worked out by hand and stated
as literals -- never derived by calling the production conversion helpers.
"""
import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal

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
from quant_core.types import OptionRight

_SCENARIO = "fx-test"
_T0 = datetime(2026, 1, 2, 9, 30, 0, tzinfo=UTC)
_QUANTUM = Decimal("1E-8")
_ZERO = Decimal(0)


def _at(seconds: int) -> datetime:
    return datetime(2026, 1, 2, 9, 30, seconds, tzinfo=UTC)


def _equity(instrument_id: str, currency: str) -> InstrumentReference:
    return InstrumentReference(
        instrument_id=instrument_id,
        instrument_type="EQUITY",
        underlying_id=instrument_id,
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


def _portfolio(portfolio_id: str, base_currency: str, positions: list[Position]) -> PortfolioFixture:
    return PortfolioFixture(
        portfolio_id=portfolio_id,
        base_currency=base_currency,
        positions=positions,
        event_time=_T0,
    )


def _fx_curve(pair: str, rate: str) -> MarketCurve:
    return MarketCurve(
        scenario_id=_SCENARIO,
        kind=CurveKind.FX_RATE,
        curve_id=pair,
        value_float=None,
        value_decimal=Decimal(rate),
        event_time=_T0,
        ingest_time=_T0,
    )


def _float_curve(kind: CurveKind, curve_id: str, value: float) -> MarketCurve:
    return MarketCurve(
        scenario_id=_SCENARIO,
        kind=kind,
        curve_id=curve_id,
        value_float=value,
        value_decimal=None,
        event_time=_T0,
        ingest_time=_T0,
    )


def _option_curves(underlying_id: str, currency: str) -> list[MarketCurve]:
    return [
        _float_curve(CurveKind.RISK_FREE_RATE, currency, 0.04),
        _float_curve(CurveKind.VOLATILITY, underlying_id, 0.25),
        _float_curve(CurveKind.DIVIDEND_YIELD, underlying_id, 0.0),
    ]


def _unpriceable_records(caplog):
    return [r for r in caplog.records if getattr(r, "event", None) == "portfolio_unpriceable"]


def _drive(kafka_stack, reference_data, portfolios, curves, ticks):
    """Seed, hydrate, produce `ticks`, process them all. Returns
    `(service, topics, per_tick)`; the caller closes the service."""
    topics = unique_topics()
    seed_portfolios(kafka_stack, topics, portfolios)
    service = make_service(kafka_stack, topics, reference_data, curves=curves)
    service.hydrate()
    service.start_tick_consumption()
    produce_ticks(kafka_stack, topics, _SCENARIO, ticks)
    per_tick = process_n_real_ticks(service, len(ticks))
    return service, topics, per_tick


def _mixed_equity_setup():
    """PF holds 10 AAPL (USD, quoted 150.00) and 3 SAP (EUR, quoted 100.03),
    base currency USD."""
    reference_data = ReferenceData({"AAPL": _equity("AAPL", "USD"), "SAP": _equity("SAP", "EUR")})
    portfolio = _portfolio(
        "PF", "USD", [_position("PF", "AAPL", "10"), _position("PF", "SAP", "3")]
    )
    ticks = [
        TickFixture("AAPL", Decimal("150.00"), "USD", _at(0)),
        TickFixture("SAP", Decimal("100.03"), "EUR", _at(1)),
    ]
    return reference_data, portfolio, ticks


def test_eur_and_usd_equities_are_converted_per_position_before_summing(
    kafka_stack,
) -> None:
    """(a) Worked by hand.

    USD position, 10 AAPL at 150.00 (contract_size 1, delta 1, other Greeks 0):
      price = 10 * 150.00 = 1500.00000000
      cash_delta = 1.0 * 150.0 * 0.01 * 10 = 15.00000000
    EUR position, 3 SAP at 100.03, in EUR:
      price = 3 * 100.03 = 300.09000000
      cash_delta = 1.0 * 100.03 * 0.01 * 3 = 3.00090000
    Converted at EURUSD = 1.08123457, each field rounded once to scale 8:
      price      300.09      * 1.08123457 = 324.4676821113  -> 324.46768211
      cash_delta 3.0009      * 1.08123457 = 3.244676821113  -> 3.24467682
    Totals (the USD position is added untouched):
      price      1500.00000000 + 324.46768211 = 1824.46768211
      cash_delta 15.00000000   + 3.24467682   = 18.24467682
    The other four fields are zero for equities and stay zero."""
    reference_data, portfolio, ticks = _mixed_equity_setup()
    service, topics, per_tick = _drive(
        kafka_stack, reference_data, [portfolio], [_fx_curve("EURUSD", "1.08123457")], ticks
    )
    try:
        assert per_tick[0] == [], "SAP has no price yet on the first tick"
        assert len(per_tick[1]) == 1

        consumed = consume_all_snapshots(kafka_stack, topics, expected_count=1)
        assert len(consumed) == 1
        snapshot = consumed[0]

        assert snapshot.portfolio_id == "PF"
        assert snapshot.base_currency == "USD"
        assert snapshot.price == Decimal("1824.46768211")
        assert snapshot.cash_delta == Decimal("18.24467682")
        assert snapshot.cash_gamma == _ZERO
        assert snapshot.cash_vega == _ZERO
        assert snapshot.cash_theta == _ZERO
        assert snapshot.cash_rho == _ZERO
    finally:
        service.close()


def test_missing_fx_curve_is_reported_missing_curve_and_no_snapshot(kafka_stack, caplog) -> None:
    """(b) The same mixed portfolio with no EURUSD curve at all: the EUR equity
    needs one even though it is not an option (ADR-0028 Decision 4)."""
    caplog.set_level(logging.WARNING, logger="pricer")
    reference_data, portfolio, ticks = _mixed_equity_setup()
    service, _topics, per_tick = _drive(kafka_stack, reference_data, [portfolio], [], ticks)
    try:
        assert per_tick == [[], []], "no snapshot on either tick"

        records = [r for r in _unpriceable_records(caplog) if r.portfolio_id == "PF"]
        # First tick: SAP has no price yet (NO_PRICE outranks MISSING_CURVE).
        # Second tick: every price is known, so the missing FX curve is what is left.
        assert [r.reason for r in records] == [
            UnpriceableReason.NO_PRICE,
            UnpriceableReason.MISSING_CURVE,
        ]
        assert records[1].missing == ["FX_RATE:EURUSD"]
        assert service.unpriceable_counts[UnpriceableReason.MISSING_CURVE] == 1
    finally:
        service.close()


def _eur_option_reference_data() -> ReferenceData:
    return ReferenceData(
        {
            "SAP-CALL-100": InstrumentReference(
                instrument_id="SAP-CALL-100",
                instrument_type="VANILLA_EUROPEAN_OPTION",
                underlying_id="SAP",
                currency="EUR",
                contract_size=Decimal(100),
                option_type=OptionRight.CALL,
                strike=Decimal("100.00"),
                expiry_iso="2026-06-01T00:00:00Z",
            ),
        }
    )


def _eur_option_position(portfolio_id: str) -> list[Position]:
    return [_position(portfolio_id, "SAP-CALL-100", "10")]


_SAP_TICK = [TickFixture("SAP", Decimal("100.00"), "EUR", _at(0))]


def test_eur_option_in_a_usd_portfolio_needs_its_option_curves_and_the_fx_pair(
    kafka_stack, caplog
) -> None:
    """(c) The required set for a EUR option in a USD portfolio is its three
    option curves AND FX_RATE:EURUSD. With everything present it prices, and
    its USD figures are its EUR figures times the rate, each field rounded
    once; with only the FX curve missing, exactly FX_RATE:EURUSD is reported."""
    caplog.set_level(logging.WARNING, logger="pricer")
    rate = Decimal("1.08123457")

    # Nothing published: the whole required set is named, sorted.
    service, _t, per_tick = _drive(
        kafka_stack,
        _eur_option_reference_data(),
        [_portfolio("PU", "USD", _eur_option_position("PU"))],
        [],
        _SAP_TICK,
    )
    try:
        assert per_tick == [[]]
        record = [r for r in _unpriceable_records(caplog) if r.portfolio_id == "PU"][-1]
        assert record.reason == UnpriceableReason.MISSING_CURVE
        assert record.missing == [
            "DIVIDEND_YIELD:SAP",
            "FX_RATE:EURUSD",
            "RISK_FREE_RATE:EUR",
            "VOLATILITY:SAP",
        ]
    finally:
        service.close()
    caplog.clear()

    # Only the FX curve missing: exactly that one key.
    service, _t, per_tick = _drive(
        kafka_stack,
        _eur_option_reference_data(),
        [_portfolio("PU", "USD", _eur_option_position("PU"))],
        _option_curves("SAP", "EUR"),
        _SAP_TICK,
    )
    try:
        assert per_tick == [[]]
        record = [r for r in _unpriceable_records(caplog) if r.portfolio_id == "PU"][-1]
        assert record.reason == UnpriceableReason.MISSING_CURVE
        assert record.missing == ["FX_RATE:EURUSD"]
    finally:
        service.close()

    # All present: prices. The reference is the same option held by a EUR
    # portfolio, which needs no FX curve at all.
    service, _t, per_tick = _drive(
        kafka_stack,
        _eur_option_reference_data(),
        [
            _portfolio("PU", "USD", _eur_option_position("PU")),
            _portfolio("PE", "EUR", _eur_option_position("PE")),
        ],
        [*_option_curves("SAP", "EUR"), _fx_curve("EURUSD", str(rate))],
        _SAP_TICK,
    )
    try:
        snapshots = {s.portfolio_id: s for s in per_tick[0]}
        assert set(snapshots) == {"PE", "PU"}
        eur, usd = snapshots["PE"], snapshots["PU"]
        assert eur.base_currency == "EUR"
        assert usd.base_currency == "USD"
        assert eur.price > _ZERO
        for field in ("price", "cash_delta", "cash_gamma", "cash_vega", "cash_theta", "cash_rho"):
            expected = (getattr(eur, field) * rate).quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
            assert getattr(usd, field) == expected, field
    finally:
        service.close()


def test_all_usd_portfolio_prices_without_any_fx_curve(kafka_stack, caplog) -> None:
    """(d) Same currency means no FX requirement: no USDUSD curve is published
    or needed, and the position is not converted (1500.00000000 exactly)."""
    caplog.set_level(logging.WARNING, logger="pricer")
    service, _t, per_tick = _drive(
        kafka_stack,
        ReferenceData({"AAPL": _equity("AAPL", "USD")}),
        [_portfolio("PF", "USD", [_position("PF", "AAPL", "10")])],
        [],
        [TickFixture("AAPL", Decimal("150.00"), "USD", _at(0))],
    )
    try:
        assert len(per_tick[0]) == 1
        snapshot = per_tick[0][0]
        assert snapshot.base_currency == "USD"
        assert snapshot.price == Decimal("1500.00000000")
        assert snapshot.cash_delta == Decimal("15.00000000")
        assert _unpriceable_records(caplog) == []
    finally:
        service.close()


def test_tick_with_the_wrong_currency_is_rejected_and_the_cached_price_is_unchanged(
    kafka_stack, caplog
) -> None:
    """(e) PF holds 10 AAPL and 5 MSFT, both USD in reference data.
      t=0 AAPL 150.00 USD  good     (MSFT unpriced -> no snapshot)
      t=1 MSFT 200.00 USD  good     -> 10*150 + 5*200 = 2500.00000000
      t=2 AAPL 999.00 EUR  REJECTED (reference says USD): logged, counted, no
                                    snapshot, and the price is not cached
      t=3 MSFT 201.00 USD  good     -> 10*150 + 5*201 = 2505.00000000, i.e. it
                                    is still the t=0 AAPL price of 150.00 that
                                    is used; had 999.00 been cached this would
                                    be 10*999 + 5*201 = 10995.00000000
    and oldest_input_event_time is still AAPL's good t=0 event time."""
    caplog.set_level(logging.WARNING, logger="pricer")
    reference_data = ReferenceData({"AAPL": _equity("AAPL", "USD"), "MSFT": _equity("MSFT", "USD")})
    portfolio = _portfolio(
        "PF", "USD", [_position("PF", "AAPL", "10"), _position("PF", "MSFT", "5")]
    )
    ticks = [
        TickFixture("AAPL", Decimal("150.00"), "USD", _at(0)),
        TickFixture("MSFT", Decimal("200.00"), "USD", _at(1)),
        TickFixture("AAPL", Decimal("999.00"), "EUR", _at(2)),
        TickFixture("MSFT", Decimal("201.00"), "USD", _at(3)),
    ]
    service, _t, per_tick = _drive(kafka_stack, reference_data, [portfolio], [], ticks)
    try:
        assert per_tick[0] == []
        assert [s.price for s in per_tick[1]] == [Decimal("2500.00000000")]
        assert per_tick[2] == [], "a rejected tick produces no snapshot"
        assert [s.price for s in per_tick[3]] == [Decimal("2505.00000000")]
        assert per_tick[3][0].oldest_input_event_time == _at(0)

        mismatches = [
            r for r in caplog.records if getattr(r, "event", None) == "tick_currency_mismatch"
        ]
        assert len(mismatches) == 1
        record = mismatches[0]
        assert record.instrument_id == "AAPL"
        assert record.tick_currency == "EUR"
        assert record.reference_currency == "USD"
        assert service.tick_currency_mismatch_count == 1
    finally:
        service.close()


def test_a_non_positive_published_fx_rate_fails_that_position_but_the_loop_survives(
    kafka_stack, caplog
) -> None:
    """A published EURUSD of 0 (the shared validator permits any finite
    decimal) must not escape and kill the tick loop: PF (USD AAPL + EUR SAP)
    is reported INSTRUMENT_NOT_PRICEABLE with a detail naming the pair and the
    value, no snapshot is produced for it, and later ticks are still
    processed -- P2 (AAPL only, USD, no FX involved) keeps producing
    snapshots on the AAPL ticks either side of it."""
    caplog.set_level(logging.WARNING, logger="pricer")
    reference_data = ReferenceData({"AAPL": _equity("AAPL", "USD"), "SAP": _equity("SAP", "EUR")})
    portfolios = [
        _portfolio("PF", "USD", [_position("PF", "AAPL", "10"), _position("PF", "SAP", "3")]),
        _portfolio("P2", "USD", [_position("P2", "AAPL", "1")]),
    ]
    ticks = [
        TickFixture("AAPL", Decimal("150.00"), "USD", _at(0)),
        TickFixture("SAP", Decimal("100.03"), "EUR", _at(1)),
        TickFixture("AAPL", Decimal("151.00"), "USD", _at(2)),
    ]
    service, _t, per_tick = _drive(
        kafka_stack, reference_data, portfolios, [_fx_curve("EURUSD", "0")], ticks
    )
    try:
        assert [s.portfolio_id for s in per_tick[0]] == ["P2"]
        assert per_tick[1] == [], "SAP tick: PF is unpriceable, P2 is not affected"
        assert [s.portfolio_id for s in per_tick[2]] == ["P2"], "the loop survived"
        assert per_tick[2][0].price == Decimal("151.00000000")

        records = [
            r
            for r in _unpriceable_records(caplog)
            if r.portfolio_id == "PF" and r.reason == UnpriceableReason.INSTRUMENT_NOT_PRICEABLE
        ]
        assert len(records) == 2, "reported on the SAP tick and again on the later AAPL tick"
        for record in records:
            assert record.missing == ["SAP"]
            assert "EURUSD" in record.detail
            assert "0E-8" in record.detail
            assert "invalid" in record.detail
        assert service.unpriceable_counts[UnpriceableReason.NO_PRICE] == 1
        assert service.unpriceable_counts[UnpriceableReason.INSTRUMENT_NOT_PRICEABLE] == 2
    finally:
        service.close()
