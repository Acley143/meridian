# Meridian — Program Plan

Four quarters, five engineers. This is the program-level plan; each
workstream has its own `PLAN.md` with concrete deliverables, boundaries, and
a session log — this file links to them and tracks which quarter is current.

## Q1 — Black-Scholes pricer, simulated Kafka feed, service/schema skeleton (COMPLETE)

Establish the skeleton end to end: contracts, a pure Black-Scholes pricer, a
simulated tick feed, a core service that can hold portfolio/trade state and
expose it, and a dashboard that can render one risk number live. Depth comes
later; Q1 proves the pipe is connected.

- [contracts](contracts/PLAN.md)
- [libs/quant-core](libs/quant-core/PLAN.md)
- [libs/quant-io](libs/quant-io/PLAN.md)
- [services/ingest](services/ingest/PLAN.md)
- [services/pricer](services/pricer/PLAN.md)
- [services/core-service](services/core-service/PLAN.md)
- [apps/dashboard](apps/dashboard/PLAN.md)
- [infra](infra/PLAN.md)

Verified end to end against the real local stack (`docker compose up` +
`services/ingest` + `services/pricer` + `services/core-service` +
`apps/dashboard`), 2026-08-31: a real tick landed in Kafka, was priced by
`services/pricer`, reached `services/core-service`, and streamed out over
SSE (`curl -N .../risk/stream`) as a live-updating `RiskSnapshot` within
the same second it was produced. The pipe is connected.

## Q2 — American options, portfolio VaR, audit log (CURRENT)

Extend the pricer to American-style exercise, add portfolio-level VaR
aggregation (single-portfolio, not yet correlated across portfolios), and
land the hash-chained audit log (ADR-0008) in `core-service`.

## Q3 — Monte Carlo, correlated portfolio risk, load-test prep

Add deterministic Monte Carlo pricing (ADR-0006) for instruments without a
closed form, extend VaR to correlated cross-portfolio risk (the reason
`portfolio.state` exists per ADR-0003), and build the load-test harness ahead
of Q4.

## Q4 — Hardening, load testing, NFR verification

Run the load test against every line in `docs/nfr-budget.md`, fix what fails,
and write up the results. No new features unless a budget line requires one
to pass.

## Open questions

- **Cross-currency portfolio aggregation (Q2 blocker).** Decided in
  `docs/adr/0028-cross-currency-aggregation.md` and now implemented:
  `portfolio.state` and `RiskSnapshot` both carry `base_currency`; the pricer
  refuses a portfolio whose currency is unknown (`UNKNOWN_BASE_CURRENCY`,
  ADR-0018); every position not in the portfolio's base currency is
  converted per position, before the sum, with the direct `FX_RATE` curve for
  `<position currency><base currency>` (never inverted), decimal throughout
  via `quant_core.numeric.convert_money`; `FX_RATE` is required for every
  position type, and a missing pair is `MISSING_CURVE` listing
  `FX_RATE:<pair>`; a tick whose currency disagrees with its instrument's
  reference currency is rejected before it is cached; and the shared curve
  validator rejects a non-positive `FX_RATE` at both the producer and the
  consumer. **A mixed-currency portfolio is now converted**, so the earlier
  warning that portfolio VaR must not start before conversion no longer
  applies. Existing `risk_snapshots` rows and old `portfolio.state` messages
  still carry the empty "unknown" `base_currency` until rewritten. Still
  outstanding: VaR's currency treatment (`var_95` is a float64 hard-coded to
  0.0, and how it converts is decided when VaR is built), and FX curves for
  `services/ingest`'s multi-currency scenario (`throughput-1000` has EUR and
  GBP instruments and declares no curves, so it cannot be priced yet).
  Owner: TBD (spans `services/pricer` and `services/ingest`), by-when: before
  Q2 VaR work starts.
