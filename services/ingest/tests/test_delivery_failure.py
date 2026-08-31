"""A dropped tick is a permanent gap in risk history (Task 3 rationale) --
ingest must surface a delivery failure, never continue past it silently.

The broker rejection is forced deterministically: a `scenario_id` large
enough that the serialized `Tick` exceeds the broker's `message.max.bytes`,
so the very first `produce()` call fails with `MSG_SIZE_TOO_LARGE`
(verified directly against a real broker; see
`libs/quant-io/quant_io/producer.py`'s handling of `KafkaException`)."""
import dataclasses
import uuid
from pathlib import Path

import pytest
from ingest.feed import PacingMode, run_feed
from ingest.scenario import load_scenario
from kafka_helpers import TopicTickProducer, consume_all
from quant_io.producer import DeliveryError

_SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "small-deterministic.yaml"
_OVERSIZED_SCENARIO_ID = "oversized-" + ("x" * (2 * 1024 * 1024))


def test_delivery_failure_surfaces_and_does_not_continue(kafka_stack) -> None:
    base = load_scenario(_SCENARIO_PATH)
    scenario = dataclasses.replace(base, scenario_id=_OVERSIZED_SCENARIO_ID, tick_count=5)
    topic = f"test.fail.{uuid.uuid4()}"
    producer = TopicTickProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topic,
    )

    with pytest.raises(DeliveryError):
        run_feed(scenario, producer, PacingMode.REPLAY)

    # Nothing should have been durably delivered -- the feed must stop at
    # the first failure, not keep producing the rest of the batch.
    delivered = consume_all(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topic,
        expected_count=1,
        timeout=3.0,
    )
    assert delivered == []
