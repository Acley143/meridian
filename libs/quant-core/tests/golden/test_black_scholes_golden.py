"""Golden tests: quant_core's Black-Scholes against an independently
derived reference (see generate_reference_values.py).

Pass criterion: 1e-6 relative error, per docs/nfr-budget.md.
"""
import json
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from quant_core.pricing.black_scholes import price
from quant_core.types import EuropeanOption, MarketState, OptionRight

_VALUATION_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_REFERENCE = json.loads((Path(__file__).parent / "black_scholes_reference.json").read_text())
_REL_TOL = 1e-6
# Money is quantised to scale 8 (ADR-0013); relative error on a price near
# that granularity (e.g. a deep-OTM option worth a few millionths) is
# dominated by quantisation, not model error, so also accept a small
# absolute error floor at the money scale.
_ABS_TOL = 5e-8


def _build(case: dict[str, Any]) -> tuple[EuropeanOption, MarketState]:
    expiry = _VALUATION_TIME + timedelta(days=case["time_to_expiry_years"] * 365)
    option = EuropeanOption(
        underlying_id="TEST",
        strike=Decimal(str(case["strike"])),
        expiry=expiry,
        right=OptionRight.CALL if case["is_call"] else OptionRight.PUT,
    )
    market = MarketState(
        spot=Decimal(str(case["spot"])),
        volatility=case["volatility"],
        risk_free_rate=case["risk_free_rate"],
        dividend_yield=case["dividend_yield"],
        valuation_time=_VALUATION_TIME,
    )
    return option, market


def _assert_close(actual: float, expected: float, label: str) -> None:
    abs_err = abs(actual - expected)
    if abs_err <= _ABS_TOL:
        return
    rel_err = abs_err / abs(expected) if expected != 0.0 else math.inf
    assert rel_err <= _REL_TOL, f"{label}: {actual} vs {expected}, rel_err={rel_err}, abs_err={abs_err}"


@pytest.mark.parametrize("case", _REFERENCE, ids=lambda c: f"S={c['spot']}_K={c['strike']}_call={c['is_call']}")
def test_golden(case: dict[str, Any]) -> None:
    option, market = _build(case)
    result = price(option, market)

    _assert_close(float(result.price), case["price"], "price")
    _assert_close(result.delta, case["delta"], "delta")
    _assert_close(result.gamma, case["gamma"], "gamma")
    _assert_close(result.vega, case["vega"], "vega")
    _assert_close(result.theta, case["theta"], "theta")
    _assert_close(result.rho, case["rho"], "rho")
