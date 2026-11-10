"""ADR-0033: the pricer prices VANILLA_AMERICAN_OPTION with quant-core's
American pricer (ADR-0031), requires the same curves as a European option,
and reports a position outside ADR-0031's validated domain as
OUTSIDE_MODEL_DOMAIN, last in precedence.

Reference data and curves are built in each test, not in the shared
fixtures. Expected numbers are computed from quant-core's American pricer
and the pricer's own aggregation, with the same inputs the service sees.
"""
import logging
from datetime import UTC, datetime
from decimal import Decimal

from loader import PortfolioFixture, TickFixture
from meridian_contracts.market_curves import CurveKind, MarketCurve
from meridian_contracts.portfolio_state import Position
from pricer.pricing import UnpriceableReason, aggregate_position
from pricer.reference_data import InstrumentReference, ReferenceData
from pricer_test_helpers import (
    make_service,
    process_n_real_ticks,
    produce_ticks,
    seed_portfolios,
    unique_topics,
)
from quant_core.numeric import to_model
from quant_core.pricing import american, black_scholes
from quant_core.risk import PositionRisk, delta_normal_var_95
from quant_core.types import AmericanOption, EuropeanOption, MarketState, OptionRight

SCENARIO = "american-test"
JAN_1 = datetime(2026, 1, 1, tzinfo=UTC)
JUL_1 = datetime(2026, 7, 1, tzinfo=UTC)

AMER_PUT = InstrumentReference(
    instrument_id="AAPL-AMER-PUT-200",
    instrument_type="VANILLA_AMERICAN_OPTION",
    underlying_id="AAPL",
    currency="USD",
    contract_size=Decimal(100),
    option_type=OptionRight.PUT,
    strike=Decimal("200.00"),
    expiry_iso="2026-06-01T00:00:00Z",
)
AMER_PUT_DEC = InstrumentReference(
    instrument_id="AAPL-AMER-PUT-200-DEC",
    instrument_type="VANILLA_AMERICAN_OPTION",
    underlying_id="AAPL",
    currency="USD",
    contract_size=Decimal(100),
    option_type=OptionRight.PUT,
    strike=Decimal("200.00"),
    expiry_iso="2026-12-01T00:00:00Z",
)
EURO_CALL = InstrumentReference(
    instrument_id="AAPL-CALL-150",
    instrument_type="VANILLA_EUROPEAN_OPTION",
    underlying_id="AAPL",
    currency="USD",
    contract_size=Decimal(100),
    option_type=OptionRight.CALL,
    strike=Decimal("150.00"),
    expiry_iso="2026-06-01T00:00:00Z",
)
AAPL_EQUITY = InstrumentReference(
    instrument_id="AAPL",
    instrument_type="EQUITY",
    underlying_id="AAPL",
    currency="USD",
    contract_size=Decimal(1),
)


def _curve(kind: CurveKind, curve_id: str, value: float) -> MarketCurve:
    return MarketCurve(
        scenario_id=SCENARIO,
        kind=kind,
        curve_id=curve_id,
        value_float=value,
        value_decimal=None,
        event_time=JAN_1,
        ingest_time=JAN_1,
    )


def _aapl_curves(volatility: float = 0.25, with_rate: bool = True) -> list[MarketCurve]:
    curves = [
        _curve(CurveKind.VOLATILITY, "AAPL", volatility),
        _curve(CurveKind.DIVIDEND_YIELD, "AAPL", 0.0),
    ]
    if with_rate:
        curves.append(_curve(CurveKind.RISK_FREE_RATE, "USD", 0.05))
    return curves


def _portfolio(portfolio_id: str, holdings: list[tuple[str, Decimal]]) -> PortfolioFixture:
    return PortfolioFixture(
        portfolio_id=portfolio_id,
        base_currency="USD",
        positions=[
            Position(
                portfolio_id=portfolio_id,
                instrument_id=instrument_id,
                quantity=quantity,
                average_cost=Decimal("1.00"),
                as_of_event_time=JAN_1,
            )
            for instrument_id, quantity in holdings
        ],
        event_time=JAN_1,
    )


def _run_one_tick(kafka_stack, references, portfolios, curves, tick_time):
    topics = unique_topics()
    seed_portfolios(kafka_stack, topics, portfolios)
    service = make_service(
        kafka_stack,
        topics,
        ReferenceData({r.instrument_id: r for r in references}),
        curves=curves,
    )
    service.hydrate()
    service.start_tick_consumption()
    produce_ticks(kafka_stack, topics, SCENARIO, [TickFixture("AAPL", Decimal("150.00"), "USD", tick_time)])
    results = process_n_real_ticks(service, 1)
    return service, results


def _unpriceable(caplog, portfolio_id: str) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if getattr(r, "event", None) == "portfolio_unpriceable"
        and r.portfolio_id == portfolio_id
        and r.trigger == "tick"
    ]


