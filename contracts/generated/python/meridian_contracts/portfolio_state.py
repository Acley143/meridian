"""GENERATED -- DO NOT EDIT.

Source: contracts/avro/portfolio-state.avsc
Regenerate via `make gen` (tools/codegen/generate.py). A hand-edit here
is silently overwritten on the next regeneration and will be flagged by
the CI drift check before that (contracts/README.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

SCHEMA_JSON = "{\n  \"type\": \"record\",\n  \"name\": \"PortfolioState\",\n  \"namespace\": \"com.meridian.contracts\",\n  \"doc\": \"Materialized current positions for a portfolio, published to the log-compacted portfolio.state topic. See docs/domain-model.md#portfoliostate and ADR-0003. TOMBSTONE CONVENTION: this schema describes the VALUE when a portfolio exists. A Kafka message on this topic with a portfolio_id key and a NULL value is a tombstone (standard Kafka log-compaction semantics) meaning that portfolio has been deleted -- a null message has no Avro payload, so this cannot be a field in the schema below; it is a producer-side convention. services/core-service (the sole producer, ADR-0003) must publish a null-valued message keyed on portfolio_id on deletion, and every consumer (services/pricer) must treat a null value as a delete, not a decode failure. See docs/domain-model.md#portfoliostate for the same note.\",\n  \"fields\": [\n    {\n      \"name\": \"portfolio_id\",\n      \"type\": \"string\",\n      \"doc\": \"Kafka message key. Portfolio this state belongs to.\"\n    },\n    {\n      \"name\": \"positions\",\n      \"type\": {\n        \"type\": \"array\",\n        \"items\": {\n          \"type\": \"record\",\n          \"name\": \"Position\",\n          \"doc\": \"See docs/domain-model.md#position.\",\n          \"fields\": [\n            {\n              \"name\": \"portfolio_id\",\n              \"type\": \"string\"\n            },\n            {\n              \"name\": \"instrument_id\",\n              \"type\": \"string\"\n            },\n            {\n              \"name\": \"quantity\",\n              \"type\": {\n                \"type\": \"bytes\",\n                \"logicalType\": \"decimal\",\n                \"precision\": 38,\n                \"scale\": 8\n              },\n              \"doc\": \"Signed quantity: positive is long, negative is short.\"\n            },\n            {\n              \"name\": \"average_cost\",\n              \"type\": {\n                \"type\": \"bytes\",\n                \"logicalType\": \"decimal\",\n                \"precision\": 38,\n                \"scale\": 8\n              },\n              \"doc\": \"Volume-weighted average price paid per unit of quantity.\"\n            },\n            {\n              \"name\": \"as_of_event_time\",\n              \"type\": {\n                \"type\": \"long\",\n                \"logicalType\": \"timestamp-micros\"\n              },\n              \"doc\": \"Event time of the last trade applied to this position.\"\n            }\n          ]\n        }\n      },\n      \"default\": [],\n      \"doc\": \"Full current set of positions for this portfolio. Not a delta against the previous message.\"\n    },\n    {\n      \"name\": \"event_time\",\n      \"type\": {\n        \"type\": \"long\",\n        \"logicalType\": \"timestamp-micros\"\n      },\n      \"doc\": \"Event time of the trade that produced this state.\"\n    },\n    {\n      \"name\": \"ingest_time\",\n      \"type\": {\n        \"type\": \"long\",\n        \"logicalType\": \"timestamp-micros\"\n      },\n      \"doc\": \"UTC instant the core service produced this message.\"\n    }\n  ]\n}"
"""The exact source .avsc text, embedded so callers need no filesystem
path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""


@dataclass(frozen=True)
class Position:
    """See docs/domain-model.md#position."""

    portfolio_id: str
    instrument_id: str
    quantity: Decimal
    average_cost: Decimal
    as_of_event_time: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
            "instrument_id": self.instrument_id,
            "quantity": self.quantity,
            "average_cost": self.average_cost,
            "as_of_event_time": self.as_of_event_time,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Position:
        return cls(
            portfolio_id=d["portfolio_id"],
            instrument_id=d["instrument_id"],
            quantity=d["quantity"],
            average_cost=d["average_cost"],
            as_of_event_time=d["as_of_event_time"],
        )


@dataclass(frozen=True)
class PortfolioState:
    """Materialized current positions for a portfolio, published to the log-compacted portfolio.state topic. See docs/domain-model.md#portfoliostate and ADR-0003. TOMBSTONE CONVENTION: this schema describes the VALUE when a portfolio exists. A Kafka message on this topic with a portfolio_id key and a NULL value is a tombstone (standard Kafka log-compaction semantics) meaning that portfolio has been deleted -- a null message has no Avro payload, so this cannot be a field in the schema below; it is a producer-side convention. services/core-service (the sole producer, ADR-0003) must publish a null-valued message keyed on portfolio_id on deletion, and every consumer (services/pricer) must treat a null value as a delete, not a decode failure. See docs/domain-model.md#portfoliostate for the same note."""

    portfolio_id: str
    positions: list[Position]
    event_time: datetime
    ingest_time: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
            "positions": [_item.to_dict() for _item in self.positions],
            "event_time": self.event_time,
            "ingest_time": self.ingest_time,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PortfolioState:
        return cls(
            portfolio_id=d["portfolio_id"],
            positions=[Position.from_dict(_item) for _item in d["positions"]],
            event_time=d["event_time"],
            ingest_time=d["ingest_time"],
        )

