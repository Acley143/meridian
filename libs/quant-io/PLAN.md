# quant-io — Plan

**Owner:** Eng-B  ·  **Quarter:** Q1  ·  **Status:** Q1 deliverables complete

## Mission
The I/O boundary between `quant-core`'s pure functions and the outside world:
Kafka producer/consumer wrappers, schema-registry client, and clock access
used by `services/pricer` and `services/ingest`. Without this, every service
would reimplement its own Kafka/registry glue, and the "no I/O in
quant-core" boundary (ADR-0010) would have nowhere consistent to live on the
Python side.

## In scope this quarter
- [x] Avro serialize/deserialize helpers wrapping the generated bindings for
      `Tick`, `PortfolioState`, and `RiskSnapshot`
      (`quant_io/tick_producer.py`, `quant_io/portfolio_state_io.py`,
      `quant_io/risk_snapshot_io.py`, `quant_io/producer.py`,
      `quant_io/consumer.py`). All three now have a real caller
      (`services/ingest` for `Tick`; `services/pricer` for all three —
      `PortfolioState` production is also `services/pricer/fixtures`'
      way of seeding the topic directly, per ADR-0003).
- [ ] Schema-registry client wrapper (register/fetch schema, compatibility
      check) used by `make gen` / CI. Schema registration itself now happens
      as a side effect of `AvroProducer`'s `AvroSerializer` (confirmed
      registering `market.ticks-value`, `portfolio.state-value`, and
      `risk.snapshots-value` correctly against the real registry), but
      there is no standalone client wrapper for `make gen`/CI to call yet.
- [x] Kafka consumer/producer thin wrappers used by `services/ingest` and
      `services/pricer` (`AvroProducer`/`AvroConsumer`, generic;
      topic-specific factories per record type). `AvroConsumer` gained
      manual-commit (`enable_auto_commit`, default `False`) and
      partition-EOF (`enable_partition_eof`, `PartitionEOF`, `on_assign`)
      support this session — needed by `services/pricer`'s hydration gate
      and by Task 7's "commit only after the snapshot is durably
      delivered" rule, and generically useful to any future consumer of
      this wrapper, not pricer-specific.
- [x] `now_utc()` helper (`quant_io/clock.py`) as the one sanctioned place a
      wall clock is read on the Python side.
- [x] Tombstone handling (a `None` value for a keyed record, e.g.
      `portfolio.state`'s deletion convention) needs no special-casing in
      `AvroConsumer` — `confluent_kafka`'s `AvroDeserializer` already
      returns `None` for `None` input without invoking the generated
      binding's `from_dict`, confirmed against a real broker/registry.

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
- [ ] Deliverables above complete (only the standalone registry-client
      wrapper for `make gen`/CI remains)
- [x] Tests per `docs/test-strategy.md` (contract-test layer, against a real
      local Kafka/registry via testcontainers — see
      `libs/quant-io/tests/contract/` and `services/pricer/tests/`, which
      exercises the `PortfolioState`/`RiskSnapshot` paths this workstream
      added this session)
- [x] Contract tests pass against `contracts/` (round-trip through a real
      broker + registry, and registered-subject-matches-checked-in-schema)
- [x] Docs updated (`docs/conventions.md` time-semantics section)
- [ ] NFR targets in `docs/nfr-budget.md` met or an ADR explains the
      deviation (N/A directly this quarter — this package has no standalone
      latency/throughput target; it's exercised via the services that use it)

## Open questions
- Consumer group naming convention across services. Owner: Eng-B, by-when:
  before a second long-running service (beyond `services/pricer`) needs a
  stable group id alongside it. Partially resolved this session:
  `services/pricer` established the pattern of a *stable* group id for a
  topic whose consumption should resume across restarts (`market.ticks`,
  passed in by the caller) versus a *fresh, unique-per-process* group id
  for a topic that should always replay from the start
  (`portfolio.state` — see that workstream's `PLAN.md`). Test code uses
  `f"test-{uuid.uuid4()}"` throughout, not a fixed convention.
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
- 2026-08-30 (pricer session): Added `quant_io/portfolio_state_io.py`
  (`PortfolioStateProducer` — including `produce_tombstone`, a null value
  for a key — and `make_portfolio_state_consumer`) and
  `quant_io/risk_snapshot_io.py` (`RiskSnapshotProducer`,
  `make_risk_snapshot_consumer`), completing the three-record scope this
  workstream originally set out with. Built together with
  `services/pricer` as their real caller.
  `AvroConsumer` (`quant_io/consumer.py`) gained `enable_auto_commit`
  (default `False` — a behavior change from last session's implicit
  confluent-kafka default of `True`; nothing in `services/ingest`'s tests
  relied on auto-commit, so this was safe), `enable_partition_eof` +
  `PartitionEOF` + `on_assign` (for `services/pricer`'s hydration gate),
  and a `commit()` method. `poll()`'s return type is now
  `Message | PartitionEOF | None` — a breaking change to every existing
  caller's type annotations, fixed in `libs/quant-io/tests/contract/
  test_tick_producer_contract.py` (the only other caller at the time).
  Every topic-specific producer/consumer factory (`TickProducer`,
  `make_tick_consumer`, `PortfolioStateProducer`,
  `make_portfolio_state_consumer`, `RiskSnapshotProducer`,
  `make_risk_snapshot_consumer`) gained a `topic` override parameter
  (defaulting to the real ADR-0016 topic name) so tests can use per-test
  topic isolation without the real service code ever seeing anything but
  the production topic name.
  Verified the tombstone-deserializes-to-`None` behavior directly against
  a real broker before relying on it (`confluent_kafka.schema_registry.
  avro.AvroDeserializer.__call__` returns `None` for `None` input before
  ever calling the configured `from_dict`) — this needed no code change in
  this library, just confirmation it already worked.
