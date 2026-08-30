# Contracts

This directory is the source of truth for every wire format and API surface
in Meridian, derived mechanically from `docs/domain-model.md`.

- `avro/` — Kafka message schemas (Avro `.avsc`), registered with the
  Confluent Schema Registry under `BACKWARD` compatibility (ADR-0002).
- `openapi/` — the core service's REST API (ADR-0009).

**Generated code is never hand-edited.** Python, Java, and TypeScript
bindings for these schemas are produced by `tools/codegen` and checked in
alongside the source `.avsc`/`.yaml` files for reviewability, but any manual
edit to a generated file will be silently overwritten on the next `make gen`
and is not the place to fix a bug — fix the schema and regenerate.

If `docs/domain-model.md` and a schema in this directory ever disagree, the
domain model document is right and the schema is a bug: file it as such,
don't patch the document to match.

A schema change that is not `BACKWARD`-compatible under the registry's check
requires an ADR (see ADR-0002).
