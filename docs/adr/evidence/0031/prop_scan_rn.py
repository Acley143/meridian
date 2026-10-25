import math, random, sys
sys.path.insert(0, ".")
from jr_extra import jr_rn
from jr_proto import bs
from tol_proto import build
random.seed(12345)
U = random.uniform
def sample(rmin=-0.1):
    return dict(s=U(1, 1e4), k=U(1, 1e4), vol=U(1e-4, 3.0), r=U(rmin, 0.3), q=U(0, 0.3), t=U(1e-4, 10.0), c=random.random() < 0.5)
M = 3000
for name, f in (("JR-fwd", jr_rn),):
    fb = fv = ft = 0; wb = wv = wt = 0.0; big_v = big_t = 0
    for _ in range(M):
        x = sample(0.0); a = (x["s"], x["k"], x["vol"], x["r"], x["q"], x["t"], x["c"])
        p = f(*a, 128)
        if x["c"]:
            e = bs(*a[:6], True)["price"]
            if p < e - 1e-9 * max(1, e): fb += 1; wb = max(wb, (e - p) / max(e, 1e-12))
    for _ in range(M):
        x = sample(); a = (x["s"], x["k"], x["vol"], x["r"], x["q"], x["t"], x["c"])
        p1 = f(*a, 128)
        p2 = f(x["s"], x["k"], x["vol"] + U(1e-4, 1.0), x["r"], x["q"], x["t"], x["c"], 128)
        p3 = f(x["s"], x["k"], x["vol"], x["r"], x["q"], min(x["t"] + U(1e-3, 2.0), 12.0), x["c"], 128)
        if p2 < p1 - 1e-9 * max(1, p1):
            fv += 1; w = (p1 - p2) / max(p1, 1e-12); wv = max(wv, w); big_v += w > 1e-2
        if p3 < p1 - 1e-9 * max(1, p1):
            ft += 1; w = (p1 - p3) / max(p1, 1e-12); wt = max(wt, w); big_t += w > 1e-2
    print(f"{name}: amer>=euroBS fails {fb}/{M} worst {wb:.2e} | mono vol fails {fv}/{M} worst {wv:.2e} (>1e-2: {big_v}) | mono T fails {ft}/{M} worst {wt:.2e} (>1e-2: {big_t})")
