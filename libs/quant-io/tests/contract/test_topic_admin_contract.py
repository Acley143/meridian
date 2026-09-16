"""Contract tests for `quant_io.topic_admin.ensure_compacted_topic`, against
a real local Kafka broker (testcontainers), not a mock of one
(docs/test-strategy.md). Never touches `market.curves` itself -- each test
provisions its own uniquely-named topic."""
from __future__ import annotations

import uuid

import pytest
from confluent_kafka.admin import AdminClient, ConfigResource, NewTopic
from quant_io.topic_admin import TopicConfigurationError, ensure_compacted_topic

from conftest import KafkaStack


def _unique_topic() -> str:
    return f"topic-admin-contract-{uuid.uuid4()}"


def _admin(bootstrap_servers: str) -> AdminClient:
    return AdminClient({"bootstrap.servers": bootstrap_servers})


def _create_topic(admin: AdminClient, topic: str, *, cleanup_policy: str, num_partitions: int) -> None:
    new_topic = NewTopic(
        topic,
        num_partitions=num_partitions,
        replication_factor=1,
        config={"cleanup.policy": cleanup_policy},
    )
    futures = admin.create_topics([new_topic])
    futures[topic].result()


def test_absent_topic_is_created(kafka_stack: KafkaStack) -> None:
    topic = _unique_topic()
    ensure_compacted_topic(kafka_stack.bootstrap_servers, topic)

    admin = _admin(kafka_stack.bootstrap_servers)
    resource = ConfigResource(ConfigResource.Type.TOPIC, topic)
    configs = admin.describe_configs([resource])[resource].result()
    assert configs["cleanup.policy"].value == "compact"

    metadata = admin.list_topics(topic=topic, timeout=10)
    assert len(metadata.topics[topic].partitions) == 1


def test_pre_existing_delete_policy_topic_raises(kafka_stack: KafkaStack) -> None:
    topic = _unique_topic()
    admin = _admin(kafka_stack.bootstrap_servers)
    _create_topic(admin, topic, cleanup_policy="delete", num_partitions=1)

    with pytest.raises(TopicConfigurationError) as excinfo:
        ensure_compacted_topic(kafka_stack.bootstrap_servers, topic)

    message = str(excinfo.value)
    assert "has cleanup.policy=delete, expected compact" in message
    assert "failed to ensure" not in message


def test_pre_existing_compact_two_partitions_raises(kafka_stack: KafkaStack) -> None:
    topic = _unique_topic()
    admin = _admin(kafka_stack.bootstrap_servers)
    _create_topic(admin, topic, cleanup_policy="compact", num_partitions=2)

    with pytest.raises(TopicConfigurationError) as excinfo:
        ensure_compacted_topic(kafka_stack.bootstrap_servers, topic)

    message = str(excinfo.value)
    assert "has 2 partition(s), expected 1" in message
    assert "failed to ensure" not in message


def test_pre_existing_compact_delete_policy_raises(kafka_stack: KafkaStack) -> None:
    topic = _unique_topic()
    admin = _admin(kafka_stack.bootstrap_servers)
    _create_topic(admin, topic, cleanup_policy="compact,delete", num_partitions=1)

    with pytest.raises(TopicConfigurationError) as excinfo:
        ensure_compacted_topic(kafka_stack.bootstrap_servers, topic)

    assert "has cleanup.policy=compact,delete, expected compact" in str(excinfo.value)


def test_matching_topic_two_calls_both_return_normally(kafka_stack: KafkaStack) -> None:
    topic = _unique_topic()
    ensure_compacted_topic(kafka_stack.bootstrap_servers, topic)
    ensure_compacted_topic(kafka_stack.bootstrap_servers, topic)
