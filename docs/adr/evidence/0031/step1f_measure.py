"""STEP 1f: validate JR-FM N=128 inside domain D(Lmax, Smax). Scratch only.

Run each shard separately (each writes step1f_<shard>.txt next to this file):
  /Users/mac/Projects/meridian/.venv/bin/python -I -B step1f_measure.py p13   # Parts 1 and 3
  /Users/mac/Projects/meridian/.venv/bin/python -I -B step1f_measure.py p2    # Part 2
  /Users/mac/Projects/meridian/.venv/bin/python -I -B step1f_measure.py p45   # Parts 4 and 5
Every random draw comes from one numpy.random.default_rng(20261012), consumed in a fixed order
(Part 1 points, 2.1 points, 2.3 points, Part 5 points) by every shard, so all shards see the
same samples. Pool.map preserves input order, so output does not depend on scheduling.
Read-only against the repo: imports only the mpmath generator
tests/golden/generate_reference_values.py; never writes bytecode.
"""
import sys

sys.dont_write_bytecode = True

import math  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402

import numpy as np  # noqa: E402

REPO = "/Users/mac/Projects/meridian"
sys.path.insert(0, f"{REPO}/libs/quant-core/tests/golden")
from generate_reference_values import price_and_greeks as mp_bs  # noqa: E402  (mpmath, 50 dps)

SEED = 20261012
HERE = os.path.dirname(os.path.abspath(__file__))
N_PROD = 128
H = 1e-4
K = 100.0
LN2 = math.log(2.0)
A_MIN = 1e-6
CANDS = [("C1", 0.1, 1.0), ("C2", 0.1, 0.5), ("C3", 0.05, 1.0), ("C4", 0.05, 0.5)]
LOOSE = {"price": (1e-2, 1e-3), "delta": 2e-2, "vega": (5e-2, 1e-3), "rho": (5e-2, 1e-3)}  # Step 1e
REL_FLOOR = 1e-8
GOLD = [  # Step 1d 1.3: (label, S, K, vol, r, q, T, is_call)
    ("call ATM 1y q0", 100.0, 100.0, 0.20, 0.05, 0.00, 1.00, True),
    ("call OTM 2y q0", 100.0, 110.0, 0.15, 0.02, 0.00, 2.00, True),
    ("call ITM 0.5y q0", 100.0, 90.0, 0.25, 0.03, 0.00, 0.50, True),
]
SRT_BINS_C1 = [(0, 0.05), (0.05, 0.2), (0.2, 0.5), (0.5, 1)]
LAM_BINS_C1 = [(0, 0.025), (0.025, 0.05), (0.05, 0.075), (0.075, 0.1)]

_OUT = None


def out(*a):
    print(*a, file=_OUT, flush=True)


# ------------------------------------------------------------------ JR-FM (Step 1d), Method B (Step 1e)
def lncosh(a):
    return a + math.log1p(math.exp(-2.0 * a)) - LN2


def _tree_greeks(kp, s, a, mu, dt):
    v2, v1, v0 = kp[2], kp[1], kp[0]
    e1, e2 = math.exp(mu), math.exp(2.0 * mu)
    ds1 = s * e1 * 2.0 * math.sinh(a)
    ds2_hi = s * e2 * math.expm1(2.0 * a)
    ds2_lo = -s * e2 * math.expm1(-2.0 * a)
    ds2_span = s * e2 * 2.0 * math.sinh(2.0 * a)
    delta = (v1[1] - v1[0]) / ds1
    gamma = ((v2[2] - v2[1]) / ds2_hi - (v2[1] - v2[0]) / ds2_lo) / (0.5 * ds2_span)
    theta = (v2[1] - delta * s * math.expm1(2.0 * mu) - v0[0]) / (2.0 * dt)  # Taylor-corrected step 2
    return {"price": float(v0[0]), "delta": float(delta), "gamma": float(gamma), "theta": float(theta)}


