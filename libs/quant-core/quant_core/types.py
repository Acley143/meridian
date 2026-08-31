"""Pricing-input and pricing-output types for quant_core.

These mirror `docs/domain-model.md` where it defines the same concepts;
where the two disagree, the document wins. `EuropeanOption` is a
pricing-scoped projection of `docs/domain-model.md#Instrument` (strike,
expiry, right, underlying) rather than the full wire `Instrument` record —
fields like `instrument_id`, `currency`, and `contract_size` are meaningful
on the wire but not needed by a pure pricing formula, so they are omitted
here rather than mirrored.

Units and sign conventions for every float field are in
`docs/conventions.md` — read that before touching a Greek.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


def _require_aware(dt: datetime, field_name: str) -> None:
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(
            f"{field_name} must be a timezone-aware UTC datetime; got a naive "
            "datetime, which would silently default to local time (ADR-0005)."
        )


class OptionRight(Enum):
    """Mirrors `docs/domain-model.md#Instrument.option_type`."""

    CALL = "CALL"
    PUT = "PUT"


@dataclass(frozen=True)
class EuropeanOption:
    """A vanilla European option, pricing-scoped (see module docstring)."""

    underlying_id: str
    strike: Decimal
    expiry: datetime
    right: OptionRight

    def __post_init__(self) -> None:
        if self.strike <= 0:
            raise ValueError(f"strike must be positive, got {self.strike}")
        _require_aware(self.expiry, "expiry")


@dataclass(frozen=True)
class MarketState:
    """The market inputs a pricer needs, as of one instant.

    `volatility` and `risk_free_rate` are continuously compounded,
    annualised decimals (docs/conventions.md) — 0.05, never 5.
    """

    spot: Decimal
    volatility: float
    risk_free_rate: float
    dividend_yield: float
    valuation_time: datetime

    def __post_init__(self) -> None:
        if self.spot <= 0:
            raise ValueError(f"spot must be positive, got {self.spot}")
        if self.volatility < 0:
            raise ValueError(f"volatility must be non-negative, got {self.volatility}")
        _require_aware(self.valuation_time, "valuation_time")


@dataclass(frozen=True)
class PricingResult:
    """The priced output of a pricer for one instrument at one instant.

    `delta`, `gamma`, `vega`, `theta`, `rho` follow the sign/unit
    conventions in `docs/conventions.md` — in particular, theta is
    per calendar year and vega/rho are per 1.00 absolute change, not
    per 1%/basis point.
    """

    price: Decimal
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    pricer_version: str


def validate_option_against_market(option: EuropeanOption, market: MarketState) -> None:
    """Cross-object validation that neither type alone can perform."""
    if option.expiry < market.valuation_time:
        raise ValueError(
            f"expiry ({option.expiry.isoformat()}) is before valuation_time "
            f"({market.valuation_time.isoformat()})"
        )
