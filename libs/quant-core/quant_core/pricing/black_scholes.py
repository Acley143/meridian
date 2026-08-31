"""Black-Scholes closed-form pricing for vanilla European options.

Continuous dividend yield, all five Greeks (delta, gamma, vega, theta, rho)
per the sign/unit conventions in `docs/conventions.md`. Uses
`statistics.NormalDist`, which is erf-based and accurate in the tails —
naive series approximations of the normal CDF lose accuracy exactly where
the accuracy budget (1e-6 relative, `docs/nfr-budget.md`) is tightest.

The T=0 and sigma=0 cases are handled explicitly rather than left to the
general formula, which diverges (NaN or a ZeroDivisionError) exactly there.
Each returns the mathematically correct limit, derived by taking the limit
of each Greek as the corresponding input approaches its degenerate value.

S -> 0 needs no dedicated branch: `MarketState` validates `spot > 0` at
construction (Task 4), so S=0 itself never reaches this module. The general
formula is already numerically safe for S far from K in either direction —
`statistics.NormalDist.cdf` saturates cleanly to 0.0/1.0 for large-magnitude
d1/d2 rather than overflowing — so deep ITM/OTM and near-zero spot are
covered without a special case; see the deep-ITM/OTM and near-zero-spot
tests in `tests/unit/test_black_scholes_boundary.py`.
"""
import math
from datetime import timedelta
from statistics import NormalDist

from quant_core import PRICER_VERSION
from quant_core.numeric import to_model, to_money
from quant_core.types import (
    EuropeanOption,
    MarketState,
    OptionRight,
    PricingResult,
    validate_option_against_market,
)

_DAYS_PER_YEAR = timedelta(days=365.25)
_NORMAL = NormalDist()
_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _time_to_expiry(option: EuropeanOption, market: MarketState) -> float:
    """ACT/365F, per docs/conventions.md — years, not days."""
    return (option.expiry - market.valuation_time) / _DAYS_PER_YEAR


def _std_normal_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def price(option: EuropeanOption, market: MarketState) -> PricingResult:
    """Price and all five Greeks for a vanilla European option."""
    validate_option_against_market(option, market)

    s = to_model(market.spot)
    k = to_model(option.strike)
    vol = market.volatility
    r = market.risk_free_rate
    q = market.dividend_yield
    t = _time_to_expiry(option, market)
    is_call = option.right is OptionRight.CALL

    if t <= 0.0:
        return _at_expiry(s, k, is_call)
    if vol <= 0.0:
        return _zero_vol(s, k, r, q, t, is_call)
    return _general_case(s, k, vol, r, q, t, is_call)


def _at_expiry(s: float, k: float, is_call: bool) -> PricingResult:
    """T=0: price is intrinsic value; delta is 0/1 (call) or -1/0 (put)
    depending on moneyness; gamma, vega, theta, rho are all 0 (no time
    left for the spot, rate, or vol to move against)."""
    if is_call:
        intrinsic = max(s - k, 0.0)
        delta = 1.0 if s > k else 0.0
    else:
        intrinsic = max(k - s, 0.0)
        delta = -1.0 if s < k else 0.0
    return PricingResult(
        price=to_money(intrinsic),
        delta=delta,
        gamma=0.0,
        vega=0.0,
        theta=0.0,
        rho=0.0,
        pricer_version=PRICER_VERSION,
    )


def _zero_vol(s: float, k: float, r: float, q: float, t: float, is_call: bool) -> PricingResult:
    """sigma=0: deterministic forward. Price is discounted intrinsic on the
    forward F = S*e^((r-q)T); each Greek is the limit of the general
    formula as sigma -> 0+ on whichever side of moneyness the forward
    lands (gamma and vega vanish; the option is a certainty, not a bet)."""
    forward = s * math.exp((r - q) * t)
    df_r = math.exp(-r * t)
    df_q = math.exp(-q * t)

    if is_call:
        itm = forward > k
        pr = (s * df_q - k * df_r) if itm else 0.0
        delta = df_q if itm else 0.0
        theta = (q * s * df_q - r * k * df_r) if itm else 0.0
        rho = (k * t * df_r) if itm else 0.0
    else:
        itm = forward < k
        pr = (k * df_r - s * df_q) if itm else 0.0
        delta = (-df_q) if itm else 0.0
        theta = (r * k * df_r - q * s * df_q) if itm else 0.0
        rho = (-k * t * df_r) if itm else 0.0

    return PricingResult(
        price=to_money(pr),
        delta=delta,
        gamma=0.0,
        vega=0.0,
        theta=theta,
        rho=rho,
        pricer_version=PRICER_VERSION,
    )


def _general_case(
    s: float, k: float, vol: float, r: float, q: float, t: float, is_call: bool
) -> PricingResult:
    sqrt_t = math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * vol * vol) * t) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    df_r = math.exp(-r * t)
    df_q = math.exp(-q * t)
    pdf_d1 = _std_normal_pdf(d1)

    if is_call:
        pr = s * df_q * _NORMAL.cdf(d1) - k * df_r * _NORMAL.cdf(d2)
        delta = df_q * _NORMAL.cdf(d1)
        theta = (
            -s * df_q * pdf_d1 * vol / (2.0 * sqrt_t)
            - r * k * df_r * _NORMAL.cdf(d2)
            + q * s * df_q * _NORMAL.cdf(d1)
        )
        rho = k * t * df_r * _NORMAL.cdf(d2)
    else:
        pr = k * df_r * _NORMAL.cdf(-d2) - s * df_q * _NORMAL.cdf(-d1)
        delta = df_q * (_NORMAL.cdf(d1) - 1.0)
        theta = (
            -s * df_q * pdf_d1 * vol / (2.0 * sqrt_t)
            + r * k * df_r * _NORMAL.cdf(-d2)
            - q * s * df_q * _NORMAL.cdf(-d1)
        )
        rho = -k * t * df_r * _NORMAL.cdf(-d2)

    gamma = df_q * pdf_d1 / (s * vol * sqrt_t)
    vega = s * df_q * pdf_d1 * sqrt_t

    return PricingResult(
        price=to_money(pr),
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        rho=rho,
        pricer_version=PRICER_VERSION,
    )
