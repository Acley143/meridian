# core-service — Plan

**Owner:** Eng-D  ·  **Quarter:** Q1  ·  **Status:** Q1 deliverables complete

## Mission
Owns portfolio, position, and trade state; is the sole producer of
`portfolio.state` (ADR-0003); exposes REST + SSE to the dashboard (ADR-0009).
Without this, there's no durable record of what any portfolio holds and
nothing for the dashboard to talk to.

## In scope this quarter
- [x] Portfolio/Position/Trade persistence (Postgres, per
      `docker-compose.yml`) matching `docs/domain-model.md` field-for-field.
- [x] Trade booking endpoint that updates positions and produces
      `portfolio.state` (ADR-0003).
- [x] REST endpoints from `contracts/openapi/service-api.yaml`:
      `GET /portfolios/{id}`, `GET /portfolios/{id}/positions`.
- [x] SSE endpoint `GET /portfolios/{id}/risk/stream`, consuming
      `risk.snapshots` and forwarding to connected clients (ADR-0012).

## Explicitly out of scope
- Any pricing logic — this service never computes a price or a Greek.
- Calling the pricer synchronously for anything — forbidden by ADR-0003.
- `market.curves` (ADR-0019) — Q2, owned by `services/ingest`, not this
  service.

## Delivered beyond the Q1 minimum (see session log)
- The hash-chained audit log (ADR-0008) was originally scoped Q2, with
  `GET /portfolios/{id}/audit` allowed to `501` until then. It landed ahead
  of schedule (Session 05b) with a working write path added in 05d (trade
  booking now writes a `trade_booked` entry) — the endpoint is wired up for
  real rather than kept behind a stub `501`, since a permanently-empty
  501 behind working functionality would have been a worse outcome. See
  `AuditController`'s doc comment for the reasoning.
