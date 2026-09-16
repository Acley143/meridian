"""GENERATED -- DO NOT EDIT.

Source: contracts/avro/market-curves.avsc
Regenerate via `make gen` (tools/codegen/generate.py). A hand-edit here
is silently overwritten on the next regeneration and will be flagged by
the CI drift check before that (contracts/README.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from decimal import Decimal
from typing import Any

SCHEMA_JSON = "{\n  \"type\": \"record\",\n  \"name\": \"MarketCurve\",\n  \"namespace\": \"com.meridian.contracts\",\n  \"doc\": \"One scalar market-data value for one scenario, published to the log-compacted market.curves topic (ADR-0027, supersedes ADR-0019's market.curves shape). Keyed by (scenario_id, kind, curve_id) -- see market-curves-key.avsc. Exactly one of value_float / value_decimal is non-null, determined by kind: RISK_FREE_RATE, VOLATILITY, and DIVIDEND_YIELD populate value_float (continuously compounded, annualised decimal fraction, per docs/conventions.md); FX_RATE populates value_decimal (units of TO per one unit of FROM, per curve_id's convention -- decimal because it multiplies cash amounts and ADR-0004 forbids floats touching cash). A record with any other combination of the two value fields is rejected in both directions, by the producer and by the consumer.\",\n  \"fields\": [\n    {\n      \"name\": \"scenario_id\",\n      \"type\": \"string\",\n      \"doc\": \"Identifies the seeded simulated market scenario this value belongs to (ADR-0011, ADR-0006). Required and non-empty -- must match MarketCurveKey.scenario_id.\"\n    },\n    {\n      \"name\": \"kind\",\n      \"type\": {\n        \"type\": \"enum\",\n        \"name\": \"CurveKind\",\n        \"symbols\": [\n          \"RISK_FREE_RATE\",\n          \"VOLATILITY\",\n          \"DIVIDEND_YIELD\",\n          \"FX_RATE\"\n        ]\n      },\n      \"doc\": \"Which market quantity this value carries. Determines the meaning of curve_id and which of value_float / value_decimal is populated. Must match MarketCurveKey.kind.\"\n    },\n    {\n      \"name\": \"curve_id\",\n      \"type\": \"string\",\n      \"doc\": \"Identifies the specific curve within (scenario_id, kind), per kind: RISK_FREE_RATE -- an ISO 4217 currency code; VOLATILITY and DIVIDEND_YIELD -- an underlying_id (docs/domain-model.md#instrument); FX_RATE -- six letters FROMTO (e.g. EURUSD), where the published value is units of TO per one unit of FROM. Must match MarketCurveKey.curve_id.\"\n    },\n    {\n      \"name\": \"value_float\",\n      \"type\": [\n        \"null\",\n        \"double\"\n      ],\n      \"default\": null,\n      \"doc\": \"The value, for kind RISK_FREE_RATE, VOLATILITY, or DIVIDEND_YIELD: a continuously compounded, annualised decimal fraction (0.05 for 5%, never 5), per docs/conventions.md. Null for kind FX_RATE, where value_decimal is used instead.\"\n    },\n    {\n      \"name\": \"value_decimal\",\n      \"type\": [\n        \"null\",\n        {\n          \"type\": \"bytes\",\n          \"logicalType\": \"decimal\",\n          \"precision\": 38,\n          \"scale\": 8\n        }\n      ],\n      \"default\": null,\n      \"doc\": \"The value, for kind FX_RATE only: units of TO per one unit of FROM, per curve_id's direction convention. Decimal (precision 38, scale 8) per ADR-0004/ADR-0013, since this value multiplies cash amounts. Null for kind RISK_FREE_RATE, VOLATILITY, or DIVIDEND_YIELD, where value_float is used instead.\"\n    },\n    {\n      \"name\": \"event_time\",\n      \"type\": {\n        \"type\": \"long\",\n        \"logicalType\": \"timestamp-micros\"\n      },\n      \"doc\": \"The scenario's start_time (scenario time, not wall clock) -- so a replay of the same scenario_id produces an identical event_time for this value. Per ADR-0005/ADR-0027.\"\n    },\n    {\n      \"name\": \"ingest_time\",\n      \"type\": {\n        \"type\": \"long\",\n        \"logicalType\": \"timestamp-micros\"\n      },\n      \"doc\": \"UTC instant the producer (services/ingest) published this value -- wall clock, per ADR-0005.\"\n    }\n  ]\n}"
"""The exact source .avsc text, embedded so callers need no filesystem
path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""


class CurveKind(str, Enum):
    RISK_FREE_RATE = "RISK_FREE_RATE"
    VOLATILITY = "VOLATILITY"
    DIVIDEND_YIELD = "DIVIDEND_YIELD"
    FX_RATE = "FX_RATE"


@dataclass(frozen=True)
class MarketCurve:
    """One scalar market-data value for one scenario, published to the log-compacted market.curves topic (ADR-0027, supersedes ADR-0019's market.curves shape). Keyed by (scenario_id, kind, curve_id) -- see market-curves-key.avsc. Exactly one of value_float / value_decimal is non-null, determined by kind: RISK_FREE_RATE, VOLATILITY, and DIVIDEND_YIELD populate value_float (continuously compounded, annualised decimal fraction, per docs/conventions.md); FX_RATE populates value_decimal (units of TO per one unit of FROM, per curve_id's convention -- decimal because it multiplies cash amounts and ADR-0004 forbids floats touching cash). A record with any other combination of the two value fields is rejected in both directions, by the producer and by the consumer."""

    scenario_id: str
    kind: CurveKind
    curve_id: str
    value_float: float | None
    value_decimal: Decimal | None
    event_time: datetime
    ingest_time: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "kind": self.kind.value,
            "curve_id": self.curve_id,
            "value_float": self.value_float,
            "value_decimal": self.value_decimal,
            "event_time": self.event_time,
            "ingest_time": self.ingest_time,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MarketCurve:
        return cls(
            scenario_id=d["scenario_id"],
            kind=CurveKind(d["kind"]),
            curve_id=d["curve_id"],
            value_float=d["value_float"],
            value_decimal=d["value_decimal"],
            event_time=d["event_time"],
            ingest_time=d["ingest_time"],
        )

