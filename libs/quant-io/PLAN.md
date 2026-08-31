# quant-io — Plan

**Owner:** Eng-B  ·  **Quarter:** Q1  ·  **Status:** in progress

## Mission
The I/O boundary between `quant-core`'s pure functions and the outside world:
Kafka producer/consumer wrappers, schema-registry client, and clock access
used by `services/pricer` and `services/ingest`. Without this, every service
would reimplement its own Kafka/registry glue, and the "no I/O in
quant-core" boundary (ADR-0010) would have nowhere consistent to live on the
Python side.

## In scope this quarter
- [x] Avro serialize/deserialize helpers wrapping the generated bindings for
      `Tick` (`quant_io/tick_producer.py`, `quant_io/producer.py`,
      `quant_io/consumer.py`). `PortfolioState`/`RiskSnapshot` equivalents
      are not built yet — no caller needs them until `services/pricer`
      starts.
- [ ] Schema-registry client wrapper (register/fetch schema, compatibility
      check) used by `make gen` / CI. Schema registration itself now happens
      as a side effect of `AvroProducer`'s `AvroSerializer` (confirmed
      registering `market.ticks-value` correctly against the real registry),
      but there is no standalone client wrapper for `make gen`/CI to call
      yet.
- [x] Kafka consumer/producer thin wrappers used by `services/ingest`
      (`AvroProducer`/`AvroConsumer`, generic; `TickProducer`/
      `make_tick_consumer`, `market.ticks`-specific). `services/pricer`
      has no caller yet, so only the `Tick` path has been exercised.
- [x] `now_utc()` helper (`quant_io/clock.py`) as the one sanctioned place a
      wall clock is read on the Python side.

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
- [ ] Deliverables above complete (Tick path only so far; PortfolioState/
      RiskSnapshot and the standalone registry-client wrapper remain)
- [x] Tests per `docs/test-strategy.md` (contract-test layer, against a real
      local Kafka/registry via testcontainers — see
      `libs/quant-io/tests/contract/`)
- [x] Contract tests pass against `contracts/` (round-trip through a real
      broker + registry, and registered-subject-matches-checked-in-schema)
- [x] Docs updated (`docs/conventions.md` time-semantics section)
- [ ] NFR targets in `docs/nfr-budget.md` met or an ADR explains the
      deviation (N/A directly this quarter — this package has no standalone
      latency/throughput target; it's exercised via the services that use it)

## Open questions
- Consumer group naming convention across services. Owner: Eng-B, by-when:
  before `services/pricer` needs to produce/consume alongside `services/ingest`
  (resolved for now: `services/ingest`'s tests use `f"test-{uuid.uuid4()}"`
  per test run, not a fixed convention — a real convention is still needed
  once a second service joins the same topics).
- `confluent-kafka` is pinned to `>=2.4,<2.5` (see `pyproject.toml`) because
  2.15's `schema_registry` module unconditionally imports an async client
  needing `httpx`/`authlib`/`cachetools`. Owner: Eng-B, by-when: revisit next
  time this pin needs bumping (e.g. a CVE or a needed 2.5+ feature) — check
  whether upstream has made the async import lazy/optional by then.

## Session log
- 2026-08-31 (contracts session, Eng-A): `contracts/generated/python`
  (package `meridian_contracts`) now exists — real dataclass bindings for
  `Tick`, `RiskSnapshot`, `PortfolioState` (+ nested `Position`) and their
  key types, with `to_dict`/`from_dict` and an embedded schema. This
  workstream's Avro serialize/deserialize helpers wrap these, not a
  hand-rolled parser — `pip install -e contracts/generated/python`.
- 2026-08-30 (ingest session): Built the `Tick` producer/consumer path —
  `quant_io/producer.py` (`AvroProducer`: idempotent, `acks=all`, explicit
  delivery callbacks, bounded-queue backpressure), `quant_io/consumer.py`
  (`AvroConsumer`), `quant_io/tick_producer.py` (`market.ticks`-specific
  `TickProducer`/`make_tick_consumer`), `quant_io/clock.py` (`now_utc`).
  Built together with `services/ingest` as its first real caller, per this
  session's operating principle that an adapter built without one is
  designed against a guess. Verified end-to-end against a real local
  Kafka + schema registry (both via `docker-compose.yml` manually and via
  testcontainers in the test suite): schema registers correctly under
  `market.ticks-value`, matching the checked-in `.avsc` byte-for-byte;
  a forced `MSG_SIZE_TOO_LARGE` broker rejection surfaces as `DeliveryError`
  rather than being swallowed (confirmed by temporarily removing the
  `except KafkaException` handling and watching the corresponding
  `services/ingest` test fail, then restoring it).
  Added `libs/.importlinter` (a `layers` contract: `quant_io` may depend on
  `quant_core`, never the reverse) since nothing previously stated that
  direction explicitly for this package pair — `libs/quant-core/.importlinter`
  only prevented `quant_core` reaching outward.
  `confluent-kafka` pinned to `<2.5` (see Open questions) after `2.15`
  failed to import without extra transitive deps not otherwise needed here.
