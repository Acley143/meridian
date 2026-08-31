# Conventions

Sign, unit, and scale conventions for the numbers `libs/quant-core` returns.
These exist because getting one of them wrong is not a crash — it is a
silent hundred-fold error on a dashboard that looks plausible enough to act
on. Every docstring that returns one of these numbers must reference this
file; do not let the convention be inferred from the formula.

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

## Rates and volatilities

Continuously compounded, annualised, expressed as **decimals** — `0.05` for
5%, never `5`. This applies to both the risk-free rate and volatility
everywhere they appear as a `quant_core` input or output.

## Time to expiry

Time to expiry `T` is in **years**, computed as:

```
T = (expiry - valuation_time) / timedelta(days=365.25)
```

ACT/365F day-count convention. This is stated explicitly here because it is
not otherwise inferable from the code, and a different day-count convention
silently changes every Greek that depends on `T` (theta, vega, rho all do).

## Money and quantities

Per ADR-0004 / ADR-0013: `Decimal`, precision 38, scale 8. See
`quant_core.numeric` (Task 2 of `libs/quant-core/PLAN.md`) for the one place
the Decimal<->float64 boundary conversion happens.
