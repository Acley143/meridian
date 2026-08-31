# ADR-0015: Contracts build topology and generated binding placement

## Status
Accepted

## Context
A previous session switched `services/core-service`'s Maven invocation from
a reactor-style `mvn -pl services/core-service -am verify` to a direct
`mvn -f services/core-service/pom.xml verify`, because at the time
`core-service` was the only Java module in the repository — a root
aggregator `pom.xml` existed for no reason but ceremony, and `-am` ("also
make" upstream dependencies) had nothing to build.

This session adds a second Java artifact: `contracts/generated/java`, the
checked-in Java bindings generated from `contracts/avro/*.avsc`
(`tools/codegen`, ADR-0002). `core-service` depends on it at compile time
(it needs `Tick`, `RiskSnapshot`, `PortfolioState`, and their key classes to
talk to Kafka). Two Java modules with a real dependency between them is
exactly the situation a Maven reactor exists for — the previous session's
reasoning no longer applies, because it isn't decorative anymore.

## Decision
A root aggregator `pom.xml` (packaging `pom`) lists two modules:
`contracts/generated/java` and `services/core-service`. `core-service`
depends on `com.meridian:contracts-generated-java` as a normal Maven
dependency. `ci.yml` and the `Makefile` revert to
`mvn -pl services/core-service -am verify` (and the equivalent for
`spotless:check`/`test`), run from the repo root — `-am` now does real
work: it builds `contracts-generated-java` first so `core-service` has
something to link against.

`contracts/generated/java/pom.xml` is a plain `jar` module. It does **not**
run `avro-maven-plugin` itself — the checked-in `.java` files under
`src/main/java` are the generated artifact (ADR-0002: generated code is
checked into git, never produced fresh by the consuming build). Actual
codegen happens once, via `tools/codegen/generate.py` (`make gen`), which
invokes a separate, standalone Maven helper
(`tools/codegen/avro-java-codegen/pom.xml`, **not** a reactor module) that
runs `avro-maven-plugin` into a throwaway `target/` directory; the script
then copies the result into `contracts/generated/java/src/main/java` with a
"generated, do not edit" banner. This keeps "what codegen produces" and
"what the reactor compiles" as two separable steps — the reactor build
never needs network access to a Maven plugin registry to produce a working
JAR from what's already checked in, and a CI drift check
(`contracts-drift` job) can regenerate into a temp directory and diff
against `contracts/generated/java` without touching the reactor at all.

## Consequences
- `mvn -pl services/core-service -am verify` from the repo root builds
  `contracts-generated-java` then `core-service`, matching
  `services/core-service/CLAUDE.md`'s documented local command (which
  already assumed a reactor — this ADR makes that assumption true again).
- Checked-in generated code can rot silently without a drift check —
  "checked in and never hand-edited" is an honour system otherwise. The
  `contracts-drift` CI job regenerates both languages into a temp directory
  and fails the build if the result differs from what's committed, so a
  schema change that wasn't followed by `make gen` (or a `.avsc` edit that
  produces different output under a newer, unpinned plugin version) is
  caught before merge, not discovered later as a mismatch between the
  schema and the code compiled against it.
- `avro-maven-plugin`'s version is pinned exactly in
  `tools/codegen/avro-java-codegen/pom.xml` (not a version range or
  "latest"). An unpinned generator would make the drift check flap on every
  plugin release instead of only on a real schema or generator change —
  the check exists to catch the latter, not to punish Maven for resolving
  a new patch version.
- `contracts/generated/java`'s own `pom.xml` needs no `avro-maven-plugin`
  configuration at all, which also means it needs no network access to a
  plugin repository to build — only to resolve its (already well-cached)
  runtime dependency on `org.apache.avro:avro`.

## Alternatives considered
- **Keep `-f services/core-service/pom.xml`, give `contracts-generated-java`
  its own independent build/install step before `core-service` builds.**
  Rejected: reimplements what a reactor already does (topological build
  ordering across a real dependency), by hand, in CI shell script — the
  reactor is the standard tool for exactly this and a hand-rolled ordering
  step is one more place to get it wrong.
- **`avro-maven-plugin` runs directly inside `contracts/generated/java`'s
  own build, generating fresh code on every `mvn verify`.** Rejected: this
  makes "checked into git, never hand-edited" a fiction — the checked-in
  `.java` files would be dead weight next to the actual build output, and
  the drift check would have nothing meaningful to diff against (the build
  would always regenerate to match itself). Per ADR-0002, generated code is
  checked in *and reviewed in PRs*; that only means something if the build
  compiles what's checked in, not something it silently regenerates.
- **One combined Python+Java codegen tool per language, invoked
  independently (`make gen-python`, `make gen-java`).** Rejected: Task 4
  wants one entry point producing both bindings from the same inputs in one
  deterministic step, so a schema change can't accidentally update one
  language's bindings and not the other in the same commit.
