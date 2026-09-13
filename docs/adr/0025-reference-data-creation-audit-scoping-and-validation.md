# ADR-0025: Reference data creation: audit scoping and validation

## Status
Accepted

## Context
`POST /api/v1/instruments` is the second creation endpoint, after
`POST /api/v1/portfolios` (ADR-0024). An `Instrument` (`docs/domain-model.md#instrument`)
is, like a `Portfolio`, fully specified by its own client-supplied fields —
`instrument_id` is client-supplied, and there is no notion of "the same
instrument, created twice" independent of its content.

ADR-0024's Context and Decision are written narrowly about the
portfolio/trade distinction specifically — it derives its conclusion from
`Portfolio`'s specific four-field shape, not from a general principle about
resource creation. This ADR is where that narrower reasoning is checked
against a second, different resource and found to generalize: the relevant
property is not "is this a portfolio" but "is this resource client-keyed
and fully identified by its own content," and an `Instrument` has that
property for the same reason a `Portfolio` does.

A never-called draft of instrument creation already existed
(`InstrumentService.createInstrument`, written in an earlier session ahead
of any REST endpoint) and informed part of this decision — see "Reference
data is immutable after creation" below for what was wrong with it.

## Decision

### Duplicate semantics and no `Idempotency-Key`, generalized from ADR-0024
`POST /api/v1/instruments` takes no `Idempotency-Key` header, for the same
reason `POST /api/v1/portfolios` does not (ADR-0024): `instrument_id` is
the request's own identity, so a second, separate client-generated token
would be redundant. Duplicate detection compares the persisted row
field-by-field against the request — all fields matching is a replay
(`200`, the stored instrument); any field differing is a conflict (`409`).
ADR-0024's argument is not restated here; this ADR relies on it and states
only that it generalizes to any client-keyed, content-identified resource
creation, of which `Instrument` is one instance and `Portfolio` was the
first.

Same insert-first mechanism as `createPortfolio`: `InstrumentService
#createInstrument` attempts the `INSERT INTO instruments` first, wrapped in
a `SAVEPOINT` set immediately before it, so a `23505` unique-violation rolls
back only to that point and the transaction stays usable for the
compare-and-decide read that follows. No check-then-insert — that would be
the identical TOCTOU race ADR-0023 and ADR-0024 already rejected.

### Reference data is immutable after creation
The pre-existing, never-called `InstrumentService.createInstrument` used
JPA `save()`, which — Spring Data JPA's documented behavior for `save` on
an entity carrying an already-persisted primary key — merges, i.e. issues
an `UPDATE`. A repeat `POST /api/v1/instruments` against that code path
would have silently overwritten the stored instrument's fields and
republished the mutated row to `reference.instruments` as fact, with no
error and no audit trail of the change. This session's `createInstrument`
replaces that method entirely: insert-first with a `SAVEPOINT`, so a
duplicate `instrument_id` fails at the database level and is resolved
explicitly to `200` (identical) or `409` (conflicting), never an implicit
overwrite.

