# ADR-0028: cross-currency aggregation — reporting currency, FX conversion, and what the snapshot records

## Status
Accepted

## Context
ADR-0014 has `libs/quant-core` price each instrument in that instrument's
own currency, with no visibility into a portfolio's `base_currency`, and
defers the currency check to "wherever currency is visible, above this
library". ADR-0017 makes cash Greeks summable across underlyings but says
in its Consequences that they are not summable across currencies, and that
it does not attempt to solve that. Root `PLAN.md` has carried this as the
Q2 blocker for portfolio VaR ever since, with the decision on where FX
conversion happens left open. ADR-0027 reserved a place for FX rates on
`market.curves` (kind `FX_RATE`, six-letter `FROMTO` curve_id, decimal
value) and explicitly decided nothing about conversion.

There is also a defect in the repository as it stands. `docs/domain-model.md`
and `contracts/avro/risk-snapshot.avsc` already declare that `price`, every
cash Greek and `var_95` are denominated in the portfolio's base currency.
The pricer never converts, and nothing on the wire, in Postgres or in the
REST API records what currency a snapshot's numbers are in. A portfolio
holding instruments in two currencies would therefore publish a sum across
currencies under a documented unit it does not have, and no component would
notice. This ADR makes that documented claim true rather than adding a
feature: it decides how the pricer learns the reporting currency, where and
how it converts, what it does when it cannot, and what the snapshot records.

Three facts constrain the design. `portfolio.state` carries no currency
today; `base_currency` exists only in Postgres and the REST API. The pricer
already knows each position's currency from reference data. And the `Tick`
schema also carries a `currency` that the pricer ignores.

## Decision
**1. `base_currency` travels on `portfolio.state`.** `PortfolioState` gains
a top-level string field `base_currency` with default `""`, placed after
`portfolio_id`, copied by `services/core-service` from the `portfolios` row
on every message it publishes. It is not put on `Position`. `Position` is
paired with an OpenAPI component (ADR-0026), so a field there would force a
REST change to serve a need that is internal to Kafka, and it would repeat
one portfolio-level fact on every position row. `PortfolioState` is a
declared-unpaired schema, so no OpenAPI change follows. This decision lands
in the same session as this ADR.

**2. An empty `base_currency` never means USD.** The empty string is the
compatibility default for messages written before the field existed, and
nothing else. A portfolio whose reporting currency is unknown is not priced.
It is reported through the pricer's existing structured unpriceable
reporting (ADR-0018) with a new reason, `UNKNOWN_BASE_CURRENCY`, which comes
first in precedence because it is a fact about the whole portfolio and no
per-position check can rescue it. Core-service, for its part, never writes
an empty value: a missing `portfolios` row is an error, not an empty
string. The pricer reason lands in a later session.

**3. Conversion happens in `services/pricer`, per position.** After a
position's cash contribution is computed, and before contributions are
summed, the pricer converts that contribution into the portfolio's base
currency. The rate is the `FX_RATE` curve on `market.curves` whose
`curve_id` is the position's currency followed by the portfolio's base
currency (a EUR position in a USD portfolio uses `EURUSD`), looked up under
the triggering tick's `scenario_id` like every other curve. A position
already in the base currency needs no rate and no lookup. Rates are never
inverted (ADR-0027): a scenario must publish the direct pair it needs. A
missing rate is reported as `MISSING_CURVE`, listing `FX_RATE:<pair>`
alongside any other missing curve keys. This lands in a later session.

**4. Every position type requires its FX rate, not only options.** An equity
quoted in another currency must be converted exactly as an option is. This
is the first required curve that is not specific to options, so ADR-0027's
Decision 8 ("`EQUITY` positions require no curve at all") is narrowed by
this ADR: an equity requires no curve only when it is already in the
portfolio's base currency.

**5. The conversion is decimal throughout.** A position's contribution
fields are already `Decimal` and an FX rate is `decimal(38,8)`, so a helper
in `quant_core.numeric` multiplies and quantises once per position
(`ROUND_HALF_EVEN`, scale 8) with no float round trip, which keeps
ADR-0004's rule that floats never touch cash. Rounding per position, before
the sum, makes the total independent of summation order. `var_95` is
`float64` and is hard-coded to `0.0` today; how VaR converts is decided when
VaR is built, not here.