def jrfm(s, k, vol, r, q, t, c, n, greeks=False, euro=False, r_eval=None):
    """Forward-matched Jarrow-Rudd. American (and optionally European) in the same backward pass.
    r_eval=None: production lattice at r (p = 1/2). r_eval given: Method B fixed grid -- nodes
    (dt, u, d) from base r, probability and discount at r_eval."""
    dt = t / n
    a = vol * math.sqrt(dt)
    mu = (r - q) * dt - lncosh(a)
    if r_eval is None:
        hd = 0.5 * math.exp(-r * dt)

        def step(v):
            return hd * (v[:-1] + v[1:])
    else:
        x = (r_eval - r) * dt + lncosh(a)
        p = (math.expm1(x) - math.expm1(-a)) / (2.0 * math.sinh(a))
        disc = math.exp(-r_eval * dt)
        pu, pd = disc * p, disc * (1.0 - p)

        def step(v):
            return pd * v[:-1] + pu * v[1:]
    sp = np.exp(a * np.arange(-n, n + 1, dtype=np.float64))
    st = s * math.exp(n * mu) * sp[0 : 2 * n + 1 : 2]
    va = np.maximum(st - k, 0.0) if c else np.maximum(k - st, 0.0)
    ve = va.copy() if euro else None
    ka, ke = {}, {}
    for i in range(n - 1, -1, -1):
        va = step(va)
        si = s * math.exp(i * mu) * sp[n - i : n + i + 1 : 2]
        np.maximum(va, (si - k) if c else (k - si), out=va)
        if euro:
            ve = step(ve)
        if greeks and i <= 2:
            ka[i] = va.copy()
            if euro:
                ke[i] = ve.copy()
    res = {"am": _tree_greeks(ka, s, a, mu, dt) if greeks else {"price": float(va[0])}}
    if euro:
        res["eu"] = _tree_greeks(ke, s, a, mu, dt) if greeks else {"price": float(ve[0])}
    return res


def jp(s, k, vol, r, q, t, c, n=N_PROD, r_eval=None):
    return jrfm(s, k, vol, r, q, t, c, n, r_eval=r_eval)["am"]["price"]


def rho_B(s, k, vol, r, q, t, c, n=N_PROD):
    return (jp(s, k, vol, r, q, t, c, n, r_eval=r + H) - jp(s, k, vol, r, q, t, c, n, r_eval=r - H)) / (2 * H)


def vega_cd(s, k, vol, r, q, t, c, h, n=N_PROD):
    return (jp(s, k, vol + h, r, q, t, c, n) - jp(s, k, vol - h, r, q, t, c, n)) / (2 * h)


def full_result(s, k, vol, r, q, t, c):
    """One priced result: 5 lattice builds (Greeks pass, rho Method B x2, vega h=0.05*vol x2)."""
    g = dict(jrfm(s, k, vol, r, q, t, c, N_PROD, greeks=True)["am"])
    g["rho"] = rho_B(s, k, vol, r, q, t, c)
    g["vega"] = vega_cd(s, k, vol, r, q, t, c, 0.05 * vol)
    return g


# ------------------------------------------------------------------ CRR reference (Step 1e)
def crr_valid(vol, r, q, t, n):
    if vol <= 0.0:
        return False
    dt = t / n
    u = math.exp(vol * math.sqrt(dt))
    if not u > 1.0:
        return False
    p = (math.exp((r - q) * dt) - 1.0 / u) / (u - 1.0 / u)
    return 0.0 < p < 1.0


def crr(s, k, vol, r, q, t, c, n):
    dt = t / n
    u = math.exp(vol * math.sqrt(dt)); d = 1.0 / u
    p = (math.exp((r - q) * dt) - d) / (u - d)
    disc = math.exp(-r * dt); pu, pd = disc * p, disc * (1.0 - p)
    pw = s * u ** np.arange(-n, n + 1, dtype=np.float64)
    v = np.maximum(pw[0 : 2 * n + 1 : 2] - k, 0.0) if c else np.maximum(k - pw[0 : 2 * n + 1 : 2], 0.0)
    for i in range(n - 1, -1, -1):
        v = pd * v[:-1] + pu * v[1:]
        si = pw[n - i : n + i + 1 : 2]
        np.maximum(v, (si - k) if c else (k - si), out=v)
    return float(v[0])


# ------------------------------------------------------------------ domain
def lam(vol, r, q, t):
    return abs(r - q) * math.sqrt(t / N_PROD) / vol


def srt(vol, t):
    return vol * math.sqrt(t)


