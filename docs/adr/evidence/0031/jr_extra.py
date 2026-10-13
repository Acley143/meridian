import math, sys
sys.path.insert(0, ".")
import numpy as np
from tol_proto import CASES, build, bs_mp
from jr_proto import zero_vol, zero_vol_continuous, bs

def jr_rn(s, k, vol, r, q, t, is_call, n, american=True):
    """Equal-probability lattice with the drift chosen so E[S_{t+dt}] = S e^((r-q)dt) exactly:
    mu = (r-q)dt - ln cosh(vol sqrt dt); p = 1/2 still."""
    dt = t / n; a = vol * math.sqrt(dt)
    mu = (r - q) * dt - math.log(math.cosh(a))
    hd = 0.5 * math.exp(-r * dt)
    sp = np.exp(a * np.arange(-n, n + 1, dtype=np.float64))
    st = s * math.exp(n * mu) * sp[0:2 * n + 1:2]
    v = np.maximum(st - k, 0.0) if is_call else np.maximum(k - st, 0.0)
    for i in range(n - 1, -1, -1):
        v = hd * (v[:-1] + v[1:])
        if american:
            si = s * math.exp(i * mu) * sp[n - i:n + i + 1:2]
            np.maximum(v, (si - k) if is_call else (k - si), out=v)
    return float(v[0])

print("== forward-matched JR variant (p=1/2, mu = (r-q)dt - ln cosh(a)): high-vol call q=0 r=.05 vs BS ==")
for vol, t in ((0.2, 1.0), (1.0, 5.0), (1.0, 10.0), (2.0, 10.0), (3.0, 10.0)):
    j = jr_rn(100.0, 100.0, vol, 0.05, 0.0, t, True, 128); b = bs(100.0, 100.0, vol, 0.05, 0.0, t, True)["price"]
    print(f"  vol={vol} T={t}: JR-fwd={j:.6f} BS={b:.6f} rel={(j-b)/b:+.2e}")
print("  golden cases, JR-fwd N=128 vs CRR N=128: max rel diff =",
      f"{max(abs(jr_rn(*a,128)-build(*a,128,'CRR'))/build(*a,128,'CRR') for _,*a in CASES):.3e}")
for _, *a in CASES:
    if a[-1] and a[4] == 0.0:
        s,k,vol,r,q,t,c = a
        print(f"  anchor N=4096 {s},{k},{t}: rel vs mpmath BS {abs(jr_rn(*a,4096)-bs_mp(s,k,vol,r,q,t))/bs_mp(s,k,vol,r,q,t):.2e}")

print("\n== vol=0 cases with an interior optimal exercise time ==")
for lab, s, k, r, q, t, c in (("put ITM, q>r, interior", 62.0, 100.0, 0.03, 0.05, 3.0, False),
                              ("call ITM, q<r, interior", 120.0, 100.0, 0.05, 0.0415, 1.0, True)):
    g = zero_vol(s, k, r, q, t, c, 128); ind, ts = zero_vol_continuous(s, k, r, q, t, c)
    print(f"  {lab:24s} grid(N=128)={g:.10f} continuous={ind:.10f} t*={ts:.4f} diff={g-ind:+.2e} rel={(g-ind)/ind:+.1e}")
