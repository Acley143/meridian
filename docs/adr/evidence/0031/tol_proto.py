"""Scratch: STEP 1b tolerance measurements. Not repo code."""
import math
import statistics
import time
from statistics import NormalDist

import mpmath
import numpy as np

_N = NormalDist()


def build(s, k, vol, r, q, t, is_call, n, scheme, american=True, greeks=False):
    dt = t / n
    if scheme == "CRR":
        u = math.exp(vol * math.sqrt(dt))
        d = 1.0 / u
        p = (math.exp((r - q) * dt) - d) / (u - d)
    else:  # Jarrow-Rudd: drift in the nodes, p = 1/2
        mu = (r - q - 0.5 * vol * vol) * dt
        u = math.exp(mu + vol * math.sqrt(dt))
        d = math.exp(mu - vol * math.sqrt(dt))
        p = 0.5
    if not 0.0 < p < 1.0:
        raise ValueError(f"{scheme} p={p} outside (0,1)")
    disc = math.exp(-r * dt)
    pu, pd = disc * p, disc * (1.0 - p)
    j = np.arange(n + 1, dtype=np.float64)
    st = s * u ** j * d ** (n - j)
    v = np.maximum(st - k, 0.0) if is_call else np.maximum(k - st, 0.0)
    keep = {}
    for i in range(n - 1, -1, -1):
        v = pd * v[:-1] + pu * v[1:]
        if american:
            ji = j[: i + 1]
            si = s * u ** ji * d ** (i - ji)
            np.maximum(v, (si - k) if is_call else (k - si), out=v)
        if greeks and i <= 2:
            keep[i] = v.copy()
    if not greeks:
        return float(v[0])
    v2, v1, v0 = keep[2], keep[1], keep[0]
    s1 = (s * d, s * u)
    s2 = (s * d * d, s * u * d, s * u * u)
    delta = (v1[1] - v1[0]) / (s1[1] - s1[0])
    gamma = ((v2[2] - v2[1]) / (s2[2] - s2[1]) - (v2[1] - v2[0]) / (s2[1] - s2[0])) / (0.5 * (s2[2] - s2[0]))
    # theta from the level-2 middle node; for JR that node sits at S*u*d != S,
    # so correct to first order with delta.
    theta = (v2[1] - delta * (s2[1] - s) - v0[0]) / (2.0 * dt)
    return float(v0[0]), float(delta), float(gamma), float(theta)


def full(s, k, vol, r, q, t, is_call, n, scheme, hv=1e-4, hr=1e-4):
    pr, de, ga, th = build(s, k, vol, r, q, t, is_call, n, scheme, greeks=True)
    ve = (build(s, k, vol + hv, r, q, t, is_call, n, scheme) - build(s, k, vol - hv, r, q, t, is_call, n, scheme)) / (2 * hv)
    rh = (build(s, k, vol, r + hr, q, t, is_call, n, scheme) - build(s, k, vol, r - hr, q, t, is_call, n, scheme)) / (2 * hr)
    return {"price": pr, "delta": de, "gamma": ga, "vega": ve, "theta": th, "rho": rh}


def mp_jr(s, k, vol, r, q, t, is_call, n):
    mpmath.mp.dps = 50
    s, k, vol, r, q, t = (mpmath.mpf(x) for x in (s, k, vol, r, q, t))
    dt = t / n
    mu = (r - q - vol * vol / 2) * dt
    u = mpmath.e ** (mu + vol * mpmath.sqrt(dt))
    d = mpmath.e ** (mu - vol * mpmath.sqrt(dt))
    disc = mpmath.e ** (-r * dt) / 2
    v = [max(s * u ** j * d ** (n - j) - k, 0) if is_call else max(k - s * u ** j * d ** (n - j), 0) for j in range(n + 1)]
    for i in range(n - 1, -1, -1):
        v = [max(disc * (v[jj] + v[jj + 1]), (s * u ** jj * d ** (i - jj) - k) if is_call else (k - s * u ** jj * d ** (i - jj))) for jj in range(i + 1)]
    return float(v[0])