def acoef(vol, t):
    return vol * math.sqrt(t / N_PROD)


def in_cand(vol, r, q, t, lmax, smax):
    return lam(vol, r, q, t) < lmax and srt(vol, t) < smax and acoef(vol, t) >= A_MIN


def tags(vol, r, q, t):
    return tuple(in_cand(vol, r, q, t, lm, sm) for _, lm, sm in CANDS)


# ------------------------------------------------------------------ sampling
LG = math.log


def _draw(rng, n, r_lo=None, r_hi=None, r_fixed=None, q_fixed=None):
    sk = np.exp(rng.uniform(LG(0.25), LG(4.0), n))
    vol = np.exp(rng.uniform(LG(1e-4), LG(3.0), n))
    t = np.exp(rng.uniform(LG(1e-4), LG(10.0), n))
    r = np.full(n, r_fixed) if r_fixed is not None else rng.uniform(r_lo, r_hi, n)
    q = np.full(n, q_fixed) if q_fixed is not None else rng.uniform(0.0, 0.3, n)
    c = rng.random(n) < 0.5
    return sk, vol, t, r, q, c


def _rejection(rng, want, batch, **kw):
    acc, drawn = [], 0
    while len(acc) < want:
        sk, vol, t, r, q, c = _draw(rng, batch, **kw)
        for i in range(batch):
            drawn += 1
            v, rr, qq, tt = float(vol[i]), float(r[i]), float(q[i]), float(t[i])
            if in_cand(v, rr, qq, tt, 0.1, 1.0):
                x = {"sk": float(sk[i]), "s": float(sk[i]) * K, "vol": v, "r": rr, "q": qq, "t": tt, "c": bool(c[i])}
                x.update(lam=lam(v, rr, qq, tt), srt=srt(v, tt), a=acoef(v, tt), tag=tags(v, rr, qq, tt))
                acc.append(x)
                if len(acc) == want:
                    break
    return acc, drawn


def all_samples():
    rng = np.random.default_rng(SEED)
    p1, d1 = _rejection(rng, 20000, 50000, r_lo=-0.1, r_hi=0.3)
    p21, d21 = _rejection(rng, 2000, 20000, r_lo=1e-3, r_hi=0.3, q_fixed=0.0)
    for x in p21:
        x["c"] = True
    p23, d23 = _rejection(rng, 300, 5000, r_fixed=0.0, q_fixed=0.0)
    for i, x in enumerate(p23):
        x["c"] = i < 150
    n5 = 100000
    p5 = {"sk": np.exp(rng.uniform(LG(0.5), LG(2.0), n5)), "vol": np.exp(rng.uniform(LG(0.05), LG(1.0), n5)),
          "t": np.exp(rng.uniform(LG(0.01), LG(5.0), n5)), "r": rng.uniform(-0.01, 0.1, n5),
          "q": rng.uniform(0.0, 0.1, n5)}
    return {"p1": p1, "d1": d1, "p21": p21, "d21": d21, "p23": p23, "d23": d23, "p5": p5}


def sampling_header(S):
    out(f"sampling: Part 1 accepted 20000 of {S['d1']} drawn -> acceptance rate {20000 / S['d1']:.4f}")
    out(f"          2.1    accepted 2000 of {S['d21']} drawn -> acceptance rate {2000 / S['d21']:.4f}")
    out(f"          2.3    accepted 300 of {S['d23']} drawn -> acceptance rate {300 / S['d23']:.4f}")
    for ci, (nm, lm, sm) in enumerate(CANDS):
        out(f"  Part 1 points in {nm}=(Lmax={lm:g}, Smax={sm:g}): {sum(x['tag'][ci] for x in S['p1'])}"
            f"   calls {sum(x['tag'][ci] and x['c'] for x in S['p1'])}")


# ------------------------------------------------------------------ helpers
def pct(xs, p):
    return float(np.percentile(np.asarray(xs, dtype=np.float64), p)) if len(xs) else float("nan")


def fmt_pt(x):
    return (f"{'call' if x['c'] else 'put '} S={x['s']:.10g} K={K:g} vol={x['vol']:.10g} r={x['r']:.10g} "
            f"q={x['q']:.10g} T={x['t']:.10g} | lambda={x['lam']:.4g} sigmaRootT={x['srt']:.4g} a={x['a']:.4g}")


