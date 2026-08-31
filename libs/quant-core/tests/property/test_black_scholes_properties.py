"""Property tests (Hypothesis) for Black-Scholes, per docs/test-strategy.md.

A property failure means the model is wrong, not just an example — these
run across wide input ranges rather than fixed cases.
"""
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from quant_core.pricing.black_scholes import price
from quant_core.types import EuropeanOption, MarketState, OptionRight

_VALUATION_TIME = datetime(2026, 1, 1, tzinfo=UTC)

_spot = st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False, allow_infinity=False)
_strike = st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False, allow_infinity=False)
_vol = st.floats(min_value=1e-4, max_value=3.0, allow_nan=False, allow_infinity=False)
_rate = st.floats(min_value=-0.1, max_value=0.3, allow_nan=False, allow_infinity=False)
_div = st.floats(min_value=0.0, max_value=0.3, allow_nan=False, allow_infinity=False)
_ttm_years = st.floats(min_value=1e-4, max_value=10.0, allow_nan=False, allow_infinity=False)


def _market(spot: float, vol: float, r: float, q: float) -> MarketState:
    return MarketState(
        spot=Decimal(str(spot)),
        volatility=vol,
        risk_free_rate=r,
        dividend_yield=q,
        valuation_time=_VALUATION_TIME,
    )


def _option(strike: float, ttm_years: float, right: OptionRight) -> EuropeanOption:
    expiry = _VALUATION_TIME + timedelta(days=ttm_years * 365.25)
    return EuropeanOption(underlying_id="TEST", strike=Decimal(str(strike)), expiry=expiry, right=right)


@settings(max_examples=200)
@given(spot=_spot, strike=_strike, vol=_vol, r=_rate, q=_div, ttm=_ttm_years)
def test_put_call_parity(spot: float, strike: float, vol: float, r: float, q: float, ttm: float) -> None:
    market = _market(spot, vol, r, q)
    call = price(_option(strike, ttm, OptionRight.CALL), market)
    put = price(_option(strike, ttm, OptionRight.PUT), market)

    lhs = float(call.price) - float(put.price)
    rhs = spot * math.exp(-q * ttm) - strike * math.exp(-r * ttm)
    scale = max(1.0, abs(rhs))
    assert abs(lhs - rhs) / scale < 1e-4


@settings(max_examples=200)
@given(spot=_spot, strike=_strike, vol=_vol, r=_rate, q=_div, ttm=_ttm_years)
def test_call_delta_bounds(spot: float, strike: float, vol: float, r: float, q: float, ttm: float) -> None:
    market = _market(spot, vol, r, q)
    result = price(_option(strike, ttm, OptionRight.CALL), market)
    assert -1e-9 <= result.delta <= 1.0 + 1e-9


@settings(max_examples=200)
@given(spot=_spot, strike=_strike, vol=_vol, r=_rate, q=_div, ttm=_ttm_years)
def test_put_delta_bounds(spot: float, strike: float, vol: float, r: float, q: float, ttm: float) -> None:
    market = _market(spot, vol, r, q)
    result = price(_option(strike, ttm, OptionRight.PUT), market)
    assert -1.0 - 1e-9 <= result.delta <= 1e-9


@settings(max_examples=200)
@given(spot=_spot, strike=_strike, vol=_vol, r=_rate, q=_div, ttm=_ttm_years, is_call=st.booleans())
def test_gamma_and_vega_non_negative(spot: float, strike: float, vol: float, r: float, q: float, ttm: float, is_call: bool) -> None:
    market = _market(spot, vol, r, q)
    right = OptionRight.CALL if is_call else OptionRight.PUT
    result = price(_option(strike, ttm, right), market)
    assert result.gamma >= -1e-12
    assert result.vega >= -1e-12


@settings(max_examples=200)
@given(spot=_spot, strike=_strike, r=_rate, q=_div, ttm=_ttm_years, is_call=st.booleans(), vol_low=_vol, vol_delta=st.floats(min_value=1e-4, max_value=1.0))
def test_price_monotonic_in_volatility(spot: float, strike: float, r: float, q: float, ttm: float, is_call: bool, vol_low: float, vol_delta: float) -> None:
    right = OptionRight.CALL if is_call else OptionRight.PUT
    option = _option(strike, ttm, right)
    vol_high = vol_low + vol_delta

    price_low = price(option, _market(spot, vol_low, r, q))
    price_high = price(option, _market(spot, vol_high, r, q))

    assert float(price_high.price) >= float(price_low.price) - 1e-8


@settings(max_examples=200)
@given(spot=_spot, strike=_strike, vol=_vol, r=_rate, q=_div, ttm=_ttm_years, is_call=st.booleans())
def test_price_at_least_forward_discounted_intrinsic(spot: float, strike: float, vol: float, r: float, q: float, ttm: float, is_call: bool) -> None:
    # The no-arbitrage floor for a *European* option under a continuous
    # dividend yield is intrinsic value on the discounted forward
    # (S*e^-qT, K*e^-rT), not raw (spot - strike): a positive dividend
    # yield means the option holder forgoes dividends a direct holder of
    # the underlying would receive, so price can legitimately fall below
    # max(spot - strike, 0) when q is large relative to r. See PLAN.md
    # open questions.
    right = OptionRight.CALL if is_call else OptionRight.PUT
    market = _market(spot, vol, r, q)
    result = price(_option(strike, ttm, right), market)

    forward_spot = spot * math.exp(-q * ttm)
    disc_strike = strike * math.exp(-r * ttm)
    floor = max(forward_spot - disc_strike, 0.0) if is_call else max(disc_strike - forward_spot, 0.0)
    assert float(result.price) >= floor - 1e-6 * max(1.0, floor)


@settings(max_examples=200)
@given(spot=_spot, strike=_strike, vol=_vol, r=_rate, q=_div, is_call=st.booleans())
def test_price_approaches_intrinsic_as_t_to_zero(spot: float, strike: float, vol: float, r: float, q: float, is_call: bool) -> None:
    right = OptionRight.CALL if is_call else OptionRight.PUT
    market = _market(spot, vol, r, q)
    result = price(_option(strike, 0.0, right), market)

    intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    assert abs(float(result.price) - intrinsic) < 1e-6


@settings(max_examples=200)
@given(spot=_spot, vol=_vol, r=_rate, q=_div, ttm=_ttm_years, strike_low=_strike, strike_delta=st.floats(min_value=1e-3, max_value=100.0))
def test_call_price_monotonic_non_increasing_in_strike(spot: float, vol: float, r: float, q: float, ttm: float, strike_low: float, strike_delta: float) -> None:
    strike_high = strike_low + strike_delta
    market = _market(spot, vol, r, q)

    price_low_k = price(_option(strike_low, ttm, OptionRight.CALL), market)
    price_high_k = price(_option(strike_high, ttm, OptionRight.CALL), market)

    assert float(price_high_k.price) <= float(price_low_k.price) + 1e-8