def bs_mp(s, k, vol, r, q, t):
    mpmath.mp.dps = 50
    s, k, vol, r, q, t = (mpmath.mpf(x) for x in (s, k, vol, r, q, t))
    cdf = lambda x: (1 + mpmath.erf(x / mpmath.sqrt(2))) / 2
    d1 = (mpmath.log(s / k) + (r - q + vol * vol / 2) * t) / (vol * mpmath.sqrt(t))
    d2 = d1 - vol * mpmath.sqrt(t)
    return float(s * mpmath.e ** (-q * t) * cdf(d1) - k * mpmath.e ** (-r * t) * cdf(d2))


# (label, S, K, vol, r, q, T, is_call)
CASES = [
    ("put ATM 1y q0",        100.0, 100.0, 0.20, 0.05, 0.00, 1.00, False),
    ("put ITM 0.5y q0",      100.0, 110.0, 0.25, 0.03, 0.00, 0.50, False),
    ("put OTM 1y q0",        100.0,  90.0, 0.20, 0.05, 0.00, 1.00, False),
    ("put ATM 0.1y q0",      100.0, 100.0, 0.20, 0.05, 0.00, 0.10, False),
    ("put deepITM 2y q0",     80.0, 100.0, 0.25, 0.06, 0.00, 2.00, False),
    ("put ATM 3y q>0",       100.0, 100.0, 0.30, 0.04, 0.02, 3.00, False),
    ("put ATM 1y r0 q0",     100.0, 100.0, 0.20, 0.00, 0.00, 1.00, False),
    ("call ATM 1y q0",       100.0, 100.0, 0.20, 0.05, 0.00, 1.00, True),
    ("call OTM 2y q0",       100.0, 110.0, 0.15, 0.02, 0.00, 2.00, True),
    ("call ITM 0.5y q0",     100.0,  90.0, 0.25, 0.03, 0.00, 0.50, True),
    ("call ITM 1y q>0",      110.0, 100.0, 0.25, 0.02, 0.05, 1.00, True),
    ("call ATM 2y q>0",      100.0, 100.0, 0.20, 0.01, 0.03, 2.00, True),
    ("call OTM 1y q>0",      100.0, 110.0, 0.30, 0.03, 0.04, 1.00, True),
    ("call ITM 0.25y q>0",   105.0, 100.0, 0.20, 0.03, 0.06, 0.25, True),
    ("call deepITM 5y q>0", 1000.0, 500.0, 0.50, 0.10, 0.02, 5.00, True),
]
EXCLUDED = [
    ("call deepOTM 0.25y (BS golden)", 50.0, 100.0, 0.30, 0.01, 0.00, 0.25, True),
    ("put deepOTM 0.25y", 150.0, 100.0, 0.20, 0.05, 0.00, 0.25, False),
    ("put vol0.01 T0.01 (BS golden)", 100.0, 100.0, 0.01, 0.05, 0.00, 0.01, False),
]
GREEKS = ("price", "delta", "gamma", "vega", "theta", "rho")


