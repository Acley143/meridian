"""Compacted-topic provisioning (ADR-0027 Decision 10): the sole producer of
a compacted topic owns that topic's configuration. It creates the topic if
absent, and if the topic already exists it verifies -- rather than assumes
-- that the existing configuration matches what this module would have
created, refusing to start otherwise rather than silently altering the
topic underneath whatever else might already be consuming it.

Mirrors `services/core-service/.../kafka/CompactedTopicInitializer.java`,
the same convention `portfolio.state` and `reference.instruments` already
follow on the Java side; this module is `market.curves`' equivalent on the
Python side.
"""
from __future__ import annotations

from confluent_kafka import KafkaError, KafkaException
from confluent_kafka.admin import AdminClient, ConfigResource, NewTopic

_CLEANUP_POLICY_CONFIG = "cleanup.policy"
_EXPECTED_CLEANUP_POLICY = "compact"
_EXPECTED_PARTITION_COUNT = 1
_REPLICATION_FACTOR = 1


class TopicConfigurationError(Exception):
    """An existing topic's configuration does not match what this module
    would have created, or the topic could not be created or verified."""


def ensure_compacted_topic(bootstrap_servers: str, topic: str, *, timeout: float = 30.0) -> None:
    """Create `topic` as a single-partition, `cleanup.policy=compact` topic
    if it does not exist. If it already exists, verify its `cleanup.policy`
    and partition count match, raising `TopicConfigurationError` on a
    mismatch. Never alters an existing topic."""
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    try:
        new_topic = NewTopic(
            topic,
            num_partitions=_EXPECTED_PARTITION_COUNT,
            replication_factor=_REPLICATION_FACTOR,
            config={_CLEANUP_POLICY_CONFIG: _EXPECTED_CLEANUP_POLICY},
        )
        futures = admin.create_topics([new_topic], request_timeout=timeout)
        futures[topic].result()
        return
    except KafkaException as exc:
        error = exc.args[0]
        if error.code() != KafkaError.TOPIC_ALREADY_EXISTS:
            raise TopicConfigurationError(
                f"failed to ensure compacted topic {topic}: {exc}"
            ) from exc
    except TopicConfigurationError:
        raise
    except Exception as exc:
        raise TopicConfigurationError(f"failed to ensure compacted topic {topic}: {exc}") from exc

    # Topic already exists -- verify rather than assume, and never alter it.
    try:
        resource = ConfigResource(ConfigResource.Type.TOPIC, topic)
        configs = admin.describe_configs([resource], request_timeout=timeout)[resource].result()
        cleanup_policy = configs[_CLEANUP_POLICY_CONFIG].value
        if cleanup_policy != _EXPECTED_CLEANUP_POLICY:
            raise TopicConfigurationError(
                f"existing topic {topic} has cleanup.policy={cleanup_policy}, "
                f"expected {_EXPECTED_CLEANUP_POLICY}"
            )

        metadata = admin.list_topics(topic=topic, timeout=timeout)
        partition_count = len(metadata.topics[topic].partitions)
        if partition_count != _EXPECTED_PARTITION_COUNT:
            raise TopicConfigurationError(
                f"existing topic {topic} has {partition_count} partition(s), "
                f"expected {_EXPECTED_PARTITION_COUNT}"
            )
    except TopicConfigurationError:
        raise
    except Exception as exc:
        raise TopicConfigurationError(f"failed to ensure compacted topic {topic}: {exc}") from exc
