"""Unit tests for quant_core.pricing.american (ADR-0031): the lattice step,
rho Method B's probability, the validated domain D, the at-expiry and
deterministic (sigma = 0) branches, and one public smoke test.

Tolerances are ADR-0031's Verification table; the measured values behind
them are in docs/adr/evidence/0031.
"""
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from quant_core import PRICER_VERSION
from quant_core.pricing import american, black_scholes
from quant_core.pricing.american import (
    STEP_COUNT,
    ModelDomainError,
    _deterministic,
    _domain_violations,
    _exercise_date,
    _fixed_grid_probability,
    _lattice,
    _step_parameters,
    american_domain_violations,
)
from quant_core.types import AmericanOption, EuropeanOption, MarketState, OptionRight

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _option(strike: float, ttm_years: float, right: OptionRight) -> AmericanOption:
    expiry = _NOW + timedelta(days=ttm_years * 365)
    return AmericanOption(underlying_id="TEST", strike=Decimal(str(strike)), expiry=expiry, right=right)


def _market(spot: float, vol: float, r: float, q: float) -> MarketState:
    return MarketState(spot=Decimal(str(spot)), volatility=vol, risk_free_rate=r, dividend_yield=q, valuation_time=_NOW)


# ---------------------------------------------------------------- the step
@pytest.mark.parametrize("vol", [0.05, 0.2, 1.0, 3.0])
@pytest.mark.parametrize("t", [0.01, 1.0, 10.0])
@pytest.mark.parametrize("r", [-0.1, 0.3])
@pytest.mark.parametrize("q", [0.0, 0.3])
def test_forward_identity(vol: float, t: float, r: float, q: float) -> None:
    dt = t / 128
    u, d, p, _ = _step_parameters(r, q, vol, dt)
    forward = math.exp((r - q) * dt)
    assert abs(0.5 * (u + d) - forward) <= 1e-14 * forward  # round-off guard
    assert p == 0.5


_METHOD_B_GRID = [
    (vol, t, r, q)
    for vol in (0.0001, 0.001, 0.05, 0.2, 1.0)
    for t in (0.01, 1.0, 10.0)
    for r in (-0.1, 0.05, 0.3)
    for q in (0.0, 0.1, 0.3)
    if vol * math.sqrt(t / 128) >= 1e-6
]


@pytest.mark.parametrize(("vol", "t", "r", "q"), _METHOD_B_GRID)
def test_method_b_probability_at_base_rate(vol: float, t: float, r: float, q: float) -> None:
    # Exactly 1/2 in exact arithmetic; ln cosh(a) = a + log1p(e^-2a) - ln 2
    # cancels at small a, measured at up to 5.122e-10 (ADR-0031 Decision 2).
    p = _fixed_grid_probability(r, vol, t / 128, rate_eval=r)
    assert abs(p - 0.5) <= 1.1e-9


# r and q do not enter the Method B probability (x = (rate_eval - r)*dt + ln cosh a),
# so these pairs vary nothing but are the ones specified. r = -0.1 has q
# clamped to 0; that point is outside D either way (lambda ~ 28 to 88).
_ENVELOPE_RATES = [(0.0, 0.0), (0.3, 0.3), (-0.1, 0.0)]


@pytest.mark.parametrize("t", [1.0, 10.0])
@pytest.mark.parametrize(("r", "q"), _ENVELOPE_RATES)
def test_method_b_bumped_probability_envelope(t: float, r: float, q: float) -> None:
    # Evaluated at the domain's own volatility floor, read at run time, so a
    # change to VOL_MIN is exercised here. Measured envelope over the Step 1e
    # grid: [0.360246, 0.639755]; at sigma = 1e-6 the bumped p reaches 8.155.
    vol = american.VOL_MIN
    for rate_eval in (r + american.RHO_BUMP, r - american.RHO_BUMP):
        p = _fixed_grid_probability(r, vol, t / STEP_COUNT, rate_eval)
        assert 0.3 <= p <= 0.7


def test_step_count_is_pinned() -> None:
    # Regression guard: N is a model parameter (ADR-0031 Decision 1). Changing
    # it changes published prices and the validated domain, and needs a
    # PRICER_VERSION bump and a superseding ADR.
    assert STEP_COUNT == 128


