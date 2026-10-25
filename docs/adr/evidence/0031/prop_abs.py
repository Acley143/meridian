import math, random, sys
sys.path.insert(0, ".")
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    from jr_extra import jr_rn
from jr_proto import jr, bs
U = random.uniform
M = 3000
for name, f in (("JR (plain)", jr), ("JR-fwd", jr_rn)):
    random.seed(12345)
    out = {"amer>=euroBS": [], "mono vol": [], "mono T": []}
    def sample(rmin=-0.1):
        return dict(s=U(1, 1e4), k=U(1, 1e4), vol=U(1e-4, 3.0), r=U(rmin, 0.3), q=U(0, 0.3), t=U(1e-4, 10.0), c=random.random() < 0.5)
    for _ in range(M):
        x = sample(0.0); a = (x["s"], x["k"], x["vol"], x["r"], x["q"], x["t"], x["c"])
        p = f(*a, 128)
        if x["c"]:
            e = bs(*a[:6], True)["price"]
            if p < e: out["amer>=euroBS"].append((e - p, e, x))
    for _ in range(M):
        x = sample(); a = (x["s"], x["k"], x["vol"], x["r"], x["q"], x["t"], x["c"])
        p1 = f(*a, 128)
        p2 = f(x["s"], x["k"], x["vol"] + U(1e-4, 1.0), x["r"], x["q"], x["t"], x["c"], 128)
        p3 = f(x["s"], x["k"], x["vol"], x["r"], x["q"], min(x["t"] + U(1e-3, 2.0), 12.0), x["c"], 128)
        if p2 < p1: out["mono vol"].append((p1 - p2, p1, x))
        if p3 < p1: out["mono T"].append((p1 - p3, p1, x))
    for k, v in out.items():
        if not v: print(f"{name:10s} {k:13s} no failures"); continue
        rel_to_strike = [d / x["k"] for d, _, x in v]
        dmax, pr, x = max(v, key=lambda z: z[0] / z[2]["k"])
        print(f"{name:10s} {k:13s} fails {len(v):4d}  max shortfall/strike {max(rel_to_strike):.2e}  "
              f"(at vol={x['vol']:.2f} T={x['t']:.2f} S/K={x['s']/x['k']:.2f}, shortfall {dmax:.3g} on price {pr:.3g}); "
              f"count with shortfall/strike > 1e-3: {sum(r > 1e-3 for r in rel_to_strike)}")
