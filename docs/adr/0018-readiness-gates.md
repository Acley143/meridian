# ADR-0018: Readiness gates and price cache recovery

**Status:** Accepted

## Context

A consumer derives its output from several state sources, and those sources recover differently after a restart.

`portfolio.state` and `reference.instruments` are log-compacted, so a materialised view rebuilds in full by reading each assigned partition to its end. `market.ticks` is a retention stream, so the last-known-price cache built from it has no equivalent recovery path.

Session 04 established a hydration gate for the portfolio view but not for the price cache. The restart tests surfaced the consequence: a restarted pricer resumes from its last committed offset, never re-sees ticks it already committed, and cannot price a multi-instrument portfolio until every underlying ticks again. In liquid names that window is seconds; in illiquid ones it is unbounded.

The failure is silent. No exception, no snapshot — the portfolio simply disappears from the output until the gap closes on its own.

A related variant applies to any consumer that begins work before a compacted view is complete: it acts on a partially loaded portfolio, produces a plausible result, and self-corrects moments later, leaving one wrong record permanently persisted under a valid identity.

## Decision

A consumer reports ready only after every state source it depends on has hydrated, and emits nothing until it does.

- **Compacted views** hydrate by reading each assigned partition to its end.
- **The price cache** hydrates by bounded replay: a separate consumer assigns partitions directly, seeks by timestamp to a configured lookback window, and reads forward to the committed offset, populating last-known prices only.
- **No output is produced during hydration**, from any source.
- Each source's readiness transition is logged separately.

The replay consumer must not use the main consumer group, so committed offsets are untouched.

The lookback window is an operational parameter and must exceed the longest expected gap between ticks for the least liquid instrument. If an instrument has not ticked within the window, the affected portfolio cannot be priced, and that must be reported — a structured log line naming the portfolio and the missing instruments, plus a counter — never silence.

## Consequences

- Startup is slower by the cost of the replay, bounded by the lookback window.
- Replay is safe because ADR-0007's identity tuple makes duplicate snapshots idempotent; suppressing emission during hydration means duplicates do not arise at all.
- The pattern generalises to any consumer with derived state.
- Degradation becomes visible rather than silent, the same motivation behind `oldest_input_event_time`.

## Alternatives considered

**A second compacted `market.prices.latest` topic.** Rejected: adds a topic and a producer to own, duplicating data already on `market.ticks`.

**A local state store (RocksDB or similar).** Rejected: operational weight disproportionate to a five-person project, and introduces local disk state to back up or rebuild.

**Querying `core-service` at startup.** Rejected: reintroduces the coupling ADR-0003 removed, and prices are not persisted in Postgres.

**Accepting the gap and documenting it.** Rejected: every restart produces a blind window with no error, and a restarted service shows an unexplained blank dashboard.
