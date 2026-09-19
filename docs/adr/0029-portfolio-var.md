# ADR-0029: portfolio VaR — delta-normal, 1-day 95%

## Status
Accepted

## Context

`RiskSnapshot.var_95` has existed since Q1 and is hard-coded to `0.0`. What
the repository already fixes about it:

- **Horizon and confidence:** 1-day, 95% (`docs/domain-model.md`, the `var_95`
  row; the Avro doc in `contracts/avro/risk-snapshot.avsc`).
- **Unit:** the portfolio's `base_currency`, expressed as a magnitude.
- **Type:** `float64` (Avro `double`), per ADR-0004, even though its unit is
  currency: it is a risk statistic, not a cash balance.
- **Nullability:** not nullable, in the domain model, in Avro (no default) and
  in Postgres (`DOUBLE PRECISION NOT NULL`).

What it does not fix is the method, the lookback, or how currency is handled.
ADR-0028 deferred the currency question to "when VaR is built", and root
`PLAN.md` puts single-portfolio VaR in Q2 and correlated cross-portfolio risk
and Monte Carlo in Q3.

The decisive constraint is that **the system keeps no price history at all**:

- The pricer holds one last price and one last event time per underlying
  (`_last_price` and `_last_event_time` in `services/pricer/pricer/service.py`),
  overwritten on every tick and lost on restart.
- Prices are not persisted. Postgres has no per-underlying price table, and
  `risk_snapshots` records portfolio-level values only (ADR-0018 says prices
  are not persisted in Postgres).
- No committed scenario contains a usable return series. The longest spans 20
  seconds of simulated time: `small-deterministic` and
  `small-deterministic-v2` are `tick_interval_seconds: 1.0` with
  `tick_count: 20`, and `throughput-1000` is `tick_interval_seconds: 0.001`
  with `tick_count: 3000`, which is 3 seconds.

Any method that needs a return series would therefore have to invent data.
Monte Carlo and correlation are Q3's scope. ADR-0006's seed formula is per
`instrument_id` and defines no portfolio-level seed.

What the pricer does have at pricing time, for every position, is its cash
delta (ADR-0017), its conversion into the reporting currency (ADR-0028), and
a `VOLATILITY` curve for its underlying (ADR-0027).

## Decision

1. **Delta-normal parametric VaR, first order only.** The inputs are already
   present at pricing time: each position's converted `cash_delta` and the
   `VOLATILITY` curve value for its underlying.

2. **The formula.** For each position:

   - `daily_vol = annual_volatility / sqrt(CALENDAR_DAYS_PER_YEAR)`
   - `shock = Z_95 * daily_vol`, a relative return
   - `position VaR = abs(cash_delta) * shock / 0.01`

   `cash_delta` is P&L per 1% relative move (ADR-0017), so dividing by `0.01`
   rescales it to the shock. `Z_95 = 1.6448536269514722` is the one-tailed 95%
   standard normal quantile. The portfolio figure is the sum of the position
   values.

3. **Daily volatility scales by `sqrt(365)`.** `docs/conventions.md` fixes
   ACT/365F for time to expiry (`T = (expiry - valuation_time) /
   timedelta(days=365)`); it does not itself govern VaR horizons. Scaling
   annual volatility by `sqrt(365)` extends that convention by analogy, and
   this ADR makes that a deliberate choice, preferring internal consistency
   within one system to importing the external 252-trading-day convention
   halfway. The constant is named `CALENDAR_DAYS_PER_YEAR`, because it is
   calendar days, not trading days. A later ADR may revisit this.

4. **No diversification benefit.** Per-position magnitudes are summed. A long
   and a short of equal size add rather than cancel. With no correlation data,
   netting would claim a hedge that cannot be evidenced, so this errs toward
   overstating risk and never understates it. Q3's correlated work is what
   earns netting.

5. **The statistic is a pure function in `libs/quant-core`
   (`quant_core.risk`); assembling its inputs stays in `services/pricer`.**
   This resolves a contradiction between `libs/quant-core/PLAN.md` (VaR out of
   scope, aggregation lives in the pricer) and `docs/rotation.md` (VaR
   assigned to `libs/quant-core`). Both are corrected alongside this ADR. The
   function takes `float64` inputs, so the `Decimal` to `float64` conversion of
   `cash_delta` happens in the pricer at the boundary (ADR-0004).

6. **VaR is computed from contributions after FX conversion**, so it is in the
   portfolio's base currency by construction. This answers the question
   ADR-0028 deferred, with no separate FX step for VaR.

7. **`VOLATILITY` becomes a required curve for every position type, not only
   options.** This lands in the pricer session, not here. A missing volatility
   is then reported as `MISSING_CURVE` with the existing machinery: no new
   unpriceable reason, and no need to make `var_95` nullable, because this
   method needs no history and therefore has no "insufficient data" state.

8. **Excluded deliberately:** gamma, vega and theta risk; cross-portfolio
   correlation; and realised versus implied volatility (the curve carries
   implied volatility, which is what this method uses).

## Consequences

- The pricer session that wires this in changes every golden snapshot, because
  `var_95` stops being `0.0`. That is the first deliberate change to those
  values.
- The dashboard does not display `var_95` today, so nothing renders it until
  someone adds it.
- A zero-volatility book yields zero VaR. That is correct for this method, not
  a stub.
- Delta-only VaR understates the risk of convexity- or volatility-dominated
  books, and the no-netting rule overstates the risk of hedged ones. Both are
  accepted and documented rather than hidden.
- Requiring `VOLATILITY` for equity positions adds a curve dependency that
  equity pricing did not have before.

## Alternatives considered

- **Historical simulation.** Rejected: no return history exists anywhere, and
  the longest committed scenario spans 20 seconds.
- **Monte Carlo revaluation.** Rejected for this quarter: it is Q3 scope, and
  ADR-0006's seed formula is per `instrument_id` and defines no portfolio-level
  seed, so it would need extending first.
- **Full-Greek or delta-gamma VaR.** Rejected: it needs second-order terms
  that are not aggregated in a form usable here today.
- **Correlation-aware netting.** Rejected: there is no covariance data.
- **252-day scaling.** Rejected: the repository's day count is ACT/365F, and
  mixing conventions inside one system is worse than following either
  consistently.
- **Making `var_95` nullable to express "unknown".** Rejected: it is a paired
  schema change that this method does not need, since it has no "insufficient
  data" state.
