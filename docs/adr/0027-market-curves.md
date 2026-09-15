# ADR-0027: market.curves shape, numeric types, and scenario scoping

## Status
Accepted

## Context
ADR-0019 fixed a shape for `market.curves` — keyed by `(currency,
scenario_id)`, value carrying `risk_free_rate: float64` and `volatility:
float64` — before any consumer needed the topic to hold real data. That
shape has three defects, visible now that `services/pricer`'s stand-in
fixture (`services/pricer/fixtures/instruments.yaml`) exists:

- **The key cannot represent the current data.** `AAPL-CALL-150` is at
  `volatility: 0.25` and `MSFT-PUT-280` is at `volatility: 0.35`, both
  quoted in `currency: USD`. Both would collapse onto the same
  `(USD, scenario_id)` key under ADR-0019's shape, even though they are two
  different underlyings' volatilities. Volatility (and, in general,
  dividend yield) varies per underlying, not per currency; only the
  risk-free rate is naturally keyed by currency alone.
- **`dividend_yield` has no field**, despite ADR-0019's own prose stating
  that `market.curves` "replaces" the fixture's `volatility`,
  `risk_free_rate`, and `dividend_yield` fields. The fixture carries all
  three; the shape ADR-0019 fixed only carries two.
- **No place for FX rates.** Root `PLAN.md`'s open questions name
  cross-currency portfolio aggregation as an unresolved Q2 blocker: one
  reporting currency per portfolio, with FX conversion needed wherever a
  position's currency differs from its portfolio's. That decision is
  already settled at the root-`PLAN.md` level; the concrete consequence for
  this topic is that FX rates must come from `market.curves`, event-time
  keyed and scenario-scoped exactly like every other curve, and ADR-0019's
  shape has no field for one.

A log-compacted topic only ever retains the latest value per key. That
constrains what this ADR can build cheaply: a value that must change within
the lifetime of a single scenario cannot be replayed from a compacted
topic, because compaction discards every value but the last. Anything
requiring intra-scenario variation is out of scope here by construction,
not by oversight.

## Decision

1. **One topic, `market.curves`, single producer `services/ingest`,
   log-compacted.** Key `(scenario_id, kind, curve_id)`; value as specified
   below. One scalar per key — no tenor structure, the same minimalism
   ADR-0019 already chose and that this ADR does not revisit.

2. **`curve_id` meaning is per `kind`:** `RISK_FREE_RATE` — an ISO 4217
   currency code; `VOLATILITY` and `DIVIDEND_YIELD` — an `underlying_id`;
   `FX_RATE` — six letters `FROMTO` (e.g. `EURUSD`), where the published
   value is units of `TO` per one unit of `FROM`. Only direct quotes are
   published, for the pairs a scenario actually needs. Consumers never
   invert a published FX rate to derive its reverse pair — inversion
   introduces a rounding choice, and a rounding choice made independently
   by each consumer is a determinism leak this system cannot tolerate
   (every other numeric rule in this codebase exists to prevent exactly
   this class of leak).

3. **Numeric types.** Risk-free rate, volatility, and dividend yield are
   `float64` — per ADR-0004, these are continuous risk quantities, not cash
   amounts. FX rate is `decimal(38,8)`, because an FX rate multiplies a
   cash amount and ADR-0004 forbids floats touching cash; converting a
   float cash Greek across currencies is an explicit boundary conversion,
   exactly as ADR-0004 already requires for every other float/decimal
   boundary. This is why the value carries two nullable fields
   (`value_float`, `value_decimal`) rather than one: exactly one is
   non-null, determined by `kind`, and a record violating that rule is
   rejected in both directions — by the producer and by the consumer — the
   same reasoning ADR-0025 already applies to its own conditional fields.

4. **Curves are constant per scenario in Q2.** The producer publishes every
   curve key a scenario needs exactly once, before that scenario's first
   tick, and waits for delivery acknowledgement before producing any tick.
   Compaction is lossless under this rule, because nothing is ever
   overwritten mid-scenario. A curve that must vary within a scenario's
   lifetime requires a new ADR, and probably a non-compacted, event-time
   -joined topic instead — not an extension of this one.

5. **Time fields.** `event_time` is the scenario's `start_time`, so a
   replay of the same `scenario_id` produces byte-identical curve values
   every time (the same reproducibility guarantee `Tick.scenario_id`
   already gives the tick stream). `ingest_time` is the producer's wall
   clock, per ADR-0005. `scenario_id` is required and non-empty — unlike
   `Tick.scenario_id`, this field carries no legacy empty-string default,
   because `market.curves` has no pre-ADR-0011 history to be backward
   compatible with.

6. **Curve lookup is by the triggering tick's `scenario_id`.** A tick whose
   `scenario_id` is the empty string — `Tick`'s legacy BACKWARD-compatible
   default (see `docs/domain-model.md#Tick`) — finds no curves under any
   key, by construction: no producer ever publishes a curve keyed to the
   empty string.

