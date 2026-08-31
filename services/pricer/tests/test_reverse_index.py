"""Task 2: the reverse index (underlying_id -> {portfolio_id}) must be
updated on every portfolio.state change, including a position removal --
the case people forget, which otherwise leaves a portfolio being repriced
forever on an instrument it no longer holds."""
import time
from datetime import UTC, datetime
from decimal import Decimal

from loader import PortfolioFixture
from meridian_contracts.portfolio_state import Position
from pricer_test_helpers import (
    default_reference_data,
    make_service,
    process_n_real_ticks,
    seed_portfolios,
    unique_topics,
)


def test_removing_a_position_stops_it_from_triggering_snapshots(kafka_stack) -> None:
    topics = unique_topics()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    with_position = PortfolioFixture(
        portfolio_id="P",
        positions=[
            Position(
                portfolio_id="P",
                instrument_id="AAPL-CALL-150",
                quantity=Decimal(10),
                average_cost=Decimal("12.50"),
                as_of_event_time=t0,
            )
        ],
        event_time=t0,
    )
    seed_portfolios(kafka_stack, topics, [with_position])

    service = make_service(kafka_stack, topics, default_reference_data())
    service.hydrate()
    assert service.view.portfolios_for_underlying("AAPL") == {"P"}

    service.start_tick_consumption()
    _send_tick(kafka_stack, topics, "AAPL", "150.00", datetime(2026, 1, 2, tzinfo=UTC))

    first = process_n_real_ticks(service, 1)
    assert len(first[0]) == 1, "expected one snapshot while the position is still held"

    # Full-state replacement removing the position -- not a delta.
    without_position = PortfolioFixture(portfolio_id="P", positions=[], event_time=datetime(2026, 1, 3, tzinfo=UTC))
    seed_portfolios(kafka_stack, topics, [without_position])

    _send_tick(kafka_stack, topics, "AAPL", "151.00", datetime(2026, 1, 4, tzinfo=UTC))
    second = process_n_real_ticks(service, 1)

    assert second[0] == [], "a tick on an instrument no longer held must not trigger a snapshot"
    assert service.view.portfolios_for_underlying("AAPL") == set()
    assert "P" in service.view.portfolio_ids(), "the portfolio itself still exists, just with no positions"

    service.close()


def test_reindexing_leaves_other_portfolios_on_the_same_underlying_untouched(kafka_stack) -> None:
    """Removing one portfolio's position on an underlying must not affect
    another portfolio still holding a position on that same underlying."""
    topics = unique_topics()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    p1 = PortfolioFixture(
        portfolio_id="P1",
        positions=[
            Position(
                portfolio_id="P1",
                instrument_id="AAPL",
                quantity=Decimal(100),
                average_cost=Decimal(100),
                as_of_event_time=t0,
            )
        ],
        event_time=t0,
    )
    p2 = PortfolioFixture(
        portfolio_id="P2",
        positions=[
            Position(
                portfolio_id="P2",
                instrument_id="AAPL",
                quantity=Decimal(50),
                average_cost=Decimal(100),
                as_of_event_time=t0,
            )
        ],
        event_time=t0,
    )
    seed_portfolios(kafka_stack, topics, [p1, p2])

    service = make_service(kafka_stack, topics, default_reference_data())
    service.hydrate()
    assert service.view.portfolios_for_underlying("AAPL") == {"P1", "P2"}

    seed_portfolios(kafka_stack, topics, [PortfolioFixture(portfolio_id="P1", positions=[], event_time=datetime(2026, 1, 2, tzinfo=UTC))])
    # _drain_portfolio_updates() polls with timeout=0 (non-blocking, so it
    # never stalls the hot tick-processing path) -- give the consumer a
    # few real chances to actually fetch the just-produced message rather
    # than asserting after a single zero-timeout call.
    for _ in range(20):
        service._drain_portfolio_updates()
        if service.view.portfolios_for_underlying("AAPL") == {"P2"}:
            break
        time.sleep(0.25)

    assert service.view.portfolios_for_underlying("AAPL") == {"P2"}
    service.close()


def _send_tick(kafka_stack, topics, instrument_id: str, price: str, event_time) -> None:
    from meridian_contracts.tick import Tick
    from quant_io.tick_producer import TickProducer

    producer = TickProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topics.market_ticks,
    )
    producer.produce_tick(
        Tick(
            instrument_id=instrument_id,
            price=Decimal(price),
            currency="USD",
            event_time=event_time,
            ingest_time=event_time,
            scenario_id="s",
        )
    )
    producer.flush()
