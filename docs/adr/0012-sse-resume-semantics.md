# ADR-0012: SSE resume semantics

## Status
Accepted

## Context
ADR-0007 makes `RiskSnapshot` delivery idempotent and gapless all the way to
Postgres: at-least-once delivery plus an idempotent upsert on
`(portfolio_id, as_of_event_time, pricer_version)` means no loss and no
duplication through storage. But the final hop — `core-service` forwarding
snapshots to the dashboard over SSE (ADR-0009) — had no equivalent guarantee.
A dropped browser connection simply lost whatever snapshots were produced
while it was down; the no-loss guarantee from ADR-0007 was only as strong as
this, its weakest link.

## Decision
Every SSE event carries an `id:` field equal to the ADR-0007 identity tuple,
formatted as `{portfolio_id}:{as_of_micros}:{pricer_version}`. On reconnect,
the browser's `EventSource` automatically sends the `Last-Event-ID` header
with the id of the last event it received; `core-service` parses that header
and replays persisted snapshots for that portfolio with a later `as_of` than
the one in the header.

Replay is bounded at **500 snapshots or 15 minutes, whichever is smaller**.
If the gap exceeds the bound, the service emits a `resync` event instead of
replaying, and the client is expected to refetch full current state via
`GET /portfolios/{id}/positions` and
`GET /portfolios/{id}/risk-snapshots/latest` rather than receive a long
backlog over the stream.

## Consequences
- A dashboard that briefly drops connection (the common case) sees no gap in
  its risk history — the stream picks up exactly where it left off.
- The replay bound converts "how long was I disconnected" into a case split:
  short gaps are healed transparently by the stream; long gaps are healed by
  falling back to REST, which is the cheap, already-idempotent path per
  ADR-0007's own upsert semantics.
- `core-service` must persist enough recent `RiskSnapshot` history per
  portfolio to serve the replay bound (500 snapshots / 15 minutes), not just
  the latest one — this is a real, bounded storage/query requirement, not a
  free byproduct of ADR-0007.
- Unbounded replay was rejected because it would let a flaky client
  connection (reconnecting repeatedly, each time asking for a large replay)
  turn into unbounded server-side load — the bound exists specifically to
  prevent a client-side problem from becoming a server-side one.

## Alternatives considered
- **Unbounded replay from `Last-Event-ID`.** Rejected: converts a flaky
  client connection into a server-side load event, with no bound on how much
  history a single reconnect can request.
- **No resume semantics; client always refetches full state on reconnect.**
  Rejected: makes every reconnect — including the very common brief
  network blip — pay the cost of a full resync, when the underlying data
  (recent snapshots) is already available to replay cheaply.

## Addendum
See also ADR-0009, which this ADR extends with resume semantics for the SSE
stream it establishes.

## Editorial amendments
- 2026-08-31 (core-service): **The 15-minute age bound is measured in event
  time, against persisted snapshot history, not against wall-clock
  `now()`.** The Decision above says "replayed... a later `as_of`" without
  saying what the age half of the bound is measured *against*; the initial
  implementation read that as `now() - as_of`, using `Instant.now()`.
  `as_of` is scenario-derived event time (ADR-0011), deliberately decoupled
  from wall clock so that a historical scenario can be replayed at all. A
  bound measured against `now()` makes that decoupling self-defeating: any
  reconnect against a portfolio whose `as_of` isn't approximately
  wall-clock-current resyncs immediately, regardless of how many snapshots
  or how much event time actually separates the client from current state
  — ADR-0011's replay capability and this ADR's resume semantics were
  mutually incompatible as written. The bound is instead: count bound —
  snapshots after the given `as_of` for that portfolio (already a stored
  quantity, unaffected by this amendment); age bound — the given `as_of`
  compared to the *newest persisted* `as_of` for that portfolio, not to
  `now()`. Both are robust to event time diverging arbitrarily from wall
  clock, which this system treats as a designed property, not an anomaly.
  Non-substantive to the bound's intent (still "500 snapshots or 15 minutes
  of the portfolio's own history, whichever is smaller") but substantive to
  its correctness whenever event time and wall clock diverge.
