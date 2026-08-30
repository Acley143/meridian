# schema-lint

Validates `contracts/avro/*.avsc` files (well-formed Avro, and — once a
schema registry exists to check against — `BACKWARD` compatibility per
ADR-0002). Invoked in CI (`.github/workflows/ci.yml`, `schema-compatibility`
job).

Not yet implemented — this is skeleton scaffolding. Implementation belongs to
a session working from a `PLAN.md` for this tool (none exists yet; add one
before starting, per the root `CLAUDE.md`).
