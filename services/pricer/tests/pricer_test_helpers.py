"""Test helpers: per-test topic isolation, fixture seeding, and driving a
`PricerService` against a real Kafka + schema registry (testcontainers).

The real `PricerService` hardcodes the production topic names
(`market.ticks`, `portfolio.state`, `risk.snapshots` -- ADR-0016). Tests use
its topic-override constructor params with unique per-test names instead,
so tests never share state through those fixed names.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from loader import (
    PortfolioFixture,
    TickFixture,
    load_portfolio_fixtures,
    load_tick_fixtures,
)
from meridian_contracts.portfolio_state import PortfolioState
from meridian_contracts.tick import Tick
from pricer.reference_data import ReferenceData, load_reference_data
from pricer.service import PricerService
from quant_io.consumer import PartitionEOF
from quant_io.portfolio_state_io import PortfolioStateProducer
from quant_io.risk_snapshot_io import make_risk_snapshot_consumer
from quant_io.tick_producer import TickProducer

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@dataclass(frozen=True)
class TestTopics:
    portfolio_state: str
    market_ticks: str
    risk_snapshots: str


def unique_topics() -> TestTopics:
    suffix = uuid.uuid4().hex[:8]
    return TestTopics(
        portfolio_state=f"test.portfolio.state.{suffix}",
        market_ticks=f"test.market.ticks.{suffix}",
        risk_snapshots=f"test.risk.snapshots.{suffix}",
    )


def default_reference_data() -> ReferenceData:
    return load_reference_data(_FIXTURES_DIR / "instruments.yaml")


def seed_portfolios(kafka_stack, topics: TestTopics, fixtures: list[PortfolioFixture]) -> None:
    producer = PortfolioStateProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topics.portfolio_state,
    )
    for fixture in fixtures:
        producer.produce_state(
            PortfolioState(
                portfolio_id=fixture.portfolio_id,
                positions=fixture.positions,
                event_time=fixture.event_time,
                ingest_time=fixture.event_time,
            )
        )
    producer.flush()


def produce_ticks(
    kafka_stack, topics: TestTopics, scenario_id: str, ticks: list[TickFixture]
) -> None:
    producer = TickProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topics.market_ticks,
    )
    for t in ticks:
        producer.produce_tick(
            Tick(
                instrument_id=t.instrument_id,
                price=t.price,
                currency=t.currency,
                event_time=t.event_time,
                ingest_time=t.event_time,
                scenario_id=scenario_id,
            )
        )
    producer.flush()


def make_service(
    kafka_stack,
    topics: TestTopics,
    reference_data: ReferenceData | None = None,
    tick_group_id: str | None = None,
) -> PricerService:
    return PricerService(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        reference_data=reference_data or default_reference_data(),
        tick_group_id=tick_group_id or f"test-pricer-{uuid.uuid4()}",
        portfolio_state_topic=topics.portfolio_state,
        tick_topic=topics.market_ticks,
        risk_snapshot_topic=topics.risk_snapshots,
    )


def process_n_real_ticks(
    service: PricerService, n: int, max_polls: int = 50, timeout: float = 5.0
) -> list[list]:
    """Calls `process_one_tick` until `n` *real* ticks have been consumed
    (a `None` return -- poll timeout, no message -- doesn't count; the
    consumer's first poll after subscribing is often exactly this, wasted
    on rebalance/group-join). Returns each tick's snapshot list, in order."""
    results: list[list] = []
    for _ in range(max_polls):
        if len(results) >= n:
            break
        outcome = service.process_one_tick(timeout=timeout)
        if outcome is not None:
            results.append(outcome)
    return results


def consume_all_snapshots(kafka_stack, topics: TestTopics, expected_count: int, timeout: float = 30.0):
    consumer = make_risk_snapshot_consumer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        group_id=f"test-{uuid.uuid4()}",
        topic=topics.risk_snapshots,
    )
    records = []
    deadline = time.monotonic() + timeout
    try:
        while len(records) < expected_count and time.monotonic() < deadline:
            msg = consumer.poll(1.0)
            if msg is not None and not isinstance(msg, PartitionEOF):
                records.append(msg.value())
    finally:
        consumer.close()
    return records


def run_fixture_pipeline(kafka_stack, expected_snapshot_count: int = 4) -> list:
    """Seeds fixtures/{portfolios,ticks}.yaml through a fresh `PricerService`
    (fresh topics), drives every tick, and returns every snapshot produced,
    in production order."""
    topics = unique_topics()
    reference_data = default_reference_data()
    seed_portfolios(kafka_stack, topics, load_portfolio_fixtures())

    service = make_service(kafka_stack, topics, reference_data)
    service.hydrate()
    service.start_tick_consumption()

    scenario_id, ticks = load_tick_fixtures()
    produce_ticks(kafka_stack, topics, scenario_id, ticks)

    per_tick = process_n_real_ticks(service, len(ticks))
    service.close()

    produced = [snap for batch in per_tick for snap in batch]
    if len(produced) != expected_snapshot_count:
        raise AssertionError(
            f"expected {expected_snapshot_count} snapshots, got {len(produced)}: {produced}"
        )
    return produced
