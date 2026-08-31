#!/usr/bin/env python3
"""Generate tests/golden/black_scholes_reference.json.

This is the "independent implementation" required by docs/test-strategy.md
for a golden test: it is deliberately NOT quant_core.pricing.black_scholes.
It re-derives Black-Scholes price and Greeks from first principles using
mpmath's arbitrary-precision `erf` for the normal CDF (50 decimal digits of
working precision, rounded down to float64 on output), rather than
statistics.NormalDist as production code does. A bug shared by both
implementations is unlikely: they use different libraries for the one
numerically delicate piece (the normal CDF) and were written independently
against the closed-form formulas.

Re-run this script and commit the diff whenever the case list below changes.
Do not hand-edit the generated JSON.
"""
import json
from pathlib import Path
from typing import Any

import mpmath  # type: ignore[import-untyped]

mpmath.mp.dps = 50


def _norm_cdf(x: Any) -> Any:
    return (1 + mpmath.erf(x / mpmath.sqrt(2))) / 2


def _norm_pdf(x: Any) -> Any:
    return mpmath.e ** (-x * x / 2) / mpmath.sqrt(2 * mpmath.pi)


def price_and_greeks(
    s_: float, k_: float, vol_: float, r_: float, q_: float, t_: float, is_call: bool
) -> dict[str, float]:
    s, k, vol, r, q, t = (mpmath.mpf(x) for x in (s_, k_, vol_, r_, q_, t_))
    sqrt_t = mpmath.sqrt(t)
    d1 = (mpmath.log(s / k) + (r - q + vol * vol / 2) * t) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    df_r = mpmath.e ** (-r * t)
    df_q = mpmath.e ** (-q * t)
    pdf_d1 = _norm_pdf(d1)

    if is_call:
        pr = s * df_q * _norm_cdf(d1) - k * df_r * _norm_cdf(d2)
        delta = df_q * _norm_cdf(d1)
        theta = (
            -s * df_q * pdf_d1 * vol / (2 * sqrt_t)
            - r * k * df_r * _norm_cdf(d2)
            + q * s * df_q * _norm_cdf(d1)
        )
        rho = k * t * df_r * _norm_cdf(d2)
    else:
        pr = k * df_r * _norm_cdf(-d2) - s * df_q * _norm_cdf(-d1)
        delta = df_q * (_norm_cdf(d1) - 1)
        theta = (
            -s * df_q * pdf_d1 * vol / (2 * sqrt_t)
            + r * k * df_r * _norm_cdf(-d2)
            - q * s * df_q * _norm_cdf(-d1)
        )
        rho = -k * t * df_r * _norm_cdf(-d2)

    gamma = df_q * pdf_d1 / (s * vol * sqrt_t)
    vega = s * df_q * pdf_d1 * sqrt_t

    return {
        "price": float(pr),
        "delta": float(delta),
        "gamma": float(gamma),
        "vega": float(vega),
        "theta": float(theta),
        "rho": float(rho),
    }


# (spot, strike, volatility, risk_free_rate, dividend_yield, time_to_expiry_years, is_call)
CASES = [
    (100.0, 100.0, 0.20, 0.05, 0.00, 1.0, True),
    (100.0, 100.0, 0.20, 0.05, 0.00, 1.0, False),
    (100.0, 90.0, 0.25, 0.03, 0.01, 0.5, True),
    (100.0, 90.0, 0.25, 0.03, 0.01, 0.5, False),
    (100.0, 110.0, 0.15, 0.02, 0.00, 2.0, True),
    (100.0, 110.0, 0.15, 0.02, 0.00, 2.0, False),
    (50.0, 100.0, 0.30, 0.01, 0.00, 0.25, True),
    (50.0, 100.0, 0.30, 0.01, 0.00, 0.25, False),
    (200.0, 200.0, 0.40, 0.00, 0.05, 3.0, True),
    (200.0, 200.0, 0.40, 0.00, 0.05, 3.0, False),
    (100.0, 100.0, 0.01, 0.05, 0.00, 0.01, True),
    (100.0, 100.0, 0.01, 0.05, 0.00, 0.01, False),
    (1000.0, 500.0, 0.50, 0.10, 0.02, 5.0, True),
    (1000.0, 500.0, 0.50, 0.10, 0.02, 5.0, False),
]


def main() -> None:
    out = []
    for s, k, vol, r, q, t, is_call in CASES:
        result = price_and_greeks(s, k, vol, r, q, t, is_call)
        out.append(
            {
                "spot": s,
                "strike": k,
                "volatility": vol,
                "risk_free_rate": r,
                "dividend_yield": q,
                "time_to_expiry_years": t,
                "is_call": is_call,
                **result,
            }
        )

    target = Path(__file__).parent / "black_scholes_reference.json"
    target.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {len(out)} cases to {target}")


if __name__ == "__main__":
    main()
