# Meridian

Real-time derivatives risk & pricing platform — Python quant core, Kafka
streaming, Java service layer, React dashboard. Built by a five-person team
over four quarters.

> Build the deterministic, correct core first. Layer usability on top of it —
> never the reverse.

## Status

Q1 complete: the pipe is connected end to end. A simulated tick feed
(`services/ingest`) produces to Kafka; a pure Black-Scholes pricer
(`services/pricer`) consumes ticks and portfolio state and produces
`RiskSnapshot`s; `services/core-service` holds portfolio/trade state and
exposes it over REST + SSE; `apps/dashboard` renders a live risk number,
tracks connection state through resync/reconnect, and marks stale input
data. Verified locally end to end (`docker compose up` + ingest + pricer +
core-service): a real tick lands in Kafka, is priced, and reaches the
dashboard's SSE stream as a live-updating number within the same second it
was produced. See `PLAN.md` at the repo root for what's next in Q2.

## Start here

1. `docs/adr/` — the locked architectural decisions (19 as of Q1, ADR-0001
   through ADR-0019). Read before touching anything they govern.
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

`make setup`'s `pip install -e libs/quant-io` needs `librdkafka` on the host
(`confluent-kafka`'s C extension links against it) — `brew install
librdkafka` on macOS before running `make setup` if it fails with a missing
`librdkafka/rdkafka.h`.

### Running the full stack

There's no single command for this yet — each piece is started separately.
From the repo root, after `make setup` and `make gen`:

```
make up                                                    # Kafka, schema registry, Postgres

# core-service: holds portfolio/trade state, exposes REST + SSE
mvn -pl services/core-service spring-boot:run

# seed at least one portfolio/instrument/position -- there's no creation
# endpoint yet (Q1 open item), so this is a direct insert for local dev:
#   INSERT INTO portfolios (portfolio_id, name, base_currency, owner) ...
#   INSERT INTO instruments (instrument_id, underlying_id, instrument_type, ...) ...
# then book a position via POST /api/v1/trades (snake_case body -- portfolio_id,
# instrument_id, quantity, price, event_time -- per contracts/openapi/service-api.yaml)

# pricer: consumes ticks + portfolio state, produces RiskSnapshots
python3 -m pricer.cli services/pricer/fixtures/instruments.yaml

# ingest: simulated tick feed
cd services/ingest && python3 -m ingest.cli scenarios/small-deterministic.yaml --pacing realtime

# dashboard
cd apps/dashboard && npm run dev
```

**The dashboard is same-origin, by design (ADR-0020).** `core-service` has
no CORS configuration and none is added. Instead, `apps/dashboard` never
issues a cross-origin request: every `fetch` and `EventSource` call uses a
relative `/api/v1/...` path (ADR-0021), and `vite.config.ts`'s dev proxy
forwards `/api` to `core-service` on `:8080`. This is deliberate — a permissive dev
CORS policy is the kind of thing that leaks into production by accident,
and it would decide Q3's production origin topology by default. Any
production deployment must instead serve the dashboard and the API behind
a single origin (reverse proxy or ingress); see ADR-0020.

### A local Postgres can shadow the container

If something is already listening on `5432`, Docker's port mapping is shadowed
and `core-service` connects to your local database instead of the container's —
successfully. There is no error. The schema is missing or different, so reads
return empty and writes land somewhere unexpected, which surfaces as an empty
dashboard rather than a failure.

Check `lsof -i :5432` before starting the stack. If something local is bound,
stop it or remap the container port in an untracked `docker-compose.override.yml`:

    services:
      postgres:
        ports:
          - "15432:5432"

and point `SPRING_DATASOURCE_URL` at `15432`. That file is gitignored because
the remap is machine-specific.

## License

Apache-2.0 — see `LICENSE`.
