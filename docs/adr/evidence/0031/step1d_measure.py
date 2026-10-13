"""STEP 1d: every measurement for ADR-0031, from one method (JR-FM). Scratch only.

Run: /Users/mac/Projects/meridian/.venv/bin/python -I -B step1d_measure.py
Read-only against the repo: imports quant_core (installed editable) for the
European _zero_vol/_at_expiry outputs, and the existing mpmath generator
libs/quant-core/tests/golden/generate_reference_values.py for closed-form
reference values. -B / dont_write_bytecode keep it from writing __pycache__.
"""
import sys

sys.dont_write_bytecode = True

import itertools
import math
import random
import statistics
import time
from statistics import NormalDist

import numpy as np

REPO = "/Users/mac/Projects/meridian"
sys.path.insert(0, f"{REPO}/libs/quant-core/tests/golden")
from generate_reference_values import price_and_greeks as mp_bs  # noqa: E402  (mpmath, 50 dps)
from quant_core.pricing.black_scholes import _at_expiry, _zero_vol  # noqa: E402

SEED = 12345  # used only by the random property sampling in 4.4 (Step 1c handling)
N_PROD = 128
H = 1e-4  # production vega/rho central-difference bump
LN2 = math.log(2.0)
_ND = NormalDist()
GRID_VOLS = [1e-4, 1e-3, 0.01, 0.05, 0.2, 0.5, 1.0, 2.0, 3.0]
GRID_RATES = [-0.1, -0.05, 0.0, 0.05, 0.1, 0.3]
GRID_DIVS = [0.0, 0.05, 0.1, 0.3]
GRID_TTMS = [1e-4, 0.01, 0.1, 1.0, 5.0, 10.0]
GRID_S = GRID_K = 100.0

# (label, S, K, vol, r, q, T, is_call) -- the 15 golden cases from STEP 1b/1c
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
# the seven vol=0 cases reported in STEP 1c section g: (label, S, K, r, q, T, is_call)
ZCASES = [
    ("call ITM q>0 (early)",    110.0, 100.0, 0.02, 0.08,   1.0, True),
    ("call ITM q=0",            110.0, 100.0, 0.05, 0.00,   1.0, True),
    ("call OTM",                 90.0, 100.0, 0.02, 0.00,   1.0, True),
    ("put ITM r>0 (early)",      90.0, 100.0, 0.05, 0.00,   1.0, False),
    ("put OTM",                 110.0, 100.0, 0.05, 0.00,   1.0, False),
    ("put ITM, q>r, interior",   62.0, 100.0, 0.03, 0.05,   3.0, False),
    ("call ITM, q<r, interior", 120.0, 100.0, 0.05, 0.0415, 1.0, True),
]


# ---------------------------------------------------------------- JR-FM lattice
def lncosh(a):
    return a + math.log1p(math.exp(-2.0 * a)) - LN2


def jrfm(s, k, vol, r, q, t, is_call, n, greeks=False, euro=False):
    """Forward-matched Jarrow-Rudd: p = 1/2, mu = (r-q)dt - ln cosh(a).
    American and (optionally) European in the SAME backward pass."""
    dt = t / n
    a = vol * math.sqrt(dt)
    mu = (r - q) * dt - lncosh(a)
    hd = 0.5 * math.exp(-r * dt)
    sp = np.exp(a * np.arange(-n, n + 1, dtype=np.float64))
    st = s * math.exp(n * mu) * sp[0 : 2 * n + 1 : 2]
    va = np.maximum(st - k, 0.0) if is_call else np.maximum(k - st, 0.0)
    ve = va.copy() if euro else None
    ka, ke = {}, {}
    for i in range(n - 1, -1, -1):
        va = hd * (va[:-1] + va[1:])
        si = s * math.exp(i * mu) * sp[n - i : n + i + 1 : 2]
        np.maximum(va, (si - k) if is_call else (k - si), out=va)
        if euro:
            ve = hd * (ve[:-1] + ve[1:])
        if greeks and i <= 2:
            ka[i] = va.copy()
            if euro:
                ke[i] = ve.copy()
    out = {"am": _tree_greeks(ka, s, a, mu, dt) if greeks else {"price": float(va[0])}}
    if euro:
        out["eu"] = _tree_greeks(ke, s, a, mu, dt) if greeks else {"price": float(ve[0])}
    return out


