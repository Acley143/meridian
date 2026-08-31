# ADR-0017: Portfolio Greeks are cash Greeks

## Status
Accepted

## Context
Per-instrument Greeks (`quant_core.types.PricingResult`, ADR-0014) are
per-unit `float64` — the mathematically natural form, since they're partial
derivatives of a single instrument's price with respect to a single market
variable. `RiskSnapshot.delta`/`gamma`/`vega`/`theta`/`rho` (ADR-0007) are
portfolio-level, and raw per-unit Greeks do not aggregate meaningfully
across a portfolio's different underlyings: `∂²V₁/∂S₁²` and `∂²V₂/∂S₂²` are
each expressed per unit of a *different* underlying's own spot move, so
they are not in the same units, and summing them produces a number that
renders without error and means nothing. (They *are* additive within one
underlying, because differentiation is linear — this ADR only concerns
the cross-underlying portfolio aggregate `RiskSnapshot` carries.)

Cash Greeks — the dollarized (or euro-ized, etc.) change in portfolio value
per a standard move in each risk factor — are denominated in the
portfolio's base currency and are therefore genuinely summable across
underlyings, which is why risk desks report them rather than raw Greeks at
the portfolio level.

## Decision
Per-instrument Greeks stay per-unit `float64` (ADR-0014, ADR-0004) — this
ADR does not touch `quant_core`. `RiskSnapshot`'s portfolio-level Greeks
are **cash Greeks**: currency amounts, `Decimal(38, 8)`, on a **1% basis**
for delta and gamma. Aggregation, per position, summed across the
portfolio:

- `cash_delta = Δ × S × 0.01 × quantity × contract_size` — currency change
  per 1% relative move in spot.
- `cash_gamma = Γ × S² × 0.0001 × quantity × contract_size` — change in
  `cash_delta` per 1% move in spot.
- `cash_vega = ν × quantity × contract_size` — vega is already currency
  per 1.00 absolute vol move under the existing ADR-0004/`docs/conventions.md`
  convention, so no basis-point rescaling is needed here, only the
  position multiplication.
- `cash_theta = Θ × quantity × contract_size` — currency per calendar
  year, same reasoning as vega.
- `cash_rho = ρ × quantity × contract_size` — currency per 1.00 absolute
  rate move, same reasoning.

`contract_size` is applied here, exactly once, per ADR-0014 — this is the
multiplication that ADR's own test requirement (a non-unit `contract_size`
must produce a distinguishable portfolio value) refers to, now extended
to every cash Greek, not just `price`.

## Consequences
- `contracts/avro/risk-snapshot.avsc` changes `delta`/`gamma`/`vega`/
  `theta`/`rho` from `double` to `decimal(38,8)`, renamed `cash_delta`,
  `cash_gamma`, `cash_vega`, `cash_theta`, `cash_rho` so the units are
  unmistakable at the call site — a field literally named `delta` next to
  a per-unit `PricingResult.delta` elsewhere in the codebase invites
  exactly the unit confusion this ADR exists to prevent.
  `docs/domain-model.md` was updated first, then the schema, then bindings
  regenerated (`make gen`) — same order as ADR-0002 requires generally.
- The `float64 -> Decimal` conversion for each cash Greek happens through
  `quant_core.numeric.to_money` (ADR-0013) — one rounding policy
  (`ROUND_HALF_EVEN`), no second implementation in `services/pricer`. The
  1%/1.00 basis multiplications themselves happen in `float64` (matching
  every input they operate on) before that one conversion at the boundary,
  not before it.
- The 1% basis for `cash_delta`/`cash_gamma` is recorded in
  `docs/conventions.md`, next to the existing theta and vega conventions —
  a reader checking one Greek's convention should find all of them in one
  place.
- Currency remains the open question from the contracts session: cash
  Greeks are summable across underlyings, not across currencies.
  Aggregating a EUR-denominated position into a USD portfolio total
  without conversion is silently wrong, and nothing introduced by this ADR
  changes that. Ownership stays at the root `PLAN.md` for Q2 — this ADR
  does not attempt to solve it.
- This resolves the open question `services/pricer/PLAN.md` raised in the
  prior contracts session (how per-position Greeks aggregate into
  `RiskSnapshot`'s portfolio-level fields). Closed there with a pointer to
  this ADR, plus a new deliverable: a test asserting that summing raw
  per-unit gammas across two different underlyings is *not* what the
  aggregation code does — a regression test for the exact mistake this ADR
  exists to prevent, not just a description of the correct formula.

## Alternatives considered
- **Report raw per-unit Greeks at the portfolio level, aggregated as a
  `map<underlying_id, float64>` per Greek.** Rejected: pushes the
  "these aren't summable across underlyings" problem onto every consumer
  of `RiskSnapshot` instead of solving it once, and reintroduces the same
  untyped-map wire-schema problems ADR-0015's session already moved away
  from for this record (no per-field doc/default, no BACKWARD-check
  coverage of individual keys).
- **Keep `RiskSnapshot`'s Greeks as `float64` cash amounts instead of
  `Decimal`.** Rejected: these are currency amounts once converted to
  cash terms (ADR-0004's whole basis for the decimal/float split), and a
  cash Greek feeding a portfolio total is exactly the kind of value ADR-0004
  singles out as needing exact decimal arithmetic, not float64
  approximation compounding across many summed positions.
- **Basis-point (1bp) instead of 1% for delta/gamma.** Rejected: 1% is the
  conventional basis for equity/equity-option cash delta and gamma on most
  desks (1bp is far more common for rates products, which Meridian doesn't
  price in Q1); revisit if/when a rates instrument is added.
