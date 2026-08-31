# ingest — Plan

**Owner:** Eng-C  ·  **Quarter:** Q1  ·  **Status:** in progress

## Mission
Produces the `Tick` stream that the rest of the system reacts to. In Q1
there's no real market feed, so this service simulates one — but it's the
one place `event_time`/`ingest_time` skew for ticks is established
(ADR-0005), so it has to behave like a real feed source, not a shortcut.
Per ADR-0011, this service is Python, and the stochastic price-path math it
runs lives in `libs/quant-core`, not here.

## In scope this quarter
- [x] Simulated tick generator for a small fixed set of instruments
      (equities only — options are quoted derivatively, not simulated
      directly in Q1), driven by `libs/quant-core`'s
      `simulate_path(seed, params, n)` (ADR-0011). See `ingest/feed.py`.
- [x] `scenario_id` concept: a named, seeded market scenario (ADR-0011,
      ADR-0006) — the same `scenario_id` yields a byte-identical tick stream
      on every run. Configurable at service startup (`ingest/cli.py` takes a
      scenario YAML path; see `ingest/scenario.py` and
      `services/ingest/scenarios/`).
- [x] Produces `Tick` messages (`contracts/avro/tick.avsc`) to Kafka at a
      configurable rate, with realistic (non-zero) `event_time`/`ingest_time`
      skew. Two pacing modes (`--pacing realtime|replay`), producing
      identical data (`docs/conventions.md`).
- [x] Contract tests against `contracts/avro/tick.avsc` — see
      `libs/quant-io/tests/contract/` (this workstream's producer is the
      thing under test there) and `services/ingest/tests/` for the
      reproducibility/ordering/pacing/delivery-failure suite.

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
Produces to the `market.ticks` Kafka topic, schema `contracts/avro/tick.avsc`. No
inbound interface — this is a pure source.

## Definition of done
- [x] Deliverables above complete
- [x] Tests per `docs/test-strategy.md` (contract-test layer, plus
      integration-style reproducibility/ordering/pacing/delivery-failure
      tests — all against a real local Kafka + schema registry via
      testcontainers, per `docs/test-strategy.md`'s "not a mock of either"
      rule)
- [x] Contract tests pass against `contracts/`
- [x] Docs updated (`docs/conventions.md` gained a time-semantics section;
      `services/ingest/scenarios/README.md` documents the scenario_id
      immutability rule)
- [ ] NFR targets in `docs/nfr-budget.md` met or an ADR explains the
      deviation (throughput target still formally deferred to Q4 per above,
      but measured informally this session as a sanity check: `replay`
      pacing sustained ~39,700 ticks/sec producing `throughput-1000.yaml`'s
      60,000 ticks to a single local single-partition broker — see session
      log. Not a load test, no assertion added; a real Q4 load test needs
      its own multi-partition, multi-minute run per `docs/nfr-budget.md`.)

## Open questions
- Which stochastic process(es) `simulate_path` should support beyond a
  single GBM path in Q1 (e.g. jump-diffusion, regime switching) — Owner:
  Eng-B (quant-core owner) and Eng-C jointly, by-when: Q2 planning.
- `throughput-1000.yaml`'s instrument count/tick count were sized by
  estimation (20 instruments x 3,000 ticks = 60,000 records), not derived
  from a target sustained-duration formula. Owner: Eng-C, by-when: Q4
  load-test planning — revisit sizing once the real load-test harness
  (Q3 deliverable per root `PLAN.md`) exists and can specify what duration
  it actually needs.
- This session fixed two `docker-compose.yml` bugs blocking every
  workstream (invalid `CLUSTER_ID`; Kafka's advertised listener pointing
  containers at `localhost`, which is wrong for inter-container traffic) —
  see `infra/PLAN.md` session log. Kafka's host-facing port changed from
  9092 to 9093 as a result (`infra/PLAN.md`'s stated interface). Owner:
  Eng-A, by-when: infra workstream should review this fix; it was made
  narrowly to unblock this session rather than as a full infra pass.

## Session log
- 2026-08-31 (contracts session, Eng-A): `contracts/avro/tick.avsc` gained
  `scenario_id` (ADR-0011), default `""`, propagated end-to-end to
  `RiskSnapshot.scenario_id`. This workstream's ticks must set a real
  `scenario_id`, not rely on the wire default.
- 2026-08-30 (this session): Built `services/ingest` end to end together
  with `libs/quant-io`'s producer (see that workstream's session log for
  the producer-side detail). `ingest/scenario.py` loads
  `services/ingest/scenarios/*.yaml`; `ingest/feed.py` derives each
  instrument's `simulate_path` seed deterministically from
  `(scenario_id, scenario_seed, instrument_id)` (`ingest/seeding.py`,
  mirroring ADR-0006's pattern) and stamps `event_time` purely from scenario
  arithmetic (`docs/conventions.md`), never the wall clock.
  `ingest/cli.py` is the entrypoint (`python -m ingest.cli <scenario.yaml>
  --pacing realtime|replay`). Structured logging carries `scenario_id` on
  every line (`ingest/logging_config.py`).
  Verified against a real local stack: `make gen`-produced schema registers
  correctly, `docker compose up` + `python -m ingest.cli
  scenarios/small-deterministic.yaml --pacing replay` produced 40 ticks
  (2 instruments x 20) end to end.
  Test suite (testcontainers-backed, `services/ingest/tests/`):
  reproducibility (same scenario twice -> byte-identical except
  `ingest_time`; different seed -> diverges), pacing determinism (realtime
  vs. replay -> identical data), ordering (per-instrument event-time order
  holds), delivery failure (an oversized `scenario_id` forces a real
  `MSG_SIZE_TOO_LARGE` broker rejection; confirmed the test fails if the
  producer's error handling is removed, then restored it), and scenario_id
  uniqueness across `scenarios/*.yaml`.
  Rejected approach: originally planned to run reproducibility/ordering
  tests against the shared `market.ticks` topic; switched to an ephemeral
  per-test topic (`kafka_helpers.TopicTickProducer`) instead, since reusing
  one topic across runs made it impossible to tell which run's records were
  which without offset bookkeeping the test didn't otherwise need.