def price_bound(ref):
    rel, absk = LOOSE["price"]
    return max(rel * abs(ref), absk * K)


def greek_bound(metric, ref, t):
    rel, absk = LOOSE[metric]
    return max(rel * abs(ref), absk * K * (math.sqrt(t) if metric == "vega" else t))


def bin_of(x, bins):
    for i, (lo, hi) in enumerate(bins):
        if lo <= x < hi:
            return i
    return None


# ================================================================== PARTS 1 and 3
def p13_case(x):
    s, vol, r, q, t, c = x["s"], x["vol"], x["r"], x["q"], x["t"], x["c"]
    o = {n: jrfm(s, K, vol, r, q, t, c, n, greeks=True, euro=(n == N_PROD)) for n in (N_PROD, 2048, 4096)}
    y = dict(x)
    y.update(P128=o[128]["am"]["price"], P2048=o[2048]["am"]["price"], P4096=o[4096]["am"]["price"],
             D128=o[128]["am"]["delta"], D2048=o[2048]["am"]["delta"], D4096=o[4096]["am"]["delta"],
             G128=o[128]["am"]["gamma"], E128=o[128]["eu"]["price"],
             intrinsic=max((s - K) if c else (K - s), 0.0),
             Pup=jp(s, K, vol * 1.01, r, q, t, c), tag_up=tags(vol * 1.01, r, q, t))
    y["err_price"] = abs(y["P128"] - y["P4096"]) / K
    y["err_delta"] = abs(y["D128"] - y["D4096"])
    y["ref_price"] = abs(y["P4096"] - y["P2048"]) / K
    y["ref_delta"] = abs(y["D4096"] - y["D2048"])
    y["unres_price"] = y["ref_price"] > y["err_price"] / 3.0
    y["unres_delta"] = y["ref_delta"] > y["err_delta"] / 3.0
    y["pass_price"] = y["err_price"] * K <= price_bound(y["P4096"])
    y["pass_delta"] = y["err_delta"] <= LOOSE["delta"]
    return y


