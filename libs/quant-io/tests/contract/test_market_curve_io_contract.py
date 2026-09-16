"""Contract tests for `quant_io.market_curve_io`, against a real local Kafka
+ schema registry (testcontainers), not a mock of either
(docs/test-strategy.md). Never touches `market.curves` itself -- each test
provisions its own uniquely-named topic."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from confluent_kafka import Message
from confluent_kafka.admin import AdminClient, NewTopic
from meridian_contracts.market_curves import CurveKind, MarketCurve
from quant_io.consumer import AvroConsumer, PartitionEOF
from quant_io.market_curve_io import (
    InvalidMarketCurveError,
    MarketCurveProducer,
    make_market_curve_consumer,
)
from quant_io.topic_admin import TopicConfigurationError

from conftest import KafkaStack

_EVENT_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_INGEST_TIME = datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC)


def _unique_topic() -> str:
    return f"market-curve-io-contract-{uuid.uuid4()}"


def _curve(
    *,
    scenario_id: str,
    kind: CurveKind,
    curve_id: str,
    value_float: float | None = None,
    value_decimal: Decimal | None = None,
) -> MarketCurve:
    return MarketCurve(
        scenario_id=scenario_id,
        kind=kind,
        curve_id=curve_id,
        value_float=value_float,
        value_decimal=value_decimal,
        event_time=_EVENT_TIME,
        ingest_time=_INGEST_TIME,
    )


def _scenario_curves(scenario_id: str) -> list[MarketCurve]:
    return [
        _curve(scenario_id=scenario_id, kind=CurveKind.RISK_FREE_RATE, curve_id="USD", value_float=0.05),
        _curve(scenario_id=scenario_id, kind=CurveKind.VOLATILITY, curve_id="AAPL", value_float=0.25),
        _curve(scenario_id=scenario_id, kind=CurveKind.DIVIDEND_YIELD, curve_id="AAPL", value_float=0.015),
        _curve(
            scenario_id=scenario_id,
            kind=CurveKind.FX_RATE,
            curve_id="EURUSD",
            value_decimal=Decimal("1.08000000"),
        ),
    ]


def _collect_until_eof(consumer: AvroConsumer, timeout: float = 5.0, max_polls: int = 20) -> list[Message]:
    messages: list[Message] = []
    for _ in range(max_polls):
        polled = consumer.poll(timeout)
        if polled is None:
            continue
        if isinstance(polled, PartitionEOF):
            break
        messages.append(polled)
    return messages


def test_publish_scenario_curves_round_trips_all_four_kinds(kafka_stack: KafkaStack) -> None:
    topic = _unique_topic()
    scenario_id = f"contract-{uuid.uuid4()}"
    curves = _scenario_curves(scenario_id)

    producer = MarketCurveProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topic,
    )
    producer.publish_scenario_curves(curves)

    consumer = make_market_curve_consumer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        group_id=f"test-{uuid.uuid4()}",
        topic=topic,
        enable_partition_eof=True,
    )
    try:
        messages = _collect_until_eof(consumer)
    finally:
        consumer.close()

    assert len(messages) == 4
    received = {(msg.key().kind, msg.key().curve_id): (msg.key(), msg.value()) for msg in messages}
    for curve in curves:
        key, value = received[(curve.kind, curve.curve_id)]
        assert key.scenario_id == curve.scenario_id
        assert value == curve


def test_publish_scenario_curves_rejects_mixed_scenario_ids(kafka_stack: KafkaStack) -> None:
    producer = MarketCurveProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=_unique_topic(),
    )
    curves = [
        _curve(scenario_id="scenario-a", kind=CurveKind.RISK_FREE_RATE, curve_id="USD", value_float=0.05),
        _curve(scenario_id="scenario-b", kind=CurveKind.VOLATILITY, curve_id="AAPL", value_float=0.25),
    ]
    with pytest.raises(InvalidMarketCurveError):
        producer.publish_scenario_curves(curves)


def test_publish_scenario_curves_rejects_duplicate_kind_curve_id(kafka_stack: KafkaStack) -> None:
    producer = MarketCurveProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=_unique_topic(),
    )
    scenario_id = f"contract-{uuid.uuid4()}"
    curves = [
        _curve(scenario_id=scenario_id, kind=CurveKind.RISK_FREE_RATE, curve_id="USD", value_float=0.05),
        _curve(scenario_id=scenario_id, kind=CurveKind.RISK_FREE_RATE, curve_id="USD", value_float=0.06),
    ]
    with pytest.raises(InvalidMarketCurveError):
        producer.publish_scenario_curves(curves)


def test_publish_scenario_curves_rejects_empty_sequence(kafka_stack: KafkaStack) -> None:
    producer = MarketCurveProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=_unique_topic(),
    )
    with pytest.raises(InvalidMarketCurveError):
        producer.publish_scenario_curves([])


def test_publish_scenario_curves_rejects_invalid_curve_and_produces_nothing(
    kafka_stack: KafkaStack,
) -> None:
    topic = _unique_topic()
    producer = MarketCurveProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topic,
    )
    scenario_id = f"contract-{uuid.uuid4()}"
    curves = [
        _curve(scenario_id=scenario_id, kind=CurveKind.RISK_FREE_RATE, curve_id="USD", value_float=0.05),
        # Invalid: RISK_FREE_RATE must set value_float, not value_decimal.
        _curve(
            scenario_id=scenario_id,
            kind=CurveKind.RISK_FREE_RATE,
            curve_id="EUR",
            value_decimal=Decimal("1.00000000"),
        ),
    ]
    with pytest.raises(InvalidMarketCurveError):
        producer.publish_scenario_curves(curves)

    # The batch rule requires validation before any produce -- the only
    # evidence for "nothing was produced" is that consuming the topic to
    # its end yields no records at all.
    consumer = make_market_curve_consumer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        group_id=f"test-{uuid.uuid4()}",
        topic=topic,
        enable_partition_eof=True,
    )
    try:
        messages = _collect_until_eof(consumer)
    finally:
        consumer.close()
    assert messages == []


def test_publish_scenario_curves_rejects_unrepresentable_value_decimal_and_produces_nothing(
    kafka_stack: KafkaStack,
) -> None:
    topic = _unique_topic()
    producer = MarketCurveProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topic,
    )
    scenario_id = f"contract-{uuid.uuid4()}"
    curves = [
        _curve(scenario_id=scenario_id, kind=CurveKind.VOLATILITY, curve_id="AAPL", value_float=0.25),
        # Invalid: 9 fractional digits, one more than decimal(38,8) allows.
        _curve(
            scenario_id=scenario_id,
            kind=CurveKind.FX_RATE,
            curve_id="EURUSD",
            value_decimal=Decimal("1.123456789"),
        ),
    ]
    with pytest.raises(InvalidMarketCurveError):
        producer.publish_scenario_curves(curves)

    # The batch rule requires validation before any produce -- the only
    # evidence for "nothing was produced" is that consuming the topic to
    # its end yields no records at all.
    consumer = make_market_curve_consumer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        group_id=f"test-{uuid.uuid4()}",
        topic=topic,
        enable_partition_eof=True,
    )
    try:
        messages = _collect_until_eof(consumer)
    finally:
        consumer.close()
    assert messages == []


def test_constructing_producer_against_delete_policy_topic_raises(kafka_stack: KafkaStack) -> None:
    topic = _unique_topic()
    admin = AdminClient({"bootstrap.servers": kafka_stack.bootstrap_servers})
    new_topic = NewTopic(
        topic, num_partitions=1, replication_factor=1, config={"cleanup.policy": "delete"}
    )
    admin.create_topics([new_topic])[topic].result()

    with pytest.raises(TopicConfigurationError):
        MarketCurveProducer(
            bootstrap_servers=kafka_stack.bootstrap_servers,
            schema_registry_url=kafka_stack.schema_registry_url,
            topic=topic,
        )
