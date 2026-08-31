# ADR-0016: Partition keys are a correctness decision

## Status
Accepted

## Context
Kafka orders messages within a partition, not within a topic. The
partition key — `hash(key) % partition_count` by default — therefore
determines which orderings exist at all; a topic with no key, or the wrong
key, has no ordering guarantee a consumer can rely on. Every downstream
consumer in Meridian is written assuming a specific ordering holds. That
assumption currently lives only inside the `.avsc` key schemas
(`contracts/avro/*-key.avsc`), where it reads as a serialization detail —
"this is the shape of the key" — rather than what it actually is: the
guarantee three separate components depend on to behave correctly.

## Decision
| Topic | Key | Guarantee |
|---|---|---|
| `ticks` (schema: `tick-key.avsc`) | `instrument_id` | All ticks for one instrument are totally ordered. A pricer consuming this topic never sees a stale price after a fresher one for the same instrument. |
| `risk.snapshots` (schema: `risk-snapshot-key.avsc`) | `portfolio_id` | Snapshots for one portfolio arrive in `as_of` order. This is what makes ADR-0012's SSE resume-from-`Last-Event-ID` coherent — replay only makes sense as "everything after this point," which requires the stream to already be ordered. |
| `portfolio.state` (schema: `portfolio-state-key.avsc`) | `portfolio_id` | Required by log compaction (ADR-0003) — the key *is* the compaction identity. Kafka retains the latest value per key; a different key per message from the same portfolio would defeat compaction, not just ordering. |

These are already what each `*-key.avsc` schema encodes; this ADR names
the guarantee each one buys, so it stops reading as an implementation
detail.

## Consequences
- **Changing a partition key is a breaking change to consumer semantics
  even when the schema is unchanged.** Repartitioning by a different field
  (or adding fields to a composite key) redistributes messages across
  partitions differently, silently breaking whatever ordering a consumer
  was relying on — with no schema-level signal, since the value schema
  doesn't change. This requires a superseding ADR, the same as any other
  breaking change under ADR-0002, even though `BACKWARD` compatibility
  checking (which only looks at the value schema) would not catch it.
- **Increasing partition count on a keyed topic breaks ordering across the
  boundary. This is the trap people actually fall into**, not key
  selection itself: Kafka's default partitioner is `hash(key) %
  partition_count`, so changing `partition_count` changes which partition
  a given key hashes to for every key, for messages produced after the
  change. Old messages for a key stay on the old partition; new messages
  for the same key land on a different one. A consumer reading
  partition-by-partition (or relying on "same key = same partition, so I
  can process it single-threaded per partition") sees the same key's
  messages split across two partitions with no ordering between them —
  the exact guarantee this ADR exists to name is what breaks, silently,
  with no error anywhere.
- `infra/PLAN.md` now states that partition counts are set once at topic
  creation and are not a tuning knob to revisit casually — see that
  workstream's deliverables.

## Alternatives considered
- **No key (round-robin partitioning).** Rejected outright for all three
  topics: none of them have a consumer that can tolerate out-of-order
  delivery for the same instrument/portfolio — that's the whole reason
  each one has a natural key.
- **Composite key (e.g. `(portfolio_id, as_of)` for `risk.snapshots`).**
  Rejected: would scatter one portfolio's snapshots across partitions
  (different `as_of` values hash differently), destroying exactly the
  per-portfolio ordering ADR-0012's resume semantics depend on. The
  *value* already carries the full ADR-0007 identity tuple; the key only
  needs to route, not identify.