def run_p13(pool, S):
    rows = pool.map(p13_case, S["p1"], chunksize=25)
    out("\n################ PART 1 -- price and delta, JR-FM N=128 vs N=4096 (reference error: 4096 vs 2048)")
    out("  unresolved: reference error > measured error / 3 (Step 1e). LOOSE: price max(1e-2*|P4096|, 1e-3*K), delta 2e-2")
    for ci, (nm, lm, sm) in enumerate(CANDS):
        sel = [z for z in rows if z["tag"][ci]]
        rp = [z for z in sel if not z["unres_price"]]
        rd = [z for z in sel if not z["unres_delta"]]
        rb = [z for z in sel if not (z["unres_price"] or z["unres_delta"])]
        out(f"\n## {nm} (Lmax={lm:g}, Smax={sm:g}): points {len(sel)}")
        out(f"  resolved: price {len(rp)}  delta {len(rd)}  both {len(rb)}")
        np_, nd_, nb_ = (sum(z["pass_price"] for z in rp), sum(z["pass_delta"] for z in rd),
                         sum(z["pass_price"] and z["pass_delta"] for z in rb))
        out(f"  LOOSE pass over resolved: price {np_}/{len(rp)} = {np_ / max(len(rp), 1):.5f}   "
            f"delta {nd_}/{len(rd)} = {nd_ / max(len(rd), 1):.5f}   both {nb_}/{len(rb)} = {nb_ / max(len(rb), 1):.5f}")
        up = [z for z in sel if z["unres_price"]]
        if up:
            tot_k = [z["err_price"] + z["ref_price"] for z in up]
            fr = [(z["err_price"] + z["ref_price"]) * K / abs(z["P4096"]) for z in up if abs(z["P4096"]) > REL_FLOOR]
            exc = sum((z["err_price"] + z["ref_price"]) * K > price_bound(z["P4096"]) for z in up)
            out(f"  unresolved price ({len(up)}): max (err+ref)/K {max(tot_k):.3e}; max (err+ref)/|P4096| "
                f"{max(fr) if fr else float('nan'):.3e} (|P4096|>{REL_FLOOR:g}, n={len(fr)}); "
                f"exceed LOOSE price bound: {exc}")
        else:
            out("  unresolved price: 0")
        ud = [z for z in sel if z["unres_delta"]]
        if ud:
            tot = [z["err_delta"] + z["ref_delta"] for z in ud]
            exc = sum(v > LOOSE["delta"] for v in tot)
            out(f"  unresolved delta ({len(ud)}): max (err+ref) {max(tot):.3e} vs LOOSE {LOOSE['delta']:g}; exceed: {exc}")
        else:
            out("  unresolved delta: 0")
        out("  5 worst err_price:")
        for z in sorted(sel, key=lambda z: -z["err_price"])[:5]:
            out(f"    {fmt_pt(z)}  P128={z['P128']:.8g} P4096={z['P4096']:.8g} err/K={z['err_price']:.3e} "
                f"ref/K={z['ref_price']:.2e} bound/K={price_bound(z['P4096']) / K:.2e}"
                f"{' UNRESOLVED' if z['unres_price'] else ''}{'' if z['pass_price'] else ' FAIL'}")
        out("  5 worst err_delta:")
        for z in sorted(sel, key=lambda z: -z["err_delta"])[:5]:
            out(f"    {fmt_pt(z)}  D128={z['D128']:.8g} D4096={z['D4096']:.8g} err={z['err_delta']:.3e} "
                f"ref={z['ref_delta']:.2e}{' UNRESOLVED' if z['unres_delta'] else ''}{'' if z['pass_delta'] else ' FAIL'}")

    out("\n## C1 table: sigmaRootT (rows) x lambda (cols); cell = max over cell, (n=count, u=unresolved for that metric)")
    c1 = [z for z in rows if z["tag"][0]]
    for key, ukey, title in (("err_price", "unres_price", "max err_price/K"), ("err_delta", "unres_delta", "max err_delta")):
        out(f"  {title}")
        out("  " + f"{'':>12}" + "".join(f"{f'[{lo:g},{hi:g})':>26}" for lo, hi in LAM_BINS_C1))
        for i, (lo, hi) in enumerate(SRT_BINS_C1):
            line = f"  {f'[{lo:g},{hi:g})':>12}"
            for j, _ in enumerate(LAM_BINS_C1):
                cell = [z for z in c1 if bin_of(z["srt"], SRT_BINS_C1) == i and bin_of(z["lam"], LAM_BINS_C1) == j]
                txt = f"{max(z[key] for z in cell):.2e} (n={len(cell)},u={sum(z[ukey] for z in cell)})" if cell else "-"
                line += f"{txt:>26}"
            out(line)

    out("\n################ PART 3 -- properties at N=128 (all 20,000 points, per candidate)")
    for ci, (nm, lm, sm) in enumerate(CANDS):
        sel = [z for z in rows if z["tag"][ci]]
        out(f"\n## {nm} (Lmax={lm:g}, Smax={sm:g}): points {len(sel)}")

        def report(label, fails, size, unit=""):
            if fails:
                w = max(fails, key=size)
                out(f"  {label}: failures {len(fails)}; worst size {size(w):.3e}{unit}  at {fmt_pt(w)}")
            else:
                out(f"  {label}: failures 0")
        report("American >= European (same tree)", [z for z in sel if z["P128"] < z["E128"]],
               lambda z: (z["E128"] - z["P128"]) / K, " (/K)")
        report("American >= intrinsic", [z for z in sel if z["P128"] < z["intrinsic"]],
               lambda z: (z["intrinsic"] - z["P128"]) / K, " (/K)")

        def dviol(z):
            lo, hi = (0.0, 1.0) if z["c"] else (-1.0, 0.0)
            return max(lo - z["D128"], z["D128"] - hi, 0.0)
        report("delta within bounds", [z for z in sel if dviol(z) > 0.0], dviol)
        gf = [z for z in sel if z["G128"] < 0.0]
        report("gamma >= 0", gf, lambda z: -z["G128"])
        if gf:
            out(f"    min gamma {min(z['G128'] for z in gf):.3e}; min gamma*S {min(z['G128'] * z['s'] for z in gf):.3e}")
        elig = [z for z in sel if z["tag_up"][ci]]
        mf = [z for z in elig if z["Pup"] < z["P128"]]
        sz = lambda z: (z["P128"] - z["Pup"]) / K  # noqa: E731
        out(f"  monotonic in vol (eligible: vol and 1.01*vol both in {nm}: {len(elig)}): failures {len(mf)}; "
            f"size/K > 1e-12: {sum(sz(z) > 1e-12 for z in mf)}; size/K > 1e-9: {sum(sz(z) > 1e-9 for z in mf)}")
        if mf:
            w = max(mf, key=sz)
            out(f"    worst size/K {sz(w):.3e} at {fmt_pt(w)}")


