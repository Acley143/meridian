"""market.curves publishing (ADR-0027): a scenario's declared curves are
published once, as a batch, before that scenario's first tick, and the tick
feed fails loudly -- never silently -- on any tick left undelivered after
`flush()`."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from ingest.feed import PacingMode, run_feed
from ingest.scenario import load_scenario
from kafka_helpers import TopicTickProducer, consume_all, consume_all_curves
from quant_io.market_curve_io import MarketCurveProducer
from quant_io.producer import DeliveryError

_SCENARIOS_DIR = Path(__file__).resolve().parents[1] / "scenarios"
_SMALL_DETERMINISTIC_V2 = _SCENARIOS_DIR / "small-deterministic-v2.yaml"
_SMALL_DETERMINISTIC = _SCENARIOS_DIR / "small-deterministic.yaml"


class _CountingStubTickProducer:
    """A tick producer that never touches Kafka -- records how many ticks
    it was asked to produce, so a test can assert `run_feed` stopped before
    producing anything."""

    def __init__(self) -> None:
        self.produce_tick_calls = 0

    def produce_tick(self, tick: object) -> None:
        self.produce_tick_calls += 1

    def flush(self, timeout: float = 30.0) -> int:
        return 0


class _UndeliveredStubTickProducer:
    """A tick producer whose `flush()` always reports one outstanding
    message, regardless of how many `produce_tick` calls it saw."""

    def produce_tick(self, tick: object) -> None:
        pass

    def flush(self, timeout: float = 30.0) -> int:
        return 1


def test_curves_are_published_before_ticks_and_ticks_are_delivered(kafka_stack) -> None:
    scenario = load_scenario(_SMALL_DETERMINISTIC_V2)
    ticks_topic = f"test.curves.ticks.{uuid.uuid4()}"
    curves_topic = f"test.curves.curves.{uuid.uuid4()}"

    tick_producer = TopicTickProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=ticks_topic,
    )
    curve_producer = MarketCurveProducer(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=curves_topic,
    )

    run_feed(scenario, tick_producer, PacingMode.REPLAY, curve_producer=curve_producer)

    curve_records = consume_all_curves(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=curves_topic,
        expected_count=len(scenario.curves),
    )
    assert len(curve_records) == len(scenario.curves)

    expected_curves = {
        (c.kind, c.curve_id): (c.value_float, c.value_decimal) for c in scenario.curves
    }
    for key, value in curve_records:
        assert value.scenario_id == scenario.scenario_id
        assert value.event_time == scenario.start_time
        assert (key.kind.value, key.curve_id) in expected_curves
        assert (value.value_float, value.value_decimal) == expected_curves[(key.kind.value, key.curve_id)]

    expected_tick_count = scenario.tick_count * len(scenario.instruments)
    tick_records = consume_all(
        bootstrap_servers=kafka_stack.bootstrap_servers,
        schema_registry_url=kafka_stack.schema_registry_url,
        topic=ticks_topic,
        expected_count=expected_tick_count,
    )
    assert len(tick_records) == expected_tick_count

    max_curve_ingest_time = max(value.ingest_time for _key, value in curve_records)
    min_tick_ingest_time = min(value.ingest_time for _key, value in tick_records)
    assert max_curve_ingest_time <= min_tick_ingest_time


def test_run_feed_raises_when_scenario_declares_curves_but_no_curve_producer_given() -> None:
    scenario = load_scenario(_SMALL_DETERMINISTIC_V2)
    stub = _CountingStubTickProducer()

    with pytest.raises(ValueError):
        run_feed(scenario, stub, PacingMode.REPLAY, curve_producer=None)

    assert stub.produce_tick_calls == 0


def test_run_feed_raises_delivery_error_when_ticks_are_left_undelivered() -> None:
    scenario = load_scenario(_SMALL_DETERMINISTIC)
    stub = _UndeliveredStubTickProducer()

    with pytest.raises(DeliveryError, match="1"):
        run_feed(scenario, stub, PacingMode.REPLAY)
