# codegen

Generates Python/Java/TypeScript bindings from `contracts/avro/*.avsc` and
`contracts/openapi/service-api.yaml`. Invoked via `make gen`.

Not yet implemented — this is skeleton scaffolding. Implementation belongs to
a session working from a `PLAN.md` for this tool (none exists yet; add one
before starting, per the root `CLAUDE.md`).

Output must never be hand-edited (`contracts/README.md`) — regenerating from
the schema is always the fix.