# ================================================================== PART 2
def p2_case(x):
    s, vol, r, q, t, c = x["s"], x["vol"], x["r"], x["q"], x["t"], x["c"]
    y = dict(x)
    y["vega005"] = vega_cd(s, K, vol, r, q, t, c, 0.05 * vol)
    y["vega010"] = vega_cd(s, K, vol, r, q, t, c, 0.10 * vol)
    y["rhoB"] = rho_B(s, K, vol, r, q, t, c)
    if x["kind"] == "cf":
        m = mp_bs(s, K, vol, r, q, t, True)
        y.update(ref_rho=m["rho"], ref_vega=m["vega"], referr_rho=0.0, referr_vega=0.0, excl_rho=None, excl_vega=None)
        return y
    for kind in ("rho", "vega"):
        pts = [(vol, r + H), (vol, r - H)] if kind == "rho" else [(vol + H, r), (vol - H, r)]
        if kind == "vega" and vol - H <= 0.0:
            y[f"excl_{kind}"], y[f"ref_{kind}"], y[f"referr_{kind}"] = "vol-1e-4 <= 0", None, None
            continue
        if not all(crr_valid(v, rr, q, t, n) for v, rr in pts for n in (4096, 2048)):
            y[f"excl_{kind}"], y[f"ref_{kind}"], y[f"referr_{kind}"] = "CRR p outside (0,1) at a bumped input", None, None
            continue
        g = {n: (crr(s, K, pts[0][0], pts[0][1], q, t, c, n) - crr(s, K, pts[1][0], pts[1][1], q, t, c, n)) / (2 * H)
             for n in (4096, 2048)}
        y[f"excl_{kind}"], y[f"ref_{kind}"], y[f"referr_{kind}"] = None, g[4096], abs(g[4096] - g[2048])
    return y


def p23_case(x):
    s, vol, t, c = x["s"], x["vol"], x["t"], x["c"]
    pm, p0, pp = (jp(s, K, vol, 0.0, 0.0, t, c, r_eval=re_) for re_ in (-H, 0.0, H))
    y = dict(x)
    y.update(central=(pp - pm) / (2 * H), up=(pp - p0) / H, down=(p0 - pm) / H)
    return y


def greek_block(rows, valkey, metric):
    refkey, referrkey, exclkey = f"ref_{metric}", f"referr_{metric}", f"excl_{metric}"
    excl = [z for z in rows if z[exclkey]]
    sel = [z for z in rows if not z[exclkey]]
    for z in sel:
        z["_ae"] = abs(z[valkey] - z[refkey])
        z["_re"] = z["_ae"] / abs(z[refkey]) if abs(z[refkey]) > REL_FLOOR else None
        z["_unres"] = z[referrkey] > z["_ae"] / 3.0
    res = [z for z in sel if not z["_unres"]]
    npass = sum(z["_ae"] <= greek_bound(metric, z[refkey], z["t"]) for z in res)
    out(f"      compared {len(sel)}  unresolved {len(sel) - len(res)}  excluded {len(excl)}")
    out(f"      LOOSE pass over resolved: {npass}/{len(res)} = {npass / max(len(res), 1):.5f}")
    if not sel:
        return
    ae = [z["_ae"] for z in sel]
    re_ = [z["_re"] for z in sel if z["_re"] is not None]
    out(f"      abs : median {np.median(ae):.3e}  p99 {pct(ae, 99):.3e}  max {max(ae):.3e}")
    out(f"      rel : median {np.median(re_) if re_ else float('nan'):.3e}  p99 {pct(re_, 99):.3e}  "
        f"max {max(re_) if re_ else float('nan'):.3e}  (|ref|>{REL_FLOOR:g}: n={len(re_)})")
    for z in sorted(sel, key=lambda z: -z["_ae"])[:5]:
        rel = f"{z['_re']:.2e}" if z["_re"] is not None else "n/a"
        out(f"      worst: {fmt_pt(z)}  value={z[valkey]:.6e} ref={z[refkey]:.6e} abs={z['_ae']:.3e} rel={rel} "
            f"referr={z[referrkey]:.2e} bound={greek_bound(metric, z[refkey], z['t']):.2e}"
            f"{' UNRESOLVED' if z['_unres'] else ''}")


