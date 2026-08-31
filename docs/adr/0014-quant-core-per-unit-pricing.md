# ADR-0014: quant-core prices in per-unit terms

## Status
Accepted

## Context
`EuropeanOption` (`libs/quant-core/quant_core/types.py`) deliberately
narrows `docs/domain-model.md#Instrument`, dropping `instrument_id`,
`currency`, and `contract_size` — a pure per-instrument pricer doesn't need
them. That narrowing is correct, but it leaves the contract multiplier
unowned: nothing in the system currently states where `contract_size` gets
applied. Equity options are commonly 100 shares per contract. An unowned
multiplier is a 100x error that passes every unit test in the component
where it originates, because a pricer tested only against per-unit
reference values has no way to know a multiplier is missing.

## Decision
`libs/quant-core` returns prices and Greeks **per single unit of
underlying**, in the underlying's own currency, with no contract multiplier
applied. Multiplication by `Instrument.contract_size` happens in exactly
one place: `services/pricer`, at the point where a `PricingResult` is
combined with a `Position` to produce portfolio-level values. Every public
function in `quant_core.pricing` states "per unit of underlying" in its
docstring, so the omission is visible at the call site, not just in this
document.

Currency conversion is explicitly out of scope for Q1. `quant-core` has no
visibility into a portfolio's `base_currency` (per
`docs/domain-model.md#Portfolio`) and cannot detect a currency mismatch by
construction — it prices one instrument in that instrument's own currency
and nothing more.

## Consequences
- `services/pricer`'s `PLAN.md` gains an explicit deliverable: apply
  `contract_size` at the position level, with a test that fails if the
  multiplication is removed (not a general smoke test — a non-unit
  multiplier, e.g. `contract_size=100`, must produce a portfolio value
  distinguishable from the un-multiplied one).
- A reviewer auditing a 100x-off number has exactly one place to look:
  `services/pricer`'s position-aggregation code. `quant-core` is
  categorically not a suspect, because it never sees `contract_size`.
- Aggregating positions across currencies without conversion is silently
  wrong, and `quant-core` cannot catch it — the check has to live wherever
  currency is visible, above this library. This is deferred to Q2 (root
  `PLAN.md` open questions), ahead of portfolio-level VaR, since VaR is the
  first Q2 deliverable that aggregates positions and would otherwise
  silently sum unconverted currencies.

## Alternatives considered
- **quant-core applies contract_size internally.** Rejected: it would
  require `EuropeanOption` to carry `contract_size`, re-widening the type
  Task 4 deliberately narrowed, and it duplicates a multiplication that
  `services/pricer` also needs for non-priced position fields (e.g.
  notional). One multiplier, one owner.
- **quant-core resolves currency via an injected FX rate.** Rejected as
  premature for Q1: no workstream consumes multi-currency portfolios yet,
  and per ADR-0010 quant-core takes no implicit inputs — an FX rate would
  have to flow through `MarketState` for every instrument, whether or not
  a conversion is actually needed.
