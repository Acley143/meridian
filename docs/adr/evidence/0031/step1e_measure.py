"""STEP 1e: domain map, rho/vega candidates, small-vol branch. Scratch only.

Run each shard separately (each writes step1e_<shard>.txt next to this file):
  /Users/mac/Projects/meridian/.venv/bin/python -I -B step1e_measure.py p4
  /Users/mac/Projects/meridian/.venv/bin/python -I -B step1e_measure.py p1
  /Users/mac/Projects/meridian/.venv/bin/python -I -B step1e_measure.py p23
Deterministic: no random draws anywhere; SEED is fixed and set for completeness.
Pool.map preserves input order, so output does not depend on scheduling.
Read-only against the repo: imports quant_core (installed editable) and the mpmath
generator tests/golden/generate_reference_values.py; never writes bytecode.
"""
import sys

sys.dont_write_bytecode = True

import itertools
import math
import os
import random
import time
from multiprocessing import Pool

import numpy as np

REPO = "/Users/mac/Projects/meridian"
sys.path.insert(0, f"{REPO}/libs/quant-core/tests/golden")
from generate_reference_values import price_and_greeks as mp_bs  # noqa: E402  (mpmath, 50 dps)
from quant_core.pricing.black_scholes import _zero_vol  # noqa: E402