def run_p2(pool, S):
    p22src = [x for x in S["p1"] if (not x["c"]) or x["q"] > 0.0][:5000]
    cases = [dict(x, kind="cf") for x in S["p21"]] + [dict(x, kind="crr") for x in p22src]
    rows = pool.map(p2_case, cases, chunksize=10)
    rc, rp = rows[:2000], rows[2000:]
    out(f"\n2.2 source: first {len(p22src)} Part 1 points that are puts or calls with q>0 "
        f"(puts {sum(not x['c'] for x in p22src)}, calls q>0 {sum(x['c'] for x in p22src)}); "
        f"last one is Part 1 index {S['p1'].index(p22src[-1])}")
    for kind in ("rho", "vega"):
        ex = {}
        for z in rp:
            if z[f"excl_{kind}"]:
                ex[z[f"excl_{kind}"]] = ex.get(z[f"excl_{kind}"], 0) + 1
        out(f"  2.2 excluded from CRR {kind} reference (any bumped input, N=4096 or 2048): {sum(ex.values())} {ex}")
    for title, rr in (("2.1 calls q=0, r in [1e-3,0.3], vs mpmath closed form (reference error 0)", rc),
                      ("2.2 puts and calls q>0, vs CRR N=4096 central h=1e-4 (reference error: CRR 4096 vs 2048)", rp)):
        out(f"\n################ PART {title}")
        for valkey, metric, label in (("vega005", "vega", "vega h=0.05*vol"), ("vega010", "vega", "vega h=0.10*vol"),
                                      ("rhoB", "rho", "rho Method B")):
            out(f"\n  ## {label}  (LOOSE: max(5e-2*|ref|, 1e-3*K*{'sqrt(T)' if metric == 'vega' else 'T'}))")
            for ci, (nm, lm, sm) in enumerate(CANDS):
                out(f"    {nm} (Lmax={lm:g}, Smax={sm:g}):")
                greek_block([z for z in rr if z["tag"][ci]], valkey, metric)

    out("\n################ PART 2.3 kink probe: r=0, q=0, inside C1; Method B fixed grid at base r=0, h=1e-4")
    rk = pool.map(p23_case, S["p23"], chunksize=5)
    for lab, sel in (("all", rk), ("calls", rk[:150]), ("puts", rk[150:])):
        m = [abs(z["up"] - z["down"]) / max(abs(z["central"]), 1e-8) for z in sel]
        out(f"  {lab:5s} n={len(sel)}: |up-down|/max(|central|,1e-8): median {np.median(m):.3e}  p99 {pct(m, 99):.3e}  max {max(m):.3e}")
    out("  5 largest |up - down| (absolute):")
    for z in sorted(rk, key=lambda z: -abs(z["up"] - z["down"]))[:5]:
        out(f"    {fmt_pt(z)}  central={z['central']:.6e} up={z['up']:.6e} down={z['down']:.6e} "
            f"|up-down|={abs(z['up'] - z['down']):.3e}")


