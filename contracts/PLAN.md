# contracts — Plan

**Owner:** Eng-A  ·  **Quarter:** Q1  ·  **Status:** Q1 deliverables complete

## Mission
The wire-format source of truth for every Kafka message and REST/SSE
surface in Meridian, and the codegen that turns it into typed Python and
Java bindings. Every other Q1 workstream either produces to or consumes
from a schema defined here; a schema that's ambiguous, undocumented, or
silently divergent between languages is a bug that surfaces as a wrong
number three components downstream, not a compile error here.

## In scope this quarter
- [x] `docs/adr/0015-contracts-build-topology.md`: a root Maven aggregator
      (`pom.xml`) with modules `contracts/generated/java` and
      `services/core-service`; `-pl services/core-service -am verify`
      restored now that the reactor is load-bearing (a real dependency),
      not ceremony.
- [x] Value + key Avro schemas for all three Q1 topics
      (`tick`, `risk-snapshot`, `portfolio-state`), namespace
      `com.meridian.contracts`, explicit decimal precision/scale
      (ADR-0013), `timestamp-micros` (ADR-0005), a `doc` on every field, a
      default on every field added after a schema's first version.
      `scenario_id` (ADR-0011) threaded from `Tick` through to
      `RiskSnapshot` for end-to-end lineage.
