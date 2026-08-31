# Domain Model

This document is the source of truth for every type in Meridian. Every Avro
schema in `contracts/avro/`, every DDL table, every OpenAPI schema, and every
generated language binding is a mechanical translation of what's written
here. **If a schema and this document ever disagree, this document is right
and the schema is a bug** — fix the schema, don't edit this document to match
it after the fact.

Field table columns: **name**, **type**, **unit**, **nullable**,
**precision**, **meaning**. "Precision" is `—` for non-numeric fields.

Per ADR-0004 (numeric type policy) and ADR-0013 (decimal precision): decimal
fields (money, notionals, quantities) are `decimal` (precision 38, scale 8);
everything continuous-but-not-cash (Greeks, vols, rates,
correlations) is `float64`. Per ADR-0005: every message-shaped type carries
both `event_time` and `ingest_time`, both UTC, both microsecond precision.

---

## Instrument

The static contractual definition of a tradeable thing — what it *is*, not
what anyone holds of it or what it's currently worth. Instruments do not
change day to day; a new expiry or strike is a new `Instrument`, not an
update to an existing one.

| name | type | unit | nullable | precision | meaning |
|---|---|---|---|---|---|
| instrument_id | string | — | no | — | Globally unique, stable identifier. Not a exchange ticker — tickers can be reused; this is a Meridian-internal UUID or equivalent stable key. |
| underlying_id | string | — | no | — | `instrument_id` of the underlying instrument this derivative references. For a non-derivative (e.g. an equity), equal to `instrument_id` itself. |
| instrument_type | enum {EQUITY, VANILLA_EUROPEAN_OPTION, VANILLA_AMERICAN_OPTION} | — | no | — | Discriminates which fields below are meaningful and which pricer applies. Not a free-text field — new types require a schema change. |
| option_type | enum {CALL, PUT} | — | yes (null unless instrument_type is an option) | — | Right conveyed by the option. Not meaningful for EQUITY. |
| strike | decimal | currency of `currency` field | yes (null unless an option) | precision 38, scale 8 | Strike price in the instrument's quote currency. This is a price, not a percentage-of-spot moneyness. |
| expiry | timestamp | — | yes (null unless an option) | microsecond | UTC instant the option expires. Not a date-only field — intraday expiry matters for the latency/accuracy budget. |
| currency | string (ISO 4217) | — | no | — | Currency the instrument is quoted and settled in. Not necessarily the underlying's home currency. |
| contract_size | decimal | units of underlying per contract | no | precision 38, scale 8 | Multiplier converting one contract to underlying units (e.g. 100 shares/contract). This is not the notional — see `Position.notional`. |

---

## Position

A holding of a specific `Instrument` within a specific `Portfolio`, as of the
latest applied trade. A position is derived state — it exists because trades
happened — and is not itself independently mutated; see `PortfolioState`.

| name | type | unit | nullable | precision | meaning |
|---|---|---|---|---|---|
| portfolio_id | string | — | no | — | `Portfolio` this position belongs to. |
| instrument_id | string | — | no | — | `Instrument` held. |
| quantity | decimal | contracts (options) or shares (equity) | no | precision 38, scale 8 | Signed quantity: positive is long, negative is short. Not the notional exposure — multiply by `contract_size` and price for that. |
| average_cost | decimal | currency of the instrument | no | precision 38, scale 8 | Volume-weighted average price paid per unit of `quantity`, in the instrument's quote currency. Not the current market price. |
| as_of_event_time | timestamp | — | no | microsecond | UTC instant this position reflects (the event time of the last trade applied to it). Not the time the position record was computed/materialized. |

---

## Portfolio

A named collection of positions belonging to one book. Static/slow-changing
metadata; the positions themselves live in `PortfolioState`, not here.

| name | type | unit | nullable | precision | meaning |
|---|---|---|---|---|---|
| portfolio_id | string | — | no | — | Globally unique, stable identifier. |
| name | string | — | no | — | Human-readable display name. Not guaranteed unique — `portfolio_id` is the key. |
| base_currency | string (ISO 4217) | — | no | — | Currency portfolio-level aggregates (P&L, VaR) are reported in. Individual positions may be denominated in other currencies. |
| owner | string | — | no | — | Identifier (not display name) of the desk or user responsible for the portfolio. |

---

## Trade

An immutable record of a single execution that changes a `Position`. Trades
are the append-only source of truth; positions are a fold over trades.

