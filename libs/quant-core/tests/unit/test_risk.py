import math

import pytest
from quant_core.risk import (
    CALENDAR_DAYS_PER_YEAR,
    Z_95,
    PositionRisk,
    delta_normal_var_95,
)
from scipy.stats import norm  # type: ignore[import-untyped]


def test_single_position_matches_hand_computed_value() -> None:
    # cash_delta 10_000 (P&L per 1% move), annual volatility 0.20:
    #   daily_vol = 0.20 / sqrt(365)            = 0.20 / 19.1049731745428 = 0.0104684784518
    #   shock     = 1.6448536269514722 * daily_vol                          = 0.0172191147501
    #   VaR       = 10_000 * 0.0172191147501 / 0.01                         = 17_219.1147501
    result = delta_normal_var_95([PositionRisk(cash_delta=10_000.0, annual_volatility=0.20)])
    assert result == pytest.approx(17_219.1147501, rel=1e-9)


def test_opposite_positions_of_equal_size_are_summed_not_netted() -> None:
    # The no-netting rule (ADR-0029 Decision 4): without correlation data a
    # long and a short cannot be shown to hedge each other, so their
    # magnitudes add. Netting to zero here would claim an unevidenced hedge.
    long_position = PositionRisk(cash_delta=10_000.0, annual_volatility=0.20)
    short_position = PositionRisk(cash_delta=-10_000.0, annual_volatility=0.20)

    single = delta_normal_var_95([long_position])
    both = delta_normal_var_95([long_position, short_position])

    assert both == pytest.approx(2 * single)
    assert both > 0.0


def test_zero_volatility_contributes_zero() -> None:
    assert delta_normal_var_95([PositionRisk(cash_delta=10_000.0, annual_volatility=0.0)]) == 0.0
    mixed = delta_normal_var_95(
        [
            PositionRisk(cash_delta=10_000.0, annual_volatility=0.0),
            PositionRisk(cash_delta=10_000.0, annual_volatility=0.20),
        ]
    )
    assert mixed == pytest.approx(17_219.1147501, rel=1e-9)


def test_empty_sequence_is_zero() -> None:
    assert delta_normal_var_95([]) == 0.0


def test_result_is_independent_of_position_sign() -> None:
    positive = delta_normal_var_95([PositionRisk(cash_delta=2_500.0, annual_volatility=0.35)])
    negative = delta_normal_var_95([PositionRisk(cash_delta=-2_500.0, annual_volatility=0.35)])
    assert positive == negative


def test_z_95_matches_scipy_normal_quantile() -> None:
    # Approximate, deliberately not `==`: the literal in `risk.py` and
    # scipy's `norm.ppf(0.95)` differ by one ULP (~2.2e-16). Agreement to 12
    # decimal places is the guard against silent drift; do not "tighten" it
    # to exact equality.
    assert Z_95 == pytest.approx(float(norm.ppf(0.95)), abs=1e-12)


def test_scaling_uses_365_calendar_days() -> None:
    assert CALENDAR_DAYS_PER_YEAR == 365
    # Volatility of sqrt(365) annual is exactly 1.0 daily, so VaR is
    # abs(cash_delta) * Z_95 / 0.01.
    result = delta_normal_var_95([PositionRisk(cash_delta=1.0, annual_volatility=math.sqrt(365))])
    assert result == pytest.approx(Z_95 / 0.01)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite_cash_delta(bad: float) -> None:
    with pytest.raises(ValueError, match="cash_delta"):
        delta_normal_var_95([PositionRisk(cash_delta=bad, annual_volatility=0.2)])


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_rejects_non_finite_volatility(bad: float) -> None:
    with pytest.raises(ValueError, match="annual_volatility"):
        delta_normal_var_95([PositionRisk(cash_delta=100.0, annual_volatility=bad)])


def test_rejects_negative_volatility() -> None:
    with pytest.raises(ValueError, match="-0.1"):
        delta_normal_var_95([PositionRisk(cash_delta=100.0, annual_volatility=-0.1)])
