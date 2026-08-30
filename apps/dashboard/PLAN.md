# dashboard — Plan

**Owner:** Eng-E  ·  **Quarter:** Q1  ·  **Status:** not started

## Mission
The only surface a human looks at. Renders live portfolio risk from
`core-service`'s REST + SSE API. Without this, the system computes correct
risk numbers that nobody can see, which for a demo-driven student project is
functionally the same as not computing them.

## In scope this quarter
- [ ] Portfolio list/detail view via `GET /portfolios/{id}` and
      `GET /portfolios/{id}/positions`.
- [ ] Live risk panel subscribed to `GET /portfolios/{id}/risk-stream` via
      `EventSource`, rendering `portfolio_value` at minimum (var_95/greeks
      display if the pricer has meaningful values by Q1's end, per
      `services/pricer/PLAN.md`).
- [ ] `dashboard_render_time` instrumentation at the actual render point, for
      the latency budget in `docs/nfr-budget.md`.

## Explicitly out of scope
- Any chart/visualization beyond a single live-updating number/table — data
  viz polish is not a Q1 deliverable.
- Auth/login — not in scope for any quarter unless added to a future ADR.
- Historical risk snapshot browsing (`risk-snapshots/latest` or beyond) —
  Q1 is live-only.

## Boundaries
- **Owns:** `apps/dashboard/**`.
- **Must not touch:** `contracts/openapi/service-api.yaml` without
  coordinating with Eng-A; `services/core-service`.
- **Depends on:** `contracts/openapi/service-api.yaml` (ADR-0009).

## Interfaces
Consumes `contracts/openapi/service-api.yaml` exclusively — REST calls plus
one `EventSource` subscription. No other interface.

## Definition of done
- [ ] Deliverables above complete
- [ ] Tests per `docs/test-strategy.md` (contract tests against the OpenAPI
      spec; component tests via Vitest)
- [ ] Contract tests pass against `contracts/`
- [ ] Docs updated
- [ ] NFR targets in `docs/nfr-budget.md` met or an ADR explains the
      deviation (latency numerator `dashboard_render_time` instrumented and
      reported even if the full p99 budget isn't met until Q4)

## Open questions
- Component/styling library, if any — Owner: Eng-E, by-when: before first
  component lands; note the choice in `apps/dashboard/CLAUDE.md` once
  decided.

## Session log
(none yet)
