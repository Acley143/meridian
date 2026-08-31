"""Avro-serializing Kafka producer wrapper (ADR-0002, ADR-0016).

Wraps `confluent_kafka`'s `SerializingProducer` with:

- Avro serialization through the generated `contracts/` bindings only
  (`Tick.to_dict()` / `Tick.SCHEMA_JSON`) — no hand-rolled bytes conversion
  for the `Decimal`/`timestamp-micros` logical types anywhere in this
  module. `AvroSerializer` (via `fastavro`) does that conversion from the
  schema alone, which is the boundary ADR-0013 exists to keep singular.
- `enable.idempotence=true` + `acks=all` — the producer-side half of
  ADR-0007's at-least-once story: idempotence prevents a broker-side retry
  from duplicating a message, `acks=all` means a successful delivery
  callback means the message actually reached every in-sync replica.
- Explicit delivery callbacks on every `produce()` call. There is no
  fire-and-forget path: a delivery failure is recorded and raised on the
  next call into this producer (or on `flush()`), never swallowed.
- A bounded local queue (`queue.buffering.max.messages`). When it fills,
  `produce()` blocks by polling the producer (which drains the queue via
  delivery callbacks) rather than raising `BufferError` outward or letting
  the queue grow unbounded — an overwhelmed broker slows the feed instead
  of growing memory until the process dies.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from confluent_kafka import KafkaError, KafkaException, Message, SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer

_DEFAULT_MAX_QUEUE_SIZE = 10_000
_POLL_TIMEOUT_SECONDS = 0.1


class DeliveryError(Exception):
    """A produced message was not durably delivered."""


class AvroProducer:
    """A bounded, idempotent, Avro-serializing producer for one topic.

    `to_dict` is one of the generated `contracts/` binding's `to_dict`
    methods (e.g. `Tick.to_dict`); `schema_str` is the matching binding's
    `SCHEMA_JSON`. This class never constructs Avro bytes itself.
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        schema_registry_url: str,
        topic: str,
        value_schema_str: str,
        value_to_dict: Callable[[Any], dict[str, Any]],
        key_schema_str: str,
        key_to_dict: Callable[[Any], dict[str, Any]],
        max_queue_size: int = _DEFAULT_MAX_QUEUE_SIZE,
    ) -> None:
        self._topic = topic
        self._delivery_error: Exception | None = None

        registry_client = SchemaRegistryClient({"url": schema_registry_url})
        value_serializer = AvroSerializer(
            registry_client, value_schema_str, lambda obj, ctx: value_to_dict(obj)
        )
        key_serializer = AvroSerializer(
            registry_client, key_schema_str, lambda obj, ctx: key_to_dict(obj)
        )

        self._producer = SerializingProducer(
            {
                "bootstrap.servers": bootstrap_servers,
                "key.serializer": key_serializer,
                "value.serializer": value_serializer,
                "enable.idempotence": True,
                "acks": "all",
                "queue.buffering.max.messages": max_queue_size,
            }
        )

    def produce(self, *, key: Any, value: Any) -> None:
        """Produce one message, blocking on backpressure if the local queue
        is full, and raising `DeliveryError` if an earlier message in this
        producer's queue failed delivery."""
        self._raise_if_delivery_failed()
        while True:
            try:
                self._producer.produce(
                    topic=self._topic,
                    key=key,
                    value=value,
                    on_delivery=self._on_delivery,
                )
                break
            except BufferError:
                # Local queue is full (backpressure): drain delivery
                # callbacks to free space instead of growing the queue or
                # dropping the message.
                self._producer.poll(_POLL_TIMEOUT_SECONDS)
            except KafkaException as exc:
                # A rejection the client can detect before even queuing the
                # message (e.g. MSG_SIZE_TOO_LARGE) raises synchronously
                # here rather than via the delivery callback. Either path
                # must surface as the same DeliveryError to the caller.
                raise DeliveryError(f"Kafka delivery failed: {exc}") from exc
        self._producer.poll(0)
        self._raise_if_delivery_failed()

    def flush(self, timeout: float = 30.0) -> int:
        """Block until every produced message has a delivery result.
        Returns the number of messages still outstanding after `timeout`.
        Raises `DeliveryError` if any message failed delivery."""
        remaining: int = self._producer.flush(timeout)
        self._raise_if_delivery_failed()
        return remaining

    def _on_delivery(self, err: KafkaError | None, _msg: Message) -> None:
        if err is not None and self._delivery_error is None:
            self._delivery_error = DeliveryError(f"Kafka delivery failed: {err}")

    def _raise_if_delivery_failed(self) -> None:
        if self._delivery_error is not None:
            error, self._delivery_error = self._delivery_error, None
            raise error