def _tree_greeks(kp, s, a, mu, dt):
    v2, v1, v0 = kp[2], kp[1], kp[0]
    e1, e2 = math.exp(mu), math.exp(2.0 * mu)
    ds1 = s * e1 * 2.0 * math.sinh(a)                 # s1[1]-s1[0]
    ds2_hi = s * e2 * math.expm1(2.0 * a)            # s2[2]-s2[1]
    ds2_lo = -s * e2 * math.expm1(-2.0 * a)          # s2[1]-s2[0]
    ds2_span = s * e2 * 2.0 * math.sinh(2.0 * a)     # s2[2]-s2[0]
    delta = (v1[1] - v1[0]) / ds1
    gamma = ((v2[2] - v2[1]) / ds2_hi - (v2[1] - v2[0]) / ds2_lo) / (0.5 * ds2_span)
    # Taylor-corrected step-2 theta: the middle node sits at S e^(2 mu), not S
    theta = (v2[1] - delta * s * math.expm1(2.0 * mu) - v0[0]) / (2.0 * dt)
    return {"price": float(v0[0]), "delta": float(delta), "gamma": float(gamma), "theta": float(theta)}


def jr_price(s, k, vol, r, q, t, c, n):
    return jrfm(s, k, vol, r, q, t, c, n)["am"]["price"]


def jr_full(s, k, vol, r, q, t, c, n=N_PROD, hv=H, hr=H):
    g = dict(jrfm(s, k, vol, r, q, t, c, n, greeks=True)["am"])
    g["vega"] = (jr_price(s, k, vol + hv, r, q, t, c, n) - jr_price(s, k, vol - hv, r, q, t, c, n)) / (2 * hv)
    g["rho"] = (jr_price(s, k, vol, r + hr, q, t, c, n) - jr_price(s, k, vol, r - hr, q, t, c, n)) / (2 * hr)
    return g


# ---------------------------------------------------------------- closed form (float, production-style)
def bs(s, k, v, r, q, t, c):
    dq, dr = math.exp(-q * t), math.exp(-r * t)
    if v <= 0.0:  # sigma = 0 limit, as black_scholes._zero_vol
        fwd = s * math.exp((r - q) * t)
        itm = fwd > k if c else fwd < k
        p = (s * dq - k * dr) if c else (k * dr - s * dq)
        return {"price": p if itm else 0.0, "delta": (dq if c else -dq) if itm else 0.0, "gamma": 0.0,
                "theta": ((q * s * dq - r * k * dr) if c else (r * k * dr - q * s * dq)) if itm else 0.0}
    st = math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * v * v) * t) / (v * st)
    d2 = d1 - v * st
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    if c:
        p = s * dq * _ND.cdf(d1) - k * dr * _ND.cdf(d2); de = dq * _ND.cdf(d1)
        th = -s * dq * pdf * v / (2 * st) - r * k * dr * _ND.cdf(d2) + q * s * dq * _ND.cdf(d1)
    else:
        p = k * dr * _ND.cdf(-d2) - s * dq * _ND.cdf(-d1); de = dq * (_ND.cdf(d1) - 1.0)
        th = -s * dq * pdf * v / (2 * st) + r * k * dr * _ND.cdf(-d2) - q * s * dq * _ND.cdf(-d1)
    return {"price": p, "delta": de, "gamma": dq * pdf / (s * v * st), "theta": th}


# ---------------------------------------------------------------- JR-FM with control variate
def cv_price(s, k, vol, r, q, t, c, n):
    o = jrfm(s, k, vol, r, q, t, c, n, euro=True)
    return o["am"]["price"] + bs(s, k, vol, r, q, t, c)["price"] - o["eu"]["price"]


def cv_full(s, k, vol, r, q, t, c, n=N_PROD, h=H):
    o = jrfm(s, k, vol, r, q, t, c, n, greeks=True, euro=True)
    b = bs(s, k, vol, r, q, t, c)
    g = {x: o["am"][x] - o["eu"][x] + b[x] for x in ("price", "delta", "gamma", "theta")}
    g["vega"] = (cv_price(s, k, vol + h, r, q, t, c, n) - cv_price(s, k, vol - h, r, q, t, c, n)) / (2 * h)
    g["rho"] = (cv_price(s, k, vol, r + h, q, t, c, n) - cv_price(s, k, vol, r - h, q, t, c, n)) / (2 * h)
    return g