| name | type | unit | nullable | precision | meaning |
|---|---|---|---|---|---|
| trade_id | string | — | no | — | Globally unique identifier for this execution. Not reused on amendment — a correction is a new trade with an offsetting entry, per standard trade-booking practice. |
| portfolio_id | string | — | no | — | `Portfolio` the trade is booked into. |
| instrument_id | string | — | no | — | `Instrument` traded. |
| quantity | decimal | contracts (options) or shares (equity) | no | precision 38, scale 8 | Signed quantity of this single execution: positive is a buy, negative is a sell. Not the resulting position quantity — that's a running total. |
| price | decimal | currency of the instrument | no | precision 38, scale 8 | Execution price per unit, in the instrument's quote currency. Not adjusted for fees. |
| event_time | timestamp | — | no | microsecond | UTC instant the trade executed upstream (e.g. at the exchange/venue). |
| ingest_time | timestamp | — | no | microsecond | UTC instant Meridian's ingest stage received this trade record. |

---

## Tick

A single market data observation for an instrument. The highest-volume
message type in the system; this is what the throughput budget in
`docs/nfr-budget.md` (1,000/sec) is measured against.

| name | type | unit | nullable | precision | meaning |
|---|---|---|---|---|---|
| instrument_id | string | — | no | — | `Instrument` this observation is for. |
| price | decimal | currency of `currency` field | no | precision 38, scale 8 | Last-traded or mid price, per the venue's convention — not a bid/ask spread (out of scope for Q1; see `contracts/avro/tick.avsc` for the exact field if extended later). |
| currency | string (ISO 4217) | — | no | — | Currency `price` is quoted in. |
| event_time | timestamp | — | no | microsecond | UTC instant the tick was generated at the source (exchange/feed). This is the numerator's reference point for the latency budget. |
| ingest_time | timestamp | — | no | microsecond | UTC instant Meridian's ingest stage received this tick. `ingest_time − event_time` is feed latency; `dashboard_render_time − event_time` is the end-to-end p99 budget. |
| scenario_id | string | — | no (empty string default) | — | Identifies the seeded simulated market scenario this tick belongs to (ADR-0011, ADR-0006) — the same `scenario_id` reproduces a byte-identical tick stream. Empty string is the wire default for BACKWARD compatibility (this field was added after `Tick` was first drafted); the Q1 simulated feed always sets a real value. This is what lets a `RiskSnapshot` be traced back to the exact reproducible tick stream that produced it — see `RiskSnapshot.scenario_id`. |

---

## PortfolioState

The materialized, current set of positions for a portfolio, as produced onto
the `portfolio.state` log-compacted topic by the core service (ADR-0003).
This is what the pricer consumes to build its local view — it is a snapshot
of "positions right now," not an event.

**Tombstone convention (producer-side, not expressible in the value schema
below):** a Kafka message on this log-compacted topic with a `portfolio_id`
key and a **null value** is a tombstone, per standard Kafka log-compaction
semantics, and means that portfolio has been deleted. A null message has no
Avro payload at all, so this cannot be a field inside `PortfolioState`
itself — it is a producer-side convention that `services/core-service` (the
sole producer, ADR-0003) must follow, and every consumer of this topic
(`services/pricer`) must handle a null value as a delete, not a decode
failure. See `contracts/avro/portfolio-state.avsc`'s top-level `doc` for the
same note at the point a schema author will actually see it.

| name | type | unit | nullable | precision | meaning |
|---|---|---|---|---|---|
| portfolio_id | string | — | no | — | Kafka message key. `Portfolio` this state belongs to. |
| positions | array\<Position\> | — | no (may be empty array) | — | The full current set of positions for this portfolio. Not a delta/diff against the previous message — each message is the complete state, which is what makes log compaction on `portfolio_id` correct. |
| event_time | timestamp | — | no | microsecond | UTC instant of the trade that produced this state (i.e. the triggering `Trade.event_time`). |
| ingest_time | timestamp | — | no | microsecond | UTC instant the core service produced this message. |

---

## RiskSnapshot

The priced, risk-bearing output of the pricer for one portfolio at one
instant, under one model version. Identity and delivery semantics are fixed
by ADR-0007.

