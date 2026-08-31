"""The point of the session: replaying a scenario_id twice must produce
byte-identical ticks (docs/conventions.md's event-time invariant), and
changing the seed must diverge -- otherwise a bug that ignores the seed
would pass the first assertion trivially."""
import dataclasses
import uuid
from pathlib import Path

from ingest.feed import PacingMode, run_feed
from ingest.scenario import load_scenario
from kafka_helpers import TopicTickProducer, consume_all, strip_ingest_time

_SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenarios" / "small-deterministic.yaml"


def _run(scenario, kafka_stack, *, pacing: PacingMode = PacingMode.REPLAY) -> list:
    topic = f"test.repro.{uuid.uuid4()}"
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


def test_same_scenario_run_twice_is_byte_identical_except_ingest_time(kafka_stack) -> None:
    scenario = load_scenario(_SCENARIO_PATH)

    records_a = _run(scenario, kafka_stack)
    records_b = _run(scenario, kafka_stack)

    assert strip_ingest_time(records_a) == strip_ingest_time(records_b)

    ingest_times_a = sorted(v.ingest_time for _, v in records_a)
    ingest_times_b = sorted(v.ingest_time for _, v in records_b)
    assert ingest_times_a != ingest_times_b, (
        "ingest_time was identical across two separate runs -- either the "
        "runs happened in the same microsecond (unlikely) or ingest_time is "
        "not actually being stamped freshly per run"
    )


def test_different_seed_diverges(kafka_stack) -> None:
    scenario = load_scenario(_SCENARIO_PATH)
    diverged = dataclasses.replace(scenario, seed=scenario.seed + 1)

    records_base = _run(scenario, kafka_stack)
    records_diverged = _run(diverged, kafka_stack)

    prices_base = [value.price for _, value in strip_ingest_time(records_base)]
    prices_diverged = [value.price for _, value in strip_ingest_time(records_diverged)]
    assert prices_base != prices_diverged
