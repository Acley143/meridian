# Meridian

Real-time derivatives risk & pricing platform — Python quant core, Kafka
streaming, Java service layer, React dashboard. Built by a five-person team
over four quarters.

> Build the deterministic, correct core first. Layer usability on top of it —
> never the reverse.

## Status

Skeleton stage: decisions, contracts, and plans are in place; implementation
starts from `PLAN.md` in each workstream directory. See `PLAN.md` at the
repo root for the four-quarter program plan.

## Start here

1. `docs/adr/` — the locked architectural decisions (ADR-0001 through
   ADR-0010). Read before touching anything they govern.
2. `docs/domain-model.md` — the source of truth for every type in the
   system. Every schema is a mechanical translation of this document.
3. `docs/nfr-budget.md` — the numeric pass/fail bar for Q4.
4. `CLAUDE.md` — working conventions, hard rules, and testing expectations.
5. `PLAN.md` — the program plan, linking to each workstream's own plan.

## Layout

```
meridian/
  docs/adr/           Architecture decision records (immutable once merged)
  docs/domain-model.md    Canonical type definitions
  contracts/           Avro schemas + OpenAPI spec — the wire contracts
  libs/quant-core/     Pure pricing & risk-analytics library (Python)
  libs/quant-io/       Kafka/registry I/O adapters (Python)
  services/ingest/     Simulated tick feed producer
  services/pricer/     Consumes ticks + portfolio state, produces risk
  services/core-service/  Java service: portfolio/trade state, REST+SSE API
  apps/dashboard/      React dashboard
  infra/               Local stack + deployment config
  tools/               Codegen and schema-lint utilities
```

## Local development

```
make setup   # install toolchains/dependencies
make up      # bring up Kafka, schema registry, Postgres locally
make gen     # regenerate language bindings from contracts/
make test    # run all test suites
make lint    # run all linters, including the quant-core purity check
```

## License

Apache-2.0 — see `LICENSE`.
