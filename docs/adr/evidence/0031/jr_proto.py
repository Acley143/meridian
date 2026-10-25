"""Scratch: STEP 1c, Jarrow-Rudd as production. Not repo code."""
import itertools
import math
import statistics
import sys
import time
from statistics import NormalDist

import numpy as np

sys.path.insert(0, ".")
from tol_proto import CASES, build, bs_mp  # build(..., scheme="CRR"/"JR") is the reference implementation

VEGA_BUMP = RHO_BUMP = 1e-4
_N = NormalDist()


def jr(s, k, vol, r, q, t, is_call, n, american=True, greeks=False):
    """Production-shaped JR: p = 1/2, drift in the nodes, precomputed spacing powers."""
    dt = t / n
    a = vol * math.sqrt(dt)
    mu = (r - q - 0.5 * vol * vol) * dt
    half_disc = 0.5 * math.exp(-r * dt)
    spacing = np.exp(a * np.arange(-n, n + 1, dtype=np.float64))  # e^(m a), m in [-n, n]
    st = s * math.exp(n * mu) * spacing[0 : 2 * n + 1 : 2]
    v = np.maximum(st - k, 0.0) if is_call else np.maximum(k - st, 0.0)
    keep = {}
    for i in range(n - 1, -1, -1):
        v = half_disc * (v[:-1] + v[1:])
        if american:
            si = s * math.exp(i * mu) * spacing[n - i : n + i + 1 : 2]
            np.maximum(v, (si - k) if is_call else (k - si), out=v)
        if greeks and i <= 2:
            keep[i] = v.copy()
    if not greeks:
        return float(v[0])
    v2, v1, v0 = keep[2], keep[1], keep[0]
    s1 = s * math.exp(mu) * np.array([math.exp(-a), math.exp(a)])
    s2 = s * math.exp(2 * mu) * np.array([math.exp(-2 * a), 1.0, math.exp(2 * a)])
    delta = (v1[1] - v1[0]) / (s1[1] - s1[0])
    gamma = ((v2[2] - v2[1]) / (s2[2] - s2[1]) - (v2[1] - v2[0]) / (s2[1] - s2[0])) / (0.5 * (s2[2] - s2[0]))
    theta = (v2[1] - delta * (s2[1] - s) - v0[0]) / (2.0 * dt)  # middle node sits at S e^(2 mu), not S
    return float(v0[0]), float(delta), float(gamma), float(theta)


def jr_full(s, k, vol, r, q, t, is_call, n):
    pr, de, ga, th = jr(s, k, vol, r, q, t, is_call, n, greeks=True)
    ve = (jr(s, k, vol + VEGA_BUMP, r, q, t, is_call, n) - jr(s, k, vol - VEGA_BUMP, r, q, t, is_call, n)) / (2 * VEGA_BUMP)
    rh = (jr(s, k, vol, r + RHO_BUMP, q, t, is_call, n) - jr(s, k, vol, r - RHO_BUMP, q, t, is_call, n)) / (2 * RHO_BUMP)
    return {"price": pr, "delta": de, "gamma": ga, "vega": ve, "theta": th, "rho": rh}


def crr_full(s, k, vol, r, q, t, is_call, n):
    from tol_proto import full
    return full(s, k, vol, r, q, t, is_call, n, "CRR")


def bs(s, k, v, r, q, t, call):
    st = math.sqrt(t); d1 = (math.log(s / k) + (r - q + v * v / 2) * t) / (v * st); d2 = d1 - v * st
    pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi); dq = math.exp(-q * t); dr = math.exp(-r * t)
    if call:
        return {"price": s * dq * _N.cdf(d1) - k * dr * _N.cdf(d2), "delta": dq * _N.cdf(d1), "gamma": dq * pdf / (s * v * st),
                "vega": s * dq * pdf * st, "theta": -s * dq * pdf * v / (2 * st) - r * k * dr * _N.cdf(d2) + q * s * dq * _N.cdf(d1),
                "rho": k * t * dr * _N.cdf(d2)}
    return {"price": k * dr * _N.cdf(-d2) - s * dq * _N.cdf(-d1)}


def zero_vol(s, k, r, q, t, is_call, n):
    """Proposed vol=0 branch: single deterministic path on the lattice's time grid,
    backward induction with early exercise at every grid time."""
    dt = t / n
    disc = math.exp(-r * dt)
    g = math.exp((r - q) * dt)
    pay = (lambda x: x - k) if is_call else (lambda x: k - x)
    v = max(pay(s * g ** n), 0.0)
    for i in range(n - 1, -1, -1):
        v = max(disc * v, pay(s * g ** i))
    return v


