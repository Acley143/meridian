# ADR-0031 evidence

The measurement scripts and outputs behind every figure in ADR-0031
(`../../0031-american-options-forward-matched-jarrow-rudd.md`).

These files are a frozen record and are not maintained. They are not run by
CI. They reproduce only at commit f07d530, because they import
`libs/quant-core/tests/golden/generate_reference_values.py` and private
`quant_core.pricing.black_scholes` names (`_at_expiry`, `_zero_vol`) as they
were at that commit. Every file is byte-for-byte the file the step produced;
none has been edited since.

## Files

| File | sha256 | Bytes | Step | Backs (ADR-0031) |
|---|---|---|---|---|
| `tol_proto.py` | `546706219ed8ed1dac8f2d57c3b8c7e97c7a5cb1553be25c4f33b1746ccf5f35` | 8148 | 1c | CRR and plain Jarrow-Rudd reference lattices imported by every Step 1c script |
| `jr_proto.py` | `7af26d962fd64803883c2bae068edab55f25e010531777da1b293455253713e5` | 10798 | 1c | Decision 1: CRR probability outside (0,1); plain Jarrow-Rudd forward error |
| `jr_extra.py` | `725492fbf551eb92194793432b9898bbb249e4c19f6ac4de04f209faa474e2b0` | 2144 | 1c | The forward-matched variant (`jr_rn`) used by `prop_abs.py` |
| `prop_scan.py` | `0fa564a9adb9b26ec86c5cc6281f70dc0bf280c9a91782c16a0cf6f6ee41dc9f` | 2009 | 1c | Property scan of plain Jarrow-Rudd |
| `prop_scan_rn.py` | `b06616f7f9b44acbfa79f2993c28362873c4f97430394089a92751184413a0b2` | 1473 | 1c | Property scan of the forward-matched variant |
| `prop_abs.py` | `8798cdd13a2d9068404e7005b2eae2080fdcc2e24ad1f3c77732888a15d54f56` | 1747 | 1c | Decision 1: monotonicity in vol, forward-matched variant |
| `step1c_jr_proto.txt` | `c0a838b84b24f91a3e104d75ed592771a79c5277aa44668db761834d732d9f1e` | 8608 | 1c | Decision 1: 262 of 1,296 (line 2); 34.5% below at vol 3, T 10 (line 23) |
| `step1c_jr_extra.txt` | `e27bc0e9fd85c5f10cf319d94adc517bf3d4fb06d62add872baa4ed887d63fab` | 941 | 1c | Forward-matched variant against CRR and Black-Scholes |
| `step1c_prop_scan.txt` | `efd564b36a51f2a8f6a8599f02137c6911d73bb3079f3f3bd0cea95661d91adc` | 469 | 1c | Plain Jarrow-Rudd property failures |
| `step1c_prop_scan_rn.txt` | `6dfcb8f2cb3ff3f39c5c681a953e2675516f03f9ef2454de176c853defb37752` | 1092 | 1c | Forward-matched property failures |
| `step1c_prop_abs.txt` | `ab15a2a02b04c1e3bb3f0a9eb26acbecf0f65b3dc28225f8b68fd2b21809019f` | 1037 | 1c | Decision 1: monotonicity failures, 2 for the forward-matched variant (line 5) |
| `step1d_measure.py` | `e5d31ff127c20491584dd0196f5e06268838ad659d766d32268a06ea2bb21b12` | 26857 | 1d | The lattice, theta estimator (line 111), CRR and control-variate measurements |
| `step1d_output.txt` | `314ebcb907c1f05b35c60d0a4fdfb0088bb712130fb3b57a9dc642b35e966ae6` | 26744 | 1d | Decision 1 control variate (380, 5.305e-2, 58, 46%); Verification: CRR, closed-form anchor, convergence, American = European; T → 0 limits |
| `step1e_measure.py` | `83586e576ead5c0eb3395a6dbf96cd164ab28ea92208fff2cb7204799d0d61af` | 23612 | 1e | Domain map, rho Methods A and B, vega bumps, deterministic branch |
| `step1e_p1.txt` | `d31cf9715133189b6de3e7545da66b5995a3a34c1e915da992681d21bc963fde` | 10619 | 1e | Decision 5: delta 0 against a reference of 0.35 as λ approaches 1 |
| `step1e_p23.txt` | `446e0a17f01e5cb809719ce233e4ce65b3c8794d320481de3e9368c94a30ab3d` | 19067 | 1e | Decision 2: Method B p within 5.122e-10 of 1/2, bumped p in [0.360, 0.640], rho medians; Decision 5: vega 0 against 6.7 to 9.9 |
| `step1e_p4.txt` | `b0aa77e66dbc2e81b5b702d325b94785f81682f9814f4a0d5a6056c169ebbff1` | 10626 | 1e | Decision 4 and Verification: deterministic branch against the lattice; Decision 5: gamma noise and the a floor |
| `step1f_measure.py` | `cd6df1ad004f24c5c542ad679299290f7c411ebe08d29e9da2256510aedef436` | 25752 | 1f | The sampler, candidates C1 to C4 and the budget rule |
| `step1f_p13.txt` | `1f93530516175299779bc54622ed483db44e76458c8d6e6abef836d0f9658d71` | 15678 | 1f | Decision 5: D (C4) meets the budget at 16,352 points; Verification: property bounds |
| `step1f_p2.txt` | `45d58160ab6d6a7ba84eb18dc217bb7bbbb23d4d7bafdc257425dad3c1906da6` | 37550 | 1f | Known limitations: vega and rho budget misses, the rho kink at r = 0 |
| `step1f_p45.txt` | `7054c50115a0b8ab11cb63870a3444f9513f5f52f5c88b297e3fc149eb8bd9c7` | 2945 | 1f | Verification: vega and rho goldens; Performance; Decision 5: 81.6% coverage |
| `rho_b_check.py` | `6919de356e4809e9db9b810edd82a8f19beb3fcf367a5e16b01b2d8559c65bf8` | 829 | 2b | Rho Methods A and B at σ = 1e-6 |
| `rho_b_check.txt` | `0478a3199ec5524cfbdba7e8e24f5141a687494a99c0be27aadbd5d1bdf85068` | 1264 | 2b | Decision 2: Method B bumped p reaches 8.155 at σ = 1e-6; Decision 4 and Verification: rho 1.89e-3 relative by rebuilding the grid (Method A) |