SEED = 12345
random.seed(SEED)
np.random.seed(SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
N_PROD = 128
H = 1e-4
K = 100.0
LN2 = math.log(2.0)
GRID_VOLS = [1e-4, 1e-3, 0.01, 0.05, 0.2, 0.5, 1.0, 2.0, 3.0]
GRID_RATES = [-0.1, -0.05, 0.0, 0.05, 0.1, 0.3]
GRID_DIVS = [0.0, 0.05, 0.1, 0.3]
GRID_TTMS = [1e-4, 0.01, 0.1, 1.0, 5.0, 10.0]
SK_ALL = [0.5, 0.8, 0.95, 1.0, 1.05, 1.25, 2.0]
SK_GREEK = [0.8, 1.0, 1.25]
SRT_BINS = [(0, 0.05), (0.05, 0.2), (0.2, 0.5), (0.5, 1), (1, 2), (2, math.inf)]
LAM_BINS = [(0, 0.1), (0.1, 0.25), (0.25, 0.5), (0.5, 1), (1, math.inf)]
TIGHT = {"price": (2e-3, 2e-4), "delta": 5e-3, "vega": (2e-2, 1e-3), "rho": (2e-2, 1e-3)}
LOOSE = {"price": (1e-2, 1e-3), "delta": 2e-2, "vega": (5e-2, 1e-3), "rho": (5e-2, 1e-3)}
REL_FLOOR = 1e-8
ZCASES = [  # STEP 1c section (g): (label, S, K, r, q, T, is_call)
    ("call ITM q>0 (early)",    110.0, 100.0, 0.02, 0.08,   1.0, True),
    ("call ITM q=0",            110.0, 100.0, 0.05, 0.00,   1.0, True),
    ("call OTM",                 90.0, 100.0, 0.02, 0.00,   1.0, True),
    ("put ITM r>0 (early)",      90.0, 100.0, 0.05, 0.00,   1.0, False),
    ("put OTM",                 110.0, 100.0, 0.05, 0.00,   1.0, False),
    ("put ITM, q>r, interior",   62.0, 100.0, 0.03, 0.05,   3.0, False),
    ("call ITM, q<r, interior", 120.0, 100.0, 0.05, 0.0415, 1.0, True),
]

_OUT = None


def out(*a):
    print(*a, file=_OUT, flush=True)


# ------------------------------------------------------------------ JR-FM (Step 1d definition)
def lncosh(a):
    return a + math.log1p(math.exp(-2.0 * a)) - LN2


def jrfm(s, k, vol, r, q, t, c, n, greeks=False, r_eval=None):
    """JR-FM. r_eval=None: production lattice at r. r_eval given: Method B
    fixed grid -- nodes (dt, u, d) from base r, probability and discount at r_eval."""
    dt = t / n
    a = vol * math.sqrt(dt)
    mu = (r - q) * dt - lncosh(a)
    if r_eval is None:
        p, disc = 0.5, math.exp(-r * dt)
    else:
        x = (r_eval - r) * dt + lncosh(a)  # (r'-q)dt - mu
        p = (math.expm1(x) - math.expm1(-a)) / (2.0 * math.sinh(a))
        disc = math.exp(-r_eval * dt)
    pu, pd = disc * p, disc * (1.0 - p)
    sp = np.exp(a * np.arange(-n, n + 1, dtype=np.float64))
    st = s * math.exp(n * mu) * sp[0 : 2 * n + 1 : 2]
    v = np.maximum(st - k, 0.0) if c else np.maximum(k - st, 0.0)
    kp = {}
    for i in range(n - 1, -1, -1):
        v = pd * v[:-1] + pu * v[1:]
        si = s * math.exp(i * mu) * sp[n - i : n + i + 1 : 2]
        np.maximum(v, (si - k) if c else (k - si), out=v)
        if greeks and i <= 2:
            kp[i] = v.copy()
    if not greeks:
        return float(v[0])
    v2, v1, v0 = kp[2], kp[1], kp[0]
    e1, e2 = math.exp(mu), math.exp(2.0 * mu)
    delta = (v1[1] - v1[0]) / (s * e1 * 2.0 * math.sinh(a))
    gamma = ((v2[2] - v2[1]) / (s * e2 * math.expm1(2.0 * a)) - (v2[1] - v2[0]) / (-s * e2 * math.expm1(-2.0 * a))) \
        / (0.5 * s * e2 * 2.0 * math.sinh(2.0 * a))
    theta = (v2[1] - delta * s * math.expm1(2.0 * mu) - v0[0]) / (2.0 * dt)
    return {"price": float(v0[0]), "delta": float(delta), "gamma": float(gamma), "theta": float(theta)}


def rho_A(s, k, vol, r, q, t, c, n=N_PROD):
    return (jrfm(s, k, vol, r + H, q, t, c, n) - jrfm(s, k, vol, r - H, q, t, c, n)) / (2 * H)


def rho_B(s, k, vol, r, q, t, c, n=N_PROD):
    return (jrfm(s, k, vol, r, q, t, c, n, r_eval=r + H) - jrfm(s, k, vol, r, q, t, c, n, r_eval=r - H)) / (2 * H)


def vega_cd(s, k, vol, r, q, t, c, h, n=N_PROD):
    return (jrfm(s, k, vol + h, r, q, t, c, n) - jrfm(s, k, vol - h, r, q, t, c, n)) / (2 * h)


# ------------------------------------------------------------------ CRR reference
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


# ------------------------------------------------------------------ binning / budgets
def srt(vol, t):
    return vol * math.sqrt(t)


def lam(vol, r, q, t):
    return abs(r - q) * math.sqrt(t / N_PROD) / vol


def bin_of(x, bins):
    for i, (lo, hi) in enumerate(bins):
        if lo <= x < hi:
            return i
    raise ValueError(x)


def blabel(b):
    lo, hi = b
    return f"[{lo:g},{'inf' if hi == math.inf else f'{hi:g}'})"


def passes(budget, metric, err_abs, ref_val, t):
    if metric == "price":
        rel, absk = budget["price"]
        return err_abs <= max(rel * abs(ref_val), absk * K)
    if metric == "delta":
        return err_abs <= budget["delta"]
    rel, absk = budget[metric]
    scale = math.sqrt(t) if metric == "vega" else t
    return err_abs <= max(rel * abs(ref_val), absk * K * scale)


def grid_table(rows, rowbins, colbins, rowkey, colkey, cell, cellfmt, title, extra=None):
    out(f"  {title}")
    out("  " + f"{'':>14}" + "".join(f"{blabel(b):>16}" for b in colbins))
    for i, rb in enumerate(rowbins):
        line = f"  {blabel(rb) if isinstance(rb, tuple) else rb:>14}"
        line2 = f"  {'':>14}"
        for j, _ in enumerate(colbins):
            sel = [x for x in rows if rowkey(x) == i and colkey(x) == j]
            line += f"{cellfmt(cell(sel)) if sel else '-':>16}"
            if extra:
                line2 += f"{extra(sel) if sel else '':>16}"
        out(line)
        if extra:
            out(line2)


def pct(xs, p):
    return float(np.percentile(np.asarray(xs, dtype=np.float64), p)) if xs else float("nan")


def fmt_case(x):
    return (f"{'call' if x['c'] else 'put '} S={x['s']:g} K={K:g} vol={x['vol']:g} r={x['r']:g} q={x['q']:g} "
            f"T={x['t']:g}  sigmaRootT={x['srt']:.4g} lambda={x['lam']:.4g}")


# ================================================================== PART 1
def p1_case(args):
    sk, vol, r, q, t, c = args
    s = sk * K
    o = {n: jrfm(s, K, vol, r, q, t, c, n, greeks=True) for n in (N_PROD, 2048, 4096)}
    return {"s": s, "sk": sk, "vol": vol, "r": r, "q": q, "t": t, "c": c, "srt": srt(vol, t), "lam": lam(vol, r, q, t),
            "P128": o[128]["price"], "P2048": o[2048]["price"], "P4096": o[4096]["price"],
            "D128": o[128]["delta"], "D2048": o[2048]["delta"], "D4096": o[4096]["delta"],
            "err_price": abs(o[128]["price"] - o[4096]["price"]) / K,
            "err_delta": abs(o[128]["delta"] - o[4096]["delta"]),
            "ref_price": abs(o[4096]["price"] - o[2048]["price"]) / K,
            "ref_delta": abs(o[4096]["delta"] - o[2048]["delta"])}


def run_p1(pool):
    cases = [(sk, v, r, q, t, c) for sk in SK_ALL for v, r, q, t in itertools.product(GRID_VOLS, GRID_RATES, GRID_DIVS, GRID_TTMS)
             for c in (True, False)]
    out(f"PART 1 cases: {len(cases)}")
    rows = pool.map(p1_case, cases, chunksize=24)
    for x in rows:
        x["unres_price"] = x["ref_price"] > x["err_price"] / 3.0
        x["unres_delta"] = x["ref_delta"] > x["err_delta"] / 3.0
        x["resolved_pd"] = not (x["unres_price"] or x["unres_delta"])
        ep = x["err_price"] * K
        x["tight"] = passes(TIGHT, "price", ep, x["P4096"], x["t"]) and passes(TIGHT, "delta", x["err_delta"], None, x["t"])
        x["loose"] = passes(LOOSE, "price", ep, x["P4096"], x["t"]) and passes(LOOSE, "delta", x["err_delta"], None, x["t"])
    rk = lambda x: bin_of(x["srt"], SRT_BINS)
    ck = lambda x: bin_of(x["lam"], LAM_BINS)
    out("\n## 1.1 sigmaRootT (rows) x lambda (cols); second line per row: n=cases u=unresolved for that metric")
    grid_table(rows, SRT_BINS, LAM_BINS, rk, ck, lambda sel: max(z["err_price"] for z in sel), lambda v: f"{v:.2e}",
               "max err_price = |P128-P4096|/K",
               extra=lambda sel: f"n={len(sel)} u={sum(z['unres_price'] for z in sel)}")
    grid_table(rows, SRT_BINS, LAM_BINS, rk, ck, lambda sel: max(z["err_delta"] for z in sel), lambda v: f"{v:.2e}",
               "max err_delta = |D128-D4096|",
               extra=lambda sel: f"n={len(sel)} u={sum(z['unres_delta'] for z in sel)}")
    out("\n## 1.2 q (rows) x sigmaRootT (cols), all cases")
    qbins = GRID_DIVS
    grid_table(rows, [f"q={q:g}" for q in qbins], SRT_BINS, lambda x: qbins.index(x["q"]), rk,
               lambda sel: max(z["err_price"] for z in sel), lambda v: f"{v:.2e}", "max err_price")
    grid_table(rows, [f"q={q:g}" for q in qbins], SRT_BINS, lambda x: qbins.index(x["q"]), rk,
               lambda sel: max(z["err_delta"] for z in sel), lambda v: f"{v:.2e}", "max err_delta")
    out("\n## 1.3 pass fractions (price AND delta), among cases resolved for BOTH price and delta;"
        " second line: resolved/total")
    for name in ("tight", "loose"):
        grid_table(rows, SRT_BINS, LAM_BINS, rk, ck,
                   lambda sel, nm=name: (sum(z[nm] for z in sel if z["resolved_pd"]), sum(z["resolved_pd"] for z in sel)),
                   lambda v: f"{v[0] / v[1]:.3f}" if v[1] else "n/a", f"fraction passing {name.upper()}",
                   extra=lambda sel: f"{sum(z['resolved_pd'] for z in sel)}/{len(sel)}")
    tot_r = sum(z["resolved_pd"] for z in rows)
    out(f"  overall: resolved {tot_r}/{len(rows)}; TIGHT {sum(z['tight'] for z in rows if z['resolved_pd']) / tot_r:.4f}; "
        f"LOOSE {sum(z['loose'] for z in rows if z['resolved_pd']) / tot_r:.4f}")
    out("\n## 1.4 10 worst err_price")
    for x in sorted(rows, key=lambda z: -z["err_price"])[:10]:
        out(f"    {fmt_case(x)}  P128={x['P128']:.6f} P4096={x['P4096']:.6f} err_price={x['err_price']:.3e} "
            f"ref_price={x['ref_price']:.2e}{' UNRESOLVED' if x['unres_price'] else ''}")
    out("  10 worst err_delta")
    for x in sorted(rows, key=lambda z: -z["err_delta"])[:10]:
        out(f"    {fmt_case(x)}  D128={x['D128']:.6f} D4096={x['D4096']:.6f} D2048={x['D2048']:.6f} "
            f"err_delta={x['err_delta']:.3e} ref_delta={x['ref_delta']:.2e}{' UNRESOLVED' if x['unres_delta'] else ''}")
    out("\n## 1.5 err_delta by S/K (all cases; resolved-only in brackets)")
    for sk in SK_ALL:
        sel = [z["err_delta"] for z in rows if z["sk"] == sk]
        res = [z["err_delta"] for z in rows if z["sk"] == sk and not z["unres_delta"]]
        out(f"  S/K={sk:<5g} max {max(sel):.3e}  p99 {pct(sel, 99):.3e}   [resolved n={len(res)}: max "
            f"{max(res) if res else float('nan'):.3e} p99 {pct(res, 99):.3e}]")


# ================================================================== PARTS 2 and 3
VEGA_BUMPS = [("h=1e-4", lambda v: 1e-4), ("h=0.05*vol", lambda v: 0.05 * v), ("h=0.10*vol", lambda v: 0.10 * v)]


def p23_case(args):
    sk, vol, r, q, t, c = args
    s = sk * K
    x = {"s": s, "sk": sk, "vol": vol, "r": r, "q": q, "t": t, "c": c, "srt": srt(vol, t), "lam": lam(vol, r, q, t)}
    x["rhoA"] = rho_A(s, K, vol, r, q, t, c)
    x["rhoB"] = rho_B(s, K, vol, r, q, t, c)
    for name, hf in VEGA_BUMPS:
        h = hf(vol)
        x["vega " + name] = vega_cd(s, K, vol, r, q, t, c, h) if vol - h >= 0.0 else None
    if c:  # calls with q=0, r>=0: closed form, exact (reference error 0)
        m = mp_bs(s, K, vol, r, q, t, True)
        x["ref_rho"], x["ref_vega"], x["referr_rho"], x["referr_vega"] = m["rho"], m["vega"], 0.0, 0.0
        x["excl_rho"] = x["excl_vega"] = None
        return x
    # puts: CRR at N=4096, central difference h=1e-4 for both rho and vega; N=2048 for the reference's own error
    def crr_greek(kind, n):
        if kind == "rho":
            pts = [(vol, r + H), (vol, r - H)]
        else:
            pts = [(vol + H, r), (vol - H, r)]
        if not all(crr_valid(v, rr, q, t, n) for v, rr in pts):
            return None
        return (crr(s, K, pts[0][0], pts[0][1], q, t, False, n) - crr(s, K, pts[1][0], pts[1][1], q, t, False, n)) / (2 * H)
    for kind in ("rho", "vega"):
        g4, g2 = crr_greek(kind, 4096), crr_greek(kind, 2048)
        if g4 is None or g2 is None:
            x[f"excl_{kind}"] = ("vol-1e-4 <= 0" if kind == "vega" and vol - H <= 0 else "CRR p outside (0,1) at a bumped input")
            x[f"ref_{kind}"] = x[f"referr_{kind}"] = None
        else:
            x[f"excl_{kind}"] = None
            x[f"ref_{kind}"], x[f"referr_{kind}"] = g4, abs(g4 - g2)
    return x


def greek_report(rows, label, valkey, refkey, referrkey, metric):
    sel = [z for z in rows if z.get(valkey) is not None and z.get(refkey) is not None]
    for z in sel:
        z["_ae"] = abs(z[valkey] - z[refkey])
        z["_re"] = z["_ae"] / abs(z[refkey]) if abs(z[refkey]) > REL_FLOOR else None
        z["_unres"] = z[referrkey] > z["_ae"] / 3.0
    ae = [z["_ae"] for z in sel]
    re = [z["_re"] for z in sel if z["_re"] is not None]
    out(f"    {label}: compared {len(sel)}")
    if not sel:
        return
    out(f"      abs : median {np.median(ae):.3e}  p99 {pct(ae, 99):.3e}  max {max(ae):.3e}")
    out(f"      rel : median {np.median(re):.3e}  p99 {pct(re, 99):.3e}  max {max(re):.3e}  "
        f"(|ref| > {REL_FLOOR:g}; {len(sel) - len(re)} excluded)")
    res = [z for z in sel if not z["_unres"]]
    for nm, bud in (("TIGHT", TIGHT), ("LOOSE", LOOSE)):
        npass = sum(passes(bud, metric, z["_ae"], z[refkey], z["t"]) for z in res)
        out(f"      {nm}: {npass}/{len(res)} = {npass / len(res) if res else float('nan'):.4f} of resolved "
            f"({len(sel) - len(res)} unresolved)")
    grid_table([z for z in sel if z["_re"] is not None], SRT_BINS, LAM_BINS,
               lambda z: bin_of(z["srt"], SRT_BINS), lambda z: bin_of(z["lam"], LAM_BINS),
               lambda s_: max(z["_re"] for z in s_), lambda v: f"{v:.2e}", "max rel error, sigmaRootT x lambda")
    for z in sorted(sel, key=lambda z: -z["_ae"])[:5]:
        out(f"      worst: {fmt_case(z)}  value={z[valkey]:.6e} ref={z[refkey]:.6e} abs={z['_ae']:.3e} "
            f"referr={z[referrkey]:.2e}{' UNRESOLVED' if z['_unres'] else ''}")


def run_p23(pool):
    out("## 2.0 Method B probability, over the 1296-point grid (independent of S/K)")
    dev0, pmin, pmax, outside = 0.0, math.inf, -math.inf, 0
    for vol, r, q, t in itertools.product(GRID_VOLS, GRID_RATES, GRID_DIVS, GRID_TTMS):
        dt = t / N_PROD; a = vol * math.sqrt(dt)
        for re_ in (r, r + H, r - H):
            x = (re_ - r) * dt + lncosh(a)
            p = (math.expm1(x) - math.expm1(-a)) / (2.0 * math.sinh(a))
            if re_ == r:
                dev0 = max(dev0, abs(p - 0.5))
            else:
                pmin, pmax = min(pmin, p), max(pmax, p)
                outside += not (0.0 < p < 1.0)
    out(f"  max |p' - 0.5| at r'=r: {dev0:.3e}")
    out(f"  p' at r +/- 1e-4: min {pmin:.6f}  max {pmax:.6f}  outside (0,1): {outside} of {2 * 1296}")

    calls = [(sk, v, r, 0.0, t, True) for sk in SK_GREEK for v, r, t in itertools.product(GRID_VOLS, GRID_RATES, GRID_TTMS) if r >= 0.0]
    puts = [(sk, v, r, q, t, False) for sk in SK_GREEK for v, r, q, t in itertools.product(GRID_VOLS, GRID_RATES, GRID_DIVS, GRID_TTMS)]
    out(f"\nPARTS 2/3 cases: calls (q=0, r>=0) {len(calls)}, puts {len(puts)}; S/K in {SK_GREEK}")
    rc = pool.map(p23_case, calls, chunksize=8)
    rp = pool.map(p23_case, puts, chunksize=8)
    for kind in ("rho", "vega"):
        ex = {}
        for z in rp:
            if z[f"excl_{kind}"]:
                ex[z[f"excl_{kind}"]] = ex.get(z[f"excl_{kind}"], 0) + 1
        out(f"  puts excluded from CRR {kind} reference: {sum(ex.values())} {ex}")

    out("\n## 2.1 rho, calls q=0 r>=0, vs mpmath closed form")
    greek_report(rc, "Method A (rebuild grid)", "rhoA", "ref_rho", "referr_rho", "rho")
    greek_report(rc, "Method B (fixed grid)", "rhoB", "ref_rho", "referr_rho", "rho")
    out("\n## 2.2 rho, puts, vs CRR N=4096 (h=1e-4), CRR-valid only")
    greek_report(rp, "Method A (rebuild grid)", "rhoA", "ref_rho", "referr_rho", "rho")
    greek_report(rp, "Method B (fixed grid)", "rhoB", "ref_rho", "referr_rho", "rho")

    out("\n## 3 vega, central difference in vol")
    for rows, title in ((rc, "3.1 calls q=0 r>=0 vs mpmath closed form"), (rp, "3.2 puts vs CRR N=4096 (central h=1e-4), CRR-valid only")):
        out(f"\n## {title}")
        for name, _ in VEGA_BUMPS:
            excluded = sum(1 for z in rows if z["vega " + name] is None)
            out(f"  bump {name}: excluded because vol-h < 0: {excluded}")
            greek_report(rows, f"vega {name}", "vega " + name, "ref_vega", "referr_vega", "vega")
        ind = [abs(z["vega h=0.05*vol"] - z["vega h=0.10*vol"]) / abs(z["ref_vega"]) for z in rows
               if z["ref_vega"] is not None and abs(z["ref_vega"]) > REL_FLOOR
               and z["vega h=0.05*vol"] is not None and z["vega h=0.10*vol"] is not None]
        out(f"  truncation indicator |vega(0.05vol)-vega(0.10vol)|/|ref|: median {np.median(ind):.3e}  p99 {pct(ind, 99):.3e}  (n={len(ind)})")


# ================================================================== PART 4
def branch(s, k, r, q, t, c, n=N_PROD):
    ts = [i * t / n for i in range(n + 1)]
    f = []
    for ti in ts:
        st = s * math.exp((r - q) * ti)
        f.append(math.exp(-r * ti) * max((st - k) if c else (k - st), 0.0))
    best = max(f)
    istar = f.index(best)  # earliest on ties
    others = sorted(((f[i], i) for i in range(n + 1) if i != istar), reverse=True)
    runner_val, runner_i = others[0]
    if best <= 0.0:
        return {"price": 0.0, "delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0,
                "istar": istar, "tstar": ts[istar], "runner": runner_i, "gap": best - runner_val}
    tst = ts[istar]
    delta = math.exp(-q * tst) if c else -math.exp(-q * tst)
    rho = (k * tst * math.exp(-r * tst)) if c else (-k * tst * math.exp(-r * tst))
    theta = 0.0 if istar < n else _zero_vol(s, k, r, q, t, c).theta
    return {"price": best, "delta": delta, "gamma": 0.0, "vega": 0.0, "theta": theta, "rho": rho,
            "istar": istar, "tstar": tst, "runner": runner_i, "gap": best - runner_val}


def lattice_greeks(s, k, vol, r, q, t, c):
    g = jrfm(s, k, vol, r, q, t, c, N_PROD, greeks=True)
    g["rho"] = rho_A(s, k, vol, r, q, t, c)
    return g


def run_p4(pool):
    out("## 4.1 vol=0 branch vs production lattice")
    for lab, s, k, r, q, t, c in ZCASES:
        b = branch(s, k, r, q, t, c)
        out(f"\n  {lab}  (S={s:g} K={k:g} r={r:g} q={q:g} T={t:g})")
        out(f"    branch: i*={b['istar']} t_i*={b['tstar']:.6f} runner-up i={b['runner']} gap={b['gap']:.3e}  "
            f"price={b['price']:.10f} delta={b['delta']:.8f} theta={b['theta']:.8f} rho={b['rho']:.8f} gamma=0 vega=0")
        for vol in (1e-4, 1e-5, 1e-6):
            g = lattice_greeks(s, k, vol, r, q, t, c)
            cells = []
            for m in ("price", "delta", "theta", "rho"):
                ae = abs(g[m] - b[m])
                rel = f"{ae / abs(b[m]):.2e}" if b[m] != 0.0 else "n/a"
                cells.append(f"{m} lat={g[m]:.8f} res abs={ae:.2e} rel={rel}")
            out(f"    vol={vol:g}: " + " | ".join(cells) + f" | gamma lat={g['gamma']:.2e}")
    s, k, r, q, t, c = 62.0, 100.0, 0.03, 0.05, 3.0, False
    out("\n  interior put rho evidence (vol=1e-6):")
    for rr in (r - H, r, r + H):
        p = jrfm(s, k, 1e-6, rr, q, t, c, N_PROD)
        b = branch(s, k, rr, q, t, c)
        out(f"    r={rr:.4f}: lattice price={p:.12f}  branch price={b['price']:.12f}  branch i*={b['istar']} t_i*={b['tstar']:.6f}")
    pm, p0, pp = (jrfm(s, k, 1e-6, rr, q, t, c, N_PROD) for rr in (r - H, r, r + H))
    out(f"    lattice central rho={(pp - pm) / (2 * H):.6f}; one-sided: (P(r+h)-P(r))/h={(pp - p0) / H:.6f}, "
        f"(P(r)-P(r-h))/h={(p0 - pm) / H:.6f}; branch rho at fixed i*={branch(s, k, r, q, t, c)['rho']:.6f}")
    for rr in (r - H, r + H):
        bb = branch(s, k, rr, q, t, c)
        out(f"    branch rho formula at r={rr:.4f} with its own i*={bb['istar']}: {bb['rho']:.6f}")

    out("\n## 4.2 gamma noise")
    for lab, s, expected_kind in (("ATM put S=K=100 (European-equal at small vol)", 100.0, "eu"),
                                  ("ITM put S=90 (immediate exercise)", 90.0, "zero")):
        out(f"  {lab}, r=0.05 q=0 T=1")
        out(f"    {'vol':>10} {'a':>11} {'S*a':>11} {'lattice gamma':>15} {'expected':>12} {'|diff|':>11}")
        worst_vol = None
        for kk in [2 + 0.5 * j for j in range(15)]:
            vol = 10 ** (-kk)
            dt = 1.0 / N_PROD
            a = vol * math.sqrt(dt)
            g = jrfm(s, 100.0, vol, 0.05, 0.0, 1.0, False, N_PROD, greeks=True)["gamma"]
            exp_g = mp_bs(s, 100.0, vol, 0.05, 0.0, 1.0, False)["gamma"] if expected_kind == "eu" else 0.0
            d = abs(g - exp_g)
            if d > 1e-6 and (worst_vol is None or vol > worst_vol):
                worst_vol = vol
            out(f"    {vol:>10.3e} {a:>11.3e} {s * a:>11.3e} {g:>15.6e} {exp_g:>12.4e} {d:>11.3e}")
        out(f"    largest vol with |gamma - expected| > 1e-6: {worst_vol if worst_vol is not None else 'none'}")

    out("\n## 4.3 max |lattice - branch| over the seven cases")
    for vol in (1e-4, 1e-5, 1e-6, 1e-7):
        mx = {m: (0.0, "") for m in ("price", "delta", "theta", "rho")}
        for lab, s, k, r, q, t, c in ZCASES:
            b = branch(s, k, r, q, t, c); g = lattice_greeks(s, k, vol, r, q, t, c)
            for m in mx:
                d = abs(g[m] - b[m])
                if d > mx[m][0]:
                    mx[m] = (d, lab)
        out(f"  vol={vol:g}: " + "  ".join(f"{m} {v[0]:.3e} ({v[1]})" for m, v in mx.items()))


if __name__ == "__main__":
    shard = sys.argv[1]
    _OUT = open(os.path.join(HERE, f"step1e_{shard}.txt"), "w")
    t0 = time.perf_counter()
    out(f"shard={shard} python={sys.version.split()[0]} numpy={np.__version__} cores={os.cpu_count()} SEED={SEED}")
    with Pool(os.cpu_count()) as pool:
        {"p1": run_p1, "p23": run_p23, "p4": run_p4}[shard](pool)
    out(f"\nshard {shard} wall time: {time.perf_counter() - t0:.1f} s")
    _OUT.close()
    print(f"shard {shard} done in {time.perf_counter() - t0:.1f} s")