7. **Pricing volatility and simulation volatility are deliberately
   different quantities.** The `VOLATILITY` curve published here is
   *implied* volatility, the pricing input. The GBM volatility
   `services/ingest`'s scenario simulator uses to generate tick paths is
   *realised* volatility, used only for path simulation and never
   published on this topic. These must not be unified: their difference is
   what gives a delta-hedging backtest meaningful P&L. A pricer computing
   Greeks from the same volatility that generated the underlying's price
   path would see risk that trivially nets to (near) zero — the entire
   point of running implied volatility against a simulated realised path
   is to have the two disagree.

8. **Required curves, per instrument type.** A `VANILLA_EUROPEAN_OPTION`
   position requires `RISK_FREE_RATE` for its currency, and `VOLATILITY`
   and `DIVIDEND_YIELD` for its underlying. `EQUITY` positions require no
   curve at all. `FX_RATE` is not required by anything until the
   cross-currency ADR that root `PLAN.md` still has open lands.

9. **Missing curves are reported, not silently defaulted.** Per ADR-0018,
   a portfolio missing any curve its positions require is not priced, and
   is reported through the pricer's existing structured
   unpriceable-portfolio reporting, with a new reason `MISSING_CURVE`
   listing every missing curve as `KIND:curve_id`. Precedence order among
   unpriceable reasons: `NO_REFERENCE_DATA`, `NO_PRICE`, `MISSING_CURVE`,
   `INSTRUMENT_NOT_PRICEABLE`. The pricer's ADR-0018 readiness gate is
   extended to include hydration of `market.curves`, alongside
   `reference.instruments` and `portfolio.state`.

10. **Topic provisioning convention**, recorded here because until now it
    existed only as a code comment in `services/core-service`
    (`CompactedTopicInitializer`): the sole producer of a compacted topic
    owns that topic's configuration. It creates the topic if absent, and on
    startup verifies an existing topic's `cleanup.policy` is exactly
    `compact` and its partition count matches expectations, refusing to
    start on a mismatch rather than silently altering the topic underneath
    whatever else might be consuming it. `market.curves` follows this
    convention with one partition, implemented in the producer's
    (`services/ingest`'s) library code — the same pattern already used for
    `market.ticks`, `portfolio.state`, and `reference.instruments`.

## Consequences
- `services/pricer/fixtures/instruments.yaml`'s `volatility`,
  `risk_free_rate`, and `dividend_yield` fields are retired once
  `services/pricer` consumes `market.curves` directly. The `services/ingest`
  scenario format gains curve definitions, which — per the scenario
  README's rule that a scenario's inputs are immutable once a `scenario_id`
  has been used — requires minting a new `scenario_id` rather than editing
  an existing scenario in place.
- **Known edge, accepted for Q2:** when the pricer is already `READY` and a
  new scenario starts, curves and ticks arrive over two different topics
  with no cross-topic ordering guarantee between them. A live run can
  therefore report `MISSING_CURVE` for that scenario's first few ticks,
  where a cold replay (which hydrates `market.curves` fully before
  processing any tick) would not see the same gap. Live and replay risk
  history can differ by these leading snapshots. Publish-then-acknowledge
  (Decision 4) narrows this window but does not close it; buffering ticks
  until curve hydration completes would close it, at the cost of unbounded
  memory in the pricer for however long a cold-starting scenario's curve
  publication takes.
- A future move to per-tenor curves, or curves that vary within a scenario,
  is a new ADR, not an amendment to this one — Decision 4's constancy
  assumption is load-bearing for every other decision here (in particular,
  it is what makes compaction lossless).

## Alternatives considered
- **ADR-0019's `(currency, scenario_id)` key, unchanged.** Rejected: cannot
  represent two different volatilities quoted in the same currency, the
  defect that motivated this ADR.
- **Three separately typed topics — rates, vols, FX — instead of one
  `market.curves` topic discriminated by `kind`.** Rejected: three topics
  means three sets of producer provisioning, three consumer hydration
  paths, and three places the same event-time/scenario-scoping rules must
  be kept in sync, for no benefit — nothing in this system ever needs to
  subscribe to only one kind without the others.
- **A single `["double", decimal]` union value field**, instead of two
  separate nullable fields. Rejected: Avro unions of two non-null branches
  can't each carry an independent default, and — more fundamentally — a
  single field conflates "not yet set" with "set to the wrong numeric
  representation for this `kind`," where two nullable fields make the
  exactly-one-of rule an explicit, checkable invariant instead of an
  implicit one resting on which union branch happened to be written.
- **`float64` for FX rate**, matching the other three kinds for
  uniformity. Rejected outright by ADR-0004: FX rates multiply cash
  amounts, and ADR-0004 forbids floats touching cash without an explicit
  boundary conversion.
- **Allowing consumers to invert a published FX pair** rather than
  requiring every needed direct quote to be published. Rejected: inversion
  is a rounding choice, and letting each consumer make that choice
  independently is a determinism leak.
- **Time-varying curves on a compacted topic**, accepting that a replay
  only ever recovers the last value published for a key. Rejected: this
  silently breaks replay determinism for exactly the values a backtest
  most needs to reproduce faithfully, for capability this ADR doesn't need
  in Q2 (Decision 4).