## Provenance

- `tol_proto.py`'s hash was first recorded at Step 2b. It was written in Step 1c,
  and every Step 1c script imports it.
- The five `step1c_*.txt` outputs were captured at Step 2b by re-running the
  Step 1c scripts at f07d530.
- `rho_b_check.py` and `rho_b_check.txt` were captured at Step 2b.

## Reproducing

Every command below runs from the repository root's `.venv`.

### Step 1c

The scripts put the working directory on `sys.path` (`sys.path.insert(0, ".")`)
and import `tol_proto.py`, `jr_proto.py` and `jr_extra.py` from it, so run them
from inside this directory:

```
cd docs/adr/evidence/0031
../../../../.venv/bin/python -I -B jr_proto.py > step1c_jr_proto.txt
```

and likewise for `jr_extra.py`, `prop_scan.py`, `prop_scan_rn.py` and
`prop_abs.py`. They write only to stdout. Run this way at Step 2b, four outputs
were byte-identical to the committed ones; `step1c_jr_proto.txt` differed only
in its three timing lines (108 to 110).

### Steps 1d to 1f

Each script adds `<REPO>/libs/quant-core/tests/golden` to `sys.path` and imports
the mpmath reference generator from it, so `REPO` must point to a checkout of
f07d530:

- `step1d_measure.py:22`: `REPO = "/Users/mac/Projects/meridian"`. It writes to
  stdout only; `step1d_output.txt` is that stdout.
- `step1e_measure.py:25`: `REPO = "/Users/mac/Projects/meridian"`. It writes
  `step1e_<shard>.txt` (shards `p1`, `p23`, `p4`) next to the script
  (`step1e_measure.py:469`), overwriting the committed outputs if run here.
- `step1f_measure.py:24`: `REPO = "/Users/mac/Projects/meridian"`. It writes
  `step1f_<shard>.txt` (shards `p13`, `p2`, `p45`) next to the script
  (`step1f_measure.py:522`), overwriting the committed outputs if run here.

`step1d_measure.py` and `step1e_measure.py` also import `quant_core` from the
installed package. These scripts were not re-run at Step 2b.

### rho_b_check

`rho_b_check.py:3` puts the absolute path of the Step 1d to 1f scratch
directory on `sys.path` and imports `step1e_measure` from it; that path must
point to a directory holding `step1e_measure.py`, for example this one. It
writes to stdout only. Command run at Step 2b, from the repository root:

```
.venv/bin/python -I -B <directory>/rho_b_check.py > rho_b_check.txt
```
