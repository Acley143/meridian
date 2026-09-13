# ADR-0024: Resource-creation identity and duplicate semantics

## Status
Accepted

## Context
`POST /api/v1/portfolios` is the first creation endpoint since ADR-0023 gave
`POST /trades` an `Idempotency-Key`-based dedup mechanism. ADR-0023 itself
flagged the `(endpoint, idempotency_key)` shape as "intentionally reusable
for `POST /portfolios` when that endpoint exists" — this ADR is where that
assumption gets checked against a real creation endpoint, not carried over
by default.

A trade and a portfolio differ in exactly the way that matters here.
`Trade.trade_id` is minted server-side; nothing in a trade request is its
own identity, and two requests with identical `portfolio_id`,
`instrument_id`, `quantity`, `price`, `event_time` can be two genuine trades
booked seconds apart (ADR-0023's Context). A portfolio is the opposite:
`portfolio_id` is client-supplied in the request itself, and
`docs/domain-model.md#portfolio` defines the resource as exactly four
fields (`portfolio_id`, `name`, `base_currency`, `owner`) with no
notion of "the same portfolio, booked twice." The request already carries
the identity that `Idempotency-Key` exists to supply for `POST /trades` —
requiring a second, separate token for it would be redundant, not
consistent.

## Decision

### Creation endpoints identify the resource by its own content, not a token
`POST /api/v1/portfolios` takes no `Idempotency-Key` header and does not
read or write `idempotency_keys`. `portfolio_id` is the request's identity;
duplicate detection compares the persisted row (`name`, `base_currency`,
`owner`) against the request's fields, not a `sha256` of the raw request
bytes.

This is available here specifically because the resource is small,
immutable after creation (nothing in this endpoint or elsewhere updates a
`portfolios` row), and fully specified by the request that creates it —
none of which holds for a trade. ADR-0023's reasoning does not transfer:
a trade is not identified by its content (two byte-identical trades may be
two genuine trades, per that ADR's Context), so content-comparison dedup
would be wrong there in exactly the way it's correct here.

**Consequence, stated plainly:** a retry with the same `portfolio_id` and
the same field values, sent as semantically identical but differently
formatted JSON (reordered keys, different whitespace, `"owner":"desk-1"` vs
`"owner": "desk-1"`), succeeds here — matched on parsed field equality — where
byte-different-but-semantically-identical JSON would return `409` on
`POST /trades` (fingerprinted on raw bytes, per ADR-0023, deliberately not
canonicalized). This is intended: parsed-field comparison is what "fully
specified by the request" is for, and re-fingerprinting raw bytes here would
reintroduce exactly the brittleness ADR-0023 accepted as a tradeoff for a
resource where it doesn't need to be accepted.

### Duplicate handling: insert first, compare second, never check-then-insert
Same insert-first mechanism as `IdempotencyKeyRepository#tryClaim`
(ADR-0023): `PortfolioMutationService#createPortfolio` attempts the
`INSERT INTO portfolios` first and lets the `PRIMARY KEY` constraint decide
whether this is a fresh creation, wrapping the insert in a `SAVEPOINT` set
immediately before it so a `23505` unique-violation rolls back only to that
point (not the whole transaction), leaving the transaction usable for the
read that follows. A read-then-insert check would be the same TOCTOU race
ADR-0023 rejected for trades, for the identical reason: two concurrent
creation requests for the same `portfolio_id` could both observe "no row"
and both attempt to proceed.

A losing insert reads the stored row inside the same transaction and
compares it field-by-field against the request: all three of `name`,
`base_currency`, `owner` matching is a replay (`200`, the stored portfolio);
any one differing is a conflict (`409`). Neither path appends an audit
entry or publishes `portfolio.state` — nothing new happened.

### `event_time` is the server clock at creation, not client-supplied
A trade execution has an external occurrence that precedes the request
(`Trade.event_time`, the venue's execution instant) — the request reports
it, the request is not it. Creation has no such antecedent: the request to
create a portfolio *is* the event. Accordingly, the request body carries no
`event_time` field, and a single `Instant.now()`, captured once at the top
of `createPortfolio`, is shared by both the audit entry's `event_time` and
the `portfolio.state` message's `event_time`. A client-supplied timestamp
here would be unverifiable (nothing external to check it against) and would
enter the immutable audit chain as an unverified claim — worse than a
server timestamp with a known, stated meaning ("when core-service accepted
this request").

`ingest_time` on the `portfolio.state` message is unaffected by this
decision — it remains whatever `PortfolioStateProducer.publish` already
computes internally (its own `Instant.now()`, at publish time), the same as
every other call to that method.

### Creation always publishes `portfolio.state`, with an empty `positions` array
`createPortfolio` publishes a `portfolio.state` record keyed on
`portfolio_id` with `positions: []`, in the same transaction, after the
audit append and last before commit (the same publish-last rule ADR-0003's
existing trade path already follows, so a publish failure rolls back the
whole transaction rather than leaving a committed row with no corresponding
message).

The pricer (`services/pricer/pricer/portfolio_view.py`) already treats a
non-null `portfolio.state` value with an empty `positions` array as "this
portfolio exists and holds nothing" — distinct from a null-valued tombstone,
which is a deletion (`PortfolioView.apply` vs. `PortfolioView.remove`;
verified directly against the current source before this ADR was written,
not assumed). An empty-positions record adds nothing to the pricer's
`underlying_id -> portfolio_id` reverse index today (there are no positions
to derive underlyings from) — so this decision has no pricing effect yet.
It exists so that "every write to `portfolios` publishes `portfolio.state`"
holds unconditionally, rather than holding only for trades and leaving a
newly-created, still-empty portfolio invisible to any future consumer that
expects a `portfolio.state` record to exist once a portfolio has been
created through the real API.

### Creation appends to the audit log
`portfolio_created` is registered in `docs/domain-model.md#auditentry`'s
`entry_type` field description alongside `trade_booked`, using the existing
5-argument `AuditLogRepository#append(entryId, entryType, payload,
eventTime, portfolioId)` overload — `portfolioId` set, so the entry is
scoped for `GET /api/v1/portfolios/{id}/audit`. The payload is the created
portfolio's four fields as JSON: `CanonicalForm.bytes` hashes
`entry_id + entry_type + payload` only (`docs/domain-model.md`'s canonical
form), so the payload is the entirety of what the hash chain actually
covers for this entry — a summary would leave the interesting content
unhashed. A creation event has no prior state to diff against and, being
append-only, cannot be backfilled later if omitted — it is recorded at
creation or not at all.

No `EntryType` enum is introduced. `entry_type` remains a plain `String` by
existing convention (`docs/domain-model.md#auditentry`: "Not free text in
practice — governed by the emitting service's `PLAN.md`"); a typed
enumeration of entry types is a separate decision, out of scope here.

## Known dependency: `portfolio.state` is not monotonic in `event_time`, and that is load-bearing elsewhere
A creation message's `event_time` is wall-clock (`Instant.now()` at the
moment `POST /api/v1/portfolios` is handled). A trade's `event_time` (the
existing path, unchanged by this ADR) can be a scenario-time value from a
replayed market scenario, arbitrarily far in the past or unrelated to
wall-clock order. For a given `portfolio_id`, this means successive
`portfolio.state` messages are not guaranteed to carry increasing
`event_time` values — a creation message can be temporally "later" by wall
clock than a subsequent trade message that carries an earlier scenario
time, or vice versa.

This is safe only because nothing downstream currently orders or filters on
it. Verified directly against the current source before this ADR was
written: `services/pricer/pricer/service.py`'s `_apply_portfolio_message`
calls `PortfolioView.apply` unconditionally for every non-null message, in
whichever order the Kafka consumer polls them (Kafka's own per-partition,
per-key ordering — not an `event_time` comparison); `PortfolioView.apply`
overwrites `self._portfolios[portfolio_id]` unconditionally, and the stored
`_PortfolioRecord.event_time` is written but never read back anywhere to
guard or reorder an apply. No monotonicity guard exists today, so this
decision introduces no regression.

**This is a dependency, not a closed question.** Adding an `event_time`
monotonicity guard to the pricer in the future (e.g. "ignore an incoming
`portfolio.state` message if its `event_time` is older than the one
currently held") would silently discard legitimate post-creation trade
state whenever a scenario's `event_time` sits earlier than the wall-clock
instant the portfolio was created at — which, for any replayed historical
scenario, is the common case, not an edge case. Anyone adding such a guard
must revisit this ADR first.

## Consequences
- `POST /api/v1/portfolios` diverges from `POST /trades`'s idempotency
  mechanism on purpose; a reviewer expecting `Idempotency-Key` parity across
  every mutating endpoint should read this ADR, not assume ADR-0023
  generalizes.
- Every successful call to `createPortfolio` (first-time creation only, not
  a `200`/`409` replay) produces exactly one `portfolio.state` message with
  an empty `positions` array and exactly one `portfolio_created` audit
  entry — both inside the same transaction as the `portfolios` row insert.
- `idempotency_keys` (V4 migration) is untouched by this endpoint; its
  `(endpoint, idempotency_key)` shape stays scoped to `POST /trades` only,
  contrary to ADR-0023's own speculation that it would be reused here.
- `POST /instruments` is a separate session's decision. Nothing here
  presumes instrument creation follows the same content-comparison pattern
  — `Instrument` has no update path either, per
  `docs/domain-model.md#instrument`, so the same reasoning may well apply,
  but that is for that session's own ADR (or an explicit note that this one
  covers it) to decide, not this one.

## Alternatives considered
**Reuse `idempotency_keys`/`Idempotency-Key`, as ADR-0023 speculated.**
Rejected: a portfolio's identity is already in the request
(`portfolio_id`), so a second client-generated token would be a redundant
second identity for the same resource, not a consistency win. It would also
force a client to invent and track a key for a request that is already
naturally retryable by re-sending the exact same body.

**Raw-byte request fingerprinting, as ADR-0023 does for trades.** Rejected:
would make a retry's success depend on byte-for-byte JSON formatting
identical to the original request, for a resource whose actual identity
question ("is this the same portfolio?") is answered by its parsed fields,
not its serialization. Correct for a trade (there is no other notion of
"the same trade" to fall back on); wrong here, where a better one exists.

**Client-supplied `event_time` on the creation request, matching
`TradeRequest`'s shape.** Rejected: a trade execution has a real external
event to report; a creation request does not precede any occurrence it
describes; it *is* the occurrence. Accepting a client timestamp here would
put an unverifiable value into the immutable audit chain for no benefit
over the server's own clock.

**Skip publishing `portfolio.state` on creation (only publish on the first
trade, as today).** Rejected: leaves "every write to `portfolios` produces
a `portfolio.state` message" true only by accident of there always having
been a first trade already, and reintroduces the exact gap the prior
inventory session (Session Q) found — a portfolio that exists in Postgres
with no corresponding `portfolio.state` record is invisible to the pricer
by construction, indefinitely, until some trade happens to be booked
against it.

## Editorial amendments

### 2026-09-13: `event_time` is truncated to microseconds at capture
The single `Instant.now()` captured once at the top of `createPortfolio`
(see "`event_time` is the server clock at creation, not client-supplied"
above) is truncated to microsecond precision at the point of capture,
before it is used for either the audit entry or the `portfolio.state`
publish.

Without this, the two sinks that record the same instant can disagree:
pgjdbc rounds half-up when encoding a `TIMESTAMPTZ`, while the Avro
`timestamp-micros` conversion floors. An untruncated instant whose
nanosecond remainder is >= 500ns is therefore recorded differently by the
audit log and by `portfolio.state` — one event ending up with two
different `event_time` values depending only on which storage layer is
read. Microsecond is the precision of the coarsest sink; the application
should not produce precision the storage layers disagree about how to
discard.

The trade path is unaffected by this: `Trade.event_time` is parsed from a
client-supplied JSON field, which in practice carries microsecond-or-coarser
precision. Nothing enforces that, however — a client sending nanosecond
precision in `event_time` would reintroduce the identical divergence on the
trade path. Recorded here as a known edge, not fixed.

Found by `PortfolioCreationTest`'s timestamp-equality assertion failing in
CI on runs 34675855060 and 34708325925. Fixed in commit 4e46787.
