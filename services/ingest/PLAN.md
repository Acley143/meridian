# ingest — Plan

**Owner:** Eng-C  ·  **Quarter:** Q1  ·  **Status:** not started

## Mission
Produces the `Tick` stream that the rest of the system reacts to. In Q1
there's no real market feed, so this service simulates one — but it's the
one place `event_time`/`ingest_time` skew for ticks is established
(ADR-0005), so it has to behave like a real feed source, not a shortcut.

## In scope this quarter
- [ ] Simulated tick generator for a small fixed set of instruments
      (equities only — options are quoted derivatively, not simulated
      directly in Q1).
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
  Eng-A (contracts owner) and updating `docs/domain-model.md` first.
- **Depends on:** `contracts/avro/tick.avsc` (ADR-0002), ADR-0005 (time
  policy), `libs/quant-io` for the Kafka producer wrapper.

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
- Implementation language: Python (consistent with `quant-io`) or Java
  (consistent with `core-service`)? Owner: Eng-C, by-when: before first
  commit to this directory — pick one, note the choice here, update this
  workstream's `CLAUDE.md` with the concrete toolchain.

## Session log
(none yet)
