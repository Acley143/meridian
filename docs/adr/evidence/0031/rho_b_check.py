import sys, math
sys.dont_write_bytecode = True
sys.path.insert(0, "/private/tmp/claude-502/-Users-mac-Projects-meridian/ff1dbb4c-1ebf-41b8-aed2-69033ccbd586/scratchpad")
import step1e_measure as e
for vol in (1e-6,):
    for lab, s, k, r, q, t, c in e.ZCASES:
        b = e.branch(s, k, r, q, t, c)
        ra, rb = e.rho_A(s, k, vol, r, q, t, c), e.rho_B(s, k, vol, r, q, t, c)
        dt = t / 128; a = vol * math.sqrt(dt)
        ps = [(math.expm1((re_ - r) * dt + e.lncosh(a)) - math.expm1(-a)) / (2 * math.sinh(a)) for re_ in (r + e.H, r - e.H)]
        def err(v):
            ae = abs(v - b["rho"]); return f"abs={ae:.3e} rel={'n/a' if b['rho']==0 else f'{ae/abs(b['rho']):.3e}'}"
        print(f"{lab:26s} branch rho={b['rho']:.6f} | A={ra:.6f} {err(ra)} | B={rb:.6f} {err(rb)} | p(r+h)={ps[0]:.4g} p(r-h)={ps[1]:.4g}")
