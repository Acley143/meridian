# ADR-0026: Avro <-> OpenAPI cross-contract check

## Status
Accepted

## Context
`oldest_input_event_time` existed in `contracts/avro/risk-snapshot.avsc`
since Session 04a but was missing from `contracts/openapi/service-api.yaml`'s
`RiskSnapshot` until the dashboard live-risk session noticed it was needed
for staleness rendering and added it — no CI check caught the gap, since
`gen-check` only diffs generated code against itself, not the two source
contracts against each other. Root `PLAN.md`'s open questions list carries
this as "Avro/OpenAPI field parity (Q2)" and asks for "a check that every
`docs/domain-model.md` field appears in both the Avro and OpenAPI
representations of a type, or a stated reason a given field shouldn't."

`tools/schema-lint/` — where this check belongs — had no owning `PLAN.md`
before this session; see `contracts/PLAN.md`'s "Extended scope, Q2" section
for that separately-committed fix.

### A narrower check than the open question asks for
The open question names three sources, with `docs/domain-model.md` as
authority: every domain-model field should appear in both Avro and OpenAPI.
This check compares only two sources, Avro and OpenAPI directly against
each other, with neither treated as authoritative over the other. That is a
deliberate narrowing, not an oversight:

- `docs/domain-model.md` is prose. Parsing it as a machine-checkable
  contract source makes the check brittle against wording changes — every
  other lint script in this directory (`check_avro.py`, `check_openapi.py`,
  `check_api_v1_prefix.py`, `check_adr_numbering.py`) operates on
  machine-readable artifacts, never on prose docs, and this check follows
  that precedent rather than breaking it.
- The property that actually prevents the failure that occurred is "the two
  wire/REST representations agree with each other," not "both agree with a
  prose description." `oldest_input_event_time` drifted between Avro and
  OpenAPI; a domain-model-anchored three-way check would have caught the
  same drift no more directly than a direct two-way comparison does, at the
  cost of a much less stable input.
- **Consequence, stated plainly:** a field that exists in both Avro and
  OpenAPI, agreeing with each other, but is absent from or misdescribed in
  `docs/domain-model.md`, is **not** caught by this check. That gap is
  known and accepted here, not discovered later.
- The root `PLAN.md` open question is therefore **partially, not fully,**
  addressed. What remains open: a check (or process) that keeps
  `docs/domain-model.md` itself in sync with the two machine-readable
  contracts. This ADR does not build that, and does not edit the root
  `PLAN.md` open-questions entry — whether to close, narrow, or leave it is
  a decision for whoever owns that entry next, informed by this ADR
  existing.

## Decision

### `tools/schema-lint/schema_pairing.py` is a closed-world map
Unlike `check_avro.py`'s discovery model — which globs `contracts/avro/*.avsc`
and validates whatever it finds, so a new schema is silently covered —
`check_cross_contract.py` is closed-world: it knows the full expected set of
schemas on both sides up front, via `schema_pairing.py`, and **fails** on any
schema on either side absent from that map. A check that silently ignores an
unrecognised schema covers a shrinking fraction of the contract surface
while staying green; closed-world is what keeps that fraction at 100%.

