# pricer — Plan

**Owner:** Eng-B  ·  **Quarter:** Q1  ·  **Status:** not started

## Mission
Consumes ticks and portfolio state, prices every position using
`libs/quant-core`, and produces `RiskSnapshot`s. This is where the hot path
(ADR-0003) actually runs — it's the component the latency budget in
`docs/nfr-budget.md` is mostly about.

## In scope this quarter
- [ ] Consume `portfolio.state` and materialize a local view keyed by
      `portfolio_id` (ADR-0003).
- [ ] Consume the `ticks` topic and, on each relevant tick, re-price affected
      positions using `libs/quant-core`'s Black-Scholes pricer.
- [ ] Produce `RiskSnapshot`s (`contracts/avro/risk-snapshot.avsc`) keyed per
      ADR-0007, portfolio-level `price` only (VaR/Greeks
      aggregation beyond per-position pass-through is Q2+).
- [ ] Idempotent-upsert-safe production (no duplicate/gap under at-least-once
      redelivery).
- [ ] Apply `Instrument.contract_size` to `quant-core`'s per-unit
      `PricingResult` exactly once, at the position level, when combining a
      priced position into `price` (ADR-0014 — `quant-core`
      itself never sees or applies this multiplier). Test: a position with
      a non-unit `contract_size` (e.g. 100) must produce a portfolio value
      that fails if the multiplication is removed — not a general
      pricing-smoke test, one that specifically pins the multiplier being
      applied.

## Explicitly out of scope
- Portfolio-level VaR computation (Q2) — `var_95` is produced but not yet
  meaningfully computed; a stub value is acceptable this quarter with that
  noted in the PR.
- Correlated cross-portfolio risk (Q3).
- Monte Carlo pricing (Q3, ADR-0006) — Q1 only prices instruments
  `quant-core` supports (vanilla European options), via closed form.
- Calling back into `core-service` for anything — forbidden by ADR-0003, not
  just out of scope.

## Boundaries
- **Owns:** `services/pricer/**`.
- **Must not touch:** `libs/quant-core` internals (may depend on it),
  `contracts/` (coordinate with Eng-A for any schema change).
- **Depends on:** `contracts/avro/{tick,portfolio-state,risk-snapshot}.avsc`
  (ADR-0002), ADR-0003, ADR-0004, ADR-0005, ADR-0007, ADR-0014 (quant-core
  prices per unit of underlying; this service owns `contract_size`),
  `libs/quant-core`, `libs/quant-io`.

## Interfaces
Consumes `ticks` and `portfolio.state`. Produces `risk.snapshots`, schema
`contracts/avro/risk-snapshot.avsc`.

## Definition of done
- [ ] Deliverables above complete
- [ ] Tests per `docs/test-strategy.md` (contract tests + the recovery test
      for the "kill mid-stream" requirement)
- [ ] Contract tests pass against `contracts/`
- [ ] Docs updated
- [ ] NFR targets in `docs/nfr-budget.md` met or an ADR explains the
      deviation (latency p99 ≤ 250ms — Q1 measures and reports the number
      even if it doesn't yet pass; Q4 is when it must pass)

## Open questions
- Storage for the local materialized `portfolio.state` view (in-memory dict
  vs. embedded store like SQLite/RocksDB) — matters for restart/recovery
  behavior. Owner: Eng-B, by-when: before the recovery test is written.

## Session log
- 2026-08-31 (contracts session, Eng-A): `contracts/avro/risk-snapshot.avsc`
  gained real fields this session — `portfolio_value` renamed `price`,
  the `greeks` map replaced with discrete `delta`/`gamma`/`vega`/`theta`/`rho`
  doubles, and `scenario_id` added (propagate from the `Tick`s that produced
  this snapshot). This workstream's deliverables above are updated to match
  the new field name; the aggregation logic itself (how per-position Greeks
  become the portfolio-level fields) is still this workstream's to design —
  see Open questions.