# ---------------------------------------------------------------- CRR reference
def crr_p(vol, r, q, t, n):
    dt = t / n
    u = math.exp(vol * math.sqrt(dt))
    return (math.exp((r - q) * dt) - 1.0 / u) / (u - 1.0 / u) if u > 1.0 else float("nan")


def crr_valid(vol, r, q, t, n):
    p = crr_p(vol, r, q, t, n)
    return 0.0 < p < 1.0


def crr(s, k, vol, r, q, t, c, n, greeks=False):
    dt = t / n
    u = math.exp(vol * math.sqrt(dt)); d = 1.0 / u
    p = (math.exp((r - q) * dt) - d) / (u - d)
    assert 0.0 < p < 1.0, "caller must check crr_valid first"
    disc = math.exp(-r * dt); pu, pd = disc * p, disc * (1.0 - p)
    pw = s * u ** np.arange(-n, n + 1, dtype=np.float64)
    st = pw[0 : 2 * n + 1 : 2]
    v = np.maximum(st - k, 0.0) if c else np.maximum(k - st, 0.0)
    kp = {}
    for i in range(n - 1, -1, -1):
        v = pd * v[:-1] + pu * v[1:]
        si = pw[n - i : n + i + 1 : 2]
        np.maximum(v, (si - k) if c else (k - si), out=v)
        if greeks and i <= 2:
            kp[i] = v.copy()
    if not greeks:
        return float(v[0])
    v2, v1, v0 = kp[2], kp[1], kp[0]
    delta = (v1[1] - v1[0]) / (s * u - s * d)
    gamma = ((v2[2] - v2[1]) / (s * u * u - s) - (v2[1] - v2[0]) / (s - s * d * d)) / (0.5 * (s * u * u - s * d * d))
    theta = (v2[1] - v0[0]) / (2.0 * dt)  # CRR middle node is exactly S
    return {"price": float(v0[0]), "delta": float(delta), "gamma": float(gamma), "theta": float(theta)}


# ---------------------------------------------------------------- helpers
def stats(xs):
    a = np.asarray(xs, dtype=np.float64)
    return f"median {np.median(a):.3e}  p90 {np.percentile(a, 90):.3e}  p99 {np.percentile(a, 99):.3e}  max {a.max():.3e}  (n={a.size})"


def stats3(xs):
    a = np.asarray(xs, dtype=np.float64)
    return f"median {np.median(a):.3e}  p99 {np.percentile(a, 99):.3e}  max {a.max():.3e}  (n={a.size})"


def volT_table(rows, key):
    """rows: list of dicts with vol, t and key; print max per (vol, T)."""
    print("      vol\\T " + "".join(f"{t:>11g}" for t in GRID_TTMS))
    for v in GRID_VOLS:
        cells = [max((r[key] for r in rows if r["vol"] == v and r["t"] == t), default=float("nan")) for t in GRID_TTMS]
        print(f"  {v:>9g} " + "".join(f"{x:>11.2e}" for x in cells))


def timeit(fn, args, warm=50, reps=2000):
    for _ in range(warm):
        fn(*args)
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter_ns(); fn(*args); ts.append(time.perf_counter_ns() - t0)
    ts.sort()
    return statistics.median(ts) / 1e3, ts[int(0.99 * len(ts))] / 1e3, ts[0] / 1e3


def grid():
    for vol, r, q, t in itertools.product(GRID_VOLS, GRID_RATES, GRID_DIVS, GRID_TTMS):
        yield vol, r, q, t


def fmt_in(d):
    return (f"{'call' if d['c'] else 'put '} S={d.get('s', GRID_S):g} K={d.get('k', GRID_K):g} vol={d['vol']:g} "
            f"r={d['r']:g} q={d['q']:g} T={d['t']:g}")


