# ADR-0003: Portfolio state as a log-compacted Kafka topic

## Status
Accepted

## Context
The Python pricer needs the current state of every portfolio (positions,
trades applied) to compute portfolio-level risk (e.g. correlated VaR). The
Java core service owns portfolio state changes. A naive design would have the
pricer call back into the service synchronously for each pricing run, putting
a service call in the hot path and creating a request cycle between the two
processes.

## Decision
Portfolio state travels as a log-compacted Kafka topic, `portfolio.state`,
keyed by `portfolio_id`. The Java core service is the sole producer. The
Python pricer consumes the topic and materializes it into a local view
(e.g. an in-memory or embedded-store table keyed by `portfolio_id`). The
pricer never calls back into the core service.

## Consequences
- The hot path (tick in → risk snapshot out) has no synchronous cross-service
  call; the pricer's only inputs are the tick stream and its local
  materialized view.
- The pricer's view of portfolio state is eventually consistent with the
  service's; this is acceptable because portfolio composition changes far
  less frequently than ticks arrive.
- Log compaction means the topic is bounded by portfolio count, not by time —
  a new pricer instance can rebuild its view by replaying the topic from the
  start.

## Alternatives considered
- **Synchronous REST callback from pricer to service on every pricing run.**
  Rejected: introduces a cycle in the hot path and couples pricer latency to
  service availability, directly working against the latency budget in
  `docs/nfr-budget.md`.
- **Shared database table read by both.** Rejected: couples the two services
  to a shared schema and a shared datastore's availability, and doesn't fit
  the streaming architecture used everywhere else.