def _reason_name(record: logging.LogRecord) -> str:
    return str(getattr(record.reason, "value", record.reason))


def test_a1_american_option_is_priced_with_the_american_pricer(kafka_stack) -> None:
    service, results = _run_one_tick(
        kafka_stack,
        [AMER_PUT],
        [_portfolio("P", [("AAPL-AMER-PUT-200", Decimal(10))])],
        _aapl_curves(),
        JAN_1,
    )
    try:
        option = AmericanOption(
            underlying_id="AAPL",
            strike=Decimal("200.00"),
            expiry=datetime(2026, 6, 1, tzinfo=UTC),
            right=OptionRight.PUT,
        )
        market = MarketState(
            spot=Decimal("150.00"),
            volatility=0.25,
            risk_free_rate=0.05,
            dividend_yield=0.0,
            valuation_time=JAN_1,
        )
        american_result = american.price(option, market)
        european_result = black_scholes.price(
            EuropeanOption(
                underlying_id=option.underlying_id,
                strike=option.strike,
                expiry=option.expiry,
                right=option.right,
            ),
            market,
        )
        # The early-exercise premium: routing to Black-Scholes cannot pass.
        assert abs(to_model(american_result.price) - to_model(european_result.price)) > 1e-6

        expected = aggregate_position(american_result, Decimal(10), Decimal(100), Decimal("150.00"))
        expected_var = delta_normal_var_95(
            [PositionRisk(cash_delta=to_model(expected.cash_delta), annual_volatility=0.25)]
        )

        assert len(results) == 1
        snapshots = [s for s in results[0] if s.portfolio_id == "P"]
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot.price == expected.price
        assert snapshot.cash_delta == expected.cash_delta
        assert snapshot.cash_gamma == expected.cash_gamma
        assert snapshot.cash_vega == expected.cash_vega
        assert snapshot.cash_theta == expected.cash_theta
        assert snapshot.cash_rho == expected.cash_rho
        assert snapshot.var_95 == expected_var
    finally:
        service.close()


def test_a2_out_of_domain_is_reported_and_other_portfolios_are_priced(kafka_stack, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="pricer")
    service, results = _run_one_tick(
        kafka_stack,
        [AMER_PUT, AAPL_EQUITY],
        [
            _portfolio("P", [("AAPL-AMER-PUT-200", Decimal(10))]),
            _portfolio("Q", [("AAPL", Decimal(1000))]),
        ],
        _aapl_curves(volatility=3.0),
        JAN_1,
    )
    try:
        assert len(results) == 1
        assert [s.portfolio_id for s in results[0]] == ["Q"]

        records = _unpriceable(caplog, "P")
        assert len(records) == 1
        record = records[0]
        assert _reason_name(record) == "OUTSIDE_MODEL_DOMAIN"
        assert record.missing == ["AAPL-AMER-PUT-200"]
        assert "sigma_root_t" in record.detail
        assert service.unpriceable_counts[UnpriceableReason.OUTSIDE_MODEL_DOMAIN] == 1
    finally:
        service.close()


def test_a3_instrument_not_priceable_takes_precedence_over_outside_model_domain(
    kafka_stack, caplog
) -> None:
    caplog.set_level(logging.WARNING, logger="pricer")
    service, results = _run_one_tick(
        kafka_stack,
        [EURO_CALL, AMER_PUT_DEC],
        [_portfolio("P", [("AAPL-CALL-150", Decimal(1)), ("AAPL-AMER-PUT-200-DEC", Decimal(1))])],
        _aapl_curves(volatility=3.0),
        JUL_1,
    )
    try:
        assert len(results) == 1
        assert results[0] == []

        records = _unpriceable(caplog, "P")
        assert len(records) == 1
        assert _reason_name(records[0]) == "INSTRUMENT_NOT_PRICEABLE"
        assert records[0].missing == ["AAPL-CALL-150"]
        assert not [r for r in records if _reason_name(r) == "OUTSIDE_MODEL_DOMAIN"]
    finally:
        service.close()


def test_a4_american_option_requires_the_rate_curve(kafka_stack, caplog) -> None:
    caplog.set_level(logging.WARNING, logger="pricer")
    service, results = _run_one_tick(
        kafka_stack,
        [AMER_PUT],
        [_portfolio("P", [("AAPL-AMER-PUT-200", Decimal(10))])],
        _aapl_curves(with_rate=False),
        JAN_1,
    )
    try:
        assert len(results) == 1
        assert results[0] == []

        records = _unpriceable(caplog, "P")
        assert len(records) == 1
        assert _reason_name(records[0]) == "MISSING_CURVE"
        assert records[0].missing == ["RISK_FREE_RATE:USD"]
    finally:
        service.close()