if __name__ == "__main__":
    print(f"python {sys.version.split()[0]}  numpy {np.__version__}  SEED={SEED}  N_PROD={N_PROD}  H={H}")

    print("\n######## 0.5 grid axes (STEP 1c section a) ########")
    print(f"  vol  : {GRID_VOLS}\n  r    : {GRID_RATES}\n  q    : {GRID_DIVS}\n  T    : {GRID_TTMS}")
    print(f"  points: {len(GRID_VOLS)}x{len(GRID_RATES)}x{len(GRID_DIVS)}x{len(GRID_TTMS)} = "
          f"{len(GRID_VOLS) * len(GRID_RATES) * len(GRID_DIVS) * len(GRID_TTMS)}; STEP 1c's grid had no S/K axis -- "
          f"Parts 2 and 4 use S=K={GRID_S:g}")
    print("  lncosh stable vs math.log(math.cosh): " + ", ".join(
        f"a={a:g}: {abs(lncosh(a) - math.log(math.cosh(a))):.1e}" for a in (1e-10, 1e-6, 1e-3, 0.1, 1.0, 5.0)))

    # ============================================================ PART 1
    print("\n######## 1.1 price: JR-FM N=128 vs CRR N=128, golden cases ########")
    excl = [lab for lab, s, k, v, r, q, t, c in CASES if not crr_valid(v, r, q, t, N_PROD)]
    print(f"  CRR-invalid golden cases excluded: {len(excl)} {excl}")
    rows = []
    print(f"{'case':22s} {'JRFM128':>12} {'CRR128':>12} {'abs_diff':>10} {'rel_diff':>9}")
    for lab, *a in CASES:
        if lab in excl:
            continue
        j = jr_full(*a); cr = crr(*a, N_PROD, greeks=True)
        rows.append((lab, a, j, cr))
        ad = abs(j["price"] - cr["price"])
        print(f"{lab:22s} {j['price']:12.6f} {cr['price']:12.6f} {ad:10.2e} {ad / cr['price']:9.2e}")
    print(f"MAX rel_diff={max(abs(j['price'] - cr['price']) / cr['price'] for _, _, j, cr in rows):.3e}  "
          f"MAX abs_diff={max(abs(j['price'] - cr['price']) for _, _, j, cr in rows):.3e}")

    print("\n######## 1.2 delta/gamma/theta: JR-FM vs CRR N=128, rel (abs) ########")
    mx = {g: [0.0, 0.0] for g in ("delta", "gamma", "theta")}
    for lab, a, j, cr in rows:
        cells = []
        for g in mx:
            ad = abs(j[g] - cr[g]); rd = ad / abs(cr[g])
            mx[g][0] = max(mx[g][0], rd); mx[g][1] = max(mx[g][1], ad)
            cells.append(f"{g} {rd:.2e} ({ad:.2e})")
        print(f"  {lab:22s} " + "  ".join(cells))
    print("MAX: " + "  ".join(f"{g}: rel {v[0]:.2e} abs {v[1]:.2e}" for g, v in mx.items()))

    print("\n######## 1.3 all five Greeks: JR-FM N=128 vs mpmath closed form, q=0 calls ########")
    mxv = {g: [0.0, 0.0] for g in ("delta", "gamma", "vega", "theta", "rho")}
    for lab, a, j, _ in rows:
        s, k, v, r, q, t, c = a
        if c and q == 0.0:
            m = mp_bs(s, k, v, r, q, t, True)
            cells = []
            for g in mxv:
                ad = abs(j[g] - m[g]); rd = ad / abs(m[g])
                mxv[g][0] = max(mxv[g][0], rd); mxv[g][1] = max(mxv[g][1], ad)
                cells.append(f"{g} {rd:.2e} ({ad:.2e})")
            print(f"  {lab:20s} " + "  ".join(cells))
    print("MAX vs closed form: " + "  ".join(f"{g}: rel {v[0]:.2e} abs {v[1]:.2e}" for g, v in mxv.items()))

    print("\n######## 1.4 anchor: JR-FM N=4096 vs mpmath BS, q=0 calls; same-N identity ########")
    for lab, s, k, v, r, q, t, c in CASES:
        if c and q == 0.0:
            m = mp_bs(s, k, v, r, q, t, True)["price"]
            for n in (2048, 4096, 8192):
                p = jr_price(s, k, v, r, q, t, c, n)
                print(f"  {lab:20s} N={n:<5} JRFM={p:.10f} BS={m:.10f} rel={abs(p - m) / m:.2e}")
    ident = [abs(o["am"]["price"] - o["eu"]["price"]) for o in
             (jrfm(s, k, v, r, q, t, c, N_PROD, euro=True) for _, s, k, v, r, q, t, c in CASES if c and q == 0.0 and r >= 0.0)]
    print(f"  same-N identity N=128, q=0 r>=0 calls: max |American - European| = {max(ident):.3e}")

    print("\n######## 1.5 convergence: JR-FM American put S=K=100 vol=.2 r=.05 q=0 T=1 ########")
    put = (100.0, 100.0, 0.2, 0.05, 0.0, 1.0, False)
    ref = jr_price(*put, 16384)
    print(f"  reference N=16384: {ref:.10f}")
    prev = None
    conv = {}
    for n in (16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
        p = jr_price(*put, n); conv[n] = p
        dp = "" if prev is None else f"{p - prev:+.3e}"
        print(f"  N={n:<5} {p:.10f} diff_vs_prev={dp:>11} err_vs_N16384={p - ref:+.3e}")
        prev = p
    print(f"  bound expression |P(2N)-P(N)|: at N=128 = {abs(conv[256] - conv[128]):.4e};  at N=64 = {abs(conv[128] - conv[64]):.4e}")

    print("\n######## 1.6 timing: JR-FM full priced result (5 builds), ATM put ########")
    for n in (64, 128, 256):
        med, p99, mn = timeit(jr_full, (100.0, 100.0, 0.2, 0.05, 0.0, 1.0, False, n))
        print(f"  N={n:<4} median {med:.1f} us  p99 {p99:.1f} us  min {mn:.1f} us")

    # ============================================================ PART 2 (+ cache for PART 4)
    print("\n######## PART 2: discretisation error over the grid, S=K=100, JR-FM ########")
    g2 = []
    for vol, r, q, t in grid():
        for c in (True, False):
            o128 = jrfm(GRID_S, GRID_K, vol, r, q, t, c, N_PROD, greeks=True, euro=True)
            o2048 = jrfm(GRID_S, GRID_K, vol, r, q, t, c, 2048, greeks=True, euro=True)
            o4096 = jrfm(GRID_S, GRID_K, vol, r, q, t, c, 4096, greeks=True, euro=True)
            b = bs(GRID_S, GRID_K, vol, r, q, t, c)["price"]
            cvp = {n: o["am"]["price"] + b - o["eu"]["price"] for n, o in ((128, o128), (2048, o2048), (4096, o4096))}
            g2.append({"vol": vol, "r": r, "q": q, "t": t, "c": c,
                       "p128": o128["am"]["price"], "p4096": o4096["am"]["price"],
                       "err_price": abs(o128["am"]["price"] - o4096["am"]["price"]) / GRID_K,
                       "err_ref": abs(o4096["am"]["price"] - o2048["am"]["price"]) / GRID_K,
                       "err_delta": abs(o128["am"]["delta"] - o4096["am"]["delta"]),
                       "err_ref_delta": abs(o4096["am"]["delta"] - o2048["am"]["delta"]),
                       "cv128": cvp[128], "cv4096": cvp[4096],
                       "err_price_cv": abs(cvp[128] - cvp[4096]) / GRID_K,
                       "err_ref_cv": abs(cvp[4096] - cvp[2048]) / GRID_K})
    print(f"  cases: {len(g2)} (1296 grid points x call/put)")
    print(f"  err_price = |P128-P4096|/K : {stats([x['err_price'] for x in g2])}")
    print(f"  err_ref   = |P4096-P2048|/K: {stats([x['err_ref'] for x in g2])}")
    print("  vol x T, max err_price:")
    volT_table(g2, "err_price")
    print("  10 worst err_price:")
    for x in sorted(g2, key=lambda z: -z["err_price"])[:10]:
        print(f"    {fmt_in(x)}  P128={x['p128']:.6f} P4096={x['p4096']:.6f} err={x['err_price']:.3e} err_ref={x['err_ref']:.2e}")
    print(f"  delta abs |D128-D4096|  : {stats([x['err_delta'] for x in g2])}")
    print(f"  delta abs |D4096-D2048| : {stats([x['err_ref_delta'] for x in g2])}")
    print("  vol x T, max delta abs error:")
    volT_table(g2, "err_delta")

    # ============================================================ PART 3
    print("\n######## PART 3: vega/rho bump size, JR-FM N=128 vs mpmath closed form, q=0 calls r>=0 over the grid ########")
    pts = [(vol, r, t) for vol, r, q, t in grid() if q == 0.0 and r >= 0.0]
    print(f"  points: {len(pts)}")
    REL_FLOOR = 1e-8
    for h in (1e-4, 1e-3, 1e-2):
        res = {"vega": [], "rho": []}
        neg = 0
        for vol, r, t in pts:
            m = mp_bs(GRID_S, GRID_K, vol, r, 0.0, t, True)
            p_rp = jr_price(GRID_S, GRID_K, vol, r + h, 0.0, t, True, N_PROD)
            p_rm = jr_price(GRID_S, GRID_K, vol, r - h, 0.0, t, True, N_PROD)
            res["rho"].append((abs((p_rp - p_rm) / (2 * h) - m["rho"]), m["rho"], vol, r, t))
            if vol - h < 0.0:
                neg += 1
                continue
            p_vp = jr_price(GRID_S, GRID_K, vol + h, r, 0.0, t, True, N_PROD)
            p_vm = jr_price(GRID_S, GRID_K, vol - h, r, 0.0, t, True, N_PROD)
            res["vega"].append((abs((p_vp - p_vm) / (2 * h) - m["vega"]), m["vega"], vol, r, t))
        print(f"  h={h:g}: vega points excluded because vol-h < 0: {neg}")
        for g, lst in res.items():
            ab = [e for e, *_ in lst]
            rl = [e / abs(ref) for e, ref, *_ in lst if abs(ref) >= REL_FLOOR]
            print(f"    {g:4s} abs: {stats3(ab)}")
            print(f"    {g:4s} rel: {stats3(rl)}  [rel only where |closed form| >= {REL_FLOOR:g}: "
                  f"{len(lst) - len(rl)} excluded]")
            for e, ref, vol, r, t in sorted(lst, key=lambda z: -z[0])[:5]:
                print(f"      worst {g}: call S=K=100 vol={vol:g} r={r:g} q=0 T={t:g}  abs={e:.3e} closed={ref:.6e}")

    # ============================================================ PART 4
    print("\n######## PART 4: JR-FM-CV  (Eu_lat computed in the SAME backward pass as Am_lat) ########")
    print("\n## 4.1 CV < intrinsic over the grid, N=128")
    under = []
    for x in g2:
        intr = max(GRID_S - GRID_K, 0.0) if x["c"] else max(GRID_K - GRID_S, 0.0)
        if x["cv128"] < intr:
            under.append(((intr - x["cv128"]) / GRID_K, x))
    for c in (True, False):
        u = [z for z in under if z[1]["c"] == c]
        w = max(u, key=lambda z: z[0]) if u else None
        print(f"  {'call' if c else 'put '}: CV < intrinsic in {len(u)} / {sum(1 for x in g2 if x['c'] == c)}"
              + (f"; worst (intr-CV)/K = {w[0]:.3e} at {fmt_in(w[1])}" if w else ""))
    print("  (grid is S=K, intrinsic is 0 everywhere; extra check at S/K = 0.5 and 2 below)")
    under2 = []
    for vol, r, q, t in grid():
        for s, c in ((50.0, False), (200.0, True)):
            cvv = cv_price(s, GRID_K, vol, r, q, t, c, N_PROD)
            intr = max(s - GRID_K, 0.0) if c else max(GRID_K - s, 0.0)
            if cvv < intr:
                under2.append(((intr - cvv) / GRID_K, {"s": s, "vol": vol, "r": r, "q": q, "t": t, "c": c, "cv": cvv}))
    for c in (True, False):
        u = [z for z in under2 if z[1]["c"] == c]
        w = max(u, key=lambda z: z[0]) if u else None
        print(f"  ITM {'call S=200' if c else 'put S=50 '}: CV < intrinsic in {len(u)} / 1296"
              + (f"; worst (intr-CV)/K = {w[0]:.3e} at {fmt_in(w[1])} CV={w[1]['cv']:.6f}" if w else ""))

    print("\n## 4.2 err_price_cv = |CV128 - CV4096|/K over the grid")
    print(f"  err_price_cv : {stats([x['err_price_cv'] for x in g2])}")
    print(f"  err_ref_cv = |CV4096-CV2048|/K: {stats([x['err_ref_cv'] for x in g2])}")
    print("  vol x T, max err_price_cv:")
    volT_table(g2, "err_price_cv")

    print("\n## 4.3 rho/vega on PUTS: JR-FM and CV at N=128 vs CRR N=4096 (rho h=1e-4, vega h=1e-3), CRR-valid only")
    NREF = 4096
    reasons = {"vol-1e-3 < 0": 0, "CRR p outside (0,1) at a bumped input": 0}
    out43 = {"JR-FM vega": [], "JR-FM rho": [], "CV vega": [], "CV rho": []}
    for vol, r, q, t in grid():
        if vol - 1e-3 < 0.0:
            reasons["vol-1e-3 < 0"] += 1
            continue
        bumped = [(vol + 1e-3, r), (vol - 1e-3, r), (vol, r + 1e-4), (vol, r - 1e-4)]
        if not all(crr_valid(v, rr, q, t, NREF) for v, rr in bumped):
            reasons["CRR p outside (0,1) at a bumped input"] += 1
            continue
        args = (GRID_S, GRID_K)
        ref_vega = (crr(*args, vol + 1e-3, r, q, t, False, NREF) - crr(*args, vol - 1e-3, r, q, t, False, NREF)) / 2e-3
        ref_rho = (crr(*args, vol, r + 1e-4, q, t, False, NREF) - crr(*args, vol, r - 1e-4, q, t, False, NREF)) / 2e-4
        j = jr_full(*args, vol, r, q, t, False)
        cv = cv_full(*args, vol, r, q, t, False)
        key = {"vol": vol, "r": r, "q": q, "t": t}
        out43["JR-FM vega"].append((abs(j["vega"] - ref_vega), ref_vega, key))
        out43["JR-FM rho"].append((abs(j["rho"] - ref_rho), ref_rho, key))
        out43["CV vega"].append((abs(cv["vega"] - ref_vega), ref_vega, key))
        out43["CV rho"].append((abs(cv["rho"] - ref_rho), ref_rho, key))
    print(f"  grid puts: 1296; excluded: {reasons}; compared: {len(out43['CV rho'])}")
    for name, lst in out43.items():
        ab = [e for e, *_ in lst]
        rl = [e / abs(ref) for e, ref, _ in lst if abs(ref) >= REL_FLOOR]
        print(f"  {name:10s} abs: {stats3(ab)}")
        print(f"  {name:10s} rel: {stats3(rl)}  [{len(lst) - len(rl)} excluded, |ref| < {REL_FLOOR:g}]")
        for e, ref, kk in sorted(lst, key=lambda z: -z[0])[:5]:
            print(f"      worst: put S=K=100 vol={kk['vol']:g} r={kk['r']:g} q={kk['q']:g} T={kk['t']:g}  abs={e:.3e} ref={ref:.6e}")

    print(f"\n## 4.4 properties on CV, N=128, 3000 random inputs each, random.seed({SEED}) as STEP 1c")
    U = random.uniform

    def sample(rmin=-0.1):
        return dict(s=U(1, 1e4), k=U(1, 1e4), vol=U(1e-4, 3.0), r=U(rmin, 0.3), q=U(0, 0.3), t=U(1e-4, 10.0), c=random.random() < 0.5)

    random.seed(SEED)
    M = 3000
    fails = {"CV >= BS_eu": [], "CV >= intrinsic": [], "monotonic in vol": [], "monotonic in T": []}
    for _ in range(M):  # European/intrinsic comparisons: r >= 0, as STEP 1c
        x = sample(0.0)
        a = (x["s"], x["k"], x["vol"], x["r"], x["q"], x["t"], x["c"])
        cvv = cv_price(*a, N_PROD)
        e = bs(*a)["price"]
        intr = max(x["s"] - x["k"], 0.0) if x["c"] else max(x["k"] - x["s"], 0.0)
        if cvv < e:
            fails["CV >= BS_eu"].append(((e - cvv) / x["k"], x))
        if cvv < intr:
            fails["CV >= intrinsic"].append(((intr - cvv) / x["k"], x))
    for _ in range(M):  # monotonicity: full r range, as STEP 1c
        x = sample()
        a = (x["s"], x["k"], x["vol"], x["r"], x["q"], x["t"], x["c"])
        p1 = cv_price(*a, N_PROD)
        p2 = cv_price(x["s"], x["k"], x["vol"] + U(1e-4, 1.0), x["r"], x["q"], x["t"], x["c"], N_PROD)
        p3 = cv_price(x["s"], x["k"], x["vol"], x["r"], x["q"], min(x["t"] + U(1e-3, 2.0), 12.0), x["c"], N_PROD)
        if p2 < p1:
            fails["monotonic in vol"].append(((p1 - p2) / x["k"], x))
        if p3 < p1:
            fails["monotonic in T"].append(((p1 - p3) / x["k"], x))
    for name, lst in fails.items():
        w = max(lst, key=lambda z: z[0]) if lst else None
        big = sum(1 for z in lst if z[0] > 1e-3)
        print(f"  {name:18s} failures {len(lst):4d}/{M}" + (
            f"  worst size/K {w[0]:.3e} at {fmt_in(w[1])}; failures with size/K > 1e-3: {big}" if w else ""))

    print("\n## 4.5 timing: CV full priced result N=128 (5 combined Am+Eu passes + closed form), ATM put")
    med, p99, mn = timeit(cv_full, (100.0, 100.0, 0.2, 0.05, 0.0, 1.0, False, N_PROD))
    print(f"  N=128 median {med:.1f} us  p99 {p99:.1f} us  min {mn:.1f} us")

    # ============================================================ PART 5
    print("\n######## 5.1 vol -> 0: JR-FM N=128; vega = FORWARD difference h=1e-4; rho = central h=1e-4 ########")
    for lab, s, k, r, q, t, c in ZCASES:
        z = _zero_vol(s, k, r, q, t, c)
        print(f"  {lab}  (S={s:g} K={k:g} r={r:g} q={q:g} T={t:g})")
        print(f"    {'vol':>8} {'price':>14} {'delta':>12} {'gamma':>12} {'theta':>12} {'vega(fwd)':>12} {'rho':>12}")
        for vol in (1e-2, 1e-4, 1e-6, 1e-8):
            g = dict(jrfm(s, k, vol, r, q, t, c, N_PROD, greeks=True)["am"])
            vega = (jr_price(s, k, vol + 1e-4, r, q, t, c, N_PROD) - g["price"]) / 1e-4
            rho = (jr_price(s, k, vol, r + H, q, t, c, N_PROD) - jr_price(s, k, vol, r - H, q, t, c, N_PROD)) / (2 * H)
            print(f"    {vol:>8g} {g['price']:>14.8f} {g['delta']:>12.6f} {g['gamma']:>12.4e} {g['theta']:>12.6f} {vega:>12.6f} {rho:>12.6f}")
        print(f"    {'EU _zero_vol':>8} {float(z.price):>10.8f} {z.delta:>12.6f} {z.gamma:>12.4e} {z.theta:>12.6f} {z.vega:>12.6f} {z.rho:>12.6f}")

    print("\n######## 5.2 T -> 0: JR-FM N=128, vol=.2 r=.05 q=0, S=100; vega/rho central h=1e-4 ########")
    for c in (True, False):
        for k in (90.0, 100.0, 110.0):
            z = _at_expiry(100.0, k, c)
            print(f"  {'call' if c else 'put'} K={k:g}")
            print(f"    {'T':>8} {'price':>14} {'delta':>12} {'gamma':>12} {'theta':>14} {'vega':>12} {'rho':>12}")
            for t in (1e-2, 1e-4, 1e-6, 1e-8):
                g = jr_full(100.0, k, 0.2, 0.05, 0.0, t, c)
                print(f"    {t:>8g} {g['price']:>14.8f} {g['delta']:>12.6f} {g['gamma']:>12.4e} {g['theta']:>14.4e} {g['vega']:>12.4e} {g['rho']:>12.4e}")
            print(f"    {'BS t<=0':>8} {float(z.price):>14.8f} {z.delta:>12.6f} {z.gamma:>12.4e} {z.theta:>14.4e} {z.vega:>12.4e} {z.rho:>12.4e}")
