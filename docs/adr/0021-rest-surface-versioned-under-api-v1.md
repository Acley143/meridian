# ADR-0021: REST surface versioned under /api/v1

## Status
Accepted

## Context
`services/core-service`'s entire REST/SSE surface (ADR-0009) is served at
the root: `/portfolios/{portfolioId}/...`, `/trades`. There is no path
prefix and no version segment. Two problems follow.

`apps/dashboard/vite.config.ts`'s dev proxy (ADR-0020) routes a
hand-maintained list of prefixes, currently just `/portfolios` — the only
root the dashboard calls today. `/trades` already exists in
`contracts/openapi/service-api.yaml` and was unproxied: Vite's SPA fallback
answers an unproxied path with `index.html` and a `200`, so a client calling
an unrouted endpoint gets a plausible response carrying HTML instead of
JSON, with no error raised anywhere. Creation endpoints land in Q2 and will
add more roots, each one a chance to repeat this silently.

Separately, the Avro surface has a schema registry and a `BACKWARD`
compatibility policy (ADR-0002). The REST surface has no equivalent version
boundary. ADR-0009 fixed REST+SSE as the transport but never fixed the root
or a version segment. Today there is exactly one client (`apps/dashboard`)
and we own it; that stops being reliably true once the Q2 creation
endpoints exist.

## Decision
The REST surface is served under `/api/v1`. The version segment is explicit
and part of the path — every path in `contracts/openapi/service-api.yaml`
is written literally with the `/api/v1` prefix (not via a `servers:` base
URL, since the codegen drift detector diffs generated bindings and a
`servers` entry may not reach them), and every controller in
`services/core-service` carries a class-level
`@RequestMapping("/api/v1")`.

`server.servlet.context-path` was considered and rejected (see
Alternatives) in favor of this explicit-prefix approach.

## Rationale
- The dashboard's dev proxy collapses to a single `/api` entry
  (`apps/dashboard/vite.config.ts`) instead of an enumerated per-prefix
  list. A new endpoint root under `/api/v1` is routed automatically. The
  proxy alone only makes `/api/v1` paths safe — nothing stops a future path
  from being added at a different root, where Vite's SPA fallback would
  repeat the original `/trades` bug exactly. `tools/schema-lint/check_api_v1_prefix.py`
  closes that: it fails CI's `Contracts` job if any path in
  `service-api.yaml` isn't under `/api/v1`. That check, not the proxy shape
  alone, is what makes the gap structurally impossible rather than merely
  conventional.
- The REST surface gains a version boundary comparable to the Avro
  compatibility policy in ADR-0002, before there is more than one client to
  break.

## Consequences
- Anything Spring-managed outside `contracts/openapi/service-api.yaml`'s
  surface — actuator, if it is ever added — stays at the root, unversioned
  and unprefixed, by construction rather than by configuration. `core-service`
  does not depend on `spring-boot-starter-actuator` today and exposes no
  `/actuator/health` endpoint (confirmed: no dependency in `pom.xml`, no
  health controller, `GET /actuator/health` 404s against the running
  service) — so `server.servlet.context-path` would not, in fact, break a
  live health probe right now. It is still rejected: a servlet context path
  is a single global setting, so it would apply retroactively to any
  Spring-managed endpoint added later (actuator included) without a
  corresponding decision, where the explicit-prefix approach only ever
  covers what a developer deliberately annotates.
- Every client of the REST surface — `apps/dashboard`'s `fetch`/`EventSource`
  calls, the Java controller tests, the `swagger-request-validator`
  integration tests — now targets `/api/v1/...`. A request to the old
  unprefixed path (e.g. `GET /portfolios/{id}/risk`) returns `404`; the old
  mapping is not kept alongside the new one.
- Future breaking REST changes get a real place to land (`/api/v2`)
  instead of forcing a breaking change onto `/api/v1` or an ad hoc
  workaround.

## Alternatives considered
- **`server.servlet.context-path: /api/v1`.** Rejected: shorter to write,
  but it is a blanket setting that relocates every Spring-managed endpoint,
  not just the ones in `contracts/openapi/service-api.yaml` — including
  actuator, whenever it is added, with no corresponding decision at that
  point. The explicit-prefix approach costs a `@RequestMapping` per
  controller and a literal prefix in the spec, in exchange for only the
  REST surface actually moving.
- **Do nothing; keep enumerating proxy prefixes as new endpoint roots are
  added.** Rejected: this is precisely the maintenance burden that already
  produced a silent bug (`/trades` unproxied, answered by the SPA
  fallback); it doesn't scale past the Q2 creation endpoints.

## Addendum
Extends ADR-0009 (which fixed REST+SSE as the transport but not the path
root) rather than superseding it, and preserves ADR-0012's resume semantics
and ADR-0020's same-origin proxy design unchanged — both now operate on
`/api/v1/...` paths instead of root paths.
