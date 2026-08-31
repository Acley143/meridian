"""GENERATED -- DO NOT EDIT.

Source: contracts/avro/tick.avsc
Regenerate via `make gen` (tools/codegen/generate.py). A hand-edit here
is silently overwritten on the next regeneration and will be flagged by
the CI drift check before that (contracts/README.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

SCHEMA_JSON = "{\n  \"type\": \"record\",\n  \"name\": \"Tick\",\n  \"namespace\": \"com.meridian.contracts\",\n  \"doc\": \"A single market data observation for an instrument. See docs/domain-model.md#tick.\",\n  \"fields\": [\n    {\n      \"name\": \"instrument_id\",\n      \"type\": \"string\",\n      \"doc\": \"Instrument this observation is for.\"\n    },\n    {\n      \"name\": \"price\",\n      \"type\": {\n        \"type\": \"bytes\",\n        \"logicalType\": \"decimal\",\n        \"precision\": 38,\n        \"scale\": 8\n      },\n      \"doc\": \"Last-traded or mid price in `currency`. Decimal (precision 38, scale 8) per ADR-0004/ADR-0013.\"\n    },\n    {\n      \"name\": \"currency\",\n      \"type\": \"string\",\n      \"doc\": \"ISO 4217 currency price is quoted in.\"\n    },\n    {\n      \"name\": \"event_time\",\n      \"type\": {\n        \"type\": \"long\",\n        \"logicalType\": \"timestamp-micros\"\n      },\n      \"doc\": \"UTC instant the tick was generated at the source. Per ADR-0005.\"\n    },\n    {\n      \"name\": \"ingest_time\",\n      \"type\": {\n        \"type\": \"long\",\n        \"logicalType\": \"timestamp-micros\"\n      },\n      \"doc\": \"UTC instant Meridian's ingest stage received this tick. Per ADR-0005.\"\n    },\n    {\n      \"name\": \"scenario_id\",\n      \"type\": \"string\",\n      \"default\": \"\",\n      \"doc\": \"Identifies the seeded simulated market scenario this tick belongs to (ADR-0011, ADR-0006) -- the same scenario_id reproduces a byte-identical tick stream. Added after this schema's first version; empty string is the BACKWARD-compatible default for a producer that predates ADR-0011. Propagated through to RiskSnapshot.scenario_id for end-to-end lineage.\"\n    }\n  ]\n}"
"""The exact source .avsc text, embedded so callers need no filesystem
path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""


@dataclass(frozen=True)
class Tick:
    """A single market data observation for an instrument. See docs/domain-model.md#tick."""

    instrument_id: str
    price: Decimal
    currency: str
    event_time: datetime
    ingest_time: datetime
    scenario_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "price": self.price,
            "currency": self.currency,
            "event_time": self.event_time,
            "ingest_time": self.ingest_time,
            "scenario_id": self.scenario_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Tick:
        return cls(
            instrument_id=d["instrument_id"],
            price=d["price"],
            currency=d["currency"],
            event_time=d["event_time"],
            ingest_time=d["ingest_time"],
            scenario_id=d["scenario_id"],
        )