# ---------------------------------------------------------------- the domain
_ALONE = [
    ("lambda", {"r": 0.1, "q": 0.0, "t": 1.0, "vol": 0.05}),
    ("sigma_root_t", {"r": 0.05, "q": 0.05, "t": 1.0, "vol": 0.6}),
    ("step_spread", {"r": 0.0, "q": 0.0, "t": 1e-6, "vol": 1e-4}),
    ("rate", {"r": 0.31, "q": 0.3, "t": 1.0, "vol": 0.2}),
    ("rate", {"r": -0.11, "q": 0.0, "t": 1.0, "vol": 0.3}),
    ("dividend_yield", {"r": 0.3, "q": 0.31, "t": 1.0, "vol": 0.2}),
    ("dividend_yield", {"r": 0.0, "q": -0.01, "t": 1.0, "vol": 0.2}),
    ("vol", {"r": 0.05, "q": 0.05, "t": 0.01, "vol": 3.1}),
    ("vol", {"r": 0.05, "q": 0.05, "t": 1.0, "vol": 5e-5}),
    ("time_to_expiry", {"r": 0.05, "q": 0.05, "t": 11.0, "vol": 0.1}),
]


@pytest.mark.parametrize(("key", "inputs"), _ALONE)
def test_each_condition_alone_gives_one_violation(key: str, inputs: dict[str, float]) -> None:
    violations = _domain_violations(n_steps=128, **inputs)
    assert len(violations) == 1
    assert violations[0].startswith(key + "=")


def test_lambda_bound_is_strict() -> None:
    r, q, t, vol = 0.1, 0.0, 0.5, 0.125
    assert abs(r - q) * math.sqrt(t / 128) / vol == 0.05  # constructed to hit the bound exactly
    assert [v for v in _domain_violations(r, q, t, vol, 128) if v.startswith("lambda=")]


def test_sigma_root_t_bound_is_strict() -> None:
    r, q, t, vol = 0.05, 0.05, 4.0, 0.25
    assert vol * math.sqrt(t) == 0.5
    assert [v for v in _domain_violations(r, q, t, vol, 128) if v.startswith("sigma_root_t=")]


def test_step_spread_bound_is_inclusive() -> None:
    r, q, t, vol = 0.0, 0.0, 0.000512, 0.0005
    assert vol * math.sqrt(t / 128) == 1e-6
    assert _domain_violations(r, q, t, vol, 128) == ()


def test_rate_and_dividend_bounds_are_inclusive() -> None:
    assert _domain_violations(0.3, 0.0, 0.5, 0.4, 128) == ()
    assert [v for v in _domain_violations(0.3 + 1e-12, 0.0, 0.5, 0.4, 128) if v.startswith("rate=")]
    assert [v for v in _domain_violations(0.0, -1e-12, 0.5, 0.4, 128) if v.startswith("dividend_yield=")]


def test_vol_and_time_bounds_are_inclusive() -> None:
    assert _domain_violations(0.05, 0.05, 1.0, 1e-4, 128) == ()
    assert _domain_violations(0.05, 0.05, 0.01, 3.0, 128) == ()
    assert [v for v in _domain_violations(0.05, 0.05, 1.0, 1e-4 * (1 - 1e-12), 128) if v.startswith("vol=")]
    assert [v for v in _domain_violations(0.05, 0.05, 0.01, 3.0 * (1 + 1e-12), 128) if v.startswith("vol=")]
    assert _domain_violations(0.05, 0.05, 10.0, 0.1, 128) == ()
    assert [v for v in _domain_violations(0.05, 0.05, 10.0 + 1e-12, 0.1, 128) if v.startswith("time_to_expiry=")]


@pytest.mark.parametrize(("t", "vol"), [(1.0, 0.0), (0.0, 0.2), (-1.0, 0.2)])
def test_domain_does_not_apply_at_zero_vol_or_expiry(t: float, vol: float) -> None:
    assert _domain_violations(0.9, -0.5, t, vol, 128) == ()


def test_price_outside_domain_raises() -> None:
    option = _option(100.0, 1.0, OptionRight.PUT)
    market = _market(100.0, 0.05, 0.3, 0.0)  # lambda ~ 0.53
    assert american_domain_violations(option, market)
    with pytest.raises(ModelDomainError) as excinfo:
        american.price(option, market)
    assert isinstance(excinfo.value, ValueError)
    assert excinfo.value.violations == american_domain_violations(option, market)
    assert excinfo.value.violations[0].startswith("lambda=")


# ---------------------------------------------------------------- T <= 0
@pytest.mark.parametrize("spot", [90.0, 100.0, 110.0])
@pytest.mark.parametrize("right", [OptionRight.CALL, OptionRight.PUT])
def test_at_expiry_matches_black_scholes(spot: float, right: OptionRight) -> None:
    market = _market(spot, 0.2, 0.05, 0.0)
    amer = AmericanOption(underlying_id="TEST", strike=Decimal(100), expiry=_NOW, right=right)
    euro = EuropeanOption(underlying_id="TEST", strike=Decimal(100), expiry=_NOW, right=right)
    assert american.price(amer, market) == black_scholes.price(euro, market)


