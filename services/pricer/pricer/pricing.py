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

`oldest_input_event_time` does not include any `market.curves` event_time.
Curves are constant for the lifetime of a scenario, with event_time equal
to the scenario's start_time (ADR-0027 Decisions 4 and 5) -- including them
would pin this field to the scenario start on every snapshot, which removes
its actual purpose: signalling how stale the *prices* feeding a snapshot
are.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum

from quant_core import PRICER_VERSION
from quant_core.numeric import convert_money, to_model, to_money
from quant_core.pricing.american import ModelDomainError
from quant_core.pricing.american import price as american_price
from quant_core.pricing.black_scholes import price as black_scholes_price
from quant_core.types import AmericanOption, EuropeanOption, MarketState, PricingResult

from pricer.reference_data import InstrumentReference


class UnpriceableReason(str, Enum):
    """Stable reason codes for structured unpriceable-portfolio reporting
    (ADR-0018) -- see `pricer.service.PricerService._report_unpriceable`."""

    UNKNOWN_BASE_CURRENCY = "UNKNOWN_BASE_CURRENCY"
    NO_REFERENCE_DATA = "NO_REFERENCE_DATA"
    NO_PRICE = "NO_PRICE"
    MISSING_CURVE = "MISSING_CURVE"
    INSTRUMENT_NOT_PRICEABLE = "INSTRUMENT_NOT_PRICEABLE"
    OUTSIDE_MODEL_DOMAIN = "OUTSIDE_MODEL_DOMAIN"


OPTION_TYPES = frozenset({"VANILLA_EUROPEAN_OPTION", "VANILLA_AMERICAN_OPTION"})
"""The instrument types priced as options: each needs option statics
(reference data) and the rate and dividend curves (ADR-0033 Decisions 1, 2)."""


class UnpricableInstrumentError(Exception):
    """Raised when a position's instrument can't be priced -- an instrument
    type with no pricer, missing statics or market inputs, or quant-core
    rejected its inputs or could not represent its result (ADR-0032
    Decision 2)."""


class OutsideModelDomainError(UnpricableInstrumentError):
    """An American option whose inputs lie outside ADR-0031's validated
    domain. Reported as OUTSIDE_MODEL_DOMAIN, not INSTRUMENT_NOT_PRICEABLE
    (ADR-0033 Decision 3, ADR-0032 Decision 6). `violations` names each
    violated condition with its value."""

    def __init__(self, message: str, violations: tuple[str, ...]) -> None:
        super().__init__(message)
        self.violations = violations


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


@dataclass(frozen=True)
class OptionMarketInputs:
    """The market-rate assumptions an option pricer needs, sourced from
    `market.curves` (ADR-0027) rather than from `InstrumentReference`."""

    volatility: float
    risk_free_rate: float
    dividend_yield: float


def price_instrument(
    reference: InstrumentReference,
    spot: Decimal,
    valuation_time: datetime,
    market: OptionMarketInputs | None = None,
) -> PricingResult:
    """Price one instrument per unit of underlying. `valuation_time` is the
    triggering tick's event_time (Task 3) -- never `datetime.now()`. `market`
    carries the market-rate assumptions an option needs (ADR-0027,
    ADR-0033); this function never reads `reference.volatility`,
    `reference.risk_free_rate`, or `reference.dividend_yield`. An American
    option outside ADR-0031's validated domain raises
    `OutsideModelDomainError`; every other failed evaluation raises
    `UnpricableInstrumentError` (ADR-0032 Decision 2)."""
    if reference.instrument_type == "EQUITY":
        return _price_equity(spot)

    if reference.instrument_type in OPTION_TYPES:
        instrument_type = reference.instrument_type
        missing = [
            name
            for name, value in (
                ("option_type", reference.option_type),
                ("strike", reference.strike),
                ("expiry_iso", reference.expiry_iso),
                ("market inputs", market),
            )
            if value is None
        ]
        if missing:
            raise UnpricableInstrumentError(
                f"{reference.instrument_id}: {instrument_type} missing {missing}"
            )
        expiry = datetime.fromisoformat(reference.expiry_iso.replace("Z", "+00:00"))
        # ADR-0032 Decision 2, with ADR-0031's model-specific reason mapped
        # first (ADR-0032 Decision 6, ADR-0033 Decision 3). ModelDomainError
        # is a ValueError, so its catch must come before the general one.
        try:
            market_state = MarketState(
                spot=spot,
                volatility=market.volatility,
                risk_free_rate=market.risk_free_rate,
                dividend_yield=market.dividend_yield,
                valuation_time=valuation_time,
            )
            if instrument_type == "VANILLA_AMERICAN_OPTION":
                return american_price(
                    AmericanOption(
                        underlying_id=reference.underlying_id,
                        strike=reference.strike,
                        expiry=expiry,
                        right=reference.option_type,
                    ),
                    market_state,
                )
            return black_scholes_price(
                EuropeanOption(
                    underlying_id=reference.underlying_id,
                    strike=reference.strike,
                    expiry=expiry,
                    right=reference.option_type,
                ),
                market_state,
            )
        except ModelDomainError as exc:
            raise OutsideModelDomainError(
                f"{reference.instrument_id}: {instrument_type} is outside the ADR-0031 "
                f"validated domain: {'; '.join(exc.violations)}",
                exc.violations,
            ) from exc
        except (ValueError, OverflowError, InvalidOperation) as exc:
            raise UnpricableInstrumentError(
                f"{reference.instrument_id}: {instrument_type} could not be priced: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    # A guard, not a reachable path: every instrument type InstrumentReference
    # accepts has a pricer above (ADR-0033 Consequences). It stops a future
    # type from being accepted without one.
    raise UnpricableInstrumentError(
        f"{reference.instrument_id}: instrument_type={reference.instrument_type!r} "
        "has no pricer"
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


def convert_contribution(
    contribution: PositionCashContribution, rate: Decimal
) -> PositionCashContribution:
    """One position's contribution converted into the portfolio's reporting
    currency at `rate` (ADR-0028 Decisions 3 and 5): each of the six fields
    goes through `quant_core.numeric.convert_money` -- decimal throughout,
    quantised once per field at scale 8 -- and a new instance is returned.
    Called per position, before `aggregate_portfolio` sums, so the total does
    not depend on summation order. Raises `ValueError` for a rate that is not
    finite and strictly positive."""
    return PositionCashContribution(
        price=convert_money(contribution.price, rate),
        cash_delta=convert_money(contribution.cash_delta, rate),
        cash_gamma=convert_money(contribution.cash_gamma, rate),
        cash_vega=convert_money(contribution.cash_vega, rate),
        cash_theta=convert_money(contribution.cash_theta, rate),
        cash_rho=convert_money(contribution.cash_rho, rate),
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