### The three pairs
| Avro | OpenAPI | Why paired |
|---|---|---|
| `Position` (nested in `portfolio-state.avsc`'s `positions` array) | `Position` | Same shape, same name, both represent one portfolio position. |
| `ReferenceInstrument` | `Instrument` | Same shape (`contracts/openapi/service-api.yaml`'s `Instrument` description says so explicitly: "field-for-field the same shape published to reference.instruments"); different names because REST calls the resource `Instrument`. |
| `RiskSnapshot` | `RiskSnapshot` | Same shape, same name, the pricer's wire output and the REST/SSE response are the same object. |

`Position` is not its own `.avsc` file — it is a named nested record inside
`portfolio-state.avsc`'s `positions` array. `check_cross_contract.py` walks
into nested record definitions rather than enumerating one schema per file,
so this and any future nested record are still found.

`GET /portfolios/{id}/positions` returns an inline array whose `items`
`$ref` `Position`, not a named array component — but `Position` is also its
own top-level entry under `components/schemas`, independent of that path's
usage of it. Walking `components/schemas` alone finds it; no path-response
resolution was needed. Confirmed by running the checker against the real
spec.

### The twelve declared-unpaired schemas
**Avro, unpaired:**
- `PortfolioStateKey`, `ReferenceInstrumentKey`, `RiskSnapshotKey`, `TickKey`
  — Kafka message keys; keys never cross into OpenAPI by construction.
- `PortfolioState` — the envelope is Kafka-internal materialisation. Only
  its `positions` slice is exposed over REST, and that slice is separately
  paired as `Position`.
- `Tick` — `market.ticks` goes ingest -> pricer over Kafka and is never
  surfaced through `core-service`'s REST API.

**OpenAPI, unpaired:**
- `Portfolio` — portfolio IDENTITY (`name`, `base_currency`, `owner`).
  Despite the name, this is **not** the REST counterpart of Avro
  `PortfolioState`, which carries positions over time and none of these
  fields. Different domain objects that happen to share a name root; not
  paired.
- `PortfolioRequest`, `InstrumentRequest`, `TradeRequest` — REST-only
  creation inputs; no wire event of their own.
- `Trade` — no per-trade Avro message exists: ADR-0003 republishes full
  portfolio state after a trade rather than emitting a trade-level event.
- `AuditEntry` — the audit log is Postgres-only per ADR-0008; never
  published.

Each reason lives in `schema_pairing.py` itself, next to the entry, so a
future reader deciding whether to "fix" an unpaired entry finds the reason
before acting on it.

### What is compared, for paired schemas only
- **Field name sets, exactly.** A field on one side and not the other
  fails.
- **Type, via the mapping table below.**
- **Enum symbol sets, exactly** — not just that both sides are enum-shaped.
  `instrument_type` and `option_type` were hand-copied into OpenAPI, not
  generated; an Avro enum gaining a symbol without the spec mirroring it is
  the exact silent drift this check exists to catch.
- **Nullability and required-ness** — see the rule below.
- **Decimal precision and scale, exactly (38, 8) (ADR-0013).**
  `check_avro.py` only verifies precision/scale are *declared*, not what
  they are — a change to `decimal(20, 4)` passes `check_avro.py` today. This
  check closes that, for paired schemas' decimal fields.

### What is not compared, and why
Descriptions, field order, defaults, examples. Field order is
binary-encoding-only in Avro and meaningless in JSON; descriptions would
make the check flap on wording changes with no correctness signal.

### Type mapping table
| Avro | OpenAPI |
|---|---|
| `bytes` + `decimal(38,8)` | `string`, no format |
| `long` + `timestamp-micros` | `string`, `format: date-time` |
| `enum{symbols}` | `string` with `enum: [values]` |
| `string` | `string`, no format |
| `double` | `number, format: double` |
| `array<Record>` | `array` with `items: $ref` to that record |

`check_cross_contract.py`'s `KIND_MAP` is the executable version of this
table and takes precedence over the prose above if the two ever disagree.

Each row declares two different things equivalent and is therefore a hole:
`bytes+decimal(38,8)` and plain `string` both map to the same OpenAPI shape
(`string`, no format), so this check cannot by itself tell a decimal field
from a plain string field on the OpenAPI side alone — it only knows which
is which because it already knows, from the Avro side, which field is
being compared. A future field that is decimal on one side and plain string
on the other, both rendered as OpenAPI `string`, would pass this row's
comparison and could only be caught by the field-name-and-position context
around it, not by the row in isolation.

The timestamp row is keyed on the exact logical type `timestamp-micros`,
not `timestamp-*` generically. A future `timestamp-millis` field requires
its own row so someone notices the precision difference, rather than the
mapping silently absorbing it.

### The nullability rule
For **paired** schemas, an Avro `["null", X]` union maps to OpenAPI
`nullable: true` **and** `required: true`. The field is always present on
the wire with a possibly-null value; it is never absent.

The naive reading — `nullable -> not required` — is wrong and must not be
implemented: it would fail `Instrument`'s `option_type`, `strike`, and
`expiry`, which are all `nullable: true` and in the `required` list today,
correctly. A check that fails on correct code gets weakened or deleted,
which would kill this check outright rather than catch a real bug. This is
why `check_cross_contract.py`'s test suite runs the checker against the
real contracts and asserts it passes — a regression to the naive rule would
show up there immediately.

This rule applies only to paired schemas. `InstrumentRequest` correctly
uses `nullable: true` with `required: false`, and is unpaired, so it is
never compared.

### `reference.instruments` still carries no `event_time`/`ingest_time`
Both Avro `ReferenceInstrument` and OpenAPI `Instrument` agree in lacking
these fields, so this check passes that pair. ADR-0025's open question
("Whether `reference.instruments` should carry `event_time`/`ingest_time`
is an open question this ADR raises but does not resolve") stands,
unresolved by this ADR — agreement between two contracts that are both
silent on a field is not the same as that field's absence being correct.

## Consequences
- `tools/schema-lint/check_cross_contract.py` and
  `tools/schema-lint/schema_pairing.py` are added, wired into the
  `contracts` CI job.
- Adding a new Avro schema or OpenAPI component without updating
  `schema_pairing.py` now fails CI, by design.
- A future field-level drift between a paired Avro record and its OpenAPI
  counterpart — a renamed field, a widened decimal, an enum symbol added on
  one side only, a nullability mismatch — now fails CI instead of shipping
  silently, for the three pairs named above.
- The root `PLAN.md` "Avro/OpenAPI field parity (Q2)" open question is
  partially addressed: the Avro<->OpenAPI half is now enforced; the
  domain-model-agreement half is not. That entry is left as-is in root
  `PLAN.md`; narrowing or closing it is a decision for its owner.
- No Avro schema, no OpenAPI spec, and no endpoint changed in this session.
  `reference.instruments`' missing `event_time`/`ingest_time` remains
  exactly as open as ADR-0025 left it.

## Alternatives considered
**Anchor the check on `docs/domain-model.md`, per the root `PLAN.md`
question's literal wording.** Rejected for this session: the domain model
is prose, not a machine-readable artifact, and every existing
`tools/schema-lint/` script checks machine-readable sources only. Adding a
prose parser would make the check the most brittle one in the directory,
for a three-way check whose real value (Avro-vs-OpenAPI agreement) a
two-way check already delivers. Left as the documented remaining half of
the open question, not solved here.

**Discovery-based schema enumeration, matching `check_avro.py`'s model.**
Rejected: a discovery-based check silently covers whatever schemas exist at
run time, so a new Avro record or OpenAPI component that should be paired
(or explicitly declared unpaired) but isn't yet would pass by simply not
being examined. The whole point of this check is to make that specific
failure mode — silent coverage shrinkage — impossible.

**`nullable -> not required` for the nullability rule.** Rejected as
factually wrong for this contract: it would fail `Instrument`'s
`option_type`/`strike`/`expiry`, which are correct as written. See "The
nullability rule" above.
