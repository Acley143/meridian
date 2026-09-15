"""ADR-0018: a portfolio that cannot be priced is reported with a structured
log line (event=portfolio_unpriceable) naming the portfolio and what is
missing, plus a per-reason counter -- never silently skipped."""
import logging
from datetime import UTC, datetime
from decimal import Decimal

from loader import (
    PortfolioFixture,
    TickFixture,
    load_portfolio_fixtures,
    load_tick_fixtures,
)
from meridian_contracts.portfolio_state import Position
from pricer.pricing import UnpriceableReason
from pricer.reference_data import InstrumentReference, ReferenceData
from pricer_test_helpers import (
    default_reference_data,
    make_service,
    process_n_real_ticks,
    produce_ticks,
    seed_portfolios,
    unique_topics,
)


def _unpriceable_records(caplog):
    return [r for r in caplog.records if getattr(r, "event", None) == "portfolio_unpriceable"]


def test_no_price_reported_on_default_fixture_pipeline(kafka_stack, caplog) -> None:
    """(a) The load-bearing case: PF-1's first AAPL tick is reported with
    reason NO_PRICE (missing=["MSFT"]) via the real fixture pipeline, while
    PF-2 -- unaffected by PF-1's skip -- still gets its first snapshot for
    that same tick. Mirrors `pricer_test_helpers.run_fixture_pipeline`'s
    exact sequence so the service instance can be inspected afterward."""
    caplog.set_level(logging.WARNING, logger="pricer")

    topics = unique_topics()
    reference_data = default_reference_data()
    seed_portfolios(kafka_stack, topics, load_portfolio_fixtures())

    service = make_service(kafka_stack, topics, reference_data)
    service.hydrate()
    service.start_tick_consumption()

    scenario_id, ticks = load_tick_fixtures()
    produce_ticks(kafka_stack, topics, scenario_id, ticks)

    per_tick = process_n_real_ticks(service, len(ticks))

    try:
        first_tick_snapshots = per_tick[0]
        assert any(s.portfolio_id == "PF-2" for s in first_tick_snapshots)

        records = [
            r
            for r in _unpriceable_records(caplog)
            if r.portfolio_id == "PF-1" and r.trigger == "tick"
        ]
        assert len(records) >= 1
        record = records[0]
        assert record.reason == UnpriceableReason.NO_PRICE
        assert record.missing == ["MSFT"]

        assert service.unpriceable_counts[UnpriceableReason.NO_PRICE] >= 1
    finally:
        service.close()


def test_no_reference_data_reported_at_tick_time(kafka_stack, caplog) -> None:
    """(b) A portfolio holding one known instrument and one instrument
    absent from reference data: a tick on the known underlying reports the
    unknown instrument_id, and produces no snapshot for that portfolio."""
    caplog.set_level(logging.WARNING, logger="pricer")

    topics = unique_topics()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    fixture = PortfolioFixture(
        portfolio_id="P",
        positions=[
            Position(
                portfolio_id="P",
                instrument_id="AAPL",
                quantity=Decimal(10),
                average_cost=Decimal(100),
                as_of_event_time=t0,
            ),
            Position(
                portfolio_id="P",
                instrument_id="UNKNOWN-1",
                quantity=Decimal(5),
                average_cost=Decimal(50),
                as_of_event_time=t0,
            ),
        ],
        event_time=t0,
    )
    seed_portfolios(kafka_stack, topics, [fixture])

    service = make_service(kafka_stack, topics, default_reference_data())
    service.hydrate()
    service.start_tick_consumption()

    produce_ticks(
        kafka_stack,
        topics,
        "s",
        [TickFixture("AAPL", Decimal("150.00"), "USD", t0)],
    )

    results = process_n_real_ticks(service, 1)
    try:
        assert len(results) == 1
        assert results[0] == []

        records = [
            r for r in _unpriceable_records(caplog) if r.portfolio_id == "P" and r.trigger == "tick"
        ]
        assert len(records) >= 1
        record = records[0]
        assert record.reason == UnpriceableReason.NO_REFERENCE_DATA
        assert "UNKNOWN-1" in record.missing

        assert service.unpriceable_counts[UnpriceableReason.NO_REFERENCE_DATA] >= 1
    finally:
        service.close()


def test_no_reference_data_reported_at_portfolio_update_time(kafka_stack, caplog) -> None:
    """(c) A portfolio holding only an unknown instrument is never affected
    by any tick (PortfolioView only indexes positions with reference data),
    so it must instead be reported right at hydration/portfolio-update
    time, or it would never be reported at all."""
    caplog.set_level(logging.WARNING, logger="pricer")

    topics = unique_topics()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    fixture = PortfolioFixture(
        portfolio_id="P",
        positions=[
            Position(
                portfolio_id="P",
                instrument_id="UNKNOWN-2",
                quantity=Decimal(1),
                average_cost=Decimal(1),
                as_of_event_time=t0,
            ),
        ],
        event_time=t0,
    )
    seed_portfolios(kafka_stack, topics, [fixture])

    service = make_service(kafka_stack, topics, default_reference_data())
    service.hydrate()

    try:
        records = [
            r
            for r in _unpriceable_records(caplog)
            if r.portfolio_id == "P" and r.trigger == "portfolio_update"
        ]
        assert len(records) >= 1
        record = records[0]
        assert "UNKNOWN-2" in record.missing

        assert service.unpriceable_counts[UnpriceableReason.NO_REFERENCE_DATA] >= 1
    finally:
        service.close()


def test_instrument_not_priceable_reported_at_tick_time(kafka_stack, caplog) -> None:
    """(d) An instrument type with no pricer yet (VANILLA_AMERICAN_OPTION,
    Q2) is reported with reason INSTRUMENT_NOT_PRICEABLE, not silently
    skipped, and produces no snapshot for its portfolio."""
    caplog.set_level(logging.WARNING, logger="pricer")

    reference_data = ReferenceData(
        {
            "AAPL-AMER-150": InstrumentReference(
                instrument_id="AAPL-AMER-150",
                instrument_type="VANILLA_AMERICAN_OPTION",
                underlying_id="AAPL",
                currency="USD",
                contract_size=Decimal(100),
            ),
        }
    )

    topics = unique_topics()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    fixture = PortfolioFixture(
        portfolio_id="P",
        positions=[
            Position(
                portfolio_id="P",
                instrument_id="AAPL-AMER-150",
                quantity=Decimal(10),
                average_cost=Decimal("12.50"),
                as_of_event_time=t0,
            ),
        ],
        event_time=t0,
    )
    seed_portfolios(kafka_stack, topics, [fixture])

    service = make_service(kafka_stack, topics, reference_data)
    service.hydrate()
    service.start_tick_consumption()

    produce_ticks(
        kafka_stack,
        topics,
        "s",
        [TickFixture("AAPL", Decimal("150.00"), "USD", t0)],
    )

    results = process_n_real_ticks(service, 1)
    try:
        assert len(results) == 1
        assert results[0] == []

        records = [
            r for r in _unpriceable_records(caplog) if r.portfolio_id == "P" and r.trigger == "tick"
        ]
        assert len(records) >= 1
        record = records[0]
        assert record.reason == UnpriceableReason.INSTRUMENT_NOT_PRICEABLE
        assert "AAPL-AMER-150" in record.missing

        assert service.unpriceable_counts[UnpriceableReason.INSTRUMENT_NOT_PRICEABLE] >= 1
    finally:
        service.close()
