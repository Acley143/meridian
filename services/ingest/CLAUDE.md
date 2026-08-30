# ingest

Java (or Python — see workstream `PLAN.md` for the Q1 decision) service that
takes market data from a feed (simulated in Q1) and produces `Tick` messages
onto Kafka.

- This is the point of origin for `event_time`/`ingest_time` on every tick
  (ADR-0005) — `event_time` comes from the upstream feed's own timestamp
  (or, for the Q1 simulated feed, is generated to look like one); `ingest_time`
  is stamped here, at receipt, not later in the pipeline.
- This is the first and only place a `Tick` is constructed — downstream
  consumers (the pricer) must treat it as immutable once produced.
- Local test/build command: see the manifest in this directory once the
  language choice lands (`PLAN.md`); either way, contract tests against
  `contracts/avro/tick.avsc` are mandatory before this service can produce to
  a shared topic.
- The one mistake most likely here: generating ticks for the Q1 simulated
  feed with `event_time == ingest_time` always exactly equal — that silently
  zeroes out feed latency in every downstream latency measurement. Simulate
  realistic (even if small) skew.
