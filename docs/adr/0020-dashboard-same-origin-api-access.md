# ADR-0020: Dashboard same-origin API access

## Status
Accepted

## Context
`apps/dashboard` (`:5173` in dev) calls `services/core-service` (`:8080`) for
both REST (ADR-0009) and the SSE risk stream. `core-service` carries no CORS
configuration, so a browser request from `:5173` to `:8080` is rejected on
preflight — confirmed while verifying Q1 end to end (see `PLAN.md` open
questions and `README.md`'s "Known local-only gap" note). The rest of the
pipeline was verified directly against the stream (`curl -N`), which is
unaffected since it isn't a browser client.

The two options were: add a CORS policy to `core-service`, or make the
dashboard's requests same-origin so no cross-origin request — and therefore
no CORS decision — exists at all.

## Decision
The dashboard issues only same-origin requests to the API: every `fetch`
call and `EventSource` subscription uses a relative path (`/portfolios/...`),
never an absolute `http://localhost:8080/...` URL. In development this is
achieved with Vite's dev proxy (`apps/dashboard/vite.config.ts`), which
forwards `/portfolios` to `http://localhost:8080` with `changeOrigin: true`.
`core-service` carries no CORS configuration, and none is added by this ADR.

## Consequences
- Any production deployment must serve the dashboard and the API behind a
  single origin — a reverse proxy or ingress in front of both. This is a
  constraint on Q3's deployment topology, recorded here so it is inherited
  deliberately rather than discovered.
- If a genuine cross-origin consumer of `core-service`'s API ever appears
  (a client that cannot be placed behind the same origin), this ADR is
  superseded and CORS becomes a real decision at that point, made on its own
  merits — not one made by accident to unblock local dev.
- The dev proxy must be verified, not assumed: SSE responses can be buffered
  by a proxy (arriving all at once on disconnect instead of incrementally),
  and `Last-Event-ID` (ADR-0012) is a request header that a naive proxy can
  drop, silently degrading resume to a full replay or to nothing.
- Enforcement: the invariant (no absolute core-service URL under
  `apps/dashboard/src`) is checked by `scripts/check_dashboard_same_origin.py`,
  wired into `make lint` and the CI `typescript` job — it is not a convention
  left to code review.

## Alternatives considered
- **Permissive CORS on `core-service` (`Access-Control-Allow-Origin: *`) for
  dev only.** Rejected: a dev-only permissive policy is exactly the kind of
  thing that leaks into production by accident, and it decides production
  origin topology (Q3's actual decision) by default rather than deliberately.
- **An explicit CORS allowlist on `core-service`.** Rejected for now: needs a
  real answer for what origins are allowed in each deployment target, which
  is not yet decided (see `PLAN.md`'s CORS open question) — same-origin sidesteps
  the question entirely rather than answering it prematurely.

## Addendum
See ADR-0009 (REST + SSE between service and dashboard) and ADR-0012 (SSE
resume semantics), both of which this ADR's proxy must preserve unchanged
end to end.

## Editorial amendments
- 2026-08-31 (dashboard): The enforcement script initially landed at
  `scripts/check_dashboard_same_origin.py`. `scripts/` isn't this repo's
  convention for a check like this — `tools/schema-lint/` is, per the
  existing `check_no_attribution.py`, `check_adr_numbering.py`, etc. Moved
  to `tools/check-dashboard-origin/check_dashboard_same_origin.py`
  (`Makefile` and the CI `typescript` job updated to match); non-substantive
  to the Decision or Enforcement invariant itself, only to where the
  checking script lives.
- 2026-08-31 (dashboard): The enforcement script's original bare-port
  pattern (`(?<![\w.]):8080`) never fired for the case it existed to catch.
  Its negative lookbehind excluded any `:8080` preceded by a word character
  -- but a real hostname almost always ends in one (`localhost:8080`,
  `core-service:8080`), so a literal `"localhost:8080"` with no `http://`
  prefix passed the check silently. Only the `http://localhost:8080` and
  `127.0.0.1:8080` alternatives had ever been exercised against a failing
  fixture; the third had not. Fixed to a single `:8080\b` pattern with no
  leading lookbehind (trailing `\b` still keeps it from matching inside a
  longer digit run, e.g. `:80800`). Substantive to the Enforcement
  guarantee -- the invariant was weaker than stated until this fix.
