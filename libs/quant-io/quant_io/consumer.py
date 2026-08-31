"""Avro-deserializing Kafka consumer wrapper, the read side of `producer.py`.

Deserializes through the generated `contracts/` bindings only, same
boundary rule as the producer side.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from confluent_kafka import DeserializingConsumer, KafkaError, Message
from confluent_kafka.error import ConsumeError
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer

_DEFAULT_POLL_TIMEOUT_SECONDS = 5.0


class AvroConsumer:
    """A single-topic Avro consumer. `value_from_dict` is one of the
    generated bindings' `from_dict` classmethods (e.g. `Tick.from_dict`)."""

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        schema_registry_url: str,
        topic: str,
        group_id: str,
        value_schema_str: str,
        value_from_dict: Callable[[dict[str, Any]], Any],
        key_schema_str: str,
        key_from_dict: Callable[[dict[str, Any]], Any],
        auto_offset_reset: str = "earliest",
    ) -> None:
        registry_client = SchemaRegistryClient({"url": schema_registry_url})
        value_deserializer = AvroDeserializer(
            registry_client, value_schema_str, lambda d, ctx: value_from_dict(d)
        )
        key_deserializer = AvroDeserializer(
            registry_client, key_schema_str, lambda d, ctx: key_from_dict(d)
        )

        self._consumer = DeserializingConsumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "key.deserializer": key_deserializer,
                "value.deserializer": value_deserializer,
                "group.id": group_id,
                "auto.offset.reset": auto_offset_reset,
            }
        )
        self._consumer.subscribe([topic])

    def poll(self, timeout: float = _DEFAULT_POLL_TIMEOUT_SECONDS) -> Message | None:
        try:
            return self._consumer.poll(timeout)
        except ConsumeError as exc:
            if exc.args[0].code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                # The topic hasn't been created yet (e.g. nothing has ever
                # been successfully produced to it) -- not a consumer
                # error, just "no messages yet".
                return None
            raise

    def close(self) -> None:
        self._consumer.close()
