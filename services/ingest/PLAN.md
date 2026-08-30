# ingest — Plan

**Owner:** Eng-C  ·  **Quarter:** Q1  ·  **Status:** not started

## Mission
Produces the `Tick` stream that the rest of the system reacts to. In Q1
there's no real market feed, so this service simulates one — but it's the
one place `event_time`/`ingest_time` skew for ticks is established
(ADR-0005), so it has to behave like a real feed source, not a shortcut.
Per ADR-0011, this service is Python, and the stochastic price-path math it
runs lives in `libs/quant-core`, not here.

## In scope this quarter
- [ ] Simulated tick generator for a small fixed set of instruments
      (equities only — options are quoted derivatively, not simulated
      directly in Q1), driven by `libs/quant-core`'s
      `simulate_path(seed, params, n)` (ADR-0011).
- [ ] `scenario_id` concept: a named, seeded market scenario (ADR-0011,
      ADR-0006) — the same `scenario_id` yields a byte-identical tick stream
      on every run. Configurable at service startup.
- [ ] Produces `Tick` messages (`contracts/avro/tick.avsc`) to Kafka at a
      configurable rate, with realistic (non-zero) `event_time`/`ingest_time`
      skew.
- [ ] Contract tests against `contracts/avro/tick.avsc`.

## Explicitly out of scope
- Any real market data integration — simulated only through Q1 (and likely
  longer; not on the current roadmap).
- Options ticks — only the underlying equities are simulated; option prices
  are computed by the pricer, not fed in.
- Rate control tied to the 1,000 ticks/sec throughput target — that's a Q4
  load-test concern; Q1's rate is whatever's convenient for development.

## Boundaries
- **Owns:** `services/ingest/**`.
- **Must not touch:** `contracts/avro/tick.avsc` without coordinating with
  Eng-A (contracts owner) and updating `docs/domain-model.md` first;
  `libs/quant-core` internals (may depend on `simulate_path`, may not modify
  it in the same PR without a separate review).
- **Depends on:** `contracts/avro/tick.avsc` (ADR-0002), ADR-0005 (time
  policy), ADR-0011 (ingest is Python; `simulate_path` in `quant-core`),
  `libs/quant-core` for path simulation, `libs/quant-io` for the Kafka
  producer wrapper.

## Interfaces
Produces to the `ticks` Kafka topic, schema `contracts/avro/tick.avsc`. No
inbound interface — this is a pure source.

## Definition of done
- [ ] Deliverables above complete
- [ ] Tests per `docs/test-strategy.md` (contract-test layer)
- [ ] Contract tests pass against `contracts/`
- [ ] Docs updated
- [ ] NFR targets in `docs/nfr-budget.md` met or an ADR explains the
      deviation (throughput target explicitly deferred to Q4, see above)

## Open questions
- Which stochastic process(es) `simulate_path` should support beyond a
  single GBM path in Q1 (e.g. jump-diffusion, regime switching) — Owner:
  Eng-B (quant-core owner) and Eng-C jointly, by-when: Q2 planning.

## Session log
(none yet)
