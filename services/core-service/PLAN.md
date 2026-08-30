# core-service — Plan

**Owner:** Eng-D  ·  **Quarter:** Q1  ·  **Status:** not started

## Mission
Owns portfolio, position, and trade state; is the sole producer of
`portfolio.state` (ADR-0003); exposes REST + SSE to the dashboard (ADR-0009).
Without this, there's no durable record of what any portfolio holds and
nothing for the dashboard to talk to.

## In scope this quarter
- [ ] Portfolio/Position/Trade persistence (Postgres, per
      `docker-compose.yml`) matching `docs/domain-model.md` field-for-field.
- [ ] Trade booking endpoint that updates positions and produces
      `portfolio.state` (ADR-0003).
- [ ] REST endpoints from `contracts/openapi/service-api.yaml`:
      `GET /portfolios/{id}`, `GET /portfolios/{id}/positions`.
- [ ] SSE endpoint `GET /portfolios/{id}/risk-stream`, consuming
      `risk.snapshots` and forwarding to connected clients.

## Explicitly out of scope
- The hash-chained audit log (ADR-0008) — Q2.
- `GET /portfolios/{id}/risk-snapshots/latest` — nice to have, not required
  for Q1's live-stream demo path; add if time allows, not required for DoD.
- Any pricing logic — this service never computes a price or a Greek.
- Calling the pricer synchronously for anything — forbidden by ADR-0003.

## Boundaries
- **Owns:** `services/core-service/**`.
- **Must not touch:** `contracts/` without coordinating with Eng-A;
  `libs/quant-core`.
- **Depends on:** `contracts/avro/portfolio-state.avsc` (ADR-0002, ADR-0003),
  `contracts/openapi/service-api.yaml` (ADR-0009), ADR-0004, ADR-0005.

## Interfaces
REST + SSE per `contracts/openapi/service-api.yaml`. Produces
`portfolio.state`, schema `contracts/avro/portfolio-state.avsc`. Consumes
`risk.snapshots` (to forward over SSE) but does not produce to it.

## Definition of done
- [ ] Deliverables above complete
- [ ] Tests per `docs/test-strategy.md` (contract tests against both the
      Avro topic and the OpenAPI spec)
- [ ] Contract tests pass against `contracts/`
- [ ] Docs updated
- [ ] NFR targets in `docs/nfr-budget.md` met or an ADR explains the
      deviation

## Open questions
- Trade booking: synchronous REST endpoint vs. its own inbound Kafka topic?
  Q1 assumes REST for simplicity; revisit if a trade-source integration
  needs otherwise. Owner: Eng-D, by-when: before Q2 planning.

## Session log
(none yet)
