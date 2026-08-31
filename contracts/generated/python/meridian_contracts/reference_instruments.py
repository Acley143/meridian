"""GENERATED -- DO NOT EDIT.

Source: contracts/avro/reference-instruments.avsc
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

SCHEMA_JSON = "{\n  \"type\": \"record\",\n  \"name\": \"ReferenceInstrument\",\n  \"namespace\": \"com.meridian.contracts\",\n  \"doc\": \"Static contractual definition of a tradeable instrument, published to the log-compacted reference.instruments topic. See docs/domain-model.md#instrument and ADR-0019. Keyed by instrument_id (reference-instruments-key.avsc); one current record per key, gaining keys over time -- a new expiry/strike is a new instrument, never an update to an existing one, per docs/domain-model.md#instrument. Consumers materialize this into a keyed local view gated by the same hydrate-before-ready pattern already used for portfolio.state (services/pricer/pricer/service.py's hydrate()) -- see ADR-0019 for why no ADR yet names that pattern generically.\",\n  \"fields\": [\n    {\n      \"name\": \"instrument_id\",\n      \"type\": \"string\",\n      \"doc\": \"Kafka message key. Globally unique, stable identifier -- not a reusable exchange ticker.\"\n    },\n    {\n      \"name\": \"underlying_id\",\n      \"type\": \"string\",\n      \"doc\": \"instrument_id of the underlying this derivative references. Equal to instrument_id itself for a non-derivative (e.g. an equity).\"\n    },\n    {\n      \"name\": \"instrument_type\",\n      \"type\": {\n        \"type\": \"enum\",\n        \"name\": \"InstrumentType\",\n        \"symbols\": [\n          \"EQUITY\",\n          \"VANILLA_EUROPEAN_OPTION\",\n          \"VANILLA_AMERICAN_OPTION\"\n        ]\n      },\n      \"doc\": \"Discriminates which fields below are meaningful and which pricer applies. Not free text -- new types require a schema change.\"\n    },\n    {\n      \"name\": \"option_type\",\n      \"type\": [\n        \"null\",\n        {\n          \"type\": \"enum\",\n          \"name\": \"OptionType\",\n          \"symbols\": [\n            \"CALL\",\n            \"PUT\"\n          ]\n        }\n      ],\n      \"default\": null,\n      \"doc\": \"Right conveyed by the option. Null unless instrument_type is an option; not meaningful for EQUITY.\"\n    },\n    {\n      \"name\": \"strike\",\n      \"type\": [\n        \"null\",\n        {\n          \"type\": \"bytes\",\n          \"logicalType\": \"decimal\",\n          \"precision\": 38,\n          \"scale\": 8\n        }\n      ],\n      \"default\": null,\n      \"doc\": \"Strike price in the instrument's quote currency (currency field below). Null unless an option. A price, not a percentage-of-spot moneyness.\"\n    },\n    {\n      \"name\": \"expiry\",\n      \"type\": [\n        \"null\",\n        {\n          \"type\": \"long\",\n          \"logicalType\": \"timestamp-micros\"\n        }\n      ],\n      \"default\": null,\n      \"doc\": \"UTC instant the option expires, microsecond precision. Null unless an option. Not date-only -- intraday expiry matters for the latency/accuracy budget.\"\n    },\n    {\n      \"name\": \"currency\",\n      \"type\": \"string\",\n      \"doc\": \"ISO 4217 currency the instrument is quoted and settled in. Not necessarily the underlying's home currency.\"\n    },\n    {\n      \"name\": \"contract_size\",\n      \"type\": {\n        \"type\": \"bytes\",\n        \"logicalType\": \"decimal\",\n        \"precision\": 38,\n        \"scale\": 8\n      },\n      \"doc\": \"Multiplier converting one contract to underlying units (e.g. 100 shares/contract). Applied exactly once, in services/pricer, per ADR-0014/ADR-0017. Not the notional -- see docs/domain-model.md#position.\"\n    }\n  ]\n}"
"""The exact source .avsc text, embedded so callers need no filesystem
path to the schema at runtime. Parse with avro.schema.parse(SCHEMA_JSON)."""


class InstrumentType(str, Enum):
    EQUITY = "EQUITY"
    VANILLA_EUROPEAN_OPTION = "VANILLA_EUROPEAN_OPTION"
    VANILLA_AMERICAN_OPTION = "VANILLA_AMERICAN_OPTION"


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


@dataclass(frozen=True)
class ReferenceInstrument:
    """Static contractual definition of a tradeable instrument, published to the log-compacted reference.instruments topic. See docs/domain-model.md#instrument and ADR-0019. Keyed by instrument_id (reference-instruments-key.avsc); one current record per key, gaining keys over time -- a new expiry/strike is a new instrument, never an update to an existing one, per docs/domain-model.md#instrument. Consumers materialize this into a keyed local view gated by the same hydrate-before-ready pattern already used for portfolio.state (services/pricer/pricer/service.py's hydrate()) -- see ADR-0019 for why no ADR yet names that pattern generically."""

    instrument_id: str
    underlying_id: str
    instrument_type: InstrumentType
    option_type: OptionType | None
    strike: Decimal | None
    expiry: datetime | None
    currency: str
    contract_size: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "underlying_id": self.underlying_id,
            "instrument_type": self.instrument_type.value,
            "option_type": (self.option_type.value if self.option_type is not None else None),
            "strike": self.strike,
            "expiry": self.expiry,
            "currency": self.currency,
            "contract_size": self.contract_size,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReferenceInstrument:
        return cls(
            instrument_id=d["instrument_id"],
            underlying_id=d["underlying_id"],
            instrument_type=InstrumentType(d["instrument_type"]),
            option_type=(OptionType(d["option_type"]) if d["option_type"] is not None else None),
            strike=d["strike"],
            expiry=d["expiry"],
            currency=d["currency"],
            contract_size=d["contract_size"],
        )