**Revised when this became a wire format (contracts session, see
`docs/adr/0015-contracts-build-topology.md`'s sibling schema work):** the
original sketch used a free-form `greeks: map<string, float64>` for
extensibility. As an Avro field, a map's values carry no per-key schema of
their own — no per-Greek doc string, no per-Greek default, no way for the
registry's `BACKWARD` check to catch a typo in a key ("delta" vs "Delta")
until it silently produces an empty aggregate at read time. Replaced with
discrete typed fields, one per Greek, matching `docs/conventions.md`'s
sign/unit conventions exactly the way `quant_core.types.PricingResult`
already does. `portfolio_value` is renamed `price` to match the field name
used throughout `libs/quant-core` for the same concept (ADR-0014).

**Revised again (ADR-0017):** those discrete fields were still raw
per-unit Greeks, which do not aggregate meaningfully across a portfolio's
different underlyings (`∂²V₁/∂S₁²` and `∂²V₂/∂S₂²` are not in the same
units). Renamed `cash_delta`/`cash_gamma`/`cash_vega`/`cash_theta`/
`cash_rho` and retyped `float64 -> decimal(38,8)` — cash Greeks are
currency amounts and genuinely summable, which is the entire point of
reporting them at the portfolio level at all. See ADR-0017 for the
aggregation formulas.

| name | type | unit | nullable | precision | meaning |
|---|---|---|---|---|---|
| portfolio_id | string | — | no | — | Part of the identity tuple (ADR-0007). |
| as_of | timestamp | — | no | microsecond | Part of the identity tuple. The event time this snapshot values the portfolio as of — not the time the computation ran, and not `ingest_time` below. Renamed from `as_of_event_time` for brevity; same field. |
| pricer_version | string | — | no | — | Part of the identity tuple. Identifies the exact pricing model/code version used, enabling re-pricing history and diffing (ADR-0007). Not a build number of the whole service — scoped specifically to the pricing logic. |
| price | decimal | `Portfolio.base_currency` | no | precision 38, scale 8 | Total mark-to-market value of the portfolio. A cash amount — decimal per ADR-0004/ADR-0013. Named to match `quant_core`'s `PricingResult.price` (ADR-0014); this is a portfolio-level aggregate, not a per-instrument price. |
| cash_delta | decimal | `Portfolio.base_currency` per 1% relative move in spot | no | precision 38, scale 8 | Aggregated portfolio-level **cash delta** (ADR-0017): `Δ × S × 0.01 × quantity × contract_size`, summed across positions. Decimal, not float64 — raw per-unit deltas across different underlyings are not in comparable units and cannot be summed meaningfully; cash delta is a currency amount and can be. Per `docs/conventions.md`. |
| cash_gamma | decimal | `Portfolio.base_currency` per 1% move in spot | no | precision 38, scale 8 | Aggregated portfolio-level **cash gamma** (ADR-0017): `Γ × S² × 0.0001 × quantity × contract_size`, summed across positions. Change in `cash_delta` per 1% move. Same cross-underlying summability reasoning as `cash_delta`. |
| cash_vega | decimal | `Portfolio.base_currency` per 1.00 absolute change in volatility | no | precision 38, scale 8 | Aggregated portfolio-level **cash vega** (ADR-0017): `ν × quantity × contract_size`, summed across positions. Per `docs/conventions.md` — per 1.00 vol, not per 1%. |
| cash_theta | decimal | `Portfolio.base_currency` per calendar year | no | precision 38, scale 8 | Aggregated portfolio-level **cash theta** (ADR-0017): `Θ × quantity × contract_size`, summed across positions. Per `docs/conventions.md` — per year, not per day. |
| cash_rho | decimal | `Portfolio.base_currency` per 1.00 absolute change in rate | no | precision 38, scale 8 | Aggregated portfolio-level **cash rho** (ADR-0017): `ρ × quantity × contract_size`, summed across positions. Per `docs/conventions.md`. |
| var_95 | float64 | `Portfolio.base_currency`, expressed as a magnitude | no | — | 1-day 95% Value at Risk. A risk statistic, not a cash balance — float64 per ADR-0004, even though its unit is currency. |
| scenario_id | string | — | no (empty string default) | — | Propagated from the `Tick` stream that produced the positions/prices this snapshot is derived from (ADR-0011). End-to-end lineage: any risk number can be traced back to the exact reproducible tick stream that produced it, which is what makes "replay the same market day under two pricers and diff" work. Empty string is the wire default. |
| ingest_time | timestamp | — | no | microsecond | UTC instant this snapshot was produced by the pricer. This, not `as_of`, is what `dashboard_render_time` is compared against downstream of the pricer for latency accounting at that stage. |

---

## AuditEntry

One row in the append-only, hash-chained audit log (ADR-0008).

| name | type | unit | nullable | precision | meaning |
|---|---|---|---|---|---|
| entry_id | string | — | no | — | Globally unique identifier for this row, assigned at write time. Not a hash — see `entry_hash` below. |
| entry_type | string | — | no | — | What kind of event this row records (e.g. "trade_booked", "risk_snapshot_produced"). Not free text in practice — governed by the emitting service's `PLAN.md`. |
| payload | string (canonical JSON) | — | no | — | The canonical serialization of the event being audited. "Canonical" means a fixed, deterministic field order and encoding — required for `entry_hash`/`prev_hash` to be reproducibly verifiable. |
| prev_hash | string (hex-encoded SHA-256) | — | no (empty string for the first row only) | — | SHA-256 of the canonical form of the *previous* row in the chain. This is what makes the log tamper-evident (ADR-0008) — it is not a hash of this row. |
| entry_hash | string (hex-encoded SHA-256) | — | no | — | SHA-256 of this row's own canonical form (`entry_id` + `entry_type` + `payload`, excluding `entry_hash` itself). Stored so a verifier doesn't need to recompute it from scratch to check the *next* row's `prev_hash`. |
| event_time | timestamp | — | no | microsecond | UTC instant the audited fact occurred. |
| ingest_time | timestamp | — | no | microsecond | UTC instant this audit row was written. |
