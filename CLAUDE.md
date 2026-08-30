# Meridian

Real-time derivatives risk & pricing platform. Python quant core → Kafka → Java service → React dashboard.

> Build the deterministic, correct core first. Layer usability on top of it — never the reverse.

## Before you write anything

1. Read `PLAN.md` in the directory you are working in. It defines your scope, your definition of done, and what you are forbidden to touch. If there is no `PLAN.md`, stop and ask for one.
2. Read `docs/domain-model.md`. It is the source of truth for every type in this system.
3. Check `docs/adr/` for a decision covering what you are about to do. If one exists, follow it. If one should exist and doesn't, stop and say so — don't decide by writing code.

## Hard rules

- **`libs/quant-core` performs no I/O.** No network, no disk, no database, no `datetime.now()`. Time and data are arguments. CI enforces this with `import-linter`; a violation is a build failure, not a discussion.
- **Money is decimal.** `Decimal` / `BigDecimal`, scale 8. Greeks, vols, rates, and correlations are `float64`. Never mix them.
- **Time is UTC and explicit.** No naive datetimes. Every message carries `event_time` and `ingest_time`.
- **Generated code is never hand-edited.** Regenerate from `contracts/`.
- **Schemas change by addition.** `BACKWARD` compatibility is enforced by the registry; a breaking change needs an ADR.
- **Monte Carlo is seeded deterministically.** Never call an unseeded RNG.
- **No `Co-Authored-By` trailer and no "Generated with Claude Code" line on any commit or PR.** Ever.

## Conventions

- Commits: Conventional Commits, scope = workstream. `feat(pricer): add SABR volatility surface`
- Branches: `<workstream>/<short-slug>` — `pricer/sabr-surface`
- Every PR names the ADR it follows, or states that no ADR governs it.
- ADRs are immutable. Superseded, never edited.
- Tests come with the change, in the same PR. A PR with no tests needs a sentence explaining why.

## Testing expectations

Correctness here has financial meaning, so the test plan is a design artifact — see `docs/test-strategy.md`.

- **Golden tests** for every pricer, against published analytic values.
- **Property tests** for relationships that must hold regardless of input: put-call parity, delta bounds in `[0,1]` for calls, gamma non-negative for vanillas, monotonicity of price in volatility.
- **Contract tests** at every boundary, driven by `contracts/`.
- A bug fix starts with a failing test that reproduces it.

## When you are stuck or the plan is wrong

Say so, in the PR or in the session. Do not improvise around a bad plan — an improvised deviation costs more to unwind than a paused session costs to restart.
