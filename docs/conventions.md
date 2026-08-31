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
