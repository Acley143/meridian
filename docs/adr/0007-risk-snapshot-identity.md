# ADR-0007: Risk snapshot identity

## Status
Accepted

## Context
Risk snapshots are produced continuously and delivered at-least-once (Kafka's
default delivery semantics under consumer restarts/rebalances). We need a
key that makes redelivery idempotent, and that supports re-pricing history
under a new model without losing the old result.

## Decision
A risk snapshot's identity is the tuple
`(portfolio_id, as_of_event_time, pricer_version)`. Storage of risk snapshots
is an idempotent upsert on this key: redelivering the same snapshot overwrites
itself with an identical row, never creates a duplicate.

## Consequences
- At-least-once delivery is safe by construction; no separate deduplication
  layer is needed.
- Re-pricing history under a new `pricer_version` produces new rows alongside
  the old ones (same `portfolio_id`/`as_of_event_time`, different
  `pricer_version`), so old and new can be diffed directly — this is the
  primary mechanism for validating a new pricing model against production
  history.
- Any consumer that needs "the current price" must know to filter for the
  latest `pricer_version`, not just the latest row.

## Alternatives considered
- **Surrogate auto-increment key with dedup by content hash.** Rejected:
  adds a dedup layer to do exactly what the natural key already gives us for
  free, and doesn't naturally support the re-pricing/diff use case.
- **Identity without `pricer_version`.** Rejected: would make re-pricing
  under a new model overwrite the old result instead of coexisting with it,
  which defeats the stated purpose of keeping snapshots at all.