- `GET /portfolios/{id}/risk` and `/risk/history` (marked "nice to have,
  add if time allows" in the original scope) were both implemented.
- `services/core-service` also produces `reference.instruments`
  (ADR-0019, keyed by `instrument_id`) via an internal `InstrumentService`
  seam — no REST endpoint exposes instrument creation yet; that's a future
  session's work.

## Boundaries
- **Owns:** `services/core-service/**`.
- **Must not touch:** `contracts/` without coordinating with Eng-A;
  `libs/quant-core`.
- **Depends on:** `contracts/avro/portfolio-state.avsc` (ADR-0002, ADR-0003),
  `contracts/avro/reference-instruments.avsc` (ADR-0019),
  `contracts/openapi/service-api.yaml` (ADR-0009), ADR-0004, ADR-0005,
  ADR-0007, ADR-0008, ADR-0012.

## Interfaces
REST + SSE per `contracts/openapi/service-api.yaml`. Sole producer of
`portfolio.state` (`contracts/avro/portfolio-state.avsc`) and
`reference.instruments` (`contracts/avro/reference-instruments.avsc`).
Consumes `risk.snapshots` (ADR-0007 identity, idempotent upsert into
Postgres) both to persist it and to forward it over SSE; does not produce
to `risk.snapshots`. Writes the hash-chained audit log (ADR-0008) on trade
booking.

## Definition of done
- [x] Deliverables above complete
- [x] Tests per `docs/test-strategy.md` (contract tests against both the
      Avro topic — real Kafka + schema-registry round trips via
      `KafkaAvroSerializer`/`KafkaAvroDeserializer` in the 05c/05d test
      suites — and the OpenAPI spec, via `swagger-request-validator`
      against `contracts/openapi/service-api.yaml` itself, Session 05d)
- [x] Contract tests pass against `contracts/` (the pre-existing
      `contracts/tests/python` suite: 32/32, including the two new
      `reference-instruments.avsc` cases added in 05a)
- [x] Docs updated (`docs/domain-model.md`, ADR-0019, ADR-0008's editorial
      amendment, this file)
- [~] NFR targets in `docs/nfr-budget.md`: these are stated as Q4
      load-testing pass/fail criteria (latency, sustained throughput,
      recovery under load), not something a Q1 session measures directly;
      no load-test harness exists yet for this service. The one criterion
      exercised at unit/integration scope this quarter — "kill a consumer
      mid-stream; on restart, zero duplicate rows and zero gaps" — is
      covered by 05a's upsert-dedup test and 05c's offset-commit-failure
      redelivery test (with a real bug in the redelivery path found and
      fixed by that test, see 05c's session log). Full load-test
      validation against the stated numbers remains open, tracked here
      rather than silently assumed.

## Open questions
- Trade booking: synchronous REST endpoint vs. its own inbound Kafka topic?
  Q1 assumes REST for simplicity; revisit if a trade-source integration
  needs otherwise. Owner: Eng-D, by-when: before Q2 planning.
- REST compatibility policy: ADR-0021 gives the REST surface a version
  segment (`/api/v1`) but no equivalent to ADR-0002's `BACKWARD`
  compatibility policy for Avro — no definition of what counts as a
  breaking REST change, who decides, or whether `/api/v1` keeps serving
  once `/api/v2` exists. `/api/v1` is a container, not a policy; don't read
  one into it from the version number alone. Needs its own ADR in Q2 — not
  pre-numbered here, since cross-currency aggregation (root `PLAN.md`) is
  also pending an ADR and whichever gets drafted first should take the next
  number. Owner: unassigned, by-when: Q2 planning.
- Health probes with nothing consuming them: ADR-0022 (Session O) added
  `/actuator/health/liveness` and `/actuator/health/readiness`, but
  `core-service` has no `Dockerfile` and no entry in `docker-compose.yml` —
  it's a local process, not a compose service, so there is no compose
  `healthcheck:`/`depends_on: condition:` to point at them yet, and Q3's
  deploy work is the first real consumer. Containerizing the service (base
  image, JVM flags, the in-network hostname/env-var contract) is its own
  decision, deliberately not made in Session O. Neither `postgres`, `kafka`,
  nor `schema-registry` has a compose healthcheck either, and
  `schema-registry`'s `depends_on: kafka` has no `condition:` — both
  predate Session O and are noted here rather than fixed, since fixing them
  wasn't this session's scope. Owner: unassigned, by-when: Q3 deploy
  planning.
- Kafka consumer death is invisible to any *automated* system: ADR-0022 made
  this an explicit, deliberate readiness exclusion (a dead/rebalancing
  consumer degrades reads to stale, not absent), and Session O's own fixture
  testing caught and fixed a real bug in the health detail meant to surface
  it — `pollThreadAlive`/the original poll-loop timestamp kept reading
  "healthy" through a full broker outage, since `KafkaConsumer.poll()`
  doesn't throw on one; a `lastHeartbeatSecondsAgo` field (sourced from the
  consumer's own Kafka group heartbeat) now genuinely reflects it, verified
  by hand against a real outage. But nothing *pages* on any of this yet — a
  human still has to read the `riskSnapshotConsumer` health detail; alerting
  on `lastHeartbeatSecondsAgo`/`pollLoopIterationCount` staying stuck is the
  actual open item. Owner: unassigned, by-when: Q2 planning.
- Testcontainers doesn't run in this local sandbox: two sessions in a row
  (Session N-era per the 05d log, and Session O) have hand-verified Java
  changes against the real `docker-compose.yml` stack instead, with CI as
  the only place the real suite runs. Root-caused further in Session O: it
  isn't a `DOCKER_HOST`/socket misconfiguration (tried pointing explicitly
  at the Docker Desktop socket, same failure) — testcontainers 1.20.1's
  bundled `docker-java` client fails Docker API version negotiation against
  this Docker Desktop install (`docker compose`, the Go CLI, works fine
  against the same daemon). Not urgent — CI is a working backstop — but it's
  a compounding tax: every local Java change gets zero automated feedback
  before push. Worth investigating whether a `testcontainers`/`docker-java`
  version bump fixes it, as its own session (a dependency bump is a real
  decision, not a drive-by). Owner: unassigned, by-when: Q2 planning.

## Session log
- 2026-08-31 (contracts session, Eng-A): `contracts/openapi/service-api.yaml`
  restructured for the Q1 surface — risk endpoints moved under
  `/portfolios/{id}/risk`, `/risk/history` (new), `/risk/stream` (renamed
  from `/risk-stream`); `POST /trades` and `GET /portfolios/{id}/audit`
  (contract-only, Q2 implementation) added. `contracts/generated/java` now
  exists as a Maven reactor sibling (ADR-0015) — build/test with
  `mvn -pl services/core-service -am verify` from the repo root, not
  `-f services/core-service/pom.xml`.
- 2026-08-31 (Session 05a): ADR-0019 (reference data / market curves),
  `reference-instruments.avsc` + key schema, Postgres schema
  (`V1__init_schema.sql`: instruments/portfolios/positions/trades/
  risk_snapshots/audit_log, `NUMERIC(38,8)` throughout per ADR-0013,
  ADR-0007's identity as a real `UNIQUE` constraint), and idempotent
  `RiskSnapshotRepository` upsert. Extended `tools/codegen`'s Python
  generator to support Avro enums and nullable unions (first schema to
  need either). ADR-0018 (a generic "hydration/readiness gate" ADR) does
  **not exist** — `services/pricer/pricer/service.py`'s `hydrate()` is the
  only place that pattern is documented; ADR-0019 points at the code
  directly rather than inventing the ADR. Flagged as a gap for whoever
  owns that generalization.
- 2026-08-31 (Session 05b): Hash-chained audit log (ADR-0008) — canonical
  form specified in `docs/domain-model.md#auditentry` (length-prefixed
  encoding of `entry_id`+`entry_type`+`payload` only; `event_time`/
  `ingest_time`/`prev_hash` deliberately excluded, per the domain model's
  own pre-existing `entry_hash` doc), an independent verifier
  (`AuditChainVerifier`, deliberately not sharing code with the writer),
  and a database-level append-only trigger (`V2__audit_log_hash_chain.sql`).
  ADR-0008 amended (editorial, per the ADR-0016 pattern) with an honest
  threat model: tamper-*evident*, not tamper-*proof* — a privileged actor
  who rewrites the whole chain forward produces a chain that still
  verifies. Real tamper-evidence needs an externally-anchored head hash;
  not solved here, flagged as a real gap.
- 2026-08-31 (Session 05c): Kafka wiring — `RiskSnapshotConsumerService`
  (manual per-record `commitSync`, never auto-commit, same reasoning as
  `libs/quant-io`'s Python consumer), `PortfolioStateProducer` and
  `ReferenceInstrumentProducer` (both log-compacted, `cleanup.policy`
  enforced by `CompactedTopicInitializer` since `infra/PLAN.md`'s topic
  creation is still "not started"), and `PortfolioMutationService`/
  `InstrumentService` as internal seams ahead of 05d's REST layer. A
  teeth-check in `OffsetCommitFailureTest` caught a real bug: without an
  explicit `consumer.seek()` back on write failure, `KafkaConsumer.poll()`
  had already advanced the client's own fetch position past the whole
  batch, so a still-running consumer would never re-fetch a failed record
  on its own — only a full process restart would. Fixed.
- 2026-08-31 (Session 05d): REST + SSE. `POST /trades` wired to 05c's
  `PortfolioMutationService` (its first real caller); `GET /portfolios/
  {id}/audit` wired up for real rather than kept behind Q1's planned
  `501` (see "Delivered beyond the Q1 minimum" above) — a `portfolio_id`
  column was added to `audit_log` (`V3__audit_log_portfolio_scoping.sql`,
  server-side filtering only, not part of `AuditEntry`'s wire shape or
  canonical form) since nothing previously wrote to the audit log at all.
  SSE resume per ADR-0012, replay from Postgres, bounded resync. Money
  serializes as a JSON string globally via a Jackson `BigDecimal`
  serializer. Contract conformance tested against
  `contracts/openapi/service-api.yaml` itself via
  `swagger-request-validator`. Running the actual application for the
  first time this session (Testcontainers is unavailable in this sandbox;
  hand-verified against the real `docker-compose.yml` stack instead)
  surfaced and fixed several real, previously-latent bugs never exercised
  by any unit test: `RiskSnapshotConsumerService` had two constructors
  and no `@Autowired`, so Spring couldn't instantiate it at all; nothing
  anywhere actually drove `RiskSnapshotConsumerService.pollOnce()` in the
  running application (added `RiskSnapshotConsumerRunner`); and the
  module had no BOM pinning Jackson/SLF4J to a mutually-compatible
  version set, causing three separate runtime-only failures (fixed by
  importing `spring-boot-dependencies` as `dependencyManagement`, plus
  `-parameters` on the compiler, which `@PathVariable`/`@RequestParam`
  need without an explicit name and which a `spring-boot-starter-parent`
  would otherwise have set for free).
- 2026-09-01 (Session O): ADR-0022 — `spring-boot-starter-actuator`,
  liveness/readiness probes, `RiskSnapshotConsumerHealthIndicator` (Kafka
  as a health-body detail, explicitly excluded from the readiness group).
  Session prompt assumed `core-service` already had (or could readily get)
  a `docker-compose.yml` healthcheck; it has no compose entry and no
  `Dockerfile` at all, so that task was dropped rather than improvised —
  see "Open questions" above. Testcontainers is broken in this sandbox
  (docker-java's bundled client negotiates an API version the local Docker
  daemon rejects — confirmed pre-existing by reverting this session's
  changes and running an untouched existing Kafka test, which failed
  identically), so the new tests were verified by hand against the real
  `docker-compose.yml` stack instead, same fallback as 05d for the same
  reason. Fixtures 5 and 6 (Postgres outage, Kafka outage) were run for
  real: readiness correctly went 503/DOWN on a stopped Postgres container
  while liveness stayed 200/UP throughout, and recovered to UP within ~1s
  of Postgres restarting with no core-service restart; readiness and
  `GET /api/v1/portfolios/{id}/risk` were both unaffected by a stopped
  Kafka container. That same fixture surfaced a real design finding, caught
  and fixed before merge rather than shipped and amended a week later:
  `KafkaConsumer.poll()` doesn't throw on an unreachable broker, so
  `pollThreadAlive`/`lastPollLoopIterationAt` keep looking healthy through a
  total broker outage — a field reporting "fine" during a real failure,
  worse than no field at all, since it's the first thing an on-call
  engineer checks. The fix, in this same session: those fields stay (loop
  liveness is still real information) but now carry an explicit
  `pollLoopIterationCaveat` string saying they don't indicate broker
  reachability, and a new `lastHeartbeatSecondsAgo` field (from
  `KafkaConsumer`'s own `consumer-coordinator-metrics`, published the same
  cross-thread-safe way) is the signal that actually reflects it. Re-ran the
  Kafka-outage fixture with the assertion inverted — the new field must grow
  during the outage — and confirmed by hand: it climbed from ~0s to 61s over
  a 60s outage and dropped back to ~1s within 6s of Kafka restarting. See
  ADR-0022 for the full writeup. Pushing the branch alone did not run CI —
  this repo's workflow triggers only on `push: [master]` or `pull_request`
  — so a PR (#2) had to be opened to get a real run.
- 2026-09-01 (Session O, continued — review feedback): the
  `pollLoopIterationCaveat` string design above was itself replaced before
  merge, on review. Prose in a health payload can't be asserted on by a
  test and drifts from the field it describes; renamed the timestamp/age
  pair to a bare `pollLoopIterationCount` instead, since nobody reads a raw
  iteration counter as a broker-reachability claim, and dropped the caveat
  string — the explanation now lives only in code comments, this file, and
  ADR-0022. Also fixed a second, real instance of the identical failure
  shape inside the fix itself: `kafka-clients` 3.7.0 returns the literal
  sentinel `-1.0` (not `NaN`) for `last-heartbeat-seconds-ago` before any
  heartbeat has ever been sent (decompiled and confirmed against
  `AbstractCoordinator`) — a live `/actuator/health` response showed
  `"lastHeartbeatSecondsAgo": -1.0` at startup before this was caught.
  `extractHeartbeatSecondsAgo` now treats any negative value as `null`, the
  same as `NaN`/non-numeric, pinned by a new Docker-free unit test
  (`RiskSnapshotConsumerHeartbeatMetricParsingTest`). Also added a
  startup-only check (`RiskSnapshotConsumerRunner
  .checkHeartbeatMetricIsRegisteredOnce`) that logs an `ERROR` if the
  `last-heartbeat-seconds-ago` metric name is ever missing from the running
  Kafka client, so a future client upgrade that renames it fails loudly
  instead of silently degrading the field to always-null. Re-verified the
  full outage/recovery cycle by hand once more after these changes: no
  `-1.0` observed, `lastHeartbeatSecondsAgo` still climbs during an outage
  and recovers after.
- 2026-09-01 (Session O, continued — CI run and fix): added
  `timeout-minutes: 15` to every CI job (separate PR #3, merged first, since
  a workflow change shouldn't be validated by the same run it's meant to
  bound) after PR #2's Java job sat `IN_PROGRESS` for 40+ minutes with no
  timeout to kill it. The re-run (rebased onto the updated workflow) hit the
  new 15-minute wall — but reading the actual log showed
  `KafkaOutageReadinessExclusionFixtureTest` itself had failed honestly in
  ~61s (a too-short 30s recovery timeout against a real, slower-than-local
  cold Kafka restart in CI), and the real problem was that it had stopped
  the *shared* singleton Kafka container the whole suite depends on, so the
  still-recovering broker wedged the next, unrelated test
  (`OffsetCommitFailureTest`, pre-existing, untouched) for the rest of the
  job. Fixed by giving the fixture its own private Kafka + schema registry
  (no other test can be affected by what this one does to its broker,
  structurally, not just by a longer timeout) and splitting recovery into
  two separately-timed checks (broker reachable, then consumer heartbeat
  recovered) so the two failure modes produce different error messages. See
  ADR-0022's new section for the full writeup. Not yet re-verified against a
  fresh CI run as of this entry.
