"""Golden tests for the American lattice (ADR-0031), at the float level.

- Against an independent CRR lattice at N=128 on the 15 Step 1d golden
  cases (american_crr_reference.json). Two of them lie outside the
  validated domain D (sigma*sqrt(T) >= 0.5), so the comparison calls the
  lattice directly rather than the domain-checked pricer.
- Against the mpmath Black-Scholes closed form where American and European
  values coincide: q = 0 calls (american_closed_form_reference.json).
- Convergence in N at the at-the-money put.

Tolerances are ADR-0031's Verification table: about twice the measured
value (docs/adr/evidence/0031/step1d_output.txt, step1f_p45.txt).
"""
import json
from pathlib import Path
from typing import Any

import pytest
from quant_core.pricing.american import STEP_COUNT, _lattice, _price_float

_HERE = Path(__file__).parent
_CRR = json.loads((_HERE / "american_crr_reference.json").read_text())
_CLOSED_FORM = json.loads((_HERE / "american_closed_form_reference.json").read_text())


def _args(case: dict[str, Any]) -> tuple[float, float, float, float, float, float, bool]:
    return (
        case["spot"],
        case["strike"],
        case["risk_free_rate"],
        case["dividend_yield"],
        case["time_to_expiry_years"],
        case["volatility"],
        case["is_call"],
    )


def _rel_or_abs(actual: float, expected: float, rel: float, abs_: float, label: str) -> None:
    err = abs(actual - expected)
    assert err <= abs_ or err <= rel * abs(expected), f"{label}: {actual} vs {expected}, abs={err}"


@pytest.mark.parametrize("case", _CRR, ids=lambda c: c["label"])
def test_against_crr(case: dict[str, Any]) -> None:
    price, delta, gamma, theta = _lattice(*_args(case), n_steps=STEP_COUNT)
    _rel_or_abs(price, case["price"], 8e-3, 1e-2, "price")
    _rel_or_abs(delta, case["delta"], 3e-3, 2e-3, "delta")
    _rel_or_abs(gamma, case["gamma"], 1.2e-2, 4e-4, "gamma")
    _rel_or_abs(theta, case["theta"], 5e-2, 8e-2, "theta")


@pytest.mark.parametrize("case", _CLOSED_FORM, ids=lambda c: c["label"])
def test_vega_and_rho_against_closed_form(case: dict[str, Any]) -> None:
    _, _, _, _, vega, rho = _price_float(*_args(case))
    assert abs(vega - case["vega"]) <= 4.4e-2 * abs(case["vega"])
    assert abs(rho - case["rho"]) <= 2.1e-3 * abs(case["rho"])


@pytest.mark.parametrize("case", _CLOSED_FORM, ids=lambda c: c["label"])
def test_converges_to_closed_form(case: dict[str, Any]) -> None:
    price = _lattice(*_args(case), n_steps=4096)[0]
    assert abs(price - case["price"]) <= 1e-4 * case["price"]


_Q0_CALLS = [(case["label"], _args(case)) for case in _CLOSED_FORM] + [
    (f"S=K=100 vol=0.2 T=1 r={r}", (100.0, 100.0, r, 0.0, 1.0, 0.2, True)) for r in (0.0, 0.05, 0.3)
]


@pytest.mark.parametrize(("label", "args"), _Q0_CALLS, ids=[c[0] for c in _Q0_CALLS])
def test_american_equals_european_for_q0_calls(label: str, args: tuple[float, float, float, float, float, float, bool]) -> None:
    american = _lattice(*args, n_steps=STEP_COUNT)[0]
    european = _lattice(*args, n_steps=STEP_COUNT, american=False)[0]
    assert abs(american - european) <= 1e-12  # round-off guard; measured 0


_ATM_PUT = (100.0, 100.0, 0.05, 0.0, 1.0, 0.2, False)


def test_convergence_at_the_money_put() -> None:
    def step(n: int) -> float:
        return abs(_lattice(*_ATM_PUT, n_steps=2 * n)[0] - _lattice(*_ATM_PUT, n_steps=n)[0])

    assert step(STEP_COUNT) <= 3.6e-3  # measured 1.76e-3
    # The same check at N = 64 fails (measured 1.86e-2), so it can fail.
    assert step(64) > 3.6e-3
