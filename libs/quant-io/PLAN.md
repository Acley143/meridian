# quant-io — Plan

**Owner:** Eng-B  ·  **Quarter:** Q1  ·  **Status:** not started

## Mission
The I/O boundary between `quant-core`'s pure functions and the outside world:
Kafka producer/consumer wrappers, schema-registry client, and clock access
used by `services/pricer` and `services/ingest`. Without this, every service
would reimplement its own Kafka/registry glue, and the "no I/O in
quant-core" boundary (ADR-0010) would have nowhere consistent to live on the
Python side.

## In scope this quarter
- [ ] Avro serialize/deserialize helpers wrapping the generated bindings for
      `Tick`, `PortfolioState`, `RiskSnapshot`.
- [ ] Schema-registry client wrapper (register/fetch schema, compatibility
      check) used by `make gen` / CI.
- [ ] Kafka consumer/producer thin wrappers used by `services/pricer` and
      `services/ingest`.
- [ ] `now_utc()` helper as the one sanctioned place a wall clock is read on
      the Python side.

## Explicitly out of scope
- Any pricing logic — that's `libs/quant-core`.
- Portfolio materialization/business logic — that's `services/pricer`.
- Java or TypeScript equivalents — those live alongside `services/core-service`
  and `apps/dashboard` respectively, not here.

## Boundaries
- **Owns:** `libs/quant-io/**`.
- **Must not touch:** everything else, including `libs/quant-core` internals
  (may depend on it, may not modify it in the same PR without a separate
  review).
- **Depends on:** `contracts/avro/*.avsc` (ADR-0002), ADR-0005 (time policy).

## Interfaces
Python functions/classes wrapping `confluent-kafka` and the schema-registry
client, consumed only by direct import from `services/pricer` and
`services/ingest`. Not itself a wire contract.

## Definition of done
- [ ] Deliverables above complete
- [ ] Tests per `docs/test-strategy.md` (contract-test layer, against a real
      local Kafka/registry via `docker-compose.yml`)
- [ ] Contract tests pass against `contracts/`
- [ ] Docs updated
- [ ] NFR targets in `docs/nfr-budget.md` met or an ADR explains the
      deviation (N/A directly this quarter — this package has no standalone
      latency/throughput target; it's exercised via the services that use it)

## Open questions
- Consumer group naming convention across services. Owner: Eng-B, by-when:
  before `services/ingest` needs to produce to a shared topic.

## Session log
(none yet)
