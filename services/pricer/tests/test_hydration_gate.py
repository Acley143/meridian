"""The hydration gate's assignment handling, without a broker.

`PricerService._hydrate_to_end` must read every assigned partition to its
end before hydration counts as complete. An empty assignment assigns
nothing, so it cannot satisfy that: hydration keeps waiting for partitions,
and times out as "no partitions were assigned" if none ever arrive.

A scripted fake consumer drives `on_assign` at chosen points. Constructing
`PricerService` does not need a reachable broker (its producer connects in
the background), and `_hydrate_to_end` takes the consumer factory and the
message handler as arguments, so no Kafka is involved.
"""
from __future__ import annotations

import logging

import pytest
from confluent_kafka import TopicPartition
from pricer.reference_data import ReferenceData
from pricer.service import PricerService
from quant_io.consumer import PartitionEOF

TOPIC = "test.hydration.gate"

_NO_ASSIGN = object()


class ScriptedConsumer:
    """Each `poll()` takes the next scripted step: optionally invoke the
    stored `on_assign` with a partition list, then return a value. Once the
    script runs out, every `poll()` returns `None`."""

    def __init__(self, on_assign, script: list[tuple[object, object]]) -> None:
        self._on_assign = on_assign
        self._script = list(script)
        self.polls = 0
        self.steps_consumed = 0

    def poll(self, timeout: float = 1.0) -> object:
        self.polls += 1
        if not self._script:
            return None
        assignment, result = self._script.pop(0)
        self.steps_consumed += 1
        if assignment is not _NO_ASSIGN:
            self._on_assign(self, assignment)
        return result

    def close(self) -> None:
        pass


@pytest.fixture
def service() -> PricerService:
    return PricerService(
        bootstrap_servers="127.0.0.1:1",
        schema_registry_url="http://127.0.0.1:1",
        reference_data=ReferenceData({}),
        tick_group_id="test-hydration-gate",
    )


def _hydrate(service: PricerService, script, timeout: float = 5.0):
    applied: list[object] = []
    holder: dict[str, ScriptedConsumer] = {}

    def make_consumer(on_assign):
        holder["consumer"] = ScriptedConsumer(on_assign, script)
        return holder["consumer"]

    service._hydrate_to_end(
        topic_name=TOPIC,
        timeout=timeout,
        make_consumer=make_consumer,
        apply_message=applied.append,
    )
    return applied, holder["consumer"]


def test_h1_empty_then_real_assignment_reads_the_partition_to_its_end(service, caplog) -> None:
    record = object()
    script = [
        ([], None),
        (_NO_ASSIGN, None),
        ([TopicPartition(TOPIC, 0)], record),
        (_NO_ASSIGN, PartitionEOF(topic=TOPIC, partition=0)),
    ]
    with caplog.at_level(logging.WARNING, logger="pricer"):
        applied, consumer = _hydrate(service, script)

    assert applied == [record], "the record after the real assignment must be applied"
    assert consumer.steps_consumed == 4, (
        f"the loop must poll through to the EOF, not exit after the empty "
        f"assignment (consumed {consumer.steps_consumed} of 4 scripted steps)"
    )
    warnings = [r for r in caplog.records if getattr(r, "event", None) == "hydration_empty_assignment"]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    assert warnings[0].topic == TOPIC


def test_h2_only_empty_assignment_times_out_as_unassigned(service) -> None:
    script = [([], None)]
    with pytest.raises(TimeoutError) as exc_info:
        _hydrate(service, script, timeout=0.5)

    message = str(exc_info.value)
    assert TOPIC in message
    assert "no partitions were assigned" in message


def test_h3_normal_assignment_reads_to_eof_and_returns(service) -> None:
    record = object()
    script = [
        ([TopicPartition(TOPIC, 0)], record),
        (_NO_ASSIGN, PartitionEOF(topic=TOPIC, partition=0)),
    ]
    applied, consumer = _hydrate(service, script)

    assert applied == [record]
    assert consumer.steps_consumed == 2
