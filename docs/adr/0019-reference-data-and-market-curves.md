# ADR-0019: Reference data and market curves

## Status
Accepted

## Context
`portfolio.state` (ADR-0003) carries `Position.instrument_id` and a
quantity/cost, and `market.ticks` carries a price. Neither carries what a
pricer actually needs to price an option: strike, expiry, option right,
`contract_size`, or the risk-free rate and volatility a model requires as
inputs. The session that built `services/pricer` (Session 04) had to fill
this gap to get anything pricing at all, and did so with a checked-in YAML
fixture (`services/pricer/fixtures/instruments.yaml`, see its module
docstring and `services/pricer/PLAN.md`'s open questions — flagged there as
a stand-in for "a real reference-data feed that doesn't exist yet"). That
fixture conflates two things that have different owners and different
rates of change:

- **Static instrument data** (`underlying_id`, `strike`, `expiry`,
  `option_type`, `contract_size`, `currency`) — set once when an instrument
  is created and never changes. This is `core-service`'s data: it is the
  system of record for what instruments exist (`services/core-service`'s
  `instruments` table, `docs/domain-model.md#instrument`).
- **Market assumptions** (`risk_free_rate`, `volatility`) — change
  continuously, and are exactly the kind of input `services/ingest`
  already owns for every other market-facing input (`market.ticks`,
  ADR-0011).

The constraint that actually matters here is not ownership convenience —
it's determinism. `market.ticks` carries `scenario_id` precisely so a
`RiskSnapshot` can be traced back to the exact reproducible tick stream
that produced it (`docs/domain-model.md#tick`, ADR-0006, ADR-0011). A flat
`risk_free_rate`/`volatility` read from an editable YAML file has no
`scenario_id` at all: two runs against the same tick scenario can price
differently depending on what happened to be in the file at the time,
with nothing on the wire to say so. That silently breaks the exact
replay-determinism property the last four sessions were built to
establish (ADR-0006's seeded Monte Carlo, ADR-0007's re-pricing-history
identity, ADR-0011's `scenario_id` lineage). Rate and volatility must be
scenario-scoped, the same as a tick, or they undermine every one of those
guarantees.

## Decision
Two new log-compacted Kafka topics, split by owner:

| Topic | Key | Producer | Carries | Status |
|---|---|---|---|---|
| `reference.instruments` | `instrument_id` (`reference-instruments-key.avsc`) | `services/core-service` | Static instrument facts: `underlying_id`, `instrument_type`, `option_type`, `strike`, `expiry`, `currency`, `contract_size` — field-for-field `docs/domain-model.md#instrument`. | Q1, this session. |
| `market.curves` | `(currency, scenario_id)` | `services/ingest` | `risk_free_rate` (float64), `volatility` (float64), both scenario-scoped. | Q2 — shape fixed now, not implemented. |

**`reference.instruments`** is compacted the same way `portfolio.state` is
(ADR-0003, ADR-0016): one current record per `instrument_id`, consistent
with `docs/domain-model.md#instrument`'s rule that a new expiry or strike
is a new `Instrument`, never an update to an existing one — so in practice
this topic only ever gains keys, it does not need to handle a
value actually changing under an existing key, though compaction still
protects against redelivery the same way it does for any keyed topic.
Consumers (`services/pricer`) materialize it into a keyed local view using
the same block-until-fully-replayed pattern already implemented for
`portfolio.state` in `services/pricer/pricer/service.py`'s `hydrate()`
(`READY`/`HYDRATING` states, a fresh consumer group per hydration run, a
tick arriving before hydration completes is queued and priced only once
the view is populated — see `services/pricer/PLAN.md` and
`services/pricer/tests/test_hydration.py`). **This project has no ADR
naming that hydration-gate pattern generically** (only the `portfolio.state`
instance is documented, in `services/pricer`'s own `PLAN.md`); this ADR
does not create one either — it just requires `reference.instruments`
consumers to reuse the identical mechanism, and flags the missing ADR as a
gap for whoever owns that generalization.

**`market.curves`** is **not implemented this session.** Its shape is
fixed here so that when it lands, it isn't a redesign of
`services/pricer/fixtures/instruments.yaml`'s `volatility`/
`risk_free_rate`/`dividend_yield` fields (which is what it replaces) but a
direct translation of the same fields onto a topic with a `scenario_id`.
Key is `(currency, scenario_id)` rather than a bare curve identifier: Q1
has no multi-curve-per-currency requirement (no tenor structure, no
issuer-specific curve), and inventing one now would be speculative; the
composite key is the minimum that satisfies the scenario-scoping
constraint above. Value carries `risk_free_rate: float64` and
`volatility: float64` (not `decimal` — these are continuous risk
quantities under ADR-0004, not cash amounts) plus `scenario_id: string`
and the standard `event_time`/`ingest_time` pair (ADR-0005). Until this
lands, `services/pricer/fixtures/instruments.yaml` continues to be read
for `volatility`/`risk_free_rate`/`dividend_yield`, now explicitly marked
in that file as a Q1 stand-in for this topic.

## Consequences
- The pricer materializes three compacted views (`portfolio.state`,
  `reference.instruments`, and eventually `market.curves`) plus its own
  price cache, all gated by the same hydrate-before-ready pattern.
  `services/pricer/PLAN.md` gains a Q2 deliverable to consume
  `reference.instruments` and retire `fixtures/instruments.yaml`'s
  instrument-shape fields (`instrument_type`, `underlying_id`,
  `option_type`, `strike`, `expiry`, `currency`, `contract_size`); the
  fixture's `volatility`/`risk_free_rate`/`dividend_yield` fields stay
  until `market.curves` itself lands.
- `contract_size` and `currency` — referenced by ADR-0014 (contract
  multiplier ownership) and ADR-0017 (cash Greek aggregation) but never
  actually carried on any wire message until now — get a home in
  `reference.instruments`.
- `services/core-service` gains a durable `instruments` table
  (this session, see `V1__init_schema.sql`) as the system of record it
  publishes `reference.instruments` from; instruments are entered there
  and published, never mutated (per `docs/domain-model.md#instrument`, a
  changed strike/expiry is a new instrument, not an update).
- `market.curves` not existing yet means Q1 risk snapshots still cannot
  be reproduced from wire data alone for the rate/vol inputs — only
  `reference.instruments`, once this ships, closes that gap for the
  static half. This is a known, accepted Q1 gap, not a hidden one.

## Alternatives considered
- **Fold instrument statics into `portfolio.state`.** Rejected: different
  owner (a position mutation has nothing to do with an instrument being
  defined) and different rate of change — bloating every position-mutation
  message on a hot, frequently-republished topic with static data that
  almost never changes is a wasteful compaction key design, not a
  simplification.
- **One combined reference-data topic for both instruments and curves.**
  Rejected: different producers (`core-service` vs. `services/ingest`) and
  different timelines (Q1 vs. Q2). A combined topic would force
  `core-service` to block on `ingest`'s Q2 curve work to ship
  `reference.instruments` at all, or force `ingest` to co-own a topic
  `core-service` is the sole producer of — both violate the
  single-producer-per-topic pattern `portfolio.state` already established
  (ADR-0003).
- **Curve key without `scenario_id`.** Rejected outright — this is the
  entire problem this ADR exists to fix. A curve identified only by
  `currency` reintroduces exactly the untraceable-flat-vol failure mode
  described in Context, just moved from a YAML file onto a Kafka topic.