**6. The snapshot records `base_currency`, and not the rates used.** The
unit must be on the record, because the docs already promise it. The rates
need not be, because curves are constant per scenario and `market.curves`
is compacted, so `(scenario_id, FX_RATE, pair)` recovers exactly the rate
that was used. That stops being true if curves ever vary within a scenario,
and whichever ADR introduces time-varying curves must revisit this decision:
`RiskSnapshot` is paired with OpenAPI, so every field added there costs a
migration, a DTO change and a TypeScript binding, and that cost is why the
rates are not recorded now. Adding `base_currency` to `RiskSnapshot` lands
in a later session.

**7. Reference data is authoritative for a position's currency.** The `Tick`
schema carries a `currency` and the pricer ignores it today. A tick whose
currency disagrees with its instrument's reference currency is a data error,
reported with its own event and counter, and that price is not cached.
Pricing from a mislabelled price is the wrong-number failure this system is
designed to avoid. This lands in a later session.

## Consequences
**Lands in this session (plumbing only, no conversion):** the `base_currency`
field on `portfolio.state` and its regenerated bindings; `services/core-service`
copying it from the `portfolios` row on both publish paths (creation, and the
republish after a trade); the `docs/domain-model.md` row; the test
constructions and assertions that follow from the new field. The pricer
decodes the field and stores nothing new; no snapshot value changes.

**Lands in later sessions:** `UNKNOWN_BASE_CURRENCY` reporting (Decision 2);
the `numeric` helper, the per-position conversion, the required `FX_RATE`
curves and `MISSING_CURVE` reporting (Decisions 3 to 5); `base_currency` on
`RiskSnapshot` across Avro, Postgres, the REST DTO and the TypeScript
binding (Decision 6); the tick-currency mismatch check (Decision 7).

Other consequences:
- Existing messages on the compacted `portfolio.state` topic carry the empty
  default until core-service next republishes each portfolio. Until then the
  pricer, once Decision 2 lands, will treat those portfolios as
  unknown-currency and not price them. That is deliberate and self-heals as
  portfolios are touched.
- A scenario must publish a direct `FX_RATE` pair for every (position
  currency, base currency) combination it uses. Nothing derives the reverse
  pair.
- `services/ingest`'s `throughput-1000` scenario already contains EUR and GBP
  instruments and declares no curves, so it cannot be priced until curves,
  including FX pairs, are added for it.
- ADR-0014's and ADR-0017's Consequences about deferral are resolved by this
  ADR's Decisions 3 to 5, once those land. Neither is edited; ADRs are
  immutable.

## Alternatives considered
- **`base_currency` on `Position`.** Rejected: `Position` is paired with
  OpenAPI (ADR-0026), so this would force a REST change for a Kafka-internal
  need, and it would repeat one portfolio-level fact on every row.
- **The pricer looks `base_currency` up over REST from core-service.**
  Rejected: ADR-0003 forbids the pricer calling back into core-service, and
  a synchronous lookup on the pricing path would put a network dependency
  into the latency budget.
- **Converting inside `quant-core`.** Rejected by ADR-0014: quant-core has no
  visibility into currency by construction, and an FX rate would have to flow
  through `MarketState` for every instrument whether or not a conversion is
  needed.
- **Converting in core-service after the snapshot.** Rejected: snapshots
  carry cash Greeks that were already summed across currencies, and a sum
  cannot be un-summed. Conversion has to happen per position, before the sum.
- **Float conversion.** Rejected by ADR-0004: an FX rate multiplies a cash
  amount, and floats must not touch cash without an explicit boundary
  conversion.
- **Allowing consumers to invert an FX pair.** Rejected by ADR-0027:
  inversion is a rounding choice, and a rounding choice made independently by
  each consumer is a determinism leak.
- **Recording each rate used on the snapshot now.** Rejected for now: while
  curves are constant per scenario the rate is recoverable from
  `market.curves`, and each new field on `RiskSnapshot` costs a migration, a
  DTO and a TypeScript binding. Revisit if curves ever vary within a scenario.