Updating an existing instrument is not supported by any endpoint that
exists today, and this ADR does not introduce one. `docs/domain-model.md#instrument`
already states an instrument never changes once created ("a new expiry or
strike is a new `Instrument`, not an update to an existing one"); this
decision is what makes that true in code as well as in the domain model,
rather than true only until the first accidental retry. Adding a real
update path is a deliberate future decision this ADR does not make.

### Instrument creation appends to the audit log with a null `portfolio_id`
`instrument_created` is registered in `docs/domain-model.md#auditentry`'s
`entry_type` field description alongside `trade_booked` and
`portfolio_created`, using `AuditLogRepository#append`'s 4-argument
overload (no `portfolio_id`) — an instrument is not scoped to any one
portfolio. The payload is the complete created instrument as JSON
(`CanonicalForm` hashes `entry_id + entry_type + payload`, so the payload
is the entirety of what the hash chain covers for this entry; a summary
would leave the interesting content unhashed). The audit chain is
append-only and immutable, so a creation event is recorded at creation or
not at all — it cannot be backfilled later if omitted, the same reasoning
ADR-0024 already gives for `portfolio_created`.

**Known consequence:** `GET /api/v1/portfolios/{id}/audit` filters on
`audit_log.portfolio_id` (V3 migration). `instrument_created` entries carry
a null `portfolio_id` and are therefore in the hash chain — verifiable,
counted toward chain integrity — but reachable through no endpoint that
exists today. This is accepted deliberately: an entry that exists but is
unreachable through any current endpoint is recoverable later by adding one
(e.g. a future `GET /api/v1/instruments/{id}/audit` or an unscoped audit
listing); an entry that was never written because no endpoint existed yet
to expose it is not recoverable at all. The append-only, immutable nature
of the chain makes "write it now, expose it later" the only reversible
choice available.

### Instrument type validity is enforced at the REST edge, not by a database constraint
`instrument_type` and `option_type` are parsed into the generated Avro
enums (`com.meridian.contracts.InstrumentType`, `com.meridian.contracts.OptionType`)
by `InstrumentController`, and an unparseable value is rejected there with
`400`. No `CHECK` constraint is added to the `instruments` table (both
columns stay bare `TEXT`, as they already were in the pre-existing schema),
and no migration is part of this ADR. The Avro schema
(`contracts/avro/reference-instruments.avsc`) is the contract of record for
what a valid `instrument_type`/`option_type` is (ADR-0002); a `CHECK`
constraint duplicating that enum into Postgres would be a second place to
update every time a new instrument type is added, with no guarantee the two
stay in sync.

### Conditional fields are rejected in both directions, not ignored
`option_type`, `strike`, and `expiry` are required together when
`instrument_type` is one of a positive, explicitly-named set —
`VANILLA_EUROPEAN_OPTION` or `VANILLA_AMERICAN_OPTION` — and must all be
absent otherwise. Both directions are enforced as `400`s:
present-and-non-null on a non-option instrument is rejected, not silently
dropped, because an ignored `strike` on an `EQUITY` would still persist
whatever partial state existed and could be misread later as meaningful; an
absent `strike` on an option is obviously incomplete. `InstrumentController`
holds this option-bearing set as a single named constant
(`OPTION_BEARING_TYPES`), not scattered across validation, DTO mapping, and
tests, specifically so that a future `InstrumentType` addition forces a
deliberate choice about which side of the rule it falls on, rather than
silently defaulting to "not an option" (a negative `!= EQUITY` rule) or
silently defaulting to "an option" (whatever the negative rule's inverse
would have been).

### Open question: `reference.instruments` carries no `event_time`/`ingest_time`
Unlike `portfolio.state` (`event_time` and `ingest_time` on every message,
ADR-0005), `contracts/avro/reference-instruments.avsc` has neither field.
Instrument creation therefore records its event time only in the audit log
(as this ADR's `instrument_created` entry); a consumer of
`reference.instruments` itself cannot tell when an instrument was created,
and cannot order two versions of a compaction key by event time, only by
partition/offset order.

Whether this is correct — reference data being effectively atemporal, with
ordering supplied entirely by log compaction and partition sequence rather
than a carried timestamp — or an oversight in a schema that, per a
same-session inventory, has never actually been consumed by anything, is
**not settled by this ADR**. It is recorded here as an open question, to be
resolved after the queued Avro-vs-OpenAPI cross-contract check, since
adding either field is a schema change with `BACKWARD`-compatibility
consequences under ADR-0002's registry-enforced policy, not something to
fold into an endpoint session. This ADR does not modify
`reference-instruments.avsc` and takes no position on which answer is
right.

## Consequences
- `POST /api/v1/instruments` diverges from `POST /trades`'s
  `Idempotency-Key` mechanism for the same reason `POST /api/v1/portfolios`
  does (ADR-0024): a reviewer should not assume ADR-0023 generalizes to
  every mutating endpoint.
- Every successful call to `createInstrument` (first-time creation only,
  not a `200`/`409` replay) produces exactly one `reference.instruments`
  message and exactly one `instrument_created` audit entry with a null
  `portfolio_id` — both inside the same transaction as the `instruments`
  row insert.
- `instrument_created` audit entries exist in the hash chain but are not
  retrievable through any endpoint today — see "Known consequence" above.
- No migration, no `CHECK` constraint, and no change to
  `reference-instruments.avsc` are part of this ADR.
- Whether `reference.instruments` should carry `event_time`/`ingest_time`
  is an open question this ADR raises but does not resolve.

## Alternatives considered
**Reuse `idempotency_keys`/`Idempotency-Key`.** Rejected for the same
reason ADR-0024 rejected it for portfolios: `instrument_id` is already the
request's identity, so a second client-generated token is a redundant
second identity for the same resource.

**A `CHECK` constraint on `instrument_type`/`option_type` mirroring the
Avro enum.** Rejected: two places to update for every new instrument type,
with no mechanism keeping them in sync — the Avro schema is already the
contract of record (ADR-0002) and the REST-edge parse already rejects an
invalid value before it reaches the database.

**Silently ignore conditional fields that don't apply (e.g. drop a stray
`strike` on an `EQUITY`) instead of rejecting them.** Rejected: a client
that mistakenly sent a strike for an equity would get a `201` with no
indication its request was misunderstood, and the persisted row would look
identical to one where the field was correctly absent — an accidental
success indistinguishable from a correct one is worse than an explicit
`400`.

**Add `event_time`/`ingest_time` to `reference-instruments.avsc` now, while
touching this schema's consumer for the first time.** Rejected for this
session: adding fields to a published Avro schema is a `BACKWARD`
compatibility decision under ADR-0002's registry-enforced policy, and
belongs after the queued Avro-vs-OpenAPI cross-contract check settles what
this schema should look like on the merits, not folded into an unrelated
endpoint session as a drive-by.
