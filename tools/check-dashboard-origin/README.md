# check-dashboard-origin

Verifies `apps/dashboard/src` contains no absolute URL pointing at
`core-service`'s host/port — the dashboard must issue only same-origin
requests (ADR-0020), proxied in dev by `apps/dashboard/vite.config.ts`.
Invoked via `make check-dashboard-same-origin` and in CI
(`.github/workflows/ci.yml`, `typescript` job).
