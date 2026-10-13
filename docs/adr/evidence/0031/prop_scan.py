import math, random, sys
sys.path.insert(0, ".")
from jr_proto import jr, bs
random.seed(12345)  # scratch sampling only
U = random.uniform
def sample(rmin=-0.1):
    return dict(s=U(1, 1e4), k=U(1, 1e4), vol=U(1e-4, 3.0), r=U(rmin, 0.3), q=U(0, 0.3), t=U(1e-4, 10.0), c=random.random() < 0.5)
fails = {k: 0 for k in ("amer>=euroBS", "amer>=euroJR", ">=intrinsic", "delta bounds", "gamma>=0", "mono vol", "mono T")}
worst = {k: 0.0 for k in fails}
M = 3000
for _ in range(M):
    x = sample(0.0); a = (x["s"], x["k"], x["vol"], x["r"], x["q"], x["t"], x["c"])
    p, d, g, th = jr(*a, 128, greeks=True)
    if x["c"] and x["vol"] * math.sqrt(x["t"]) > 1e-6:
        e = bs(*a[:6], True)["price"]
        if p < e - 1e-9 * max(1, e): fails["amer>=euroBS"] += 1; worst["amer>=euroBS"] = max(worst["amer>=euroBS"], (e - p) / max(e, 1e-12))
    e2 = jr(*a, 128, american=False)
    if p < e2 - 1e-12 * max(1, e2): fails["amer>=euroJR"] += 1
    intr = max(x["s"] - x["k"], 0) if x["c"] else max(x["k"] - x["s"], 0)
    if p < intr - 1e-9 * max(1, intr): fails[">=intrinsic"] += 1
    if not ((-1e-9 <= d <= 1 + 1e-9) if x["c"] else (-1 - 1e-9 <= d <= 1e-9)): fails["delta bounds"] += 1; worst["delta bounds"] = max(worst["delta bounds"], abs(d))
    if g < -1e-12: fails["gamma>=0"] += 1
x0 = None
for _ in range(M):
    x = sample(); a = (x["s"], x["k"], x["vol"], x["r"], x["q"], x["t"], x["c"])
    hv = U(1e-4, 1.0)
    p1 = jr(*a, 128); p2 = jr(x["s"], x["k"], x["vol"] + hv, x["r"], x["q"], x["t"], x["c"], 128)
    if p2 < p1 - 1e-9 * max(1, p1): fails["mono vol"] += 1; worst["mono vol"] = max(worst["mono vol"], (p1 - p2) / max(p1, 1e-12))
    ht = U(1e-3, 2.0)
    p3 = jr(x["s"], x["k"], x["vol"], x["r"], x["q"], min(x["t"] + ht, 12.0), x["c"], 128)
    if p3 < p1 - 1e-9 * max(1, p1): fails["mono T"] += 1; worst["mono T"] = max(worst["mono T"], (p1 - p2 if False else p1 - p3) / max(p1, 1e-12))
for k in fails:
    print(f"  {k:14s} failures {fails[k]:4d}/{M}   worst rel shortfall {worst[k]:.2e}")
