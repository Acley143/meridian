"""Static instrument reference data and market-rate assumptions.

**This module is a stand-in for a real feed that doesn't exist yet, and is
called out explicitly in `services/pricer/PLAN.md`'s open questions.**
`docs/domain-model.md#Instrument` defines the static fields a pricer needs
(strike, expiry, option_type, contract_size, currency, underlying_id), and
Black-Scholes additionally needs volatility/risk_free_rate/dividend_yield
per `quant_core.types.MarketState` -- but nothing in `contracts/avro/`
publishes either over Kafka. `portfolio.state`'s `Position` carries only
`instrument_id`, `quantity`, `average_cost`, `as_of_event_time` (see
`docs/domain-model.md#position`); `market.ticks` carries only a price.

There is no ADR covering where this data should come from. Per root
`CLAUDE.md`: "If [a decision] should exist and doesn't, stop and say so —
don't decide by writing code." This session cannot literally stop (there
is no pricer without *some* answer), so the judgment call made here is
narrow and reversible: a checked-in static YAML fixture
(`services/pricer/fixtures/instruments.yaml`), loaded once at startup,
standing in for what should eventually be either a real reference-data
topic or a market-data-assumptions service. Flagged in `PLAN.md` open
questions for Eng-A to turn into a real ADR-backed decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml
from quant_core.types import OptionRight


@dataclass(frozen=True)
class InstrumentReference:
    """Static definition of one instrument, per docs/domain-model.md#Instrument,
    plus the market-rate assumptions Black-Scholes needs that have no other
    source this quarter (see module docstring)."""

    instrument_id: str
    instrument_type: str  # "EQUITY" | "VANILLA_EUROPEAN_OPTION" | "VANILLA_AMERICAN_OPTION"
    underlying_id: str
    currency: str
    contract_size: Decimal
    option_type: OptionRight | None = None
    strike: Decimal | None = None
    expiry_iso: str | None = None
    volatility: float | None = None
    risk_free_rate: float | None = None
    dividend_yield: float | None = None

    def __post_init__(self) -> None:
        if self.instrument_type not in ("EQUITY", "VANILLA_EUROPEAN_OPTION", "VANILLA_AMERICAN_OPTION"):
            raise ValueError(f"unknown instrument_type: {self.instrument_type!r}")
        if self.instrument_type == "VANILLA_EUROPEAN_OPTION":
            missing = [
                name
                for name, value in (
                    ("option_type", self.option_type),
                    ("strike", self.strike),
                    ("expiry_iso", self.expiry_iso),
                    ("volatility", self.volatility),
                    ("risk_free_rate", self.risk_free_rate),
                    ("dividend_yield", self.dividend_yield),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    f"{self.instrument_id}: VANILLA_EUROPEAN_OPTION requires {missing}"
                )


class ReferenceData:
    """A static lookup: instrument_id -> InstrumentReference."""

    def __init__(self, instruments: dict[str, InstrumentReference]) -> None:
        self._instruments = instruments

    def get(self, instrument_id: str) -> InstrumentReference:
        try:
            return self._instruments[instrument_id]
        except KeyError:
            raise KeyError(
                f"no reference data for instrument_id={instrument_id!r} -- "
                "services/pricer/fixtures/instruments.yaml has no entry for it"
            ) from None

    def __contains__(self, instrument_id: str) -> bool:
        return instrument_id in self._instruments


def load_reference_data(path: Path) -> ReferenceData:
    raw = yaml.safe_load(path.read_text())
    instruments = {}
    for instrument_id, cfg in raw["instruments"].items():
        option_type = None
        if cfg.get("option_type") is not None:
            option_type = OptionRight[cfg["option_type"]]
        instruments[instrument_id] = InstrumentReference(
            instrument_id=instrument_id,
            instrument_type=cfg["instrument_type"],
            underlying_id=cfg["underlying_id"],
            currency=cfg["currency"],
            contract_size=Decimal(str(cfg["contract_size"])),
            option_type=option_type,
            strike=Decimal(str(cfg["strike"])) if cfg.get("strike") is not None else None,
            expiry_iso=cfg.get("expiry"),
            volatility=cfg.get("volatility"),
            risk_free_rate=cfg.get("risk_free_rate"),
            dividend_yield=cfg.get("dividend_yield"),
        )
    return ReferenceData(instruments)
