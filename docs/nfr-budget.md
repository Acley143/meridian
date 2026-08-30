# Non-Functional Requirement Budget

These are the pass/fail criteria for Q4 load testing. They are numbers, not
adjectives. A workstream's `PLAN.md` Definition of Done references this file
directly; a deviation requires an ADR explaining why, not a note in a PR
description.

## Latency

p99 tick-to-rendered-risk ≤ **250 ms**, measured as
`dashboard_render_time − tick.event_time`.

## Throughput

**1,000 ticks/sec** sustained for **30 minutes** with no consumer lag growth
(lag at minute 30 ≤ lag at minute 1, within noise).

## Pricing accuracy

- Vanilla European options: within **1e-6 relative error** of the
  closed-form (Black-Scholes) reference value.
- Monte Carlo pricers: within **3 standard errors** of the analytic value,
  for instruments where an analytic value exists.

## Recovery

Kill any consumer mid-stream. On restart, it rejoins and produces **zero
duplicate rows** and **zero gaps** in its output.

## Availability target

None. This is a student project and pretending otherwise is theatre.
