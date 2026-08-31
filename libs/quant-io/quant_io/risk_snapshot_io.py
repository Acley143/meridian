"""The `risk.snapshots` producer/consumer (ADR-0016: keyed by
`portfolio_id`).

`services/pricer` is this producer's real caller; the consumer factory
exists for tests (and any future SSE-forwarding consumer in
`services/core-service`) to read back what the pricer produced.
"""
from __future__ import annotations

from meridian_contracts import risk_snapshot as risk_snapshot_schema
from meridian_contracts import risk_snapshot_key as risk_snapshot_key_schema
from meridian_contracts.risk_snapshot import RiskSnapshot
from meridian_contracts.risk_snapshot_key import RiskSnapshotKey

from quant_io.consumer import AvroConsumer
from quant_io.producer import AvroProducer

RISK_SNAPSHOTS_TOPIC = "risk.snapshots"


class RiskSnapshotProducer:
    """Produces `RiskSnapshot` messages to `risk.snapshots`, keyed by
    `portfolio_id`. Duplicates under at-least-once redelivery are expected
    and safe -- ADR-0007's identity tuple makes the downstream write an
    idempotent upsert; this producer does not itself deduplicate."""

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        schema_registry_url: str,
        topic: str = RISK_SNAPSHOTS_TOPIC,
        max_queue_size: int = 10_000,
    ) -> None:
        self._producer = AvroProducer(
            bootstrap_servers=bootstrap_servers,
            schema_registry_url=schema_registry_url,
            topic=topic,
            value_schema_str=risk_snapshot_schema.SCHEMA_JSON,
            value_to_dict=RiskSnapshot.to_dict,
            key_schema_str=risk_snapshot_key_schema.SCHEMA_JSON,
            key_to_dict=RiskSnapshotKey.to_dict,
            max_queue_size=max_queue_size,
        )

    def produce_snapshot(self, snapshot: RiskSnapshot) -> None:
        self._producer.produce(
            key=RiskSnapshotKey(portfolio_id=snapshot.portfolio_id), value=snapshot
        )

    def flush(self, timeout: float = 30.0) -> int:
        return self._producer.flush(timeout)


def make_risk_snapshot_consumer(
    *,
    bootstrap_servers: str,
    schema_registry_url: str,
    group_id: str,
    topic: str = RISK_SNAPSHOTS_TOPIC,
) -> AvroConsumer:
    return AvroConsumer(
        bootstrap_servers=bootstrap_servers,
        schema_registry_url=schema_registry_url,
        topic=topic,
        group_id=group_id,
        value_schema_str=risk_snapshot_schema.SCHEMA_JSON,
        value_from_dict=RiskSnapshot.from_dict,
        key_schema_str=risk_snapshot_key_schema.SCHEMA_JSON,
        key_from_dict=RiskSnapshotKey.from_dict,
    )
