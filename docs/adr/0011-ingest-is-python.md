# ADR-0011: Ingest is Python

## Status
Accepted

## Context
`services/ingest` (Q1: a simulated market feed) needs to generate stochastic
price paths for the instruments it feeds into the system. Generating a
realistic price path is quant logic — the same category of code as pricing —
and per ADR-0010, that logic belongs in `libs/quant-core`, which is Python.

`services/ingest`'s implementation language was left as an open question in
its `PLAN.md`. If ingest were implemented on the JVM (to match
`services/core-service`), it could not call into `libs/quant-core` directly,
forcing a second implementation of the same stochastic process (e.g.
geometric Brownian motion) in Java. That's two implementations of one
process, in the one component whose entire job is to be a trustworthy input
to everything downstream — and two implementations diverge silently, with no
mechanism to catch the drift.

## Decision
`services/ingest` is Python. The simulated price-path generator lives in
`libs/quant-core` as a pure function, `simulate_path(seed, params, n)`,
seeded deterministically per ADR-0006. `services/ingest` calls this function
directly and wraps its output as `Tick` messages via `libs/quant-io`.

## Consequences
- One implementation of the stochastic process, shared by ingest and (should
  it ever be needed) any test or tool that wants to regenerate the same
  scenario.
- A seeded feed makes a market scenario reproducible: a `scenario_id` yields
  a byte-identical tick stream on every run, the same way a
  `pricer_version` yields a reproducible price under ADR-0006.
- Combined with ADR-0007's pricer-versioned risk snapshots, the same
  simulated market day (`scenario_id`) can be replayed against two different
  `pricer_version`s and the resulting risk diffed — the same
  reproducibility property ADR-0006 and ADR-0007 already give the pricer,
  now extended to the market data that feeds it.
- `services/ingest`'s `PLAN.md` open question on implementation language is
  resolved; its manifest (`pyproject.toml`) already reflected this default
  and needs no further change.

## Alternatives considered
- **JVM ingest with an independent Java GBM/path-simulation implementation.**
  Rejected: creates a second, silently-divergent implementation of the same
  stochastic process, in the component whose only job is to be a trustworthy
  input — the highest-cost place in the system to have unverified
  cross-language drift.
- **JVM ingest calling into `quant-core` over a language boundary (e.g. a
  local RPC or subprocess call to Python).** Rejected as unnecessary
  complexity: it reintroduces a cross-process call in a component that has
  no other reason to need one, purely to avoid picking Python.
