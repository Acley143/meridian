"""GENERATED -- DO NOT EDIT.

Source: contracts/avro/risk-snapshot-key.avsc
Regenerate via `make gen` (tools/codegen/generate.py). A hand-edit here
is silently overwritten on the next regeneration and will be flagged by
the CI drift check before that (contracts/README.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_JSON = "{\n  \"type\": \"record\",\n  \"name\": \"RiskSnapshotKey\",\n  \"namespace\": \"com.meridian.contracts\",\n  \"doc\": \"Kafka message key for the risk.snapshots topic. Keyed by portfolio_id for partition affinity -- the full ADR-0007 identity tuple (portfolio_id, as_of, pricer_version) governs storage-level idempotency, but the key only needs to keep one portfolio's snapshots ordered on one partition.\",\n  \"fields\": [\n    {\n      \"name\": \"portfolio_id\",\n      \"type\": \"string\",\n      \"doc\": \"Portfolio this risk snapshot is for. Matches RiskSnapshot.portfolio_id.\"\n    }\n  ]\n}"
"""The exact source .avsc text, embedded so callers need no filesystem
path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""


@dataclass(frozen=True)
class RiskSnapshotKey:
    """Kafka message key for the risk.snapshots topic. Keyed by portfolio_id for partition affinity -- the full ADR-0007 identity tuple (portfolio_id, as_of, pricer_version) governs storage-level idempotency, but the key only needs to keep one portfolio's snapshots ordered on one partition."""

    portfolio_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RiskSnapshotKey:
        return cls(
            portfolio_id=d["portfolio_id"],
        )

