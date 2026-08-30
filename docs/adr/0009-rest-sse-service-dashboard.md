# ADR-0009: REST + Server-Sent Events between service and dashboard

## Status
Accepted

## Context
The React dashboard needs to (a) issue request/response calls against the
core service (fetch a portfolio, list positions) and (b) receive a live
stream of risk updates as they're produced. The data flow for the live
stream is one-directional: service → dashboard.

## Decision
The core service exposes a REST API (`contracts/openapi/service-api.yaml`)
for request/response operations, and a Server-Sent Events (SSE) endpoint for
streaming risk updates to the dashboard. No gRPC, no WebSockets.

## Consequences
- Streaming risk updates reuses plain HTTP; the browser's native
  `EventSource` reconnects automatically on connection drop, so the
  dashboard doesn't need custom reconnect/backoff logic.
- Because the stream is one-directional, SSE's lack of client-to-server
  messages on the same connection is not a limitation here; bidirectional
  needs (if any arise) go through the REST API instead.
- No gRPC-Web proxy, no WebSocket upgrade handling, no separate binary
  protocol tooling for the TypeScript side to integrate.

## Alternatives considered
- **gRPC (with gRPC-Web for the browser).** Rejected: gRPC-Web requires a
  translating proxy in front of the service for no benefit at this scale,
  and the streaming need is one-directional, which SSE already covers.
- **WebSockets.** Rejected: gives bidirectional messaging the dashboard
  doesn't need, at the cost of manual reconnect/backoff logic that SSE
  provides for free via `EventSource`.

## Addendum
See ADR-0012 for the SSE stream's resume/replay semantics on reconnect.
