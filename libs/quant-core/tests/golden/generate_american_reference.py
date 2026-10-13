#!/usr/bin/env python3
"""Generate the American-option golden fixtures (ADR-0031).

Writes three files next to this script:

- american_crr_reference.json: the 15 Step 1d golden cases priced by an
  independent Cox-Ross-Rubinstein lattice at N=128 (price, delta, gamma,
  theta). CRR is a second parameterisation, written here from scratch and
  deliberately not imported from quant_core.
- american_closed_form_reference.json: the 3 Step 1d q=0 call cases, where
  the American and European values coincide, from the mpmath closed form in
  generate_reference_values.py (50 digits).
- american_domain_reference.json: the first 2,000 points of the Step 1f
  sampler (numpy.random.default_rng(20261012), same draw order) that lie in
  the validated domain D, with the production lattice at N=4096 and N=2048
  as the convergence reference for the accuracy budget.

mpmath is imported lazily, only for the closed-form fixture, so the
freshness test can load the CRR and domain functions without it.

Re-run this script and commit the diff whenever a case list or the
production lattice changes. Do not hand-edit the generated JSON.
"""
import json
import math
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
from quant_core.pricing.american import _lattice
from quant_core.pricing.black_scholes import _time_to_expiry
from quant_core.types import AmericanOption, MarketState, OptionRight

_HERE = Path(__file__).parent
_VALUATION_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_STRIKE = 100.0
_N = 128
_SEED = 20261012
_DOMAIN_ROWS = 2000

# (label, spot, strike, volatility, risk_free_rate, dividend_yield, time_to_expiry_years, is_call)
# -- the 15 golden cases of step1d_measure.py (docs/adr/evidence/0031).
CRR_CASES = [
    ("put ATM 1y q0", 100.0, 100.0, 0.20, 0.05, 0.00, 1.00, False),
    ("put ITM 0.5y q0", 100.0, 110.0, 0.25, 0.03, 0.00, 0.50, False),
    ("put OTM 1y q0", 100.0, 90.0, 0.20, 0.05, 0.00, 1.00, False),
    ("put ATM 0.1y q0", 100.0, 100.0, 0.20, 0.05, 0.00, 0.10, False),
    ("put deepITM 2y q0", 80.0, 100.0, 0.25, 0.06, 0.00, 2.00, False),
    ("put ATM 3y q>0", 100.0, 100.0, 0.30, 0.04, 0.02, 3.00, False),
    ("put ATM 1y r0 q0", 100.0, 100.0, 0.20, 0.00, 0.00, 1.00, False),
    ("call ATM 1y q0", 100.0, 100.0, 0.20, 0.05, 0.00, 1.00, True),
    ("call OTM 2y q0", 100.0, 110.0, 0.15, 0.02, 0.00, 2.00, True),
    ("call ITM 0.5y q0", 100.0, 90.0, 0.25, 0.03, 0.00, 0.50, True),
    ("call ITM 1y q>0", 110.0, 100.0, 0.25, 0.02, 0.05, 1.00, True),
    ("call ATM 2y q>0", 100.0, 100.0, 0.20, 0.01, 0.03, 2.00, True),
    ("call OTM 1y q>0", 100.0, 110.0, 0.30, 0.03, 0.04, 1.00, True),
    ("call ITM 0.25y q>0", 105.0, 100.0, 0.20, 0.03, 0.06, 0.25, True),
    ("call deepITM 5y q>0", 1000.0, 500.0, 0.50, 0.10, 0.02, 5.00, True),
]
# The q=0 calls among them: American = European, so the closed form applies.
CLOSED_FORM_CASES = [c for c in CRR_CASES if c[7] and c[5] == 0.0]


def _inputs(case: tuple[str, float, float, float, float, float, float, bool]) -> dict[str, Any]:
    label, s, k, vol, r, q, t, is_call = case
    return {
        "label": label,
        "spot": s,
        "strike": k,
        "volatility": vol,
        "risk_free_rate": r,
        "dividend_yield": q,
        "time_to_expiry_years": t,
        "is_call": is_call,
    }


# ---------------------------------------------------------------- CRR, independent of production
def crr_greeks(s: float, k: float, vol: float, r: float, q: float, t: float, is_call: bool, n: int) -> dict[str, float]:
    """American option on a Cox-Ross-Rubinstein lattice: u = e^(vol*sqrt(dt)),
    d = 1/u, p = (e^((r-q)dt) - d)/(u - d). u*d = 1, so the step-2 middle
    node sits at S and theta is the plain step-2 difference."""
    dt = t / n
    u = math.exp(vol * math.sqrt(dt))
    d = 1.0 / u
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if not 0.0 < p < 1.0:
        raise ValueError(f"CRR probability {p} outside (0,1)")
    disc = math.exp(-r * dt)
    p_up, p_down = disc * p, disc * (1.0 - p)
    powers = s * u ** np.arange(-n, n + 1, dtype=np.float64)
    terminal = powers[0 : 2 * n + 1 : 2]
    v = np.maximum(terminal - k, 0.0) if is_call else np.maximum(k - terminal, 0.0)
    kept: dict[int, Any] = {}
    for i in range(n - 1, -1, -1):
        v = p_down * v[:-1] + p_up * v[1:]
        spots = powers[n - i : n + i + 1 : 2]
        np.maximum(v, (spots - k) if is_call else (k - spots), out=v)
        if i <= 2:
            kept[i] = v.copy()
    v2, v1, v0 = kept[2], kept[1], kept[0]
    delta = (v1[1] - v1[0]) / (s * u - s * d)
    gamma = ((v2[2] - v2[1]) / (s * u * u - s) - (v2[1] - v2[0]) / (s - s * d * d)) / (0.5 * (s * u * u - s * d * d))
    theta = (v2[1] - v0[0]) / (2.0 * dt)
    return {"price": float(v0[0]), "delta": float(delta), "gamma": float(gamma), "theta": float(theta)}