# ================================================================== PARTS 4 and 5
def run_p45(S):
    out("\n################ PART 4.2 timing: full priced result (5 lattice builds), ATM put S=K=100 vol 0.2 r 0.05 q 0 T 1, N=128")
    args = (100.0, 100.0, 0.2, 0.05, 0.0, 1.0, False)
    for _ in range(50):
        full_result(*args)
    ts = []
    for _ in range(2000):
        t0 = time.perf_counter_ns()
        full_result(*args)
        ts.append(time.perf_counter_ns() - t0)
    ts_us = [v / 1000.0 for v in ts]
    out(f"  warm-up 50, timed 2000 (single process, no pool): median {np.median(ts_us):.1f} us  "
        f"p99 {pct(ts_us, 99):.1f} us  min {min(ts_us):.1f} us")
    g = full_result(*args)
    out("  result: " + "  ".join(f"{k_}={v:.8g}" for k_, v in g.items()))

    out("\n################ PART 4.1 golden cases (Step 1d 1.3) vs mpmath closed form")
    mx = {}
    for lab, s, k, vol, r, q, t, c in GOLD:
        m = mp_bs(s, k, vol, r, q, t, c)
        vals = {"vega h=0.05*vol": (vega_cd(s, k, vol, r, q, t, c, 0.05 * vol), m["vega"]),
                "vega h=0.10*vol": (vega_cd(s, k, vol, r, q, t, c, 0.10 * vol), m["vega"]),
                "rho Method B": (rho_B(s, k, vol, r, q, t, c), m["rho"])}
        tg = tags(vol, r, q, t)
        out(f"  {lab} (S={s:g} K={k:g} vol={vol:g} r={r:g} q={q:g} T={t:g}; lambda={lam(vol, r, q, t):.4g} "
            f"sigmaRootT={srt(vol, t):.4g} a={acoef(vol, t):.4g}; in " +
            ",".join(nm for (nm, _, _), b in zip(CANDS, tg) if b) + ")")
        for key, (v, ref) in vals.items():
            ae = abs(v - ref); re_ = ae / abs(ref)
            mx.setdefault(key, [0.0, 0.0])
            mx[key][0] = max(mx[key][0], re_); mx[key][1] = max(mx[key][1], ae)
            out(f"    {key:16s} value={v:.10f} ref={ref:.10f} rel={re_:.3e} abs={ae:.3e}")
    out("  MAX: " + "  ".join(f"{k_}: rel {v[0]:.3e} abs {v[1]:.3e}" for k_, v in mx.items()))

    out("\n################ PART 5 coverage of realistic box (100,000 points)")
    p = S["p5"]
    lm_ = np.abs(p["r"] - p["q"]) * np.sqrt(p["t"] / N_PROD) / p["vol"]
    sr_ = p["vol"] * np.sqrt(p["t"])
    a_ = p["vol"] * np.sqrt(p["t"] / N_PROD)
    n = len(lm_)
    for nm, lmax, smax in CANDS:
        ins = (lm_ < lmax) & (sr_ < smax) & (a_ >= A_MIN)
        out(f"  inside {nm} (Lmax={lmax:g}, Smax={smax:g}): {int(ins.sum())}/{n} = {ins.mean():.5f}")
    fl, fs, fa = lm_ >= 0.1, sr_ >= 1.0, a_ < A_MIN
    outside = fl | fs | fa
    out(f"  outside C1: {int(outside.sum())}")
    out(f"    separately: lambda fails {int(fl.sum())}  sigmaRootT fails {int(fs.sum())}  a fails {int(fa.sum())}")
    for lab, m in (("lambda only", fl & ~fs & ~fa), ("sigmaRootT only", ~fl & fs & ~fa), ("a only", ~fl & ~fs & fa),
                   ("lambda+sigmaRootT", fl & fs & ~fa), ("lambda+a", fl & ~fs & fa), ("sigmaRootT+a", ~fl & fs & fa),
                   ("all three", fl & fs & fa)):
        out(f"    combination {lab:18s}: {int(m.sum())}")
    out(f"  min a over box: {a_.min():.3e}; max lambda {lm_.max():.4g}; max sigmaRootT {sr_.max():.4g}")


if __name__ == "__main__":
    shard = sys.argv[1]
    _OUT = open(os.path.join(HERE, f"step1f_{shard}.txt"), "w")
    t0 = time.perf_counter()
    out(f"shard={shard} python={sys.version.split()[0]} numpy={np.__version__} cores={os.cpu_count()} SEED={SEED}")
    S = all_samples()
    sampling_header(S)
    if shard == "p45":
        run_p45(S)
    else:
        with Pool(os.cpu_count()) as pool:
            {"p13": run_p13, "p2": run_p2}[shard](pool, S)
    out(f"\nshard {shard} wall time: {time.perf_counter() - t0:.1f} s")
    _OUT.close()
    print(f"shard {shard} done in {time.perf_counter() - t0:.1f} s")
