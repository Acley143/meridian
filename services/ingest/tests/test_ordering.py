"""All ticks for one instrument arrive in event-time order (ADR-0016:
`market.ticks` is keyed by `instrument_id` precisely so a single-partition
consumer never sees a stale price after a fresher one for the same
instrument)."""
import uuid
from collections import defaultdict
from pathlib import Path

from ingest.feed import PacingMode, run_feed
from ingest.scenario import load_scenario
from kafka_helpers import TopicTickProducer, consume_all

_SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "small-deterministic.yaml"


def test_ticks_for_one_instrument_are_totally_ordered_by_event_time(kafka_stack) -> None:
    scenario = load_scenario(_SCENARIO_PATH)
    topic = f"test.order.{uuid.uuid4()}"
    producer = TopicTickProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topic,
    )
    run_feed(scenario, producer, PacingMode.REPLAY)

    expected_count = scenario.tick_count * len(scenario.instruments)
    records = consume_all(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topic,
        expected_count=expected_count,
    )

    event_times_by_instrument: dict[str, list] = defaultdict(list)
    for key, value in records:
        event_times_by_instrument[key.instrument_id].append(value.event_time)

    assert set(event_times_by_instrument) == set(scenario.instruments)
    for instrument_id, event_times in event_times_by_instrument.items():
        assert event_times == sorted(event_times), (
            f"{instrument_id}: ticks arrived out of event-time order: {event_times}"
        )
        assert len(event_times) == scenario.tick_count
