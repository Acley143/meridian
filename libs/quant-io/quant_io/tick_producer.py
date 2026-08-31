"""The `market.ticks` producer (ADR-0016: keyed by `instrument_id`).

Thin factory over `AvroProducer` so `services/ingest` never has to know the
topic name, key schema, or value schema directly — it only calls
`produce_tick`.
"""
from __future__ import annotations

from meridian_contracts import tick as tick_schema
from meridian_contracts import tick_key as tick_key_schema
from meridian_contracts.tick import Tick
from meridian_contracts.tick_key import TickKey

from quant_io.consumer import AvroConsumer
from quant_io.producer import AvroProducer

MARKET_TICKS_TOPIC = "market.ticks"


class TickProducer:
    """Produces `Tick` messages to `market.ticks`, keyed by `instrument_id`."""

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        schema_registry_url: str,
        topic: str = MARKET_TICKS_TOPIC,
        max_queue_size: int = 10_000,
    ) -> None:
        self._producer = AvroProducer(
            bootstrap_servers=bootstrap_servers,
            schema_registry_url=schema_registry_url,
            topic=topic,
            value_schema_str=tick_schema.SCHEMA_JSON,
            value_to_dict=Tick.to_dict,
            key_schema_str=tick_key_schema.SCHEMA_JSON,
            key_to_dict=TickKey.to_dict,
            max_queue_size=max_queue_size,
        )

    def produce_tick(self, tick: Tick) -> None:
        self._producer.produce(key=TickKey(instrument_id=tick.instrument_id), value=tick)

    def flush(self, timeout: float = 30.0) -> int:
        return self._producer.flush(timeout)


def make_tick_consumer(
    *,
    bootstrap_servers: str,
    schema_registry_url: str,
    group_id: str,
    topic: str = MARKET_TICKS_TOPIC,
) -> AvroConsumer:
    """A consumer of `market.ticks`, for tests and any future downstream
    reader that wants the generic wrapper rather than a service of its own."""
    return AvroConsumer(
        bootstrap_servers=bootstrap_servers,
        schema_registry_url=schema_registry_url,
        topic=topic,
        group_id=group_id,
        value_schema_str=tick_schema.SCHEMA_JSON,
        value_from_dict=Tick.from_dict,
        key_schema_str=tick_key_schema.SCHEMA_JSON,
        key_from_dict=TickKey.from_dict,
    )
