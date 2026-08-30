# dashboard

React + TypeScript app consuming `core-service`'s REST API and SSE risk
stream (ADR-0009).

- Consume the risk stream with the browser's native `EventSource` — don't
  reach for a WebSocket or polling library; reconnection is meant to come
  for free here (ADR-0009).
- Decimal fields (`portfolio_value`, `quantity`, `average_cost`, etc.) arrive
  over the wire as strings (see `contracts/openapi/service-api.yaml`), not
  JSON numbers — never `parseFloat` them for display of an exact cash amount;
  use a decimal-safe formatting library.
- Types consumed from the API should come from codegen against
  `contracts/openapi/service-api.yaml`, not hand-written interfaces that can
  drift from the contract.
- Local dev/test: `npm run dev` to run against the local stack
  (`docker-compose.yml` + `core-service`); `npm test` (Vitest) for unit
  tests; `npx tsc --noEmit` for the type check CI also runs.
- The one mistake most likely here: computing `dashboard_render_time` (the
  numerator of the latency budget in `docs/nfr-budget.md`) at the moment data
  is fetched instead of the moment it's actually painted to the screen —
  measure at render, not at fetch.
