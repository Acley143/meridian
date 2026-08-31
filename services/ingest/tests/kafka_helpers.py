"""Test-only helpers: a `Tick` producer/consumer pair pointed at an
ephemeral per-test topic, so reproducibility/ordering/pacing tests never
share state with each other or with the real `market.ticks` topic (that
topic's own contract is covered by `libs/quant-io`'s contract tests).
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Iterable
from typing import Any

from meridian_contracts import tick as tick_schema
from meridian_contracts import tick_key as tick_key_schema
from meridian_contracts.tick import Tick
from meridian_contracts.tick_key import TickKey
from quant_io.consumer import AvroConsumer
from quant_io.producer import AvroProducer


class TopicTickProducer:
    """Same wiring as `quant_io.tick_producer.TickProducer`, targeting an
    arbitrary topic instead of the hardcoded `market.ticks`."""

    def __init__(self, *, bootstrap_servers: str, schema_registry_url: str, topic: str) -> None:
        self._producer = AvroProducer(
            bootstrap_servers=bootstrap_servers,
            schema_registry_url=schema_registry_url,
            topic=topic,
            value_schema_str=tick_schema.SCHEMA_JSON,
            value_to_dict=Tick.to_dict,
            key_schema_str=tick_key_schema.SCHEMA_JSON,
            key_to_dict=TickKey.to_dict,
        )

    def produce_tick(self, tick: Tick) -> None:
        self._producer.produce(key=TickKey(instrument_id=tick.instrument_id), value=tick)

    def flush(self, timeout: float = 30.0) -> int:
        return self._producer.flush(timeout)


def consume_all(
    *,
    bootstrap_servers: str,
    schema_registry_url: str,
    topic: str,
    expected_count: int,
    timeout: float = 30.0,
) -> list[tuple[TickKey, Tick]]:
    consumer = AvroConsumer(
        bootstrap_servers=bootstrap_servers,
        schema_registry_url=schema_registry_url,
        topic=topic,
        group_id=f"test-{uuid.uuid4()}",
        value_schema_str=tick_schema.SCHEMA_JSON,
        value_from_dict=Tick.from_dict,
        key_schema_str=tick_key_schema.SCHEMA_JSON,
        key_from_dict=TickKey.from_dict,
        auto_offset_reset="earliest",
    )
    records: list[tuple[TickKey, Tick]] = []
    deadline = time.monotonic() + timeout
    try:
        while len(records) < expected_count and time.monotonic() < deadline:
            msg = consumer.poll(1.0)
            if msg is not None:
                records.append((msg.key(), msg.value()))
    finally:
        consumer.close()
    return records


def strip_ingest_time(records: Iterable[tuple[TickKey, Tick]]) -> list[tuple[str, Any]]:
    """Sort key+value pairs by (instrument, event_time) and drop
    `ingest_time`, leaving exactly what docs/conventions.md says must be
    reproducible across runs/pacing modes."""
    from dataclasses import replace

    normalized = [(key.instrument_id, replace(value, ingest_time=None)) for key, value in records]
    return sorted(normalized, key=lambda pair: (pair[0], pair[1].event_time))
