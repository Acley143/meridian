# ADR-0010: `libs/quant-core` is pure

## Status
Accepted

## Context
Pricing logic (closed-form formulas, Monte Carlo engines, Greeks) is the part
of the system where correctness is most valuable and most testable, and that
value is highest when the logic is a pure function of its inputs — no
network, no disk, no database, no wall clock — because pure functions are
trivially golden-testable and property-testable (see `docs/test-strategy.md`
and the root `CLAUDE.md`).

## Decision
`libs/quant-core` may not import anything that performs I/O: no Kafka client,
no HTTP client, no filesystem access, no database driver, no system clock
(`datetime.now()`/`time.time()` and equivalents are forbidden — time is
always an explicit argument). This is enforced in CI by `import-linter`
against the contract in `libs/quant-core/.importlinter`, not by code review.

## Consequences
- Every pricer function's signature must take all its inputs explicitly,
  including the valuation time — no reaching out for "now."
- Golden tests and property tests for pricers need no mocking of I/O,
  because there is none to mock.
- I/O concerns (reading market data, publishing results, persistence) live in
  `libs/quant-io` and the services that depend on `quant-core`, which compose
  the pure pricing functions with the outside world.
- A PR that would violate this fails CI automatically; there is no path to
  merge an I/O-performing change to `quant-core` by review sign-off alone.

## Alternatives considered
- **Enforce purity by code review convention only.** Rejected: convention
  drifts under deadline pressure; the whole point is that this is a build
  failure, not a discussion.
- **Allow I/O in quant-core behind an injected interface/dependency
  injection.** Rejected as unnecessary complexity for this project's scale:
  a flat "no I/O imports at all" rule is simpler to state, enforce, and
  verify than a partial-purity discipline with injected ports.
