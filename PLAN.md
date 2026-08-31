# Meridian — Program Plan

Four quarters, five engineers. This is the program-level plan; each
workstream has its own `PLAN.md` with concrete deliverables, boundaries, and
a session log — this file links to them and tracks which quarter is current.

## Q1 — Black-Scholes pricer, simulated Kafka feed, service/schema skeleton (CURRENT)

Establish the skeleton end to end: contracts, a pure Black-Scholes pricer, a
simulated tick feed, a core service that can hold portfolio/trade state and
expose it, and a dashboard that can render one risk number live. Depth comes
later; Q1 proves the pipe is connected.

- [contracts](contracts/PLAN.md)
- [libs/quant-core](libs/quant-core/PLAN.md)
- [libs/quant-io](libs/quant-io/PLAN.md)
- [services/ingest](services/ingest/PLAN.md)
- [services/pricer](services/pricer/PLAN.md)
- [services/core-service](services/core-service/PLAN.md)
- [apps/dashboard](apps/dashboard/PLAN.md)
- [infra](infra/PLAN.md)

## Q2 — American options, portfolio VaR, audit log

Extend the pricer to American-style exercise, add portfolio-level VaR
aggregation (single-portfolio, not yet correlated across portfolios), and
land the hash-chained audit log (ADR-0008) in `core-service`.

## Q3 — Monte Carlo, correlated portfolio risk, load-test prep

Add deterministic Monte Carlo pricing (ADR-0006) for instruments without a
closed form, extend VaR to correlated cross-portfolio risk (the reason
`portfolio.state` exists per ADR-0003), and build the load-test harness ahead
of Q4.

## Q4 — Hardening, load testing, NFR verification

Run the load test against every line in `docs/nfr-budget.md`, fix what fails,
and write up the results. No new features unless a budget line requires one
to pass.

## Open questions

- **Cross-currency portfolio aggregation (Q2 blocker).** Per ADR-0014,
  `libs/quant-core` prices each instrument in that instrument's own
  currency and has no visibility into a portfolio's `base_currency`
  (`docs/domain-model.md#Portfolio`) — it cannot detect or prevent a
  currency mismatch by construction. ADR-0017 (cash Greeks) makes this
  concrete: cash Greeks are summable across a portfolio's different
  underlyings *within one currency*, not across currencies — aggregating a
  EUR-denominated position into a USD portfolio total without conversion
  is silently wrong, and nothing in ADR-0017 solves it (deliberately —
  see that ADR's Consequences). Q2's portfolio VaR is the first
  deliverable that aggregates positions across a portfolio; if any two
  positions in a book are quoted in different currencies, summing them
  without conversion is silently wrong and no existing component catches
  it. Needs a decision on where FX conversion happens (`services/pricer` at
  aggregation time is the natural place, but that's not yet decided) before
  VaR aggregation is implemented. Owner: TBD (spans `services/pricer` and
  `services/core-service`, not a single workstream), by-when: before Q2
  VaR work starts.

## Team & ownership

See `docs/rotation.md` for who owns which surface, per quarter.
