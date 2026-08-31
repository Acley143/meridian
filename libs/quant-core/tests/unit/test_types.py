from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from quant_core.types import (
    EuropeanOption,
    MarketState,
    OptionRight,
    PricingResult,
    validate_option_against_market,
)

_AWARE = datetime(2026, 1, 1, tzinfo=UTC)
_NAIVE = datetime(2026, 1, 1)  # noqa: DTZ001 — deliberately naive, exercises the rejection path


def test_european_option_valid() -> None:
    opt = EuropeanOption(underlying_id="X", strike=Decimal(100), expiry=_AWARE, right=OptionRight.CALL)
    assert opt.strike == Decimal(100)


def test_european_option_rejects_non_positive_strike() -> None:
    with pytest.raises(ValueError):
        EuropeanOption(underlying_id="X", strike=Decimal(0), expiry=_AWARE, right=OptionRight.CALL)
    with pytest.raises(ValueError):
        EuropeanOption(underlying_id="X", strike=Decimal(-5), expiry=_AWARE, right=OptionRight.CALL)


def test_european_option_rejects_naive_expiry() -> None:
    with pytest.raises(ValueError):
        EuropeanOption(underlying_id="X", strike=Decimal(100), expiry=_NAIVE, right=OptionRight.CALL)


def test_market_state_valid() -> None:
    ms = MarketState(spot=Decimal(100), volatility=0.2, risk_free_rate=0.05, dividend_yield=0.0, valuation_time=_AWARE)
    assert ms.volatility == 0.2


def test_market_state_rejects_non_positive_spot() -> None:
    with pytest.raises(ValueError):
        MarketState(spot=Decimal(0), volatility=0.2, risk_free_rate=0.05, dividend_yield=0.0, valuation_time=_AWARE)


def test_market_state_rejects_negative_volatility() -> None:
    with pytest.raises(ValueError):
        MarketState(spot=Decimal(100), volatility=-0.01, risk_free_rate=0.05, dividend_yield=0.0, valuation_time=_AWARE)


def test_market_state_rejects_naive_valuation_time() -> None:
    with pytest.raises(ValueError):
        MarketState(spot=Decimal(100), volatility=0.2, risk_free_rate=0.05, dividend_yield=0.0, valuation_time=_NAIVE)


def test_validate_option_against_market_rejects_expiry_before_valuation() -> None:
    opt = EuropeanOption(underlying_id="X", strike=Decimal(100), expiry=_AWARE, right=OptionRight.CALL)
    later = datetime(2026, 6, 1, tzinfo=UTC)
    market = MarketState(spot=Decimal(100), volatility=0.2, risk_free_rate=0.05, dividend_yield=0.0, valuation_time=later)
    with pytest.raises(ValueError):
        validate_option_against_market(opt, market)


def test_types_are_frozen() -> None:
    opt = EuropeanOption(underlying_id="X", strike=Decimal(100), expiry=_AWARE, right=OptionRight.CALL)
    with pytest.raises(FrozenInstanceError):
        opt.strike = Decimal(200)  # type: ignore[misc]


def test_pricing_result_construction() -> None:
    result = PricingResult(price=Decimal("10.5"), delta=0.5, gamma=0.01, vega=20.0, theta=-5.0, rho=10.0, pricer_version="0.1.0")
    assert result.pricer_version == "0.1.0"
