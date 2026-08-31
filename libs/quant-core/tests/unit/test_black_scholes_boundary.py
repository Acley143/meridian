"""Named tests for each degenerate case in
quant_core.pricing.black_scholes (Task 5 of libs/quant-core/PLAN.md).

A pricer that returns NaN at expiry is a pricer that will return NaN on
demo day — these assert the mathematically correct limit, not just "does
not crash".
"""
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from quant_core.pricing.black_scholes import price
from quant_core.types import EuropeanOption, MarketState, OptionRight, PricingResult

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _option(strike: float, ttm_years: float, right: OptionRight) -> EuropeanOption:
    expiry = _NOW + timedelta(days=ttm_years * 365)
    return EuropeanOption(underlying_id="TEST", strike=Decimal(str(strike)), expiry=expiry, right=right)


def _market(spot: float, vol: float, r: float = 0.05, q: float = 0.0) -> MarketState:
    return MarketState(spot=Decimal(str(spot)), volatility=vol, risk_free_rate=r, dividend_yield=q, valuation_time=_NOW)


def _no_nan_or_inf(result: PricingResult) -> None:
    for greek in (result.delta, result.gamma, result.vega, result.theta, result.rho):
        assert math.isfinite(greek)
    assert result.price.is_finite()


# --- T = 0 -------------------------------------------------------------


def test_t_zero_itm_call_is_intrinsic_with_delta_one() -> None:
    result = price(_option(90, 0.0, OptionRight.CALL), _market(100, 0.2))
    assert result.price == Decimal("10.00000000")
    assert result.delta == 1.0
    assert result.gamma == 0.0
    assert result.vega == 0.0
    assert result.theta == 0.0
    assert result.rho == 0.0


def test_t_zero_otm_call_is_worthless_with_delta_zero() -> None:
    result = price(_option(110, 0.0, OptionRight.CALL), _market(100, 0.2))
    assert result.price == Decimal("0.00000000")
    assert result.delta == 0.0


def test_t_zero_itm_put_is_intrinsic_with_delta_minus_one() -> None:
    result = price(_option(110, 0.0, OptionRight.PUT), _market(100, 0.2))
    assert result.price == Decimal("10.00000000")
    assert result.delta == -1.0
    assert result.gamma == 0.0
    assert result.vega == 0.0


def test_t_zero_otm_put_is_worthless() -> None:
    result = price(_option(90, 0.0, OptionRight.PUT), _market(100, 0.2))
    assert result.price == Decimal("0.00000000")
    assert result.delta == 0.0


def test_t_zero_never_nan() -> None:
    _no_nan_or_inf(price(_option(100, 0.0, OptionRight.CALL), _market(100, 0.2)))


# --- sigma = 0 -----------------------------------------------------------


def test_zero_vol_itm_call_is_discounted_forward_intrinsic() -> None:
    result = price(_option(90, 1.0, OptionRight.CALL), _market(100, 0.0, r=0.05, q=0.0))
    forward = 100 * math.exp(0.05 * 1.0)
    expected = math.exp(-0.05 * 1.0) * (forward - 90)
    assert abs(float(result.price) - expected) < 1e-6
    assert result.gamma == 0.0
    assert result.vega == 0.0


def test_zero_vol_otm_call_is_worthless() -> None:
    result = price(_option(200, 1.0, OptionRight.CALL), _market(100, 0.0, r=0.05, q=0.0))
    assert result.price == Decimal("0.00000000")
    assert result.delta == 0.0


def test_zero_vol_itm_put_is_discounted_forward_intrinsic() -> None:
    result = price(_option(200, 1.0, OptionRight.PUT), _market(100, 0.0, r=0.05, q=0.0))
    forward = 100 * math.exp(0.05 * 1.0)
    expected = math.exp(-0.05 * 1.0) * (200 - forward)
    assert abs(float(result.price) - expected) < 1e-6


def test_zero_vol_never_nan() -> None:
    _no_nan_or_inf(price(_option(100, 1.0, OptionRight.CALL), _market(100, 0.0)))


# --- S -> 0 ------------------------------------------------------------
#
# S=0 itself never reaches black_scholes: MarketState validates spot > 0
# at construction (Task 4). These test the limit as S -> 0+ through the
# general formula, which needs no dedicated branch (see module docstring).


def test_near_zero_spot_call_approaches_worthless() -> None:
    result = price(_option(100, 1.0, OptionRight.CALL), _market(1e-150, 0.2))
    assert float(result.price) < 1e-6
    assert result.delta < 1e-6
    _no_nan_or_inf(result)


def test_near_zero_spot_put_approaches_discounted_strike() -> None:
    result = price(_option(100, 1.0, OptionRight.PUT), _market(1e-150, 0.2, r=0.05))
    expected = 100 * math.exp(-0.05 * 1.0)
    assert abs(float(result.price) - expected) < 1e-6
    assert abs(result.delta - (-1.0)) < 1e-6
    _no_nan_or_inf(result)


# --- deep ITM / deep OTM (general formula, no overflow) --------------------


def test_deep_itm_call_no_overflow_price_near_forward_intrinsic() -> None:
    result = price(_option(1.0, 1.0, OptionRight.CALL), _market(1_000_000.0, 0.2, r=0.05))
    _no_nan_or_inf(result)
    assert result.delta > 0.999


def test_deep_otm_call_no_overflow_near_worthless() -> None:
    result = price(_option(1_000_000.0, 1.0, OptionRight.CALL), _market(1.0, 0.2, r=0.05))
    _no_nan_or_inf(result)
    assert result.delta < 1e-6
    assert float(result.price) < 1e-6


def test_deep_itm_put_no_overflow() -> None:
    result = price(_option(1_000_000.0, 1.0, OptionRight.PUT), _market(1.0, 0.2, r=0.05))
    _no_nan_or_inf(result)
    assert result.delta < -0.999


def test_deep_otm_put_no_overflow() -> None:
    result = price(_option(1.0, 1.0, OptionRight.PUT), _market(1_000_000.0, 0.2, r=0.05))
    _no_nan_or_inf(result)
    assert float(result.price) < 1e-6


# --- no-arbitrage floor: put breaks the naive intrinsic bound even at q=0 --


def test_deep_itm_long_dated_put_breaks_naive_intrinsic_floor_at_zero_dividend() -> None:
    """S=50, K=100, r=0.10, q=0, T=5: deep ITM, long-dated, no dividend.

    "Price >= intrinsic value" (max(K-S, 0) = 50 for this put) is NOT a
    valid property here — the correct European no-arbitrage floor is
    intrinsic value on the discounted forward, max(K*e^-rT - S*e^-qT, 0),
    which for these inputs is ~10.65, far below the naive 50. A positive
    risk-free rate alone (no dividend needed) is enough to break the naive
    bound for a deep ITM, long-dated put, because the strike is only
    received at expiry, discounted, while the naive bound pretends it is
    received today. See docs/test-strategy.md and PLAN.md session log.
    """
    option = _option(100, 5.0, OptionRight.PUT)
    market = _market(50, 0.2, r=0.10, q=0.0)
    result = price(option, market)

    raw_intrinsic = max(100 - 50, 0.0)
    forward_floor = max(100 * math.exp(-0.10 * 5.0) - 50 * math.exp(0.0), 0.0)

    assert float(result.price) < raw_intrinsic, "expected the naive floor to be broken"
    assert float(result.price) >= forward_floor - 1e-6
    _no_nan_or_inf(result)
