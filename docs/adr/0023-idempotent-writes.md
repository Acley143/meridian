# ADR-0023: Idempotent writes on POST /trades

## Status
Accepted

## Context
`POST /api/v1/trades` mints `trade_id` server-side and has no dedup of any
kind. A client that times out waiting for a response and retries the exact
same trade books it twice — there is nothing in the request, the endpoint,
or the database that can tell the retry apart from a second, genuine
submission.

Natural-key dedup (treating two requests with identical `portfolio_id`,
`instrument_id`, `quantity`, `price`, `event_time` as the same trade) is
wrong here, not just imprecise: two genuine trades can share every one of
those fields at the same instant (a desk booking two identical clips of the
same name seconds apart is ordinary, not suspicious). Only a client-chosen
token can distinguish "this is a retry of that request" from "this is a new
request that happens to look the same."

The audit log (ADR-0008) raises the stakes above a normal duplicate-row
problem. It is an append-only hash chain — a duplicate `trade_booked` entry
cannot be deleted afterward without breaking the chain for every entry after
it. The only place to prevent a duplicate is before the append; there is no
"clean up later."

## Decision

### Client-supplied `Idempotency-Key`, required
`POST /api/v1/trades` requires an `Idempotency-Key` header. Missing or empty
→ `400`, before any business logic runs.

### Fingerprint the raw bytes, never canonicalize
The stored `request_fingerprint` is `sha256(raw request body bytes as
received)`. A genuine retry from a real client sends byte-identical content;
canonicalizing (re-serializing to a normal form before hashing) would add a
step that can diverge from what the client actually sent in either
direction — a canonicalizer bug could make two different requests fingerprint
the same, or make one genuine retry fingerprint differently because of
incidental formatting (key order, whitespace) a naive client's JSON
serializer isn't guaranteed to reproduce byte-for-byte between calls.
`TradeController` reads the body as `byte[]` and only deserializes into
`TradeRequestDto` from those same bytes afterward, purely to extract fields
`PortfolioMutationService` needs — the fingerprint is computed from the
untouched bytes.

### One row per (endpoint, key); match replays, mismatch rejects
`idempotency_keys` (V4 migration) has a `PRIMARY KEY (endpoint, idempotency_key)`.
`endpoint` is part of the key deliberately: a client-chosen key is only
required to be unique in the client's own head, and a key reused across
`POST /trades` and a future `POST /portfolios` is not the same request
merely because it reused a string.

- Same key, same fingerprint → the stored response is replayed verbatim,
  status and body byte-for-byte, including the original `trade_id`. No new
  UUID is minted, no business logic runs again.
- Same key, different fingerprint → `409`, and the request is never applied.
  Replaying a stored response for a request the client did not actually
  send would be silently wrong in a way invisible to both client and
  server; rejecting is the safe failure.

### Insert-first concurrency: the unique constraint is the lock
There is no read-then-write "does this key exist?" check before the
INSERT — that check-then-act pair is exactly the TOCTOU race two concurrent
retries would hit (both read "no row", both proceed to book). Instead
`IdempotencyKeyRepository#tryClaim` always attempts the INSERT first and
lets the unique constraint answer the question: it succeeds (this caller is
the first writer) or fails with `23505` (a row already exists; the caller
must `find` it to decide replay vs. `409`).

Because the claim INSERT is inside the same `@Transactional`
`PortfolioMutationService#applyTradeIdempotent` call as the rest of trade
booking, a second concurrent request for the same key blocks on that row's
lock until the first transaction commits or rolls back — Postgres's normal
behavior for a conflicting INSERT into a unique index, not anything built by
hand here. Once the first transaction resolves, the second either fails the
constraint (row now exists, committed, safe to read) or succeeds outright
(the first rolled back, freeing the key).

**A Postgres wrinkle found while implementing this:** a failed INSERT
doesn't just fail — Postgres aborts the rest of the enclosing transaction
(`current transaction is aborted, commands ignored until end of transaction
block`, SQLSTATE `25P02`) until a `ROLLBACK`. The first implementation
caught the constraint violation in Java, returned `false`, and then ran
`find()` in the same (now-aborted) transaction — every request that lost a
claim race returned `500`, confirmed against the real stack before this
landed (see Verification). `tryClaim` now sets a `SAVEPOINT` immediately
before the INSERT and rolls back to *that* on a `23505`, not the whole
transaction, leaving the transaction usable for the `find`/replay/`409`
decision that follows. This is a correctness requirement of the design, not
an optimization — without it, every losing claim 500s instead of replaying
or rejecting.

### Ordering: idempotency insert before the audit append
`applyTradeIdempotent` claims the key before calling into `applyTrade`
(trade save, position save, `AuditLogRepository#append`). If the claim came
after the audit append instead, two concurrent same-key requests could both
pass the (unserialized, at that point) claim check and both reach
`AuditLogRepository#append`'s JVM-level `synchronized` section — which only
serializes appends against each other, not against a claim that hasn't
happened yet — producing two `trade_booked` entries in an append-only chain
that cannot be fixed after the fact. Lock order is therefore fixed: Postgres
row lock (the idempotency claim) first, then the JVM audit lock. Reversing
it reopens exactly the race this ADR exists to close.

### Not a filter, interceptor, or AOP aspect
The claim, response storage, and read-back all live inside
`PortfolioMutationService#applyTradeIdempotent`, the same `@Transactional`
method that does the rest of trade booking — not in a servlet filter or a
`@Around` advice wrapping the controller. Those run outside the transaction
boundary; if the claim were taken in a filter and the transaction later
rolled back, the claim would survive the rollback and permanently lock out
retries of a request that never actually succeeded (see the rollback
requirement below).

