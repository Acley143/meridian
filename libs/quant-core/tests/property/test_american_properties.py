"""Property tests (Hypothesis) for the American lattice (ADR-0031), at the
float level, on inputs inside the validated domain D.

Ranges are Step 1f's sampled ranges (K = 100; log-uniform S/K, vol and T;
uniform r and q); points outside D are discarded with assume(). Bounds are
ADR-0031's Verification table.
"""
import math

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from quant_core.pricing.american import STEP_COUNT, _domain_violations, _lattice

_K = 100.0


def _log_uniform(lo: float, hi: float) -> st.SearchStrategy[float]:
    return st.floats(min_value=math.log(lo), max_value=math.log(hi), allow_nan=False, allow_infinity=False).map(math.exp)


_moneyness = _log_uniform(0.25, 4.0)
_vol = _log_uniform(1e-4, 3.0)
_ttm = _log_uniform(1e-4, 10.0)
_rate = st.floats(min_value=-0.1, max_value=0.3, allow_nan=False, allow_infinity=False)
_div = st.floats(min_value=0.0, max_value=0.3, allow_nan=False, allow_infinity=False)


def _in_domain(vol: float, r: float, q: float, t: float) -> bool:
    return _domain_violations(r, q, t, vol, STEP_COUNT) == ()


# derandomize=True: Hypothesis draws the same examples on every run, so a
# property that passes in review passes in CI and a failure reproduces on the
# first rerun. It trades away finding new counterexamples on later runs.
_SETTINGS = settings(max_examples=200, derandomize=True)


@_SETTINGS
@given(sk=_moneyness, vol=_vol, t=_ttm, r=_rate, q=_div, is_call=st.booleans())
def test_american_at_least_european_on_the_same_tree(sk: float, vol: float, t: float, r: float, q: float, is_call: bool) -> None:
    assume(_in_domain(vol, r, q, t))
    args = (sk * _K, _K, r, q, t, vol, is_call)
    assert _lattice(*args, n_steps=STEP_COUNT)[0] >= _lattice(*args, n_steps=STEP_COUNT, american=False)[0]


@_SETTINGS
@given(sk=_moneyness, vol=_vol, t=_ttm, r=_rate, q=_div, is_call=st.booleans())
def test_american_at_least_intrinsic(sk: float, vol: float, t: float, r: float, q: float, is_call: bool) -> None:
    assume(_in_domain(vol, r, q, t))
    s = sk * _K
    intrinsic = max((s - _K) if is_call else (_K - s), 0.0)
    assert _lattice(s, _K, r, q, t, vol, is_call, STEP_COUNT)[0] >= intrinsic


@_SETTINGS
@given(sk=_moneyness, vol=_vol, t=_ttm, r=_rate, q=_div, is_call=st.booleans())
def test_delta_bounds(sk: float, vol: float, t: float, r: float, q: float, is_call: bool) -> None:
    assume(_in_domain(vol, r, q, t))
    delta = _lattice(sk * _K, _K, r, q, t, vol, is_call, STEP_COUNT)[1]
    lo, hi = (0.0, 1.0) if is_call else (-1.0, 0.0)
    assert lo - 3e-10 <= delta <= hi + 3e-10


@_SETTINGS
@given(sk=_moneyness, vol=_vol, t=_ttm, r=_rate, q=_div, is_call=st.booleans())
def test_gamma_non_negative(sk: float, vol: float, t: float, r: float, q: float, is_call: bool) -> None:
    assume(_in_domain(vol, r, q, t))
    s = sk * _K
    gamma = _lattice(s, _K, r, q, t, vol, is_call, STEP_COUNT)[2]
    assert gamma * s >= -1.6e-4


@_SETTINGS
@given(sk=_moneyness, vol=_vol, t=_ttm, r=_rate, q=_div, is_call=st.booleans())
def test_monotonic_in_volatility(sk: float, vol: float, t: float, r: float, q: float, is_call: bool) -> None:
    assume(_in_domain(vol, r, q, t) and _in_domain(vol * 1.01, r, q, t))
    args = (sk * _K, _K, r, q, t)
    low = _lattice(*args, vol, is_call, STEP_COUNT)[0]
    high = _lattice(*args, vol * 1.01, is_call, STEP_COUNT)[0]
    assert high >= low - 1e-12 * _K  # round-off guard
