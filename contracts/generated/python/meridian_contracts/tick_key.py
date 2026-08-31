"""GENERATED -- DO NOT EDIT.

Source: contracts/avro/tick-key.avsc
Regenerate via `make gen` (tools/codegen/generate.py). A hand-edit here
is silently overwritten on the next regeneration and will be flagged by
the CI drift check before that (contracts/README.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_JSON = "{\n  \"type\": \"record\",\n  \"name\": \"TickKey\",\n  \"namespace\": \"com.meridian.contracts\",\n  \"doc\": \"Kafka message key for the market.ticks topic. Keyed by instrument_id so all ticks for one instrument land on the same partition, in order.\",\n  \"fields\": [\n    {\n      \"name\": \"instrument_id\",\n      \"type\": \"string\",\n      \"doc\": \"Instrument this tick observation is for. Matches Tick.instrument_id.\"\n    }\n  ]\n}"
"""The exact source .avsc text, embedded so callers need no filesystem
path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""


@dataclass(frozen=True)
class TickKey:
    """Kafka message key for the market.ticks topic. Keyed by instrument_id so all ticks for one instrument land on the same partition, in order."""

    instrument_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TickKey:
        return cls(
            instrument_id=d["instrument_id"],
        )