- **Avro/OpenAPI field parity (Q2).** `oldest_input_event_time` existed in
  `contracts/avro/risk-snapshot.avsc` since Session 04a but was missing from
  `contracts/openapi/service-api.yaml`'s `RiskSnapshot` until the dashboard
  live-risk session noticed it was needed for staleness rendering and added
  it — no CI check would have caught the gap on its own, since `gen-check`
  only diffs generated code against itself, not the two source contracts
  against each other. Needs a check that every `docs/domain-model.md` field
  appears in both the Avro and OpenAPI representations of a type, or a
  stated reason a given field shouldn't (see `contracts/README.md`). Owner:
  TBD, by-when: before Q2 contract work starts.
- **`core-service` has no CORS configuration (Q1 end-to-end verification).**
  Discovered while running the full local stack: `apps/dashboard`'s dev
  server (`localhost:5173`) talking to `core-service` (`localhost:8080`)
  is rejected by the browser (`Invalid CORS request` on preflight) —
  `core-service` never sends an `Access-Control-Allow-Origin` header. The
  rest of the pipeline works and was verified directly against the SSE
  stream instead of through a browser. No ADR covers what origins should
  be allowed (dev-only permissive vs. an explicit allowlist that also
  needs to work in whatever Q4 deployment target emerges). Owner: TBD
  (`services/core-service`), by-when: before the dashboard can be
  demoed live in an actual browser against a real `core-service`.
- **A local Postgres can silently shadow the container (Q1 end-to-end
  verification).** If something is already listening on `5432`, Docker's
  port mapping is shadowed and `core-service` connects to the local
  database instead of the container's — successfully, with no error. The
  schema is missing or different, so reads return empty and writes land
  somewhere unexpected, surfacing as an empty dashboard rather than a
  failure. Documented in `README.md` (check `lsof -i :5432`; remap the
  container port via an untracked `docker-compose.override.yml` if
  something local is bound). No code fix yet — nothing in `core-service`
  or `infra/` detects or warns about this today. Owner: TBD (`infra`),
  by-when: no hard deadline, but worth revisiting before onboarding new
  engineers who are more likely to have a local Postgres already running.
- **No portfolio/instrument creation endpoint (Q1 end-to-end verification).**
  `services/core-service` can hold and serve portfolio/trade/position state,
  but nothing in Q1 exposes `POST /portfolios` or an instrument-creation
  endpoint — `InstrumentService.createInstrument` and the portfolios table
  exist only as internal seams (see `services/core-service/PLAN.md`
  session log). Verifying Q1 end to end required inserting the seed
  `portfolios`/`instruments` rows directly via SQL, which is fine for this
  one-time local verification but isn't a real onboarding path for a new
  portfolio. Owner: TBD (`services/core-service`), by-when: before Q2, if
  Q2's VaR/audit-log work assumes portfolios can be created without a DBA.
- **`idempotency_keys` retention sweep not built (ADR-0023, Session P).**
  `POST /trades`'s idempotency store (`services/core-service`) records
  `created_at` and indexes it for a 24-hour retention window, but no sweep
  job exists yet — rows accumulate indefinitely. ADR-0023 covers the
  reasoning; this is the tracked follow-up it points to, not a decision
  still to make. Owner: TBD (`services/core-service`), by-when:
  unscheduled.
- **`services/pricer/tests/test_tombstone.py::test_tombstone_mid_stream_stops_snapshots`
  failed nondeterministically (found 2026-09-11, Session P).** Failed on
  master run `33582972332` with `AssertionError: a tombstoned portfolio
  must not produce a snapshot`, and passed on the immediately preceding
  branch run `33580881002` with identical code. Not yet established whether
  the nondeterminism is in the test itself or in the pricer's tombstone
  handling — in a system built on deterministic replay, a real ordering
  race is a live possibility and this must not be assumed to be a
  test-only issue. Not investigated this session (out of scope). Owner:
  TBD (`services/pricer`), by-when: before relying on tombstone handling
  for Q2 VaR work.

## Team & ownership

See `docs/rotation.md` for who owns which surface, per quarter.
