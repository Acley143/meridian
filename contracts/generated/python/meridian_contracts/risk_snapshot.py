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

SCHEMA_JSON = "{\n  \"type\": \"record\",\n  \"name\": \"RiskSnapshot\",\n  \"namespace\": \"com.meridian.contracts\",\n  \"doc\": \"Priced, risk-bearing output of the pricer for one portfolio at one instant under one model version. See docs/domain-model.md#risksnapshot and ADR-0007. Discrete Greek fields (not a map) so each carries its own doc/default and the registry's BACKWARD check can catch a typo in a field name at schema-review time rather than at read time. Portfolio-level Greeks are cash Greeks (ADR-0017), Decimal(38,8) -- not the per-unit float64 Greeks quant_core.types.PricingResult carries -- because raw per-unit Greeks are not summable across a portfolio's different underlyings.\",\n  \"fields\": [\n    {\n      \"name\": \"portfolio_id\",\n      \"type\": \"string\",\n      \"doc\": \"Part of the identity tuple (ADR-0007).\"\n    },\n    {\n      \"name\": \"as_of\",\n      \"type\": {\n        \"type\": \"long\",\n        \"logicalType\": \"timestamp-micros\"\n      },\n      \"doc\": \"Part of the identity tuple. Event time this snapshot values the portfolio as of -- distinct from ingest_time below, which is when the pricer produced this message.\"\n    },\n    {\n      \"name\": \"pricer_version\",\n      \"type\": \"string\",\n      \"doc\": \"Part of the identity tuple. Exact pricing model/code version used (ADR-0007).\"\n    },\n    {\n      \"name\": \"price\",\n      \"type\": {\n        \"type\": \"bytes\",\n        \"logicalType\": \"decimal\",\n        \"precision\": 38,\n        \"scale\": 8\n      },\n      \"doc\": \"Total mark-to-market value of the portfolio, in the portfolio's base currency. Decimal (precision 38, scale 8) per ADR-0004/ADR-0013. Named to match quant_core.types.PricingResult.price (ADR-0014); this is a portfolio-level aggregate, not a single-instrument price.\"\n    },\n    {\n      \"name\": \"cash_delta\",\n      \"type\": {\n        \"type\": \"bytes\",\n        \"logicalType\": \"decimal\",\n        \"precision\": 38,\n        \"scale\": 8\n      },\n      \"doc\": \"Aggregated portfolio-level cash delta (ADR-0017): sum of delta * S * 0.01 * quantity * contract_size across positions -- currency change per 1% relative move in spot. Decimal, not float64: raw per-unit deltas across different underlyings are not in comparable units and cannot be summed meaningfully; a cash amount can be. Per docs/conventions.md.\"\n    },\n    {\n      \"name\": \"cash_gamma\",\n      \"type\": {\n        \"type\": \"bytes\",\n        \"logicalType\": \"decimal\",\n        \"precision\": 38,\n        \"scale\": 8\n      },\n      \"doc\": \"Aggregated portfolio-level cash gamma (ADR-0017): sum of gamma * S^2 * 0.0001 * quantity * contract_size across positions -- change in cash_delta per 1% move in spot. Per docs/conventions.md.\"\n    },\n    {\n      \"name\": \"cash_vega\",\n      \"type\": {\n        \"type\": \"bytes\",\n        \"logicalType\": \"decimal\",\n        \"precision\": 38,\n        \"scale\": 8\n      },\n      \"doc\": \"Aggregated portfolio-level cash vega (ADR-0017): sum of vega * quantity * contract_size across positions -- currency per 1.00 absolute change in volatility, not per 1% (docs/conventions.md).\"\n    },\n    {\n      \"name\": \"cash_theta\",\n      \"type\": {\n        \"type\": \"bytes\",\n        \"logicalType\": \"decimal\",\n        \"precision\": 38,\n        \"scale\": 8\n      },\n      \"doc\": \"Aggregated portfolio-level cash theta (ADR-0017): sum of theta * quantity * contract_size across positions -- currency per calendar year, not per day (docs/conventions.md).\"\n    },\n    {\n      \"name\": \"cash_rho\",\n      \"type\": {\n        \"type\": \"bytes\",\n        \"logicalType\": \"decimal\",\n        \"precision\": 38,\n        \"scale\": 8\n      },\n      \"doc\": \"Aggregated portfolio-level cash rho (ADR-0017): sum of rho * quantity * contract_size across positions -- currency per 1.00 absolute change in the risk-free rate (docs/conventions.md).\"\n    },\n    {\n      \"name\": \"var_95\",\n      \"type\": \"double\",\n      \"doc\": \"1-day 95% Value at Risk, as a magnitude in the portfolio's base currency. float64 per ADR-0004 despite the currency unit -- this is a risk statistic, not a cash balance.\"\n    },\n    {\n      \"name\": \"scenario_id\",\n      \"type\": \"string\",\n      \"default\": \"\",\n      \"doc\": \"Propagated from the Tick stream that produced the prices behind this snapshot (ADR-0011). End-to-end lineage: any risk number can be traced back to the exact reproducible tick stream that produced it -- what makes 'replay the same market day under two pricers and diff' actually work. Added after this schema's first version; empty string is the BACKWARD-compatible default.\"\n    },\n    {\n      \"name\": \"oldest_input_event_time\",\n      \"type\": {\n        \"type\": \"long\",\n        \"logicalType\": \"timestamp-micros\"\n      },\n      \"default\": 0,\n      \"doc\": \"Earliest event_time among the prices actually used to price this snapshot's positions -- min over each position's underlying's last-known tick event_time at computation time. Equal to as_of when every input was priced off the triggering tick itself; smaller when at least one position's price is from an earlier tick on an instrument that hasn't updated since. Lets a consumer distinguish a live risk number from one resting on a feed that quietly stopped -- a dead feed and a quiet market otherwise look identical downstream. Added after this schema's first version; the BACKWARD-compatible default (epoch, 0) is a sentinel meaning 'unknown, written before this field existed,' never a real staleness value.\"\n    },\n    {\n      \"name\": \"ingest_time\",\n      \"type\": {\n        \"type\": \"long\",\n        \"logicalType\": \"timestamp-micros\"\n      },\n      \"doc\": \"UTC instant this snapshot was produced by the pricer.\"\n    }\n  ]\n}"
"""The exact source .avsc text, embedded so callers need no filesystem
path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""


@dataclass(frozen=True)
class RiskSnapshot:
    """Priced, risk-bearing output of the pricer for one portfolio at one instant under one model version. See docs/domain-model.md#risksnapshot and ADR-0007. Discrete Greek fields (not a map) so each carries its own doc/default and the registry's BACKWARD check can catch a typo in a field name at schema-review time rather than at read time. Portfolio-level Greeks are cash Greeks (ADR-0017), Decimal(38,8) -- not the per-unit float64 Greeks quant_core.types.PricingResult carries -- because raw per-unit Greeks are not summable across a portfolio's different underlyings."""

    portfolio_id: str
    as_of: datetime
    pricer_version: str
    price: Decimal
    cash_delta: Decimal
    cash_gamma: Decimal
    cash_vega: Decimal
    cash_theta: Decimal
    cash_rho: Decimal
    var_95: float
    scenario_id: str
    oldest_input_event_time: datetime
    ingest_time: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
            "as_of": self.as_of,
            "pricer_version": self.pricer_version,
            "price": self.price,
            "cash_delta": self.cash_delta,
            "cash_gamma": self.cash_gamma,
            "cash_vega": self.cash_vega,
            "cash_theta": self.cash_theta,
            "cash_rho": self.cash_rho,
            "var_95": self.var_95,
            "scenario_id": self.scenario_id,
            "oldest_input_event_time": self.oldest_input_event_time,
            "ingest_time": self.ingest_time,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RiskSnapshot:
        return cls(
            portfolio_id=d["portfolio_id"],
            as_of=d["as_of"],
            pricer_version=d["pricer_version"],
            price=d["price"],
            cash_delta=d["cash_delta"],
            cash_gamma=d["cash_gamma"],
            cash_vega=d["cash_vega"],
            cash_theta=d["cash_theta"],
            cash_rho=d["cash_rho"],
            var_95=d["var_95"],
            scenario_id=d["scenario_id"],
            oldest_input_event_time=d["oldest_input_event_time"],
            ingest_time=d["ingest_time"],
        )

