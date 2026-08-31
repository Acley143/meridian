"""Task 9: a portfolio deleted mid-stream stops producing snapshots."""
from datetime import UTC, datetime
from decimal import Decimal

from meridian_contracts.portfolio_state import PortfolioState, Position
from meridian_contracts.tick import Tick
from pricer_test_helpers import (
    default_reference_data,
    make_service,
    process_n_real_ticks,
    unique_topics,
)
from quant_io.portfolio_state_io import PortfolioStateProducer
from quant_io.tick_producer import TickProducer


def test_tombstone_mid_stream_stops_snapshots(kafka_stack) -> None:
    topics = unique_topics()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)

    portfolio_producer = PortfolioStateProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topics.portfolio_state,
    )
    portfolio_producer.produce_state(
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
    portfolio_producer.flush()

    service = make_service(kafka_stack, topics, default_reference_data())
    service.hydrate()
    assert "P" in service.view.portfolio_ids()

    service.start_tick_consumption()
    tick_producer = TickProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topics.market_ticks,
    )

    def send_tick(price: str, event_time: datetime) -> None:
        tick_producer.produce_tick(
            Tick(
                instrument_id="AAPL",
                price=Decimal(price),
                currency="USD",
                event_time=event_time,
                ingest_time=event_time,
                scenario_id="s",
            )
        )
        tick_producer.flush()

    send_tick("150.00", datetime(2026, 1, 2, tzinfo=UTC))
    first = process_n_real_ticks(service, 1)
    assert len(first[0]) == 1

    portfolio_producer.produce_tombstone("P")
    portfolio_producer.flush()

    send_tick("151.00", datetime(2026, 1, 3, tzinfo=UTC))
    second = process_n_real_ticks(service, 1)

    assert second[0] == [], "a tombstoned portfolio must not produce a snapshot"
    assert "P" not in service.view.portfolio_ids()
    assert service.view.portfolios_for_underlying("AAPL") == set()

    service.close()