def crr_row(case: tuple[str, float, float, float, float, float, float, bool]) -> dict[str, Any]:
    _, s, k, vol, r, q, t, is_call = case
    return {**_inputs(case), **crr_greeks(s, k, vol, r, q, t, is_call, _N)}


# ---------------------------------------------------------------- mpmath closed form (lazy)
def closed_form_row(case: tuple[str, float, float, float, float, float, float, bool]) -> dict[str, Any]:
    # Imported here, not at module level: it imports mpmath (mp.dps = 50).
    from generate_reference_values import price_and_greeks

    _, s, k, vol, r, q, t, is_call = case
    return {**_inputs(case), **price_and_greeks(s, k, vol, r, q, t, is_call)}


# ---------------------------------------------------------------- domain fixture
def _in_domain_c4(vol: float, r: float, q: float, t: float) -> bool:
    """Step 1f candidate C4 = ADR-0031's D on the sampled ranges."""
    return (
        abs(r - q) * math.sqrt(t / _N) / vol < 0.05
        and vol * math.sqrt(t) < 0.5
        and vol * math.sqrt(t / _N) >= 1e-6
    )


def sampled_c4_points() -> Iterator[dict[str, Any]]:
    """Port of step1f_measure.py's Part 1 sampler: same generator, seed,
    batch size and draw order (S/K, vol, T, r, q, call). Yields, in draw
    order, every point inside C4 (C4 is a subset of C1, so the order matches
    filtering step1f's accepted C1 stream)."""
    rng = np.random.default_rng(_SEED)
    batch = 50_000
    while True:
        sk = np.exp(rng.uniform(math.log(0.25), math.log(4.0), batch))
        vol = np.exp(rng.uniform(math.log(1e-4), math.log(3.0), batch))
        t = np.exp(rng.uniform(math.log(1e-4), math.log(10.0), batch))
        r = rng.uniform(-0.1, 0.3, batch)
        q = rng.uniform(0.0, 0.3, batch)
        c = rng.random(batch) < 0.5
        for i in range(batch):
            v, rr, qq, tt = float(vol[i]), float(r[i]), float(q[i]), float(t[i])
            if _in_domain_c4(v, rr, qq, tt):
                yield {
                    "spot": float(sk[i]) * _STRIKE,
                    "strike": _STRIKE,
                    "volatility": v,
                    "risk_free_rate": rr,
                    "dividend_yield": qq,
                    "time_to_expiry_years": tt,
                    "is_call": bool(c[i]),
                }


def time_used(point: dict[str, Any]) -> float:
    """The year fraction production computes for this point: valuation
    2026-01-01Z, expiry = valuation + timedelta(days=T*365)."""
    option = AmericanOption(
        underlying_id="TEST",
        strike=Decimal(str(point["strike"])),
        expiry=_VALUATION_TIME + timedelta(days=point["time_to_expiry_years"] * 365),
        right=OptionRight.CALL if point["is_call"] else OptionRight.PUT,
    )
    market = MarketState(
        spot=Decimal(str(point["spot"])),
        volatility=point["volatility"],
        risk_free_rate=point["risk_free_rate"],
        dividend_yield=point["dividend_yield"],
        valuation_time=_VALUATION_TIME,
    )
    return _time_to_expiry(option, market)


def domain_row(point: dict[str, Any]) -> dict[str, Any]:
    t = time_used(point)
    args = (point["spot"], point["strike"], point["risk_free_rate"], point["dividend_yield"], t, point["volatility"], point["is_call"])
    p4096, d4096, _, _ = _lattice(*args, n_steps=4096)
    p2048, d2048, _, _ = _lattice(*args, n_steps=2048)
    return {**point, "t_used": t, "p4096": p4096, "p2048": p2048, "d4096": d4096, "d2048": d2048}


def domain_points() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(kept, dropped): the first 2,000 sampled C4 points still in C4 at the
    production year fraction, and any that the round trip pushed out."""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for point in sampled_c4_points():
        t = time_used(point)
        if _in_domain_c4(point["volatility"], point["risk_free_rate"], point["dividend_yield"], t):
            kept.append(point)
        else:
            dropped.append({**point, "t_used": t})
        if len(kept) == _DOMAIN_ROWS:
            return kept, dropped
    raise AssertionError("unreachable: the sampler is infinite")


def _write(name: str, rows: list[dict[str, Any]]) -> None:
    target = _HERE / name
    target.write_text(json.dumps(rows, indent=2) + "\n")
    print(f"wrote {len(rows)} rows to {target}")


def main() -> None:
    _write("american_crr_reference.json", [crr_row(c) for c in CRR_CASES])
    _write("american_closed_form_reference.json", [closed_form_row(c) for c in CLOSED_FORM_CASES])
    kept, dropped = domain_points()
    print(f"domain round trip: {len(dropped)} sampled C4 point(s) left C4 at the production year fraction: {dropped}")
    rows = [domain_row(p) for p in kept]
    for row in rows:
        assert 1e-4 <= row["volatility"] <= 3.0, row
        assert row["t_used"] <= 10.0, row
        assert -0.1 <= row["risk_free_rate"] <= 0.3, row
        assert 0.0 <= row["dividend_yield"] <= 0.3, row
    print(f"domain bounds: all {len(rows)} rows satisfy 1e-4 <= vol <= 3, t_used <= 10, -0.1 <= r <= 0.3, 0 <= q <= 0.3")
    _write("american_domain_reference.json", rows)


if __name__ == "__main__":
    main()
