"""Contract tests for the `market.ticks` producer/consumer, against a real
local Kafka + schema registry (testcontainers), not a mock of either
(docs/test-strategy.md).
"""
import json
import uuid
from decimal import Decimal
from pathlib import Path

from meridian_contracts.tick import Tick
from quant_io.tick_producer import TickProducer, make_tick_consumer

from conftest import KafkaStack

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TICK_AVSC = _REPO_ROOT / "contracts" / "avro" / "tick.avsc"


def _sample_tick(scenario_id: str) -> Tick:
    from datetime import UTC, datetime

    return Tick(
        instrument_id="AAPL",
        price=Decimal("150.12345678"),
        currency="USD",
        event_time=datetime(2026, 1, 1, tzinfo=UTC),
        ingest_time=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        scenario_id=scenario_id,
    )


def test_round_trip_through_real_broker_and_registry(kafka_stack: KafkaStack) -> None:
    producer = TickProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
    )
    sent = _sample_tick(scenario_id=f"contract-test-{uuid.uuid4()}")
    producer.produce_tick(sent)
    producer.flush()

    consumer = make_tick_consumer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        group_id=f"test-{uuid.uuid4()}",
    )
    try:
        msg = None
        for _ in range(20):
            msg = consumer.poll(5.0)
            if msg is not None and msg.value().scenario_id == sent.scenario_id:
                break
        assert msg is not None, "no message consumed from market.ticks"
        received = msg.value()
        assert received == sent
        assert msg.key().instrument_id == sent.instrument_id
    finally:
        consumer.close()


def test_registered_subject_matches_checked_in_schema(kafka_stack: KafkaStack) -> None:
    producer = TickProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
    )
    producer.produce_tick(_sample_tick(scenario_id=f"schema-check-{uuid.uuid4()}"))
    producer.flush()

    from confluent_kafka.schema_registry import SchemaRegistryClient

    registry = SchemaRegistryClient({"url": kafka_stack.schema_registry_url})
    registered = registry.get_latest_version("market.ticks-value")
    assert json.loads(registered.schema.schema_str) == json.loads(_TICK_AVSC.read_text())
