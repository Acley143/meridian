"""GENERATED -- DO NOT EDIT.

Source: contracts/avro/portfolio-state-key.avsc
Regenerate via `make gen` (tools/codegen/generate.py). A hand-edit here
is silently overwritten on the next regeneration and will be flagged by
the CI drift check before that (contracts/README.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_JSON = "{\n  \"type\": \"record\",\n  \"name\": \"PortfolioStateKey\",\n  \"namespace\": \"com.meridian.contracts\",\n  \"doc\": \"Kafka message key for the log-compacted portfolio.state topic (ADR-0003). Keyed by portfolio_id, which is also what makes log compaction correct (one live record per key). A null VALUE for this key is a tombstone meaning portfolio deletion -- see portfolio-state.avsc's doc for the full convention.\",\n  \"fields\": [\n    {\n      \"name\": \"portfolio_id\",\n      \"type\": \"string\",\n      \"doc\": \"Portfolio this state belongs to. Matches PortfolioState.portfolio_id.\"\n    }\n  ]\n}"
"""The exact source .avsc text, embedded so callers need no filesystem
path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""


@dataclass(frozen=True)
class PortfolioStateKey:
    """Kafka message key for the log-compacted portfolio.state topic (ADR-0003). Keyed by portfolio_id, which is also what makes log compaction correct (one live record per key). A null VALUE for this key is a tombstone meaning portfolio deletion -- see portfolio-state.avsc's doc for the full convention."""

    portfolio_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PortfolioStateKey:
        return cls(
            portfolio_id=d["portfolio_id"],
        )