- [x] `contracts/openapi/service-api.yaml`: Q1 REST/SSE surface —
      `GET /portfolios/{id}/risk`, `.../risk/history`, `.../risk/stream`
      (ADR-0012 resume semantics), `POST /trades`, `GET .../audit`. Money
      fields are strings, stated explicitly in the spec description
      (IEEE-754 can't hold a scale-8 decimal exactly).
- [x] `tools/codegen/generate.py`: one entry point (`make gen`) producing
      deterministic Python dataclass and Java POJO bindings from the same
      schemas. Pinned `avro-maven-plugin` version. CI `gen-check` job
      regenerates into a temp dir and diffs against what's committed.
- [x] Contract tests: round-trip in each language, the cross-language
      `Decimal`/`BigDecimal` fidelity test, and a schema-evolution test
      that verifies the BACKWARD-compatibility check itself accepts a
      field-with-default and rejects a field-without (same principle as
      `libs/quant-core`'s purity fixture).
- [x] `docs/adr/0016-partition-key-semantics.md`: the key and the ordering
      guarantee it buys for each of the three Q1 topics, named explicitly
      rather than left implicit in the `*-key.avsc` schemas. Flags the
      actual trap (increasing partition count on a keyed topic silently
      breaks per-key ordering across the boundary) and updates
      `infra/PLAN.md` to say partition counts are set once at creation.
- [x] `docs/adr/0017-cash-greeks.md`: `RiskSnapshot`'s portfolio-level
      Greeks are cash Greeks (`Decimal(38,8)`, 1% basis for delta/gamma),
      not raw per-unit float64 Greeks — those aren't summable across a
      portfolio's different underlyings. Schema, domain model, OpenAPI,
      and `docs/conventions.md` all updated; bindings regenerated.
      Resolves the aggregation open question this file raised in the prior
      session — see `services/pricer/PLAN.md`.
- [x] "Registry stand-in" documented in `contracts/README.md`: the local
      BACKWARD check runs the same Avro resolution rules the real registry
      uses (not an approximation), with two named gaps (no
      `BACKWARD_TRANSITIVE` history check, no subject-naming coverage) and
      a Q3 `infra/PLAN.md` deliverable to close both with a real registry
      CI service container.

## Explicitly out of scope
- TypeScript Avro bindings — `apps/dashboard` consumes the OpenAPI surface,
  not Avro directly; revisit if that changes.
- A live Confluent Schema Registry in CI — none is deployed yet (see
  `.github/workflows/ci.yml`'s `schema-registry-compatibility` job and
  `contracts/README.md`'s "Registry stand-in" section for exactly what the
  local check does and doesn't cover in the meantime). Q3 per
  `infra/PLAN.md`.
- Implementing the endpoints in `service-api.yaml` — that's
  `services/core-service`'s `PLAN.md`. This workstream owns the contract,
  not the server.
- Hash-chained audit log persistence (ADR-0008, Q2) — `GET .../audit` is
  contract-only this quarter.

## Boundaries
- **Owns:** `contracts/**`, `tools/codegen/**`.
- **Must not touch:** `services/*` and `libs/*` implementation code —
  workstreams there depend on `contracts/`, not the reverse. Schema changes
  affecting a workstream's deliverables are coordinated with that
  workstream's owner, not made unilaterally.
- **Depends on:** `docs/domain-model.md` (source of truth for every type),
  ADR-0002 (Avro + registry), ADR-0003 (portfolio.state compaction),
  ADR-0004/ADR-0013 (numeric types), ADR-0005 (time policy), ADR-0007 (risk
  snapshot identity), ADR-0009/ADR-0012 (REST + SSE), ADR-0011
  (scenario_id), ADR-0014/ADR-0017 (per-unit vs. cash Greeks).

## Interfaces
`contracts/avro/*.avsc` and `contracts/openapi/service-api.yaml` are the
interface; `contracts/generated/{python,java}` are a build product of that
interface, not a second one. Every other Q1 workstream imports
`contracts/generated/python` (`libs/quant-io`, `services/pricer`,
`services/ingest`) or depends on `contracts-generated-java`
(`services/core-service`) rather than hand-rolling parsing.

## Definition of done
- [x] Deliverables above complete
- [x] Tests per `docs/test-strategy.md` (contract-test layer) — see
      `contracts/tests/` and `contracts/generated/java/src/test/java`
- [x] Docs updated: `docs/domain-model.md` (`RiskSnapshot` revised,
      `Tick`/`PortfolioState` tombstone note added), `contracts/README.md`
      (regeneration procedure, build topology, testing)
- [x] NFR targets: N/A directly — this workstream has no latency/throughput
      target of its own; it's exercised via the services that use it

## Open questions
- ~~`RiskSnapshot`'s discrete Greek fields... how the pricer aggregates
  per-position Greeks into those fields~~ **Resolved:
  `docs/adr/0017-cash-greeks.md`.** Cash Greeks, with the exact aggregation
  formula per position — not left to `services/pricer` to design.
- `POST /trades` as synchronous REST vs. an inbound Kafka topic remains
  open (see `services/core-service/PLAN.md`) — the OpenAPI contract
  reflects the Q1 REST decision but isn't load-bearing if that changes.
- Currency: cash Greeks (ADR-0017) are summable across underlyings, not
  across currencies. Deliberately not solved here or in ADR-0017 — owned
  at root `PLAN.md` for Q2, ahead of portfolio VaR.

## Session log
- 2026-08-31 (Eng-A session): Q1 contracts work — ADR-0015 (build
  topology), all three value + key Avro schemas, OpenAPI Q1 surface,
  `tools/codegen` (Python dataclass + Java POJO generation via
  avro-maven-plugin, both deterministic and byte-identical across runs),
  and the full contract test suite including the cross-language decimal
  fidelity test (12 cases: binary-FP-unrepresentable, negative, and
  precision-38-limit values, both directions, all passing) and the schema
  evolution enforcement-mechanism test. Discovered `.gitignore` had a
  blanket `**/generated/` rule that silently contradicted ADR-0002 (nothing
  under `contracts/generated/` would ever have been committed) — fixed;
  see `.gitignore`'s note. `RiskSnapshot` redesigned from a `greeks` map to
  discrete typed fields when it became clear the map shape couldn't carry
  per-field docs/defaults as a wire type; `docs/domain-model.md` updated to
  match, not left to disagree with the schema.
- 2026-08-31 (later same session, Eng-A): ADR-0016 (partition key
  semantics — named the guarantee, flagged the actual trap: partition
  count changes on a keyed topic silently break ordering) and ADR-0017
  (cash Greeks — `RiskSnapshot`'s Greek fields retyped `float64 ->
  decimal(38,8)` and renamed `cash_*`, since the previous session's
  discrete-field fix was still raw per-unit Greeks, not summable across
  underlyings). Regenerated bindings, updated every Java/Python test that
  constructs a `RiskSnapshot`; all pass, including the reactor build.
  Documented the registry stand-in's real gaps in `contracts/README.md`
  rather than changing it — it already runs the registry's own resolution
  algorithm, it just lacks transitive history and subject-naming coverage.
