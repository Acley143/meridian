# ADR-0006: Deterministic Monte Carlo

## Status
Accepted

## Context
Monte Carlo pricers are stochastic by nature, which makes them hard to test
(a golden test needs a fixed expected value) and hard to reproduce in
production (a re-run of the same inputs should not silently produce a
different price).

## Decision
The RNG seed for any Monte Carlo pricer is deterministically derived as
`seed = blake2b(instrument_id ‖ as_of ‖ pricer_version)`. No Monte Carlo
pricer may draw from an unseeded or system-entropy RNG.

## Consequences
- Given the same `(instrument_id, as_of, pricer_version)`, a Monte Carlo
  pricer always produces the same price, so it can have golden tests exactly
  like a closed-form pricer.
- A production run is reproducible after the fact for audit purposes — see
  `ADR-0008` — because the seed can be recomputed from the risk snapshot's
  identity fields (`ADR-0007`).
- Two different instruments (or the same instrument re-priced under a new
  `pricer_version`) get independent, uncorrelated seeds, avoiding accidental
  path correlation across a portfolio simulation.

## Alternatives considered
- **Seed from wall-clock or system entropy.** Rejected: makes every MC price
  irreproducible and every MC pricer untestable with a golden test.
- **Fixed global seed for all instruments.** Rejected: would correlate the
  simulated paths of unrelated instruments, biasing any portfolio-level
  aggregation of MC-priced positions.