if __name__ == "__main__":
    print("== excluded candidates (price too small for a relative tolerance) ==")
    for lab, *a in EXCLUDED:
        try:
            print(f"  {lab:32s} CRR128={build(*a, 128, 'CRR'):.3e}  JR128={build(*a, 128, 'JR'):.3e}")
        except ValueError as e:
            print(f"  {lab:32s} {e}")

    print("\n== mpmath JR (dps 50) vs numpy JR at N=128, first 3 cases ==")
    for lab, *a in CASES[:3]:
        m = mp_jr(*a, 128); f = build(*a, 128, "JR")
        print(f"  {lab:22s} mp={m:.15f} np={f:.15f} rel={abs(m-f)/m:.1e}")

    rows = []
    for lab, *a in CASES:
        crr = full(*a, 128, "CRR")
        jr = full(*a, 128, "JR")
        ref = build(*a, 16384, "JR")  # truth proxy for the price
        rows.append((lab, crr, jr, ref))

    print("\n== price: CRR N=128 vs JR N=128 (and vs JR N=16384 as a truth proxy) ==")
    print(f"{'case':22s} {'CRR128':>12} {'JR128':>12} {'abs_diff':>10} {'rel_diff':>9} | {'CRR rel err':>11} {'JR rel err':>10}")
    mx_rel = mx_abs = 0.0
    for lab, crr, jr, ref in rows:
        ad = abs(crr["price"] - jr["price"]); rd = ad / jr["price"]
        mx_rel, mx_abs = max(mx_rel, rd), max(mx_abs, ad)
        print(f"{lab:22s} {crr['price']:12.6f} {jr['price']:12.6f} {ad:10.2e} {rd:9.2e} | {abs(crr['price']-ref)/ref:11.2e} {abs(jr['price']-ref)/ref:10.2e}")
    print(f"MAX rel_diff={mx_rel:.3e}  MAX abs_diff={mx_abs:.3e}")

    print("\n== Greeks: CRR N=128 vs JR N=128, rel diff (abs diff) ==")
    print(f"{'case':22s} " + " ".join(f"{g:>20s}" for g in GREEKS[1:]))
    mx = {g: [0.0, 0.0] for g in GREEKS[1:]}
    for lab, crr, jr, _ in rows:
        cells = []
        for g in GREEKS[1:]:
            ad = abs(crr[g] - jr[g]); rd = ad / abs(jr[g]) if jr[g] else math.inf
            mx[g][0] = max(mx[g][0], rd); mx[g][1] = max(mx[g][1], ad)
            cells.append(f"{rd:9.2e} ({ad:8.2e})")
        print(f"{lab:22s} " + " ".join(f"{c:>20s}" for c in cells))
    print("MAX: " + "  ".join(f"{g}: rel {v[0]:.2e} abs {v[1]:.2e}" for g, v in mx.items()))

    print("\n== FD bump sensitivity, CRR N=128, ATM put 1y ==")
    a = CASES[0][1:]
    for h in (1e-5, 1e-4, 1e-3, 1e-2):
        f = full(*a, 128, "CRR", hv=h, hr=h)
        print(f"  bump={h:.0e}: vega={f['vega']:.6f} rho={f['rho']:.6f}")

    print("\n== anchor: CRR N=4096 American call q=0 vs mpmath Black-Scholes ==")
    for lab, *a in CASES:
        if a[-1] and a[4] == 0.0:
            s, k, vol, r, q, t, c = a
            v = build(s, k, vol, r, q, t, c, 4096, "CRR")
            b = bs_mp(s, k, vol, r, q, t)
            print(f"  {lab:22s} CRR4096={v:.10f} BS={b:.10f} abs={abs(v-b):.2e} rel={abs(v-b)/b:.2e}")
            for n in (2048, 8192):
                vv = build(s, k, vol, r, q, t, c, n, "CRR")
                print(f"      N={n}: rel={abs(vv-b)/b:.2e}")

    print("\n== runtime: one CRR N=4096 price-only build, and one per anchor case ==")
    a = CASES[7][1:]
    build(*a, 4096, "CRR")
    ts = []
    for _ in range(20):
        t0 = time.perf_counter(); build(*a, 4096, "CRR"); ts.append(time.perf_counter() - t0)
    print(f"  median {statistics.median(ts)*1e3:.1f} ms, max {max(ts)*1e3:.1f} ms")
    t0 = time.perf_counter(); mp_jr(*CASES[0][1:], 128); print(f"  mpmath JR N=128 one build: {time.perf_counter()-t0:.2f} s")
