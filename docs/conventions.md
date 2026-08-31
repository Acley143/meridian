# Conventions

Sign, unit, and scale conventions for the numbers `libs/quant-core` returns,
and for the portfolio-level cash Greeks `services/pricer` derives from them
(ADR-0017). These exist because getting one of them wrong is not a crash —
it is a silent hundred-fold error on a dashboard that looks plausible
enough to act on. Every docstring that returns one of these numbers must
reference this file; do not let the convention be inferred from the
formula.

## Greeks

- **Delta** — dPrice/dSpot, dimensionless. Per 1.00 absolute change in spot,
  in the instrument's quote currency per unit of underlying.
- **Gamma** — dDelta/dSpot. Per 1.00 absolute change in spot.
- **Vega** — dPrice/dVolatility, **per 1.00 absolute change in volatility,
  not per 1%**. A vega of 12.5 means the price moves by 12.5 for a
  volatility move from 0.20 to 1.20 (i.e. divide by 100 for a "price move
  per vol point" figure — quant-core does not do this for you).
- **Theta** — dPrice/dTime, **per calendar year, not per day**. Anyone
  wanting a per-day figure divides by 365 at the display layer; quant-core
  never does this conversion internally.
- **Rho** — dPrice/dRate, **per 1.00 absolute change in the risk-free rate**
  (e.g. from 0.02 to 1.02), not per 1% or per basis point.

## Portfolio-level (cash) Greeks

The Greeks above are per-unit, produced by `libs/quant-core`
(`quant_core.types.PricingResult`) and additive within one underlying but
**not** across different underlyings — `∂²V₁/∂S₁²` and `∂²V₂/∂S₂²` are per
a different underlying's own spot move each, so summing raw per-unit
Greeks across a portfolio's positions produces a number that renders
without error and means nothing (ADR-0017).

`RiskSnapshot`'s portfolio-level fields (`cash_delta`, `cash_gamma`,
`cash_vega`, `cash_theta`, `cash_rho`, produced by `services/pricer`, not
`quant-core`) are **cash Greeks** instead: currency amounts, genuinely
summable across underlyings because they're all denominated in the
portfolio's base currency. Per position, summed across the portfolio:

- **cash_delta** = `Δ × S × 0.01 × quantity × contract_size` — currency
  change per **1% relative move in spot** (not 1.00 absolute, unlike the
  per-unit delta above — cash delta uses a 1% basis).
- **cash_gamma** = `Γ × S² × 0.0001 × quantity × contract_size` — change
  in `cash_delta` per 1% move in spot (also a 1% basis).
- **cash_vega** = `ν × quantity × contract_size` — already currency per
  1.00 absolute vol move under the per-unit vega convention above, so no
  basis change here, only the position multiplication.
- **cash_theta** = `Θ × quantity × contract_size` — currency per calendar
  year, same reasoning as cash vega.
- **cash_rho** = `ρ × quantity × contract_size` — currency per 1.00
  absolute rate move, same reasoning.

`contract_size` is applied exactly once, here, per ADR-0014 — `quant-core`
never sees it. The `float64 -> Decimal` conversion for each cash Greek
goes through `quant_core.numeric.to_money` (ADR-0013), the one boundary
conversion point; the 1%/1.00 multiplications happen in `float64` before
that conversion, not after.

## Rates and volatilities

Continuously compounded, annualised, expressed as **decimals** — `0.05` for
5%, never `5`. This applies to both the risk-free rate and volatility
everywhere they appear as a `quant_core` input or output.

## Time to expiry

Time to expiry `T` is in **years**, under the **ACT/365F** day-count
convention: the actual number of calendar days between `valuation_time` and
`expiry` (the "actual" in ACT), divided by a **fixed 365-day year** (the
"365 Fixed" in 365F — never 365.25, never the calendar's actual day count
for that particular year). Computed as:

```
T = (expiry - valuation_time) / timedelta(days=365)
```

This is stated explicitly here because it is not otherwise inferable from
the code, and a different day-count convention silently changes every Greek
that depends on `T` (theta, vega, rho all do).

## Money and quantities

Per ADR-0004 / ADR-0013: `Decimal`, precision 38, scale 8. See
`quant_core.numeric` (Task 2 of `libs/quant-core/PLAN.md`) for the one place
the Decimal<->float64 boundary conversion happens.

## Time semantics: `event_time` vs. `ingest_time`

ADR-0005 names the two timestamps every message carries; this section states
the invariant that makes them safe to build on.

**`event_time` is derived from the scenario, never from the wall clock.** A
scenario (`services/ingest/scenarios/*.yaml`) declares `start_time`,
`tick_interval`, and `tick_count`. The event time of tick `i` is:

```
event_time(i) = start_time + i * tick_interval
```

This is arithmetic on the scenario's declared parameters, not a clock read.
Running the same scenario twice — same `scenario_id`, any number of runs, on
any machine, at any real wall-clock moment — produces identical event times
for every tick. **Event time is set once, at origin (`services/ingest`, the
only place a `Tick` is constructed — ADR-0011), and is never modified by any
later stage.** A pricer, a snapshot writer, or a replay tool that touches
`event_time` after origin has broken the one property this convention
exists to guarantee.

**`ingest_time` is wall-clock UTC, stamped independently by each stage at
the moment it receives the message.** It is never copied forward from an
upstream stage's `ingest_time`, and it is never part of any identity —
ADR-0007 builds `RiskSnapshot` identity from `(portfolio_id,
as_of_event_time, pricer_version)` precisely because `event_time` is stable
across replays and `ingest_time` is not. The only valid use of
`ingest_time` is measuring latency at the stage that stamped it
(`ingest_time − event_time`, per `docs/nfr-budget.md`); comparing one
stage's `ingest_time` to another's measures clock skew between machines, not
anything about the data.

**Why this matters:** ADR-0007 makes `as_of` (a tick's `event_time`,
propagated through to a snapshot) part of snapshot identity. If `event_time`
were wall-clock instead of scenario-derived, running the same scenario twice
would produce two disjoint sets of snapshot identities — nothing would line
up between them. Re-pricing history under a new `pricer_version` (the
entire justification for ADR-0007's identity tuple) depends on the old and
new runs sharing identical `(portfolio_id, as_of_event_time)` pairs so the
two `pricer_version`s can be diffed directly. A wall-clock `event_time`
silently destroys that: same scenario, two unrelated sets of snapshots,
nothing to compare.

**Consequence for pacing:** `services/ingest`'s two pacing modes (realtime,
replay) change only the wall-clock timing of when a tick is *sent* — they
never change `event_time`, which is fixed by the scenario before pacing is
even applied. If switching pacing mode changes the data (anything other
than `ingest_time` and real elapsed wall-clock time), the mode is a bug, not
a feature.
