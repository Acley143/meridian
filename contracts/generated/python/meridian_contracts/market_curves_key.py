"""GENERATED -- DO NOT EDIT.

Source: contracts/avro/market-curves-key.avsc
Regenerate via `make gen` (tools/codegen/generate.py). A hand-edit here
is silently overwritten on the next regeneration and will be flagged by
the CI drift check before that (contracts/README.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

SCHEMA_JSON = "{\n  \"type\": \"record\",\n  \"name\": \"MarketCurveKey\",\n  \"namespace\": \"com.meridian.contracts\",\n  \"doc\": \"Kafka message key for the log-compacted market.curves topic (ADR-0027, supersedes ADR-0019's market.curves shape). Keyed by (scenario_id, kind, curve_id), which is also the compaction identity -- one current value per key.\",\n  \"fields\": [\n    {\n      \"name\": \"scenario_id\",\n      \"type\": \"string\",\n      \"doc\": \"Identifies the seeded simulated market scenario this curve value belongs to (ADR-0011, ADR-0006). Required and non-empty -- unlike Tick.scenario_id, this field has no legacy empty-string default; every market.curves record is scenario-scoped from its first version.\"\n    },\n    {\n      \"name\": \"kind\",\n      \"type\": {\n        \"type\": \"enum\",\n        \"name\": \"CurveKind\",\n        \"symbols\": [\n          \"RISK_FREE_RATE\",\n          \"VOLATILITY\",\n          \"DIVIDEND_YIELD\",\n          \"FX_RATE\"\n        ]\n      },\n      \"doc\": \"Which market quantity this curve value carries. Determines the meaning of curve_id and which of MarketCurve's two value fields is populated -- see market-curves.avsc.\"\n    },\n    {\n      \"name\": \"curve_id\",\n      \"type\": \"string\",\n      \"doc\": \"Identifies the specific curve within (scenario_id, kind), per kind: RISK_FREE_RATE -- an ISO 4217 currency code; VOLATILITY and DIVIDEND_YIELD -- an underlying_id (docs/domain-model.md#instrument); FX_RATE -- six letters FROMTO (e.g. EURUSD), where the published value is units of TO per one unit of FROM.\"\n    }\n  ]\n}"
"""The exact source .avsc text, embedded so callers need no filesystem
path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""


class CurveKind(str, Enum):
    RISK_FREE_RATE = "RISK_FREE_RATE"
    VOLATILITY = "VOLATILITY"
    DIVIDEND_YIELD = "DIVIDEND_YIELD"
    FX_RATE = "FX_RATE"


@dataclass(frozen=True)
class MarketCurveKey:
    """Kafka message key for the log-compacted market.curves topic (ADR-0027, supersedes ADR-0019's market.curves shape). Keyed by (scenario_id, kind, curve_id), which is also the compaction identity -- one current value per key."""

    scenario_id: str
    kind: CurveKind
    curve_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "kind": self.kind.value,
            "curve_id": self.curve_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MarketCurveKey:
        return cls(
            scenario_id=d["scenario_id"],
            kind=CurveKind(d["kind"]),
            curve_id=d["curve_id"],
        )

