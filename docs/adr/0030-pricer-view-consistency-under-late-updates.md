# ADR-0030: pricer view consistency under late portfolio and curve updates

## Status
Accepted

## Context

`services/pricer` keeps two local views built from compacted topics: the
portfolio view from `portfolio.state` (ADR-0003) and the curve view from
`market.curves` (ADR-0027). It reads each on its own consumer, separately
from the consumer for `market.ticks`. Kafka orders messages within a
partition, not within a topic and not across topics (ADR-0016), so nothing
orders a `portfolio.state` or `market.curves` message relative to a tick.

`hydrate()` gates once, at startup: it reads both compacted topics to the end
before `start_tick_consumption()` subscribes to `market.ticks` (ADR-0018,
ADR-0027 Decision 9). After that, the only coupling is that
`process_one_tick` drains both view consumers with a non-blocking
`poll(0.0)` before polling for a tick. `poll(0.0)` returns only what the
client has already fetched; a message the broker has acknowledged but not
yet delivered to the client is invisible to it.

`test_tombstone.py::test_tombstone_mid_stream_stops_snapshots` failed
intermittently in CI (run `33582972332`, "a tombstoned portfolio must not
produce a snapshot"). An investigation established the cause:

- On unmodified code it passed 40 times in 40 local runs, but instrumented
  runs showed the drain picking the tombstone up only 0.4 to 1.6 ms after
  the test finished flushing the next tick. It passed because producing that
  tick took slightly longer than delivering the tombstone.
- Delaying only the portfolio consumer's fetch (`fetch.min.bytes` 10 MB,
  `fetch.wait.max.ms` 1500) reproduced the CI failure every time. At the
  moment the drain ran, the consumer's position was 1 and the broker's high
  watermark was 2: the tombstone had been acknowledged but not delivered. The
  tick was priced against the pre-tombstone view; a snapshot was produced,
  the portfolio was still in the view, and the reverse index still held it.
- The tombstone was applied on the next drain, about 2.2 s later, and the
  following tick produced no snapshot. The update is applied late, not lost.

So this is a real cross-topic race in the pricer, not a test-only bug. Two
other tests had the same shape, asserting immediately after producing an
update, and a third already worked around it with an ad-hoc sleep loop.

## Decision

1. **The pricer's portfolio and curve views are eventually consistent with
   respect to the tick stream.** A tick is priced against the views as they
   are at that moment. A portfolio or curve update still in flight from the
   broker is not waited for. Blocking the drain until the view "catches up"
   is rejected: it would stall tick processing to provide an ordering that
   Kafka does not provide across topics, and there is no point at which the
   pricer could know nothing more is in flight.

2. **The window is narrowed by draining again after the tick poll returns
   and before pricing.** The first drain runs before a poll that can block
   for its full timeout (5 s by default), so an update arriving during that
   wait was previously ignored for the very tick it waited on. Draining
   again once the tick has arrived picks such updates up. This reduces
   staleness to in-flight broker latency. It does not eliminate it: an
   update the broker has acknowledged but not yet delivered when the second
   drain runs is still missed.

3. **Consequence, stated rather than fixed: a snapshot can be published for
   a portfolio whose tombstone has not yet been applied.** It carries the
   ADR-0007 identity tuple `(portfolio_id, as_of, pricer_version)`, with
   `as_of` the triggering tick's event time. `services/core-service`
   persists it by upsert (`RiskSnapshotRepository.upsert`) and broadcasts it
   over SSE (`RiskSnapshotPersistedEvent`). Nothing downstream checks
   whether the portfolio still exists. The same applies to a full-state
   replacement that removes a position, and to a curve update.

4. **Replay does not reproduce these late snapshots.** A cold start hydrates
   `portfolio.state` and `market.curves` to the end before processing any
   tick, so the update is already applied. Live and replay risk history can
   therefore differ by the snapshots priced inside this window. ADR-0027
   accepted the same divergence for curves at the start of a scenario; this
   records it for portfolio state too.

5. **A blocking prerequisite for any portfolio deletion feature.** Deletion
   does not exist today: `PortfolioStateProducer.tombstone` in core-service
   has no callers, and there is no delete endpoint. Whoever builds it must
   handle Decision 3's late snapshot. `risk_snapshots.portfolio_id`
   references `portfolios (portfolio_id)`. If deletion removes that row, a
   late snapshot violates the foreign key; `RiskSnapshotConsumerService.pollOnce`
   then seeks back to the failed record and rethrows, so the same record is
   redelivered on every poll and that partition of `risk.snapshots` is
   blocked indefinitely. Deletion must therefore either keep the
   `portfolios` row (for example, mark it deleted) or make the snapshot
   consumer tolerate a snapshot for a deleted portfolio. A deletion feature
   is not complete until it does one of the two.

6. **Test rule.** Any test asserting on the effect of a post-hydration
   portfolio or curve update must wait until the pricer has applied it.
   `flush()` proves only that the broker accepted the write. A test that
   asserts immediately after `flush()` is asserting an ordering the system
   does not provide, and will fail intermittently. The shared helper
   `wait_until_applied` in `services/pricer/tests/pricer_test_helpers.py`
   drives the service's own drains until a predicate holds, so it waits for
   exactly the state production would reach.

## Consequences

- One extra pair of non-blocking drains per tick. Each is `poll(0.0)` until
  the local queue is empty, so the cost is negligible when nothing is
  pending.
- No other change to pricing, ordering, offsets or snapshot identity. The
  pre-poll drains stay, and `PRICER_VERSION` is unchanged: no snapshot value
  for a given input changes.
- The window is smaller but still exists. In production, late snapshots for
  a just-deleted or just-changed portfolio remain possible, and are now a
  documented property of the system rather than an unexplained flake.
- Deletion now has a stated prerequisite (Decision 5) that a future session
  must satisfy before shipping it.
- Three tests that asserted immediately after an update now wait for it,
  and an ad-hoc sleep loop is replaced by the shared helper. Their
  assertions are unchanged.

## Alternatives considered

- **Blocking drain** (poll the view consumers with a timeout, or until they
  reach the broker's high watermark, before every tick). Rejected: it adds a
  broker round trip, or a fixed wait, to every tick, which works against the
  latency budget in `docs/nfr-budget.md`. It still would not provide
  ordering, since an update can be produced just after the watermark is
  read.
- **A single consumer over a merged topic** (publish portfolio changes,
  curves and ticks to one partitioned stream so Kafka orders them).
  Rejected: `portfolio.state` and `market.curves` are compacted topics keyed
  for compaction (ADR-0003, ADR-0016, ADR-0027), while `market.ticks` is an
  unbounded, high-volume stream keyed by instrument. Merging them would
  either lose compaction or make ticks compacted, and a portfolio's
  positions span many instruments, so no single key orders a portfolio
  change against all the ticks it affects.
- **Gating ticks behind a portfolio watermark** (have each tick, or the tick
  producer, carry the `portfolio.state` offset it was produced after, and
  hold the tick until the view reaches it). Rejected: the tick feed and
  core-service are independent producers with no shared clock or offset to
  agree on, the tick schema would need a field it has no source for, and
  held ticks need an unbounded buffer, the same objection ADR-0027 raised to
  buffering ticks until curves arrive.
