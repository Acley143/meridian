# Test Strategy

Correctness in a risk platform has financial meaning: a wrong Greek or a
silently-dropped tick isn't a cosmetic bug, it's a wrong risk number someone
could act on. The test plan is therefore a design artifact, not an
afterthought bolted on after implementation — see the root `CLAUDE.md` for
the summary version of this; this document is the detail.

## Layers

### Golden tests
Every pricer in `libs/quant-core` is tested against a published, independently-derived
analytic reference value (e.g. Black-Scholes closed-form for vanilla European
options). Golden tests are what makes ADR-0006 (deterministic Monte Carlo)
worth having — an MC pricer's fixed seed means it can have a golden expected
output too, not just an analytic one.

Pass criterion: within the accuracy budget in `docs/nfr-budget.md`
(1e-6 relative error for closed-form, 3 standard errors for MC).

### Property tests
Relationships that must hold regardless of the specific input, generated
across a wide input range (Hypothesis in Python, jqwik in Java where
applicable):
- Put-call parity.
- Delta bounds: `[0, 1]` for calls, `[-1, 0]` for puts.
- Gamma non-negative for vanilla options.
- Price monotonic in volatility (higher vol never decreases a vanilla
  option's price).

A property test failure means the *model* is wrong, not just an example —
treat it with more urgency than a golden test failure on an edge case.

### Contract tests
At every boundary defined in `contracts/`: producing/consuming each Avro
topic, and both sides of the OpenAPI REST/SSE surface. Contract tests run
against the generated bindings (never hand-rolled parallel parsing) and
against a real local schema registry / Postgres via `docker-compose.yml`,
not a mock of either.

### Integration / recovery tests
Exercise the "kill a consumer mid-stream" recovery requirement in
`docs/nfr-budget.md` directly: start a consumer, feed it messages, kill it,
restart it, assert zero duplicate rows and zero gaps in its output.

### Load tests
Q4-only. Drive 1,000 ticks/sec for 30 minutes against the full local stack
and assert the throughput and latency budgets in `docs/nfr-budget.md`
directly, plus no consumer lag growth.

## Rules

- A bug fix starts with a failing test that reproduces it, added in the same
  PR as the fix.
- Tests come with the change, in the same PR. A PR with no tests needs a
  sentence explaining why (e.g. "docs-only change").
- A workstream's `PLAN.md` Definition of Done references this document's
  relevant layers explicitly, not just "tests pass."
