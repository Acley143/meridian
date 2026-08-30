# quant-io

I/O adapters that compose `quant-core`'s pure functions with the outside
world: Kafka consumers/producers, the schema-registry client, clock access.
Python 3.12.

- This is where `datetime.now()`, Kafka clients, and file/database access are
  allowed to live. If a service needs I/O, it goes through here, not
  ad hoc in the service itself, so the I/O boundary stays in one place.
- Depends on `quant-core`; `quant-core` must never depend back on this
  package (see `libs/quant-core/.importlinter`).
- Deserialize Avro messages into the generated bindings from `contracts/`
  only — never hand-roll a parallel parser for a schema that already has one.
- Local test command: `pytest libs/quant-io -q`. I/O boundaries should be
  tested against a real local Kafka/registry (via `docker-compose.yml`), not
  mocked wholesale — a mock that drifts from the real broker's behavior is
  worse than no test.
- The one mistake most likely here: leaking a naive (non-timezone-aware)
  `datetime` across the boundary back into `quant-core`. Always construct
  timezone-aware UTC datetimes at the point of I/O (ADR-0005).
