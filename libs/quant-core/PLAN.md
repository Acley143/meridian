# quant-core — Plan

**Owner:** Eng-B  ·  **Quarter:** Q1  ·  **Status:** not started

## Mission
Pure pricing and risk-analytics functions for every instrument type Meridian
supports. Without this, nothing in the system can compute a price or a Greek
— every other workstream either produces inputs to this library or consumes
its outputs. It is the one piece of the system whose correctness is
independently verifiable against a closed-form reference.

## In scope this quarter
- [ ] Black-Scholes closed-form pricer for vanilla European options (price,
      delta, gamma, vega, theta, rho).
- [ ] `.importlinter` contract enforcing ADR-0010 (no I/O imports).
- [ ] Golden tests against published Black-Scholes reference values.
- [ ] Property tests: put-call parity, delta bounds, gamma non-negativity,
      price monotonic in volatility.
- [ ] Public function signatures take valuation time as an explicit
      argument (no internal clock access).

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
  ADR-0010 (purity).

## Interfaces
Exposes pure Python functions taking `Instrument`-shaped inputs (per
`docs/domain-model.md#instrument`) and a valuation `datetime`, returning
price and Greeks as `float64`. No network or file interface — consumed only
by direct import from `services/pricer`. Not yet published to
`contracts/` because it isn't a wire contract; if that changes, it becomes
one.

## Definition of done
- [ ] Deliverables above complete
- [ ] Tests per `docs/test-strategy.md` (golden + property layers)
- [ ] Contract tests pass against `contracts/` (N/A this quarter — no wire
      contract yet; revisit if that changes)
- [ ] Docs updated (`docs/domain-model.md` if `Instrument` fields needed for
      pricing are missing)
- [ ] NFR targets in `docs/nfr-budget.md` met or an ADR explains the
      deviation (pricing-accuracy line: 1e-6 relative error vs. closed-form)

## Open questions
- Which day-count convention for time-to-expiry (ACT/365 vs. ACT/ACT)? Owner:
  Eng-B, by-when: before the first golden test is written.

## Session log
(none yet)
