"""GENERATED -- DO NOT EDIT.

Source: contracts/avro/risk-snapshot.avsc
Regenerate via `make gen` (tools/codegen/generate.py). A hand-edit here
is silently overwritten on the next regeneration and will be flagged by
the CI drift check before that (contracts/README.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

SCHEMA_JSON = "{\n  \"type\": \"record\",\n  \"name\": \"RiskSnapshot\",\n  \"namespace\": \"com.meridian.contracts\",\n  \"doc\": \"Priced, risk-bearing output of the pricer for one portfolio at one instant under one model version. See docs/domain-model.md#risksnapshot and ADR-0007. Discrete Greek fields (not a map) so each carries its own doc/default and the registry's BACKWARD check can catch a typo in a field name at schema-review time rather than at read time.\",\n  \"fields\": [\n    {\n      \"name\": \"portfolio_id\",\n      \"type\": \"string\",\n      \"doc\": \"Part of the identity tuple (ADR-0007).\"\n    },\n    {\n      \"name\": \"as_of\",\n      \"type\": {\n        \"type\": \"long\",\n        \"logicalType\": \"timestamp-micros\"\n      },\n      \"doc\": \"Part of the identity tuple. Event time this snapshot values the portfolio as of -- distinct from ingest_time below, which is when the pricer produced this message.\"\n    },\n    {\n      \"name\": \"pricer_version\",\n      \"type\": \"string\",\n      \"doc\": \"Part of the identity tuple. Exact pricing model/code version used (ADR-0007).\"\n    },\n    {\n      \"name\": \"price\",\n      \"type\": {\n        \"type\": \"bytes\",\n        \"logicalType\": \"decimal\",\n        \"precision\": 38,\n        \"scale\": 8\n      },\n      \"doc\": \"Total mark-to-market value of the portfolio, in the portfolio's base currency. Decimal (precision 38, scale 8) per ADR-0004/ADR-0013. Named to match quant_core.types.PricingResult.price (ADR-0014); this is a portfolio-level aggregate, not a single-instrument price.\"\n    },\n    {\n      \"name\": \"delta\",\n      \"type\": \"double\",\n      \"doc\": \"Aggregated portfolio-level delta, per docs/conventions.md. float64 per ADR-0004.\"\n    },\n    {\n      \"name\": \"gamma\",\n      \"type\": \"double\",\n      \"doc\": \"Aggregated portfolio-level gamma, per docs/conventions.md. float64 per ADR-0004.\"\n    },\n    {\n      \"name\": \"vega\",\n      \"type\": \"double\",\n      \"doc\": \"Aggregated portfolio-level vega, per 1.00 absolute change in volatility -- not per 1% (docs/conventions.md). float64 per ADR-0004.\"\n    },\n    {\n      \"name\": \"theta\",\n      \"type\": \"double\",\n      \"doc\": \"Aggregated portfolio-level theta, per calendar year -- not per day (docs/conventions.md). float64 per ADR-0004.\"\n    },\n    {\n      \"name\": \"rho\",\n      \"type\": \"double\",\n      \"doc\": \"Aggregated portfolio-level rho, per 1.00 absolute change in the risk-free rate (docs/conventions.md). float64 per ADR-0004.\"\n    },\n    {\n      \"name\": \"var_95\",\n      \"type\": \"double\",\n      \"doc\": \"1-day 95% Value at Risk, as a magnitude in the portfolio's base currency. float64 per ADR-0004 despite the currency unit -- this is a risk statistic, not a cash balance.\"\n    },\n    {\n      \"name\": \"scenario_id\",\n      \"type\": \"string\",\n      \"default\": \"\",\n      \"doc\": \"Propagated from the Tick stream that produced the prices behind this snapshot (ADR-0011). End-to-end lineage: any risk number can be traced back to the exact reproducible tick stream that produced it -- what makes 'replay the same market day under two pricers and diff' actually work. Added after this schema's first version; empty string is the BACKWARD-compatible default.\"\n    },\n    {\n      \"name\": \"ingest_time\",\n      \"type\": {\n        \"type\": \"long\",\n        \"logicalType\": \"timestamp-micros\"\n      },\n      \"doc\": \"UTC instant this snapshot was produced by the pricer.\"\n    }\n  ]\n}"
"""The exact source .avsc text, embedded so callers need no filesystem
path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""


@dataclass(frozen=True)
class RiskSnapshot:
    """Priced, risk-bearing output of the pricer for one portfolio at one instant under one model version. See docs/domain-model.md#risksnapshot and ADR-0007. Discrete Greek fields (not a map) so each carries its own doc/default and the registry's BACKWARD check can catch a typo in a field name at schema-review time rather than at read time."""

    portfolio_id: str
    as_of: datetime
    pricer_version: str
    price: Decimal
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    var_95: float
    scenario_id: str
    ingest_time: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
            "as_of": self.as_of,
            "pricer_version": self.pricer_version,
            "price": self.price,
            "delta": self.delta,
            "gamma": self.gamma,
            "vega": self.vega,
            "theta": self.theta,
            "rho": self.rho,
            "var_95": self.var_95,
            "scenario_id": self.scenario_id,
            "ingest_time": self.ingest_time,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RiskSnapshot:
        return cls(
            portfolio_id=d["portfolio_id"],
            as_of=d["as_of"],
            pricer_version=d["pricer_version"],
            price=d["price"],
            delta=d["delta"],
            gamma=d["gamma"],
            vega=d["vega"],
            theta=d["theta"],
            rho=d["rho"],
            var_95=d["var_95"],
            scenario_id=d["scenario_id"],
            ingest_time=d["ingest_time"],
        )

