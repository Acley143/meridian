# quant-core — Plan

**Owner:** Eng-B  ·  **Quarter:** Q1  ·  **Status:** Q1 deliverables complete

## Mission
Pure pricing and risk-analytics functions for every instrument type Meridian
supports. Without this, nothing in the system can compute a price or a Greek
— every other workstream either produces inputs to this library or consumes
its outputs. It is the one piece of the system whose correctness is
independently verifiable against a closed-form reference.

## In scope this quarter
- [x] Black-Scholes closed-form pricer for vanilla European options (price,
      delta, gamma, vega, theta, rho). `quant_core.pricing.black_scholes`.
- [x] `.importlinter` contract enforcing ADR-0010 (no I/O imports), plus a
      `tests/fixtures/purity_violation` fixture and CI step proving the
      contract can actually fail (a green run against an empty package
      proved nothing).
- [x] Golden tests against reference values from an independent
      implementation (`tests/golden/generate_reference_values.py`, mpmath).
- [x] Property tests: put-call parity, delta bounds, gamma/vega
      non-negativity, price monotonic in volatility, price monotonic
      non-increasing in strike, price at least forward-discounted
      intrinsic, price approaches intrinsic as T -> 0.
- [x] Public function signatures take valuation time as an explicit
      argument (no internal clock access) — `MarketState.valuation_time`.
- [x] `simulate_path(seed, params, n)`: pure stochastic price-path generator
      (ADR-0011), seeded per ADR-0006 via blake2b into an explicitly
      constructed `numpy.random.Generator`, consumed by `services/ingest`.
- [x] `quant_core.numeric` (`to_model`/`to_money`): the one Decimal<->float64
      boundary conversion (ADR-0013), banker's rounding, enforced by
      `tools/schema-lint/check_quant_core_boundary.py` in CI.
- [x] `quant_core.PRICER_VERSION` (manually-bumped semver, not a source
      hash), `docs/conventions.md` (Greek sign/unit conventions), frozen
      `mypy --strict`-clean types in `quant_core.types`.

## Explicitly out of scope
- American-style exercise (Q2).
- Monte Carlo pricing of any kind (Q3, ADR-0006).
- Portfolio-level aggregation (VaR, correlated risk) — this library prices
  one instrument at a time; aggregation lives in `services/pricer`.
- Any Kafka, HTTP, filesystem, or database code — that's `libs/quant-io` and
  `services/pricer`, by ADR-0010.

## Boundaries
- **Owns:** `libs/quant-core/**`.
- **Must not touch:** everything else. In particular, must not add a
  dependency on `libs/quant-io` or any `services/*` package.
- **Depends on:** `docs/domain-model.md` for the `Instrument` type shape;
  ADR-0004 (numeric types), ADR-0006 (deterministic MC, forward-looking),
  ADR-0010 (purity), ADR-0011 (ingest is Python; `simulate_path` lives here).

## Interfaces
Exposes pure Python functions taking `Instrument`-shaped inputs (per
`docs/domain-model.md#instrument`) and a valuation `datetime`, returning
price and Greeks as `float64`. `simulate_path` similarly takes a seed and
params and returns a price path. No network or file interface — consumed
only by direct import from `services/pricer` and `services/ingest`. Not yet published to
`contracts/` because it isn't a wire contract; if that changes, it becomes
one.

## Definition of done
- [x] Deliverables above complete
- [x] Tests per `docs/test-strategy.md` (golden + property layers). 60
      tests, 100% statement coverage on `quant_core`.
- [x] Contract tests pass against `contracts/` (N/A this quarter — no wire
      contract yet; revisit if that changes)
- [x] Docs updated (`docs/conventions.md` added; `docs/domain-model.md`
      needed no change — `EuropeanOption` is a pricing-scoped projection of
      `Instrument`, not a new wire type, see `quant_core/types.py`)
- [x] NFR targets in `docs/nfr-budget.md` met: golden tests assert 1e-6
      relative error, with a small absolute floor at the Decimal-scale-8
      quantisation granularity for near-zero prices (see
      `tests/golden/test_black_scholes_golden.py`).

## Open questions
- Time-to-expiry day-count: resolved as ACT/365F with a 365.25-day year
  (not the strict ACT/365F 365-day divisor) per the Q1 task spec;
  documented in `docs/conventions.md`. Worth confirming with Eng-B —
  "ACT/365F" conventionally means a fixed 365-day divisor, so pairing it
  with 365.25 is unusual and may have been a spec typo. Owner: Eng-B,
  by-when: before any pricer consumes quant-core in `services/pricer`.
- `EuropeanOption` omits `instrument_id`, `currency`, and `contract_size`
  from `docs/domain-model.md#Instrument` — pricing doesn't need them, and
  currency/contract_size conversion belongs at the position/portfolio
  layer (`services/pricer`), not inside a pure per-instrument pricer.
  Owner: Eng-B, by-when: revisit if `services/pricer`'s integration needs
  a fuller type than the pricing-scoped one here.
- `simulate_path`'s `PathParams` (s0, drift, volatility, dt) is a new type
  with no `docs/domain-model.md` counterpart, since it's a pure numerics
  input, not a wire type. Owner: Eng-B, by-when: N/A unless
  `services/ingest` needs it published as a contract.

## Session log
- 2026-08-30 (Eng-B session): Implemented all Q1 deliverables — purity
  enforcement fixture + CI assertion, `docs/conventions.md`, the
  Decimal/float64 boundary (`quant_core.numeric`) with a custom CI
  boundary-check script (import-linter can't express "no bare
  float()/Decimal() outside this file", only import graphs), `PRICER_VERSION`,
  frozen `mypy --strict` types, Black-Scholes with explicit T=0/sigma=0
  degenerate-case handling, `simulate_path` (exact-solution GBM,
  blake2b-seeded `numpy.random.Generator`, never touches global RNG
  state), and the full golden/property/boundary/determinism test suite
  (60 tests, 100% coverage). Corrected one property from the task spec:
  "price >= intrinsic value, always" only holds for European options when
  the continuous dividend yield is zero; implemented and tested the
  correct forward-discounted no-arbitrage floor instead (see
  `tests/property/test_black_scholes_properties.py`).
