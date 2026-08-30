# ADR-0002: Avro + Confluent Schema Registry, BACKWARD compatibility

## Status
Accepted

## Context
Three language runtimes need to agree on the wire format of every Kafka
message, and that format will evolve as the domain model matures. We need a
schema representation that is language-neutral, supports compatibility
checking, and can generate typed bindings for Python, Java, and TypeScript.

## Decision
All Kafka message schemas are hand-written Avro (`.avsc`) files under
`contracts/avro/`, registered with a Confluent Schema Registry running
`BACKWARD` compatibility mode. Language bindings (Python dataclasses/Java
POJOs/TypeScript types) are generated from these schemas by `tools/codegen`
and are never hand-edited.

## Consequences
- A schema change that is not backward-compatible is rejected by the registry
  at CI/deploy time, not discovered in production.
- Adding a field requires a default value; removing or retyping a field
  requires a new schema version and, if the change is truly breaking, an ADR.
- Generated code drift is prevented by regenerating in CI and diffing against
  what's checked in (see `contracts/README.md`).

## Alternatives considered
- **Protobuf.** Rejected: the team already standardized on Confluent Schema
  Registry tooling, and Avro's JSON-schema-like `.avsc` is easier for a
  five-person team to hand-author and review in PRs than `.proto` + the
  separate buf/protoc toolchain.
- **JSON Schema over Kafka.** Rejected: no compact binary encoding, no
  first-class schema evolution/compatibility enforcement via the registry.
