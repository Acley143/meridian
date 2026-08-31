"""Task 1: no snapshot is produced before the portfolio.state view has been
read to the end of every assigned partition."""
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from loader import PortfolioFixture, load_portfolio_fixtures
from meridian_contracts.portfolio_state import PortfolioState, Position
from meridian_contracts.tick import Tick
from pricer_test_helpers import (
    default_reference_data,
    make_service,
    process_n_real_ticks,
    seed_portfolios,
    unique_topics,
)
from quant_io.portfolio_state_io import PortfolioStateProducer
from quant_io.tick_producer import TickProducer


def test_start_tick_consumption_before_hydrate_raises(kafka_stack) -> None:
    service = make_service(kafka_stack, unique_topics())
    with pytest.raises(RuntimeError):
        service.start_tick_consumption()


def test_ready_flag_and_view_are_empty_before_hydrate(kafka_stack) -> None:
    topics = unique_topics()
    seed_portfolios(kafka_stack, topics, load_portfolio_fixtures())
    service = make_service(kafka_stack, topics)

    assert service.ready is False
    assert len(service.view) == 0

    service.hydrate()

    assert service.ready is True
    assert service.view.portfolio_ids() == {"PF-1", "PF-2"}


def test_ticks_produced_before_hydration_are_not_lost_or_priced_early(kafka_stack) -> None:
    """Ticks sitting on the broker before hydration starts must still be
    priced correctly afterward -- "paused," not dropped."""
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
            )
        ],
        event_time=t0,
    )
    seed_portfolios(kafka_stack, topics, [fixture])

    # Produce a tick to market.ticks *before* the service even starts
    # hydrating -- it must sit there unpriced until hydration completes and
    # tick consumption explicitly begins.
    tick_producer = TickProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topics.market_ticks,
    )
    tick_producer.produce_tick(
        Tick(
            instrument_id="AAPL",
            price=Decimal("150.00"),
            currency="USD",
            event_time=t0,
            ingest_time=t0,
            scenario_id="s",
        )
    )
    tick_producer.flush()

    service = make_service(kafka_stack, topics, default_reference_data())
    service.hydrate()
    assert service.ready is True

    service.start_tick_consumption()
    results = process_n_real_ticks(service, 1)
    assert len(results) == 1
    snapshots = results[0]
    assert len(snapshots) == 1
    assert snapshots[0].portfolio_id == "P"
    assert snapshots[0].price == Decimal("1500.00000000")


def test_tombstone_present_before_hydration_nets_to_deleted(kafka_stack) -> None:
    """Task 1: a portfolio created then tombstoned before the pricer ever
    starts must not appear in the view once hydration completes."""
    topics = unique_topics()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    producer = PortfolioStateProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topics.portfolio_state,
    )
    producer.produce_state(
        PortfolioState(
            portfolio_id="P",
            positions=[
                Position(
                    portfolio_id="P",
                    instrument_id="AAPL",
                    quantity=Decimal(10),
                    average_cost=Decimal(100),
                    as_of_event_time=t0,
                )
            ],
            event_time=t0,
            ingest_time=t0,
        )
    )
    producer.produce_tombstone("P")
    producer.flush()

    service = make_service(kafka_stack, topics, default_reference_data())
    service.hydrate()

    assert "P" not in service.view.portfolio_ids()
    assert service.view.portfolios_for_underlying("AAPL") == set()