def zero_vol_continuous(s, k, r, q, t, is_call):
    """Independent: sup over continuous t' in [0, T] of e^(-r t') payoff(S e^((r-q) t')),
    floored at 0, found analytically from f'(t') = 0."""
    if is_call:
        f = lambda u: s * math.exp(-q * u) - k * math.exp(-r * u)
    else:
        f = lambda u: k * math.exp(-r * u) - s * math.exp(-q * u)
    cands = [0.0, t]
    if r != q and q > 0 and r > 0:
        ts = math.log((r * k) / (q * s)) / (r - q)
        if 0.0 < ts < t:
            cands.append(ts)
    best = max(cands, key=f)
    return max(f(best), 0.0), best


if __name__ == "__main__":
    print("== (a) JR across the property-test strategy grid ==")
    vols = [1e-4, 1e-3, 0.01, 0.05, 0.2, 0.5, 1.0, 2.0, 3.0]
    rates = [-0.1, -0.05, 0.0, 0.05, 0.1, 0.3]
    divs = [0.0, 0.05, 0.1, 0.3]
    ttms = [1e-4, 0.01, 0.1, 1.0, 5.0, 10.0]
    n = 128
    crr_bad = 0
    worst = []
    total = 0
    for vol, r, q, t in itertools.product(vols, rates, divs, ttms):
        total += 1
        dt = t / n
        a = vol * math.sqrt(dt)
        u = math.exp((r - q - 0.5 * vol * vol) * dt + a); d = math.exp((r - q - 0.5 * vol * vol) * dt - a)
        assert u > d and math.isfinite(u) and math.isfinite(d) and d > 0
        cu = math.exp(a); cp = (math.exp((r - q) * dt) - 1 / cu) / (cu - 1 / cu)
        crr_bad += not (0 < cp < 1)
        # JR's p=1/2 is only first-order risk-neutral: per-step forward ratio is e^(-a^2/2) cosh(a)
        fwd_ratio = (math.exp(-0.5 * a * a) * math.cosh(a)) ** n
        worst.append((abs(1 - fwd_ratio), vol, r, q, t))
    print(f"grid points: {total}; JR p = 0.5 at all, u > d > 0 finite at all; CRR p outside (0,1) at {crr_bad}")
    worst.sort(reverse=True)
    print("JR lattice forward error |1 - E_lattice[S_T]/(S e^((r-q)T))|, worst grid points (N=128):")
    for e, vol, r, q, t in worst[:6]:
        print(f"   vol={vol:<5} T={t:<5} r={r:<5} q={q:<4}: {e:.3e}")
    for vol, t in ((0.2, 1.0), (0.5, 2.0), (1.0, 5.0), (1.0, 10.0), (2.0, 10.0), (3.0, 10.0)):
        a = vol * math.sqrt(t / n)
        print(f"   vol={vol}, T={t}: forward error {abs(1 - (math.exp(-0.5 * a * a) * math.cosh(a)) ** n):.3e}")

    print("\n   JR American call q=0 r>=0 vs Black-Scholes European (property 'American >= European'):")
    for vol, t in ((0.2, 1.0), (0.5, 2.0), (1.0, 5.0), (1.0, 10.0), (2.0, 10.0), (3.0, 10.0)):
        j = jr(100.0, 100.0, vol, 0.05, 0.0, t, True, 128); b = bs(100.0, 100.0, vol, 0.05, 0.0, t, True)["price"]
        c = build(100.0, 100.0, vol, 0.05, 0.0, t, True, 128, "CRR")
        print(f"   vol={vol} T={t}: JR={j:.6f} CRR={c:.6f} BS={b:.6f}  JR-BS={j - b:+.3e} rel={(j - b) / b:+.2e}")

    print("\n== (b) price: JR N=128 (production) vs CRR N=128 (reference) ==")
    print(f"{'case':22s} {'JR128':>12} {'CRR128':>12} {'abs_diff':>10} {'rel_diff':>9}")
    rows = []
    mx_rel = mx_abs = 0.0
    for lab, *a in CASES:
        j = jr_full(*a, 128); c = crr_full(*a, 128); rows.append((lab, a, j, c))
        ad = abs(j["price"] - c["price"]); rd = ad / c["price"]
        mx_rel = max(mx_rel, rd); mx_abs = max(mx_abs, ad)
        print(f"{lab:22s} {j['price']:12.6f} {c['price']:12.6f} {ad:10.2e} {rd:9.2e}")
    print(f"MAX rel_diff={mx_rel:.3e}  MAX abs_diff={mx_abs:.3e}")
    # sanity: production-shaped jr() == tol_proto JR build
    print("   prod-shaped JR vs tol_proto JR, max |diff|:",
          max(abs(jr(*a, 128) - build(*a, 128, "JR")) for _, *a in CASES))

    print("\n== (c) delta/gamma/theta: JR vs CRR, rel (abs) ==")
    mx = {g: [0.0, 0.0] for g in ("delta", "gamma", "theta")}
    for lab, a, j, c in rows:
        cells = []
        for g in mx:
            ad = abs(j[g] - c[g]); rd = ad / abs(c[g])
            mx[g][0] = max(mx[g][0], rd); mx[g][1] = max(mx[g][1], ad)
            cells.append(f"{g} {rd:.2e} ({ad:.2e})")
        print(f"  {lab:22s} " + "  ".join(cells))
    print("MAX: " + "  ".join(f"{g}: rel {v[0]:.2e} abs {v[1]:.2e}" for g, v in mx.items()))
    print("   vega/rho (and the rest) vs closed form, q=0 calls:")
    mxv = {g: 0.0 for g in ("delta", "gamma", "vega", "theta", "rho")}
    for lab, a, j, c in rows:
        if a[-1] and a[4] == 0.0:
            b = bs(*a[:6], True)
            for g in mxv:
                mxv[g] = max(mxv[g], abs(j[g] - b[g]) / abs(b[g]))
            print(f"  {lab:22s} " + "  ".join(f"{g} {abs(j[g] - b[g]) / abs(b[g]):.2e}" for g in mxv))
    print("MAX vs closed form: " + "  ".join(f"{g} {v:.2e}" for g, v in mxv.items()))

    print("\n== (d) anchor: JR N=4096 American call q=0 vs mpmath BS ==")
    for lab, *a in CASES:
        if a[-1] and a[4] == 0.0:
            s, k, vol, r, q, t, c = a
            b = bs_mp(s, k, vol, r, q, t)
            for nn in (2048, 4096, 8192):
                v = jr(s, k, vol, r, q, t, True, nn)
                print(f"  {lab:20s} N={nn:<5} JR={v:.10f} BS={b:.10f} rel={abs(v - b) / b:.2e}")
    print("  JR American == JR European at q=0 r>=0, N=128, max |diff| over q=0 calls:",
          max(abs(jr(*a, 128) - jr(*a, 128, american=False)) for _, *a in CASES if a[-1] and a[4] == 0.0))

    print("\n== (e) convergence: JR American put S=K=100 vol=.2 r=.05 q=0 T=1 ==")
    ref = jr(100.0, 100.0, 0.2, 0.05, 0.0, 1.0, False, 16384)
    prev = None
    for nn in (32, 64, 128, 256, 512, 1024, 2048, 4096):
        v = jr(100.0, 100.0, 0.2, 0.05, 0.0, 1.0, False, nn)
        dp = "" if prev is None else f"{v - prev:+.3e}"
        print(f"  N={nn:<5} {v:.10f} diff_vs_prev={dp:>11} err_vs_N16384={v - ref:+.3e}")
        prev = v
    print("  doubling difference |P(2N)-P(N)| at N=64 and N=128, per golden case, and ratio:")
    worst_ratio = math.inf
    for lab, *a in CASES:
        d64 = abs(jr(*a, 128) - jr(*a, 64)); d128 = abs(jr(*a, 256) - jr(*a, 128))
        worst_ratio = min(worst_ratio, d64 / d128 if d128 else math.inf)
        print(f"   {lab:22s} |P128-P64|={d64:.3e} |P256-P128|={d128:.3e} ratio={d64 / d128 if d128 else math.inf:.2f}")
    print(f"  smallest ratio (64-step diff / 128-step diff): {worst_ratio:.2f}")

    print("\n== (f) timing: JR N=128 full priced result (5 builds), American put S=K=100 ==")
    args = (100.0, 100.0, 0.2, 0.05, 0.0, 1.0, False)
    for nn in (64, 128, 256):
        for _ in range(50):
            jr_full(*args, nn)
        ts = []
        for _ in range(2000):
            t0 = time.perf_counter_ns(); jr_full(*args, nn); ts.append(time.perf_counter_ns() - t0)
        ts.sort()
        print(f"  N={nn:<4} median {statistics.median(ts) / 1e3:.1f} us  p99 {ts[int(0.99 * len(ts))] / 1e3:.1f} us  min {ts[0] / 1e3:.1f} us")

    print("\n== (g) vol=0: proposed grid branch (N=128) vs independent continuous-time max ==")
    zcases = [
        ("call ITM q>0 (early)", 110.0, 100.0, 0.02, 0.08, 1.0, True),
        ("call ITM q=0",         110.0, 100.0, 0.05, 0.00, 1.0, True),
        ("call OTM",              90.0, 100.0, 0.02, 0.00, 1.0, True),
        ("put ITM r>0 (early)",   90.0, 100.0, 0.05, 0.00, 1.0, False),
        ("put ITM interior",      95.0, 100.0, 0.05, 0.04, 2.0, False),
        ("put OTM",              110.0, 100.0, 0.05, 0.00, 1.0, False),
    ]
    for lab, s, k, r, q, t, c in zcases:
        g = zero_vol(s, k, r, q, t, c, 128)
        ind, tstar = zero_vol_continuous(s, k, r, q, t, c)
        print(f"  {lab:22s} grid={g:.10f} continuous={ind:.10f} t*={tstar:.4f} diff={g - ind:+.2e}")
