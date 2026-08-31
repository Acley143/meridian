# Contracts

This directory is the source of truth for every wire format and API surface
in Meridian, derived mechanically from `docs/domain-model.md`.

- `avro/` — Kafka message schemas (Avro `.avsc`), registered with the
  Confluent Schema Registry under `BACKWARD` compatibility (ADR-0002). Each
  topic has a value schema and a key schema (e.g. `tick.avsc` /
  `tick-key.avsc`).
- `openapi/` — the core service's REST API (ADR-0009).
- `generated/` — checked-in Python and Java bindings (see below). Not
  TypeScript yet — `apps/dashboard` doesn't consume Avro directly.
- `tests/` — contract tests: round-trip (each language), cross-language
  decimal fidelity, and schema-evolution tests. See "Testing" below.

## Regenerating bindings

**Generated code is never hand-edited.** Python and Java bindings for the
Avro schemas live in `contracts/generated/python/` and
`contracts/generated/java/`, produced by `tools/codegen/generate.py` and
checked into git per ADR-0002, for reviewability — a schema change and its
generated-code diff land in the same PR. Any manual edit to a file under
`contracts/generated/` will be silently overwritten on the next
regeneration and is never the place to fix a bug: fix the schema (or the
generator) and regenerate.

To regenerate after touching any `contracts/avro/*.avsc`:

```
make gen
```

This is one entry point, `tools/codegen/generate.py`, producing both
language bindings from the same schema files in one deterministic step —
same inputs, byte-identical outputs — so a schema change can't update one
language's bindings and silently leave the other stale in the same commit.
Java codegen shells out to a pinned `avro-maven-plugin` (see
`tools/codegen/avro-java-codegen/pom.xml` and ADR-0015) — an unpinned
generator would make the drift check below flap on every plugin release,
not just on a real schema change.

After regenerating, `git diff` and commit the result alongside your schema
change, in the same PR.

**Drift check (CI):** the `gen-check` job regenerates both languages into a
temp directory and fails the build if the result differs from what's
committed (`.github/workflows/ci.yml`). This is what makes "checked in and
never hand-edited" an enforced rule instead of an honour system — a schema
edited without a `make gen` follow-up, or generated code hand-patched
directly, both go red here before they can merge.

## Build topology (ADR-0015)

`contracts/generated/java` and `services/core-service` are Maven reactor
modules under the root `pom.xml`. Build/test `core-service` (which depends
on the generated Java bindings) with:

```
mvn -pl services/core-service -am verify
```

`-am` ("also make") builds `contracts-generated-java` first. This module's
own `pom.xml` does not run codegen itself — see "Regenerating bindings"
above; it only compiles what's already checked in under
`contracts/generated/java/src/main/java`.

## Testing

`contracts/tests/python/` (pytest):
- `test_round_trip.py` — Python-side round trip (serialize, deserialize,
  assert equality across all fields) for every record type.
- `test_cross_language_decimal.py` — the test this whole `contracts`
  workstream exists to enable: Python encodes a `Decimal`, the Java CLI
  tool `CrossLanguageDecimalTool` decodes it and asserts exact
  `BigDecimal` equality, and the reverse. Values chosen to break a naive
  implementation: not representable in binary floating point, negative,
  and at the precision-38 limit. Cross-language decimal divergence is the
  failure mode ADR-0013 exists to prevent; this is what actually verifies
  it, rather than just asserting it in an ADR.
- `test_schema_evolution.py` + `backward_compat.py` — verifies the
  BACKWARD-compatibility enforcement mechanism itself (no live registry is
  deployed in CI; this approximates the registry's check via Avro's own
  schema resolution rules — see the module docstring). Same principle as
  `libs/quant-core`'s purity fixture: a check that has never been observed
  to fail proves nothing, so this asserts both that adding a field WITH a
  default is accepted and that adding one WITHOUT a default is rejected.

`contracts/generated/java/src/test/java/com/meridian/contracts/` (JUnit,
run via `mvn -pl contracts/generated/java test`):
- `RoundTripTest.java` — Java-side round trip, same principle as the
  Python one, for every record type including nested `Position`.
- `CrossLanguageDecimalTool.java` — not a test; the CLI the Python
  cross-language test shells out to.

## Rules

If `docs/domain-model.md` and a schema in this directory ever disagree, the
domain model document is right and the schema is a bug: file it as such,
don't patch the document to match. (Where a schema in this session needed a
shape the domain model didn't yet have — e.g. `RiskSnapshot`'s discrete
Greek fields replacing a free-form map — the domain model was updated
first; see its `RiskSnapshot` section for why.)

A schema change that is not `BACKWARD`-compatible under the registry's
check requires an ADR (see ADR-0002).

Every Avro schema field needs a `doc` string, and every new field needs a
default (this is what makes `BACKWARD` compatibility achievable — a field
without one is a breaking change wearing a disguise). Every enum needs a
default symbol so an unknown value from a newer producer degrades instead
of throwing; none of the current Q1 schemas use an enum, but the rule
applies the moment one is added.

`portfolio-state.avsc`'s log-compacted topic uses a producer-side
convention its value schema cannot express: a null value for a given
`portfolio_id` key is a tombstone meaning portfolio deletion. See that
schema's top-level `doc` and `docs/domain-model.md#portfoliostate`.

Money in JSON (OpenAPI) is always a string, never a JSON number — see
`contracts/openapi/service-api.yaml`'s top-level description.