# ---------------------------------------------------------------- sigma = 0
# The seven Step 1e cases, with the branch values printed in step1e_p4.txt:
# (label, S, K, r, q, T, is_call, i*, price, delta, theta, rho).
_STEP1E_CASES = [
    ("call ITM q>0 (early)", 110.0, 100.0, 0.02, 0.08, 1.0, True, 0, 10.0, 1.0, 0.0, 0.0),
    ("call ITM q=0", 110.0, 100.0, 0.05, 0.00, 1.0, True, 128, 14.8770575499, 1.0, -4.75614712, 95.12294245),
    ("call OTM", 90.0, 100.0, 0.02, 0.00, 1.0, True, 0, 0.0, 0.0, 0.0, 0.0),
    ("put ITM r>0 (early)", 90.0, 100.0, 0.05, 0.00, 1.0, False, 0, 10.0, -1.0, 0.0, 0.0),
    ("put OTM", 110.0, 100.0, 0.05, 0.00, 1.0, False, 0, 0.0, 0.0, 0.0, 0.0),
    ("put ITM, q>r, interior", 62.0, 100.0, 0.03, 0.05, 3.0, False, 70, 38.0802097830, -0.92124317, 0.0, -156.18304781),
    ("call ITM, q<r, interior", 120.0, 100.0, 0.05, 0.0415, 1.0, True, 60, 20.0046814320, 0.98073487, 0.0, 45.78914179),
]
_IDS = [c[0] for c in _STEP1E_CASES]


@pytest.mark.parametrize("case", _STEP1E_CASES, ids=_IDS)
def test_deterministic_branch_matches_step1e(case: tuple[str, float, float, float, float, float, bool, int, float, float, float, float]) -> None:
    _, s, k, r, q, t, c, i_star, pr, delta, theta, rho = case
    assert _exercise_date(s, k, r, q, t, c, 128)[0] == i_star
    got = _deterministic(s, k, r, q, t, c, 128)
    assert abs(got[0] - pr) <= 1e-9
    # step1e_p4.txt prints delta, theta and rho to 8 decimals.
    assert abs(got[1] - delta) <= 1e-8
    assert abs(got[3] - theta) <= 1e-8
    assert abs(got[5] - rho) <= 1e-8
    assert got[2] == 0.0 and got[4] == 0.0


@pytest.mark.parametrize("case", _STEP1E_CASES, ids=_IDS)
def test_deterministic_branch_is_the_lattice_limit(case: tuple[str, float, float, float, float, float, bool, int, float, float, float, float]) -> None:
    # This bypasses the domain on purpose: sigma = 1e-6 lies outside D.
    _, s, k, r, q, t, c = case[:7]
    vol, h = 1e-6, 1e-4
    branch = _deterministic(s, k, r, q, t, c, 128)
    price, delta, _, theta = _lattice(s, k, r, q, t, vol, c, 128)
    assert abs(price - branch[0]) <= 1e-10  # round-off guard
    assert abs(delta - branch[1]) <= 2.5e-3
    assert abs(theta - branch[3]) <= 4e-3
    # This checks the branch's rho formula against the lattice limit, so the
    # lattice rho here rebuilds the grid at r +/- h. Production rho uses the
    # fixed grid (Method B), which is undefined at this sigma: its bumped
    # probability leaves (0, 1) (p reaches 8.155), and sigma = 1e-6 is outside D.
    rebuilt_rho = (_lattice(s, k, r + h, q, t, vol, c, 128)[0] - _lattice(s, k, r - h, q, t, vol, c, 128)[0]) / (2 * h)
    if branch[5] != 0.0:
        assert abs(rebuilt_rho - branch[5]) <= 4e-3 * abs(branch[5])
    else:
        assert abs(rebuilt_rho) <= 1e-9  # round-off guard


# ---------------------------------------------------------------- public smoke test
def test_price_inside_domain() -> None:
    option = _option(100.0, 1.0, OptionRight.PUT)
    market = _market(100.0, 0.2, 0.05, 0.0)
    assert american_domain_violations(option, market) == ()
    result = american.price(option, market)
    assert result.price.is_finite()
    for greek in (result.delta, result.gamma, result.vega, result.theta, result.rho):
        assert math.isfinite(greek)
    assert result.pricer_version == PRICER_VERSION
