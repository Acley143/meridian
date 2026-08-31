"""Realtime and replay pacing must produce identical data, differing only
in wall-clock timing (docs/conventions.md). If switching modes changes the
data, the mode is a bug."""
import dataclasses
import uuid
from datetime import timedelta
from pathlib import Path

from ingest.feed import PacingMode, run_feed
from ingest.scenario import load_scenario
from kafka_helpers import TopicTickProducer, consume_all, strip_ingest_time

_SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "small-deterministic.yaml"


def _run(scenario, kafka_stack, pacing: PacingMode) -> list:
    topic = f"test.pace.{uuid.uuid4()}"
    producer = TopicTickProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topic,
    )
    run_feed(scenario, producer, pacing)
    expected_count = scenario.tick_count * len(scenario.instruments)
    return consume_all(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=topic,
        expected_count=expected_count,
    )


def test_realtime_and_replay_pacing_produce_identical_data(kafka_stack) -> None:
    base = load_scenario(_SCENARIO_PATH)
    # A tiny interval keeps the realtime run's real wall-clock time short
    # without changing anything about what's being asserted: pacing must
    # not alter the data at any interval.
    scenario = dataclasses.replace(base, tick_interval=timedelta(seconds=0.01))

    realtime_records = _run(scenario, kafka_stack, PacingMode.REALTIME)
    replay_records = _run(scenario, kafka_stack, PacingMode.REPLAY)

    assert strip_ingest_time(realtime_records) == strip_ingest_time(replay_records)
