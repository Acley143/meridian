# Glossary

Terms used across Meridian's docs and code. For type definitions, see
`docs/domain-model.md`; this file is plain-English definitions of concepts
that show up in ADRs and plans but aren't themselves schema fields.

**As-of** — the event time a computation or snapshot is valid for, as
distinct from the (later) time the computation actually ran. See
`RiskSnapshot.as_of_event_time`.

**Backward compatibility (schema)** — a new schema version can read data
written by the previous version (old readers may not be able to read new
data). This is the compatibility mode enforced by the registry per ADR-0002.

**Book / Portfolio** — used interchangeably in conversation; the canonical
type is `Portfolio` (`docs/domain-model.md#portfolio`).

**Golden test** — a test asserting a pricer's output against a known,
independently-derived reference value (e.g. a published closed-form result),
as opposed to a property test asserting a relationship holds.

**Greeks** — sensitivities of an option's price to its inputs (delta, gamma,
vega, theta, rho). Always `float64` per ADR-0004, regardless of which input
they're a sensitivity with respect to.

**Hot path** — the sequence tick → price → risk snapshot → dashboard render,
the path the latency budget in `docs/nfr-budget.md` is measured against.

**Idempotent upsert** — a write that produces the same end state whether
applied once or many times with the same input; used for `RiskSnapshot`
storage to make at-least-once Kafka delivery safe (ADR-0007).

**Log compaction** — a Kafka topic retention policy that keeps only the
latest message per key, rather than a time/size-based retention window. Used
for `portfolio.state` (ADR-0003).

**Materialized view** — a local copy of state built by folding over a
stream, as the pricer does with `portfolio.state` to avoid a synchronous
call back to `core-service`.

**Property test** — a test asserting an invariant holds across a generated
range of inputs (e.g. "call delta is always in [0,1]"), as opposed to a
golden test asserting one specific expected output.

**Pure function / purity** — a function with no side effects and no
dependency on anything outside its arguments (no I/O, no wall clock). The
constraint enforced on `libs/quant-core` by ADR-0010.

**VaR (Value at Risk)** — a statistical estimate of potential portfolio loss
over a given horizon and confidence level; Meridian's Q1 scope is 1-day 95%
VaR, `RiskSnapshot.var_95`.