### Rollback releases the key
Storing the claim inside the same transaction as the business mutation
means a rollback undoes both together. If `applyTrade` fails after the
claim succeeded (the existing unknown-`portfolio_id`/`instrument_id` `400`
path, a real FK violation on the trade insert), the whole transaction rolls
back, including the claim row. A retry with the same key is then free to
claim it again. Storing the claim in its own, separately-committed
transaction would leave a permanent claim behind every failed request —
every retry of a failed request would replay that same failure forever,
which is worse than no idempotency at all. Verified directly (see below):
forcing the FK violation after the claim, confirming the row is gone, then
retrying the identical key successfully.

### Retention: a window, not a lookup filter
`created_at` is stored and indexed for a 24-hour retention sweep. The sweep
itself is not built in this session — tracked in
`services/core-service/PLAN.md`. Deliberately, lookups never filter on
`created_at`: an expired-but-unswept row must still collide on INSERT
(so it is not treated as free) and still be found on lookup (so it can
still be replayed or rejected). Filtering the lookup by age would let the
INSERT fail the unique check while the lookup finds nothing to replay —
an error path with no stored response, for no reason.

## Verification
Hand-run against the real `docker-compose.yml` stack (`services/pricer` and
`services/ingest` not needed for this surface) — Testcontainers does not run
in this sandbox, the same pre-existing limitation earlier sessions recorded
in `services/core-service/PLAN.md`:

1. Same key, same body, twice → identical `201` response both times
   (byte-identical body, same `trade_id`), one `trades` row, one
   `trade_booked` audit entry.
2. Same key, different body → `409` on the second call; trade/audit counts
   unchanged by it.
3. Different keys, identical bodies → two trades booked with distinct
   `trade_id`s, proving the key (not the content) is what's compared.
4. Missing header → `400`. Empty header → `400`.
5. Two concurrent requests, same key, separate threads, run across 10
   iterations with fresh portfolios each time → exactly one trade, one
   audit entry, both callers received the same `201` and the same
   `trade_id`, every iteration.
6. **The load-bearing case.** A request against a not-yet-existing
   `portfolio_id`/`instrument_id` claims the key, then fails the FK
   constraint inside `applyTrade` → `400`; the `idempotency_keys` row for
   that key was confirmed absent afterward; the identical key, retried
   after creating the portfolio/instrument, then succeeded with `201`. This
   is what caught the `25P02` transaction-abort bug above — the first
   implementation 500'd on scenario 2 (the losing side of a same-key
   collision) until `tryClaim` was fixed to use a savepoint.
7. Audit chain `prev_hash` linkage confirmed intact (each row's `prev_hash`
   equals the previous row's `entry_hash`, genesis row's `prev_hash` is
   empty) across all of the above traffic, including the replayed and
   rejected requests that must **not** have appended anything.
8. `mvn -pl services/core-service compile` and `test-compile` clean;
   `spotless:check` clean; `make gen` regenerates
   `contracts/generated/typescript/service-api.ts` cleanly from the updated
   OpenAPI spec. The Docker-dependent integration suite
   (`IdempotentTradeBookingTest` and the rest of the `@SpringBootTest`
   suite) could not be run via `mvn test` in this sandbox for the same
   Testcontainers reason as prior sessions; CI is the first place it runs
   for real, same as those sessions' precedent.

## Consequences
- `POST /api/v1/trades` is a breaking change for any existing caller that
  doesn't send `Idempotency-Key` — there are none yet (Q1/Q2 have no real
  trade-source integration per `services/core-service/PLAN.md`'s open
  question on REST vs. an inbound Kafka topic), so this is not guarded by a
  deprecation window.
- `idempotency_keys` accumulates one row per booking attempt (successful,
  replayed, or rejected) until the (not-yet-built) 24-hour sweep runs.
  Tracked as follow-up in `services/core-service/PLAN.md`.
- The `(endpoint, idempotency_key)` shape is intentionally reusable for
  `POST /portfolios` when that endpoint exists — a new caller only needs
  its own `endpoint` string and to route through the same
  `IdempotencyKeyRepository`/`IdempotencyFingerprint` pair; no schema
  change. `POST /portfolios` itself is explicitly out of scope for this
  change.
- A future multi-instance deployment of `core-service` is unaffected by the
  concurrency mechanism (the lock is a Postgres row lock, not
  JVM-local) — unlike `AuditLogRepository`'s `synchronized` append lock,
  which ADR-0008 already documents as JVM-local only.

## Alternatives considered
**Natural-key dedup** (treat identical `portfolio_id`/`instrument_id`/
`quantity`/`price`/`event_time` as the same trade). Rejected in Context
above — collapses two genuine simultaneous trades into one silently.

**Read-then-write claim** (`SELECT` for the key, `INSERT` if absent).
Rejected: classic TOCTOU — two concurrent requests can both read "absent"
and both proceed, producing exactly the duplicate this ADR exists to
prevent, under precisely the retry-storm conditions it needs to survive.

**Claim in a servlet filter or `@Around` interceptor, outside the
transaction.** Rejected: a rollback inside the transaction would not undo a
claim taken outside it, permanently locking out retries of a request that
never actually succeeded.

**Idempotency insert after the audit append instead of before.** Rejected:
reopens the concurrent-duplicate-audit-entry race the ADR-0008 append lock
alone cannot close, since two concurrent claims aren't yet serialized
against each other at that point (see "Ordering" above).
