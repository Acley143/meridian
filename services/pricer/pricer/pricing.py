"""Per-position pricing (quant_core) and portfolio-level cash-Greek
aggregation (ADR-0014, ADR-0017).

Kept free of Kafka/Avro types on purpose: takes plain `Position` records,
prices/event-times as `dict[instrument_id, ...]`, and instrument reference
data -- the same shape whether the caller is `pricer.service` wired to a
real broker or a unit test constructing everything by hand.

Order of operations per ADR-0014/ADR-0017, in this exact sequence:
1. `quant_core` prices per unit of underlying (no contract multiplier).
2. Multiply by `quantity * contract_size` (ADR-0014's one multiplication
   point) -- and, for delta/gamma only, the 1% cash basis (ADR-0017) --
   entirely in float64, matching every input already in that domain.
3. Convert to `Decimal` through `quant_core.numeric.to_money`, once per
   value, at the very end -- never before step 2's multiplications
   (ADR-0017: "the 1%/1.00 basis multiplications themselves happen in
   float64 ... before that one conversion at the boundary, not before it").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from quant_core import PRICER_VERSION
from quant_core.numeric import to_model, to_money
from quant_core.pricing.black_scholes import price as black_scholes_price
from quant_core.types import EuropeanOption, MarketState, PricingResult

from pricer.reference_data import InstrumentReference


class UnpricableInstrumentError(Exception):
    """Raised when a position's instrument can't be priced -- unsupported
    instrument_type (e.g. VANILLA_AMERICAN_OPTION, Q2), or no reference
    data / no observed price for its underlying yet."""


def _price_equity(spot: Decimal) -> PricingResult:
    """A straight equity position: price is the observed spot itself,
    delta is 1 (price moves 1:1 with itself), every other Greek is 0 --
    there is no volatility/rate/time sensitivity to a spot holding."""
    return PricingResult(
        price=spot,
        delta=1.0,
        gamma=0.0,
        vega=0.0,
        theta=0.0,
        rho=0.0,
        pricer_version=PRICER_VERSION,
    )


def price_instrument(
    reference: InstrumentReference, spot: Decimal, valuation_time: datetime
) -> PricingResult:
    """Price one instrument per unit of underlying. `valuation_time` is the
    triggering tick's event_time (Task 3) -- never `datetime.now()`."""
    if reference.instrument_type == "EQUITY":
        return _price_equity(spot)

    if reference.instrument_type == "VANILLA_EUROPEAN_OPTION":
        assert reference.option_type is not None
        assert reference.strike is not None
        assert reference.expiry_iso is not None
        assert reference.volatility is not None
        assert reference.risk_free_rate is not None
        assert reference.dividend_yield is not None
        option = EuropeanOption(
            underlying_id=reference.underlying_id,
            strike=reference.strike,
            expiry=datetime.fromisoformat(reference.expiry_iso.replace("Z", "+00:00")),
            right=reference.option_type,
        )
        market = MarketState(
            spot=spot,
            volatility=reference.volatility,
            risk_free_rate=reference.risk_free_rate,
            dividend_yield=reference.dividend_yield,
            valuation_time=valuation_time,
        )
        return black_scholes_price(option, market)

    raise UnpricableInstrumentError(
        f"{reference.instrument_id}: instrument_type={reference.instrument_type!r} "
        "has no pricer yet (Q1 supports EQUITY and VANILLA_EUROPEAN_OPTION only)"
    )


@dataclass(frozen=True)
class PositionCashContribution:
    """One position's contribution to a `RiskSnapshot`'s portfolio-level
    fields, already through the `contract_size`/1% basis multiplications
    and the one `to_money` conversion (ADR-0014, ADR-0017)."""

    price: Decimal
    cash_delta: Decimal
    cash_gamma: Decimal
    cash_vega: Decimal
    cash_theta: Decimal
    cash_rho: Decimal


def aggregate_position(
    pricing_result: PricingResult, quantity: Decimal, contract_size: Decimal, spot: Decimal
) -> PositionCashContribution:
    q = to_model(quantity)
    c = to_model(contract_size)
    s = to_model(spot)
    multiplier = q * c

    return PositionCashContribution(
        price=to_money(to_model(pricing_result.price) * multiplier),
        cash_delta=to_money(pricing_result.delta * s * 0.01 * multiplier),
        cash_gamma=to_money(pricing_result.gamma * s * s * 0.0001 * multiplier),
        cash_vega=to_money(pricing_result.vega * multiplier),
        cash_theta=to_money(pricing_result.theta * multiplier),
        cash_rho=to_money(pricing_result.rho * multiplier),
    )


@dataclass(frozen=True)
class PortfolioAggregate:
    price: Decimal
    cash_delta: Decimal
    cash_gamma: Decimal
    cash_vega: Decimal
    cash_theta: Decimal
    cash_rho: Decimal


def aggregate_portfolio(contributions: list[PositionCashContribution]) -> PortfolioAggregate:
    """Sum each field across positions in `Decimal` -- exact addition, no
    further rounding, since every value entering the sum already went
    through `to_money` exactly once (ADR-0013)."""
    zero = Decimal(0)
    return PortfolioAggregate(
        price=sum((c.price for c in contributions), zero),
        cash_delta=sum((c.cash_delta for c in contributions), zero),
        cash_gamma=sum((c.cash_gamma for c in contributions), zero),
        cash_vega=sum((c.cash_vega for c in contributions), zero),
        cash_theta=sum((c.cash_theta for c in contributions), zero),
        cash_rho=sum((c.cash_rho for c in contributions), zero),
    )


def oldest_input_event_time(
    underlying_ids: set[str], last_event_time_by_underlying: dict[str, datetime]
) -> datetime:
    """The earliest event_time among the prices actually used (Task 4).
    Every underlying_id passed in must have an entry -- callers are
    expected to have already verified every position's underlying has a
    known price before pricing (see `UnpricableInstrumentError`)."""
    return min(last_event_time_by_underlying[u] for u in underlying_ids)
