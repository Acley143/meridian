# dashboard — Plan

**Owner:** Eng-E  ·  **Quarter:** Q1  ·  **Status:** live risk panel built (latest snapshot with price, cash Greeks, VaR, reporting currency and pricer version; staleness; connection states; fetch errors); portfolio list/detail view and `dashboard_render_time` instrumentation not done

## Mission
The only surface a human looks at. Renders live portfolio risk from
`core-service`'s REST + SSE API. Without this, the system computes correct
risk numbers that nobody can see, which for a demo-driven student project is
functionally the same as not computing them.

## In scope this quarter
- [ ] Portfolio list/detail view via `GET /portfolios/{id}` and
      `GET /portfolios/{id}/positions`.
- [x] Live risk panel subscribed to `GET /portfolios/{id}/risk-stream` via
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
  decided. **Still unresolved**, though components have since landed: they
  rely on semantic HTML (`<table>`, `<th scope="row">`, `role="status"`)
  and one class name, `stale` on `RiskSnapshotTable`'s age row, which no
  stylesheet defines -- there is no CSS anywhere in `apps/dashboard`.
- **Known gap, not fixed (recorded by the VaR display session).** The
  `snapshots` array in `src/api/riskStream.ts` grows without bound, and
  nothing dedupes a REST-fetched snapshot against an identical SSE message,
  so both are appended. Owner: Eng-E, by-when: before the panel is left
  open against a long-running feed.
- **Known gap, not fixed (recorded by the VaR display session).**
  `dashboard_render_time` is still not instrumented anywhere in `src`,
  although this plan's deliverables and definition of done and
  `docs/nfr-budget.md` all call for it. Owner: Eng-E, by-when: before Q4
  load testing, which needs it as the latency numerator.

## Session log
- 2026-10-06 (VaR display session, Eng-E, Q2): `RiskSnapshotTable` now
  shows `var_95` in a "VaR (1-day, 95%)" row after the cash Greeks, through
  a new `src/format/risk.ts` `formatRisk`: exactly 2 decimals via
  `Intl.NumberFormat` (no exponent notation even at 1e21, where `toFixed`
  switches to it), and "unavailable" for a non-finite value, so the view
  never throws or shows NaN. `var_95` is a float64 statistic (ADR-0004), so
  `formatDecimal`, which takes a wire decimal string and implies scale-8
  precision, is deliberately not used. A single "Figures in <currency>"
  line above the table, from `base_currency`, gives price, the cash Greeks
  and VaR the unit none of them showed before; the empty-string sentinel
  renders "Figures in an unknown currency" with no default (ADR-0028
  Decision 2). A final "Pricer version" row lets a reader tell a 0.1.0
  `var_95` of 0.0 ("not computed") from a 0.2.0 one (a zero-volatility book,
  ADR-0029) without the view branching on the version. Existing rows, the
  stale caption and the stale class are unchanged. The live risk panel
  checkbox above is ticked: it was built in earlier sessions that left no
  log here, rendering `price` (the `portfolio_value` named above, renamed in
  `docs/domain-model.md`) from `/api/v1/portfolios/{id}/risk/stream`
  (ADR-0021). Tests: `src/format/risk.test.ts`, and new cases in
  `src/RiskSnapshotTable.test.tsx` (the VaR row, 0.0 rendering "0.00", the
  currency line for USD and for the empty string, the pricer version);
  every existing test is unchanged. Not changed, and still wrong:
  `apps/dashboard/CLAUDE.md` documents `npx tsc --noEmit`, which checks
  nothing against this solution-style tsconfig; CI runs `npx tsc -b
  --noEmit`.
