"""Avro-deserializing Kafka consumer wrapper, the read side of `producer.py`.

Deserializes through the generated `contracts/` bindings only, same
boundary rule as the producer side.

Defaults to manual offset commits (`enable_auto_commit=False`, the
constructor default): auto-commit silently converts at-least-once delivery
into at-most-once — the offset advances whether or not the message was
ever durably acted on, so the one message that crashes the consuming
process is exactly the one that gets skipped on restart. Callers commit
explicitly via `commit()` once whatever the message triggered has actually
happened (Task 7 in `services/pricer`: commit a tick's offset only after
every snapshot it produced has been durably delivered).

A `None` value for a message (a Kafka tombstone, e.g. `portfolio.state`'s
deletion convention) deserializes to `None` automatically --
`AvroDeserializer` returns `None` for `None` input without ever calling
`value_from_dict`, so a tombstone is not a decode failure here and needs no
special-casing by callers beyond checking `msg.value() is None`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from confluent_kafka import DeserializingConsumer, KafkaError, Message
from confluent_kafka.error import ConsumeError
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer

_DEFAULT_POLL_TIMEOUT_SECONDS = 5.0

OnAssign = Callable[[Any, list[Any]], None]


@dataclass(frozen=True)
class PartitionEOF:
    """This partition's fetch position has caught up to the high watermark
    it had when this consumer was assigned it -- "read to the end" for
    hydration gates (e.g. `services/pricer`'s `portfolio.state` view).
    Requires `enable_partition_eof=True`; otherwise `poll()` never returns
    this and end-of-partition is indistinguishable from "no message yet"."""

    topic: str
    partition: int


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
        enable_auto_commit: bool = False,
        enable_partition_eof: bool = False,
        on_assign: OnAssign | None = None,
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
                "enable.auto.commit": enable_auto_commit,
                "enable.partition.eof": enable_partition_eof,
            }
        )
        if on_assign is not None:
            self._consumer.subscribe([topic], on_assign=on_assign)
        else:
            self._consumer.subscribe([topic])

    def poll(self, timeout: float = _DEFAULT_POLL_TIMEOUT_SECONDS) -> Message | PartitionEOF | None:
        try:
            msg = self._consumer.poll(timeout)
        except ConsumeError as exc:
            error = exc.args[0]
            if error.code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                # The topic hasn't been created yet (e.g. nothing has ever
                # been successfully produced to it) -- not a consumer
                # error, just "no messages yet".
                return None
            if error.code() == KafkaError._PARTITION_EOF:
                return PartitionEOF(topic=exc.kafka_message.topic(), partition=exc.kafka_message.partition())
            raise
        return msg

    def commit(self, message: Message) -> None:
        self._consumer.commit(message=message, asynchronous=False)

    def close(self) -> None:
        self._consumer.close()
