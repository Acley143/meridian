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
- [ ] Produce `RiskSnapshot`s (`contracts/avro/risk-snapshot.avsc`) keyed
      per ADR-0007: `price`, and the five cash Greeks
      (`cash_delta`/`cash_gamma`/`cash_vega`/`cash_theta`/`cash_rho`,
      ADR-0017 — formulas and aggregation defined there, this workstream
      implements them, not designs them). Portfolio-level VaR (`var_95`)
      is a stub value this quarter (Q2 for real computation).
- [ ] Idempotent-upsert-safe production (no duplicate/gap under at-least-once
      redelivery).
- [ ] Apply `Instrument.contract_size` to `quant-core`'s per-unit
      `PricingResult` exactly once, at the position level, when combining a
      priced position into `price` and each cash Greek (ADR-0014, ADR-0017
      — `quant-core` itself never sees or applies this multiplier). Test: a
      position with a non-unit `contract_size` (e.g. 100) must produce a
      portfolio value/cash Greek that fails if the multiplication is
      removed — not a general pricing-smoke test, one that specifically
      pins the multiplier being applied.
- [ ] The `float64 -> Decimal` conversion for each cash Greek goes through
      `quant_core.numeric.to_money` (ADR-0013) — no second rounding
      implementation here.
- [ ] Regression test (ADR-0017): summing raw per-unit `PricingResult.gamma`
      across two positions in *different* underlyings must NOT be what the
      cash-Greek aggregation code does — assert the aggregated
      `cash_gamma` is not equal to (or derived from) a naive sum of raw
      per-unit gammas across underlyings. This is a test for the specific
      mistake ADR-0017 exists to prevent, not just a test that the correct
      formula happens to be implemented.

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
  (ADR-0002), ADR-0003, ADR-0004, ADR-0005, ADR-0007, ADR-0013 (the one
  Decimal<->float64 boundary conversion, `quant_core.numeric.to_money`),
  ADR-0014 (quant-core prices per unit of underlying; this service owns
  `contract_size`), ADR-0017 (cash Greek aggregation formulas), `libs/quant-core`,
  `libs/quant-io`.

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
- ~~How per-position Greeks aggregate into `RiskSnapshot`'s portfolio-level
  fields~~ **Resolved: `docs/adr/0017-cash-greeks.md`.** Cash Greeks
  (currency amounts, `Decimal(38,8)`, 1% basis for delta/gamma), not raw
  per-unit Greeks summed across underlyings — see that ADR for why and the
  exact formulas. This workstream implements the formulas; see the
  deliverables above.
- Storage for the local materialized `portfolio.state` view (in-memory dict
  vs. embedded store like SQLite/RocksDB) — matters for restart/recovery
  behavior. Owner: Eng-B, by-when: before the recovery test is written.
- Currency: cash Greeks are summable across underlyings, not across
  currencies. A EUR position aggregated into a USD portfolio total without
  conversion is silently wrong. Deliberately NOT owned here — see root
  `PLAN.md`'s open questions, ahead of Q2 portfolio VaR.

## Session log
- 2026-08-31 (contracts session, Eng-A): `contracts/avro/risk-snapshot.avsc`
  gained real fields this session — `portfolio_value` renamed `price`,
  the `greeks` map replaced with discrete Greek fields, and `scenario_id`
  added (propagate from the `Tick`s that produced this snapshot).
- 2026-08-31 (later same session, Eng-A): those discrete Greek fields were
  still raw per-unit Greeks, which don't aggregate meaningfully across a
  portfolio's different underlyings. Resolved via ADR-0017 (cash Greeks) —
  see Open questions and the updated deliverables above.
