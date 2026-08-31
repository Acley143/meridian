"""GENERATED -- DO NOT EDIT.

Source: contracts/avro/reference-instruments-key.avsc
Regenerate via `make gen` (tools/codegen/generate.py). A hand-edit here
is silently overwritten on the next regeneration and will be flagged by
the CI drift check before that (contracts/README.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_JSON = "{\n  \"type\": \"record\",\n  \"name\": \"ReferenceInstrumentKey\",\n  \"namespace\": \"com.meridian.contracts\",\n  \"doc\": \"Kafka message key for the log-compacted reference.instruments topic (ADR-0019). Keyed by instrument_id, which is also the compaction identity -- one current record per instrument.\",\n  \"fields\": [\n    {\n      \"name\": \"instrument_id\",\n      \"type\": \"string\",\n      \"doc\": \"Instrument this reference record describes. Matches ReferenceInstrument.instrument_id.\"\n    }\n  ]\n}"
"""The exact source .avsc text, embedded so callers need no filesystem
path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""


@dataclass(frozen=True)
class ReferenceInstrumentKey:
    """Kafka message key for the log-compacted reference.instruments topic (ADR-0019). Keyed by instrument_id, which is also the compaction identity -- one current record per instrument."""

    instrument_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReferenceInstrumentKey:
        return cls(
            instrument_id=d["instrument_id"],
        )

