# quant-core

Pure pricing library. Python 3.12, no runtime dependencies beyond NumPy/SciPy
for numerics.

- No I/O imports, ever — see ADR-0010. `.importlinter` in this directory is
  the enforced contract; run `lint-imports` locally before pushing, it's the
  same check CI runs.
- Every public function takes valuation time as an explicit argument. Never
  call `datetime.now()` — if you find yourself wanting to, the time belongs
  in the caller (a service in `services/`), not here.
- Money in, money out is `Decimal`; everything inside a pricing formula is
  `float64` (ADR-0004). Convert at the function boundary, explicitly.
- Local test command: `pytest libs/quant-core -q`. Golden tests live under
  `tests/golden/`; property tests (Hypothesis) under `tests/property/`.
- The one mistake most likely here: importing something from `quant-io` or
  any service package "just to reuse a type." Don't — it's an I/O-adjacent
  package and pulling it in breaks purity transitively. Duplicate the type or
  push it down into a truly shared, pure module instead.
