# pricer — Plan

**Owner:** Eng-B  ·  **Quarter:** Q1  ·  **Status:** Q1 deliverables complete

## Mission
Consumes ticks and portfolio state, prices every position using
`libs/quant-core`, and produces `RiskSnapshot`s. This is where the hot path
(ADR-0003) actually runs — it's the component the latency budget in
`docs/nfr-budget.md` is mostly about.

## In scope this quarter
- [x] Consume `portfolio.state` and materialize a local view keyed by
      `portfolio_id` (ADR-0003). `pricer/portfolio_view.py`. Gated by an
      explicit hydration readiness state (`PricerService.hydrate()`,
      `pricer/service.py`): blocks, reading `portfolio.state` to the end of
      every assigned partition (via `enable.partition.eof` + an `on_assign`
      callback, `quant_io.consumer.PartitionEOF`), before `market.ticks` is
      even subscribed to. Tombstones (null value) handled as deletions,
      clearing the reverse index too (see below).
- [x] Consume the `market.ticks` topic and, on each relevant tick, re-price affected
      positions using `libs/quant-core`'s Black-Scholes pricer.
      `PricerService.process_one_tick`/`_price_portfolio`.
- [x] Derived reverse index, `underlying_id -> {portfolio_id}`
      (`pricer/portfolio_view.py`'s `PortfolioView`), updated on every
      portfolio.state change including position removals (full-state
      replacement, diffed against the previous positions, not a delta
      patch). **Keyed by `underlying_id`, not raw `Position.instrument_id`**
      — ticks only ever arrive for underlyings
      (`services/ingest/PLAN.md`: "options are quoted derivatively, not
      simulated directly"), and `underlying_id == instrument_id` for a
      non-derivative by definition (`docs/domain-model.md#Instrument`), so
      this is a strict generalization, not a different index.
- [x] Produce `RiskSnapshot`s (`contracts/avro/risk-snapshot.avsc`) keyed
      per ADR-0007: `price`, and the five cash Greeks
      (`cash_delta`/`cash_gamma`/`cash_vega`/`cash_theta`/`cash_rho`,
      ADR-0017 — formulas and aggregation defined there, this workstream
      implements them, not designs them). Portfolio-level VaR (`var_95`)
      is a stub value this quarter (Q2 for real computation).
- [x] `MarketState.valuation_time`/`RiskSnapshot.as_of` is the triggering
      tick's `event_time`, never `datetime.now()` (Task 3) —
      `pricer/pricing.py:price_instrument`, `pricer/service.py:
      _price_portfolio`.
- [x] `oldest_input_event_time` (Task 4): the earliest `event_time` among
      the prices actually used for a snapshot's positions. Added to
      `contracts/avro/risk-snapshot.avsc` (`docs/domain-model.md` updated
      first, then the schema, then `make gen` — same order as ADR-0002
      requires), `default: 0` (epoch sentinel) for BACKWARD compatibility.
- [x] Idempotent-upsert-safe production (no duplicate/gap under at-least-once
      redelivery) — ADR-0007's identity tuple; see Task 7 below for the
      consumer/producer semantics that make redelivery safe rather than
      lossy.
- [x] Apply `Instrument.contract_size` to `quant-core`'s per-unit
      `PricingResult` exactly once, at the position level, when combining a
      priced position into `price` and each cash Greek (ADR-0014, ADR-0017
      — `quant-core` itself never sees or applies this multiplier). Test: a
      position with a non-unit `contract_size` (e.g. 100) must produce a
      portfolio value/cash Greek that fails if the multiplication is
      removed — not a general pricing-smoke test, one that specifically
      pins the multiplier being applied. **Verified with teeth**: the
      multiplication was deleted, the test was watched to fail, then
      restored — see session log.
- [x] The `float64 -> Decimal` conversion for each cash Greek goes through
      `quant_core.numeric.to_money` (ADR-0013) — no second rounding
      implementation here. `pricer/pricing.py:aggregate_position`.
- [x] Regression test (ADR-0017): summing raw per-unit `PricingResult.gamma`
      across two positions in *different* underlyings must NOT be what the
      cash-Greek aggregation code does — assert the aggregated
      `cash_gamma` is not equal to (or derived from) a naive sum of raw
      per-unit gammas across underlyings. This is a test for the specific
      mistake ADR-0017 exists to prevent, not just a test that the correct
      formula happens to be implemented. **Verified with teeth**: the
      aggregation was replaced with a naive raw-gamma sum, the test was
      watched to fail, then restored — see session log.
- [x] Emission policy (Task 6, Q1): one `RiskSnapshot` per affected
      portfolio per tick — no coalescing. **This is a real fan-out**: one
      tick produces as many snapshots as portfolios holding that
      instrument, and at NFR load (1,000 ticks/sec) that multiplies
      directly into `risk.snapshots` write volume. Measured on the fixture
      portfolios (`services/pricer/fixtures/`, 2 portfolios): fan-out was 1
      (tick on an instrument only one portfolio had a known price for yet)
      or 2 (both portfolios primeable) per tick, never higher only because
      the fixture has 2 portfolios total. **Coalescing is explicitly a Q2
      decision, not made here — one constraint recorded now**: any future
      coalescing must be keyed on event time, never wall-clock batching. A
      wall-clock timer makes output depend on machine speed and destroys
      replay determinism, the exact property Task 3/`docs/conventions.md`
      protects.
- [x] Manual offset commits (Task 7), never auto-commit: a tick's offset is
      committed only after every snapshot it produced has been durably
      flushed to `risk.snapshots` (`quant_io.consumer.AvroConsumer` now
      defaults `enable_auto_commit=False`). Idempotent producer settings
      (`enable.idempotence=true`, `acks=all`) as in `quant-io`'s existing
      producer wrapper — unchanged, this workstream is just its second
      real caller.
- [x] `libs/quant-io` extended with the `portfolio.state` and
      `risk.snapshots` producer/consumer pairs
      (`quant_io/portfolio_state_io.py`, `quant_io/risk_snapshot_io.py`),
      plus `AvroConsumer` gained manual-commit and partition-EOF support
      (`quant_io/consumer.py`) — closing the open items left in that
      workstream's `PLAN.md` last session, now that a real caller (this
      one) exists. See that `PLAN.md`'s own session log.

## Explicitly out of scope
- Portfolio-level VaR computation (Q2) — `var_95` is produced but not yet
  meaningfully computed; a stub value is acceptable this quarter with that
  noted in the PR.
- Correlated cross-portfolio risk (Q3).
- Monte Carlo pricing (Q3, ADR-0006) — Q1 only prices instruments
  `quant-core` supports (vanilla European options), via closed form.
- Calling back into `core-service` for anything — forbidden by ADR-0003, not
  just out of scope.

## Extended scope, Q2
- [x] Structured unpriceable-portfolio reporting (ADR-0018), owner Eng-B,
  Q2: `PricerService._report_unpriceable` (`pricer/service.py`) logs a
  structured WARNING (`event=portfolio_unpriceable`, with `portfolio_id`,
  `reason`, `trigger`, `missing` all as `extra=` attributes, never only
  free text) and increments a `collections.Counter` keyed by the new
  `UnpriceableReason` enum (`pricer/pricing.py`), exposed read-only via
  `PricerService.unpriceable_counts`. The counter counts *events*, not
  distinct portfolios -- a portfolio skipped on every tick increments its
  reason once per tick. All three of `_price_portfolio`'s existing skip
  paths (no reference data, no observed price, `UnpricableInstrumentError`)
  now report before returning `None`; `_apply_portfolio_message` also
  reports at portfolio-update time for any position whose instrument_id
  has no reference data, since `PortfolioView` only indexes positions with
  reference data and such a portfolio would otherwise never be affected by
  a tick and never be reported at all. Tests:
  `services/pricer/tests/test_unpriceable_reporting.py`, all four
  asserting on the log record's structured attributes and on
  `unpriceable_counts`, never only on the absence of a snapshot.
  Follow-up, same owner/quarter: `_price_portfolio` evaluates the whole
  portfolio before reporting, at most one event per portfolio per tick, in
  fixed precedence (missing reference data, then unpriced underlyings,
  then per-position pricing failures), with `missing` naming every
  affected id rather than only the first found, and a new `detail` field
  on `_report_unpriceable` carrying the joined `UnpricableInstrumentError`
  message(s) so the reason a position couldn't be priced isn't lost from
  the log.
- `pricer/pricing.py:price_instrument`'s six `assert` statements (one
  instrument-type branch) were replaced with an explicit check that raises
  `UnpricableInstrumentError` naming the instrument_id and the missing
  field(s), while implementing the above. This is defence in depth, not a
  reachable path today: `InstrumentReference.__post_init__`
  (`pricer/reference_data.py`) already rejects an incomplete
  `VANILLA_EUROPEAN_OPTION` at fixture-load time, so no position holding
  one can ever reach `price_instrument` with a missing field through the
  fixture-loading path this service uses. Untested for that reason -- there
  is no way to construct the failing input without bypassing
  `InstrumentReference` itself.
- [x] Consume `market.curves` for option market inputs (ADR-0027), owner
  Eng-B, Q2: `pricer/curve_view.py`'s `CurveView` materializes
  `(scenario_id, kind, curve_id) -> MarketCurve`, hydrated in `hydrate()`
  alongside `portfolio.state` (a shared private helper,
  `PricerService._hydrate_to_end`, drives both, against one deadline each)
  and kept current the same way `portfolio.state` updates are drained
  before each tick. An invalid or key/value-mismatched record supersedes
  and removes the previous value rather than leaving it in place -- the
  producer has already superseded it, and pricing from a stale value would
  be a wrong number (ADR-0018, ADR-0027 Decision 3) -- logged as a
  structured WARNING (`event=market_curve_rejected`) and counted via
  `PricerService.rejected_curve_count`. `_price_portfolio` gained a new
  precedence step, `MISSING_CURVE` (ADR-0027 Decision 9): a
  `VANILLA_EUROPEAN_OPTION` position missing any of its three required
  curves (`RISK_FREE_RATE` for currency, `VOLATILITY`/`DIVIDEND_YIELD` for
  underlying_id), looked up under the triggering tick's `scenario_id`, is
  reported with every missing key as `KIND:curve_id`, ranked between
  `NO_PRICE` and `INSTRUMENT_NOT_PRICEABLE`. `pricer/pricing.py`'s
  `price_instrument` no longer reads
  `reference.volatility`/`risk_free_rate`/`dividend_yield` at all --
  `OptionMarketInputs`, built from the looked-up curves, is now the sole
  source. `oldest_input_event_time` deliberately still excludes curve
  event_times: curves are constant per scenario with event_time equal to
  the scenario start (ADR-0027 Decisions 4/5), so including them would pin
  the field to the scenario start and remove its staleness meaning for
  prices. Tests: `services/pricer/tests/test_market_curves.py` (missing
  single curve, wrong-scenario curves, NO_PRICE/MISSING_CURVE precedence,
  hydration-time rejection, key/value mismatch, a live curve update before
  ticks, and a hydration-timeout case naming the topic). Follow-up, next
  session: `instruments.yaml`'s now-unused `volatility`/`risk_free_rate`/
  `dividend_yield` fields and `fixtures/generate_golden_snapshots.py` are
  retired -- both were kept this session only so the golden pipeline could
  prove curve-sourced inputs equal the fixture-sourced ones it already
  pinned. Done: the fields and their `InstrumentReference` attributes are
  gone, and the golden generator now reads `fixtures/curves.yaml`
  (regenerating `golden_snapshots.json` is byte-identical). Open decision (not implemented this session, recommendation only
  -- see session log): the last-price cache (`_last_price`) is not
  scenario-scoped, so a portfolio can combine one scenario's prices with
  another scenario's curves.
- [x] Reporting currency (ADR-0028 Decisions 1, 2 and 6), owner Eng-B, Q2:
  `PortfolioView` now stores each portfolio's `base_currency` from the
  `PortfolioState` message (`view.base_currency(portfolio_id)`), and
  `_price_portfolio` checks it first: an empty value is reported
  `UNKNOWN_BASE_CURRENCY` (`UnpriceableReason`, trigger `tick`, `missing` =
  `[portfolio_id]`), ranked ahead of `NO_REFERENCE_DATA`, and produces no
  snapshot -- an empty currency is never treated as USD. Every published
  `RiskSnapshot` carries the portfolio's `base_currency`, so it is never
  empty. **No conversion yet:** FX is not in the required-curve set, and a
  mixed-currency portfolio is still summed across currencies until ADR-0028
  Decision 3 lands in a later session. Fixtures: `portfolios.yaml` gained
  `base_currency` (USD) per portfolio, `PortfolioFixture` carries it as a
  required field with no default (all twelve test constructions pass an
  explicit USD), `seed_portfolios` uses it, and the golden generator writes
  it from the fixture -- `golden_snapshots.json` changed only by the added
  key, no numeric value moved. Tests: `tests/test_base_currency.py` (an
  empty-currency portfolio is refused despite being otherwise priceable,
  and a normal portfolio's consumed snapshots carry USD).
- [x] FX conversion at aggregation (ADR-0028 Decisions 3, 4, 5 and 7), owner
  Eng-B, Q2: after `aggregate_position`, a position whose currency differs
  from the portfolio's `base_currency` is converted with
  `pricing.convert_contribution` (each of the six fields through
  `quant_core.numeric.convert_money`, decimal throughout, rounded once at
  scale 8 per position, before `aggregate_portfolio` sums) using the direct
  `FX_RATE` curve `<position currency><base currency>` under the triggering
  tick's `scenario_id`, never inverted or derived (ADR-0027). EVERY position
  type requires it, not only options: the required-curve pass adds
  `(FX_RATE, pair)` for any position not in the base currency, and a missing
  pair is `MISSING_CURVE` listing `FX_RATE:<pair>` with the other missing
  keys. A same-currency position is untouched: no lookup, no multiplication,
  no re-rounding. A rate that is not finite and strictly positive does not
  escape and kill the tick loop: that position fails as
  `INSTRUMENT_NOT_PRICEABLE` with a detail saying the FX rate for the pair is
  invalid and giving the value. *Update (quant-io session, Q2, Eng-B):* the
  shared validator in `libs/quant-io` now rejects a non-positive `FX_RATE` at
  the producer and again in `CurveView.apply`, so such a rate can no longer
  reach the pricer through Kafka -- it is rejected at consume time
  (`market_curve_rejected`, `rejected_curve_count`) and the pair is simply
  missing, reported `MISSING_CURVE` listing `FX_RATE:<pair>`. The per-position
  catch stays as defence in depth for any future caller that puts a curve into
  the view another way, and is covered by a `convert_contribution` unit test
  in `tests/test_aggregation.py`; the earlier end-to-end bad-rate test in
  `tests/test_fx_conversion.py` was replaced by one of the real behaviour
  (a raw-published zero rate rejected at consume, the pair reported missing,
  the loop surviving), because the state the old test simulated is now
  unreachable. Tick currency (Decision 7): a tick whose currency differs from
  its instrument's reference-data currency is rejected before its price or
  event time is cached (logged WARNING `tick_currency_mismatch`, counted in
  `PricerService.tick_currency_mismatch_count`, offset committed, no
  snapshot); a tick for an instrument absent from reference data is cached
  as before. `var_95` is still hard-coded to `0.0`; its currency treatment is
  decided when VaR is built. Tests: `tests/test_fx_conversion.py` (mixed
  USD/EUR equities against hand-worked decimals, missing FX curve, a EUR
  option's full required set, same-currency needing no curve, a mismatched
  tick leaving the cached price unchanged, and a zero FX rate not killing the
  loop); the golden pipeline and replay determinism tests pass untouched and
  `golden_snapshots.json` is byte-identical.

## Boundaries
- **Owns:** `services/pricer/**`.
- **Must not touch:** `libs/quant-core` internals (may depend on it),
  `contracts/` (coordinate with Eng-A for any schema change).
- **Depends on:** `contracts/avro/{tick,portfolio-state,risk-snapshot}.avsc`
  (ADR-0002), ADR-0003, ADR-0004, ADR-0005, ADR-0007, ADR-0013 (the one
  Decimal<->float64 boundary conversion, `quant_core.numeric.to_money`),
  ADR-0014 (quant-core prices per unit of underlying; this service owns
  `contract_size`), ADR-0017 (cash Greek aggregation formulas), `libs/quant-core`,
  `libs/quant-io`.

## Interfaces
Consumes `market.ticks` and `portfolio.state`. Produces `risk.snapshots`, schema
`contracts/avro/risk-snapshot.avsc`.

## Definition of done
- [x] Deliverables above complete
- [x] Tests per `docs/test-strategy.md` (contract tests + the recovery test
      for the "kill mid-stream" requirement) — testcontainers throughout,
      `services/pricer/tests/`: hydration gate, reverse index / position
      removal, aggregation (ADR-0014/ADR-0017 regression tests, verified
      with teeth), replay determinism, golden pipeline (independently
      computed, `fixtures/generate_golden_snapshots.py`), staleness
      (`oldest_input_event_time`), restart (no gaps, duplicates safe — plus
      one test that honestly characterizes a real gap, see Open questions),
      tombstone.
- [x] Contract tests pass against `contracts/` (risk-snapshot schema
      round-trips, cross-language decimal fidelity, schema evolution —
      `contracts/tests/python`, updated for the new field)
- [x] Docs updated (`docs/domain-model.md`, `docs/conventions.md` untouched
      this session — no new convention introduced beyond what ADR-0017
      already recorded)
- [ ] NFR targets in `docs/nfr-budget.md` met or an ADR explains the
      deviation (latency p99 ≤ 250ms — not measured this session; this
      session's tests exercise correctness, not load. Q1's own throughput
      deferral precedent (`services/ingest/PLAN.md`) applies here too — a
      real latency measurement needs the full pipeline (ingest -> pricer ->
      core-service -> dashboard) running together, which doesn't exist yet.
      Owner: whoever's session first wires the full pipeline end to end.)

## Open questions
- ~~How per-position Greeks aggregate into `RiskSnapshot`'s portfolio-level
  fields~~ **Resolved: `docs/adr/0017-cash-greeks.md`.** Cash Greeks
  (currency amounts, `Decimal(38,8)`, 1% basis for delta/gamma), not raw
  per-unit Greeks summed across underlyings — see that ADR for why and the
  exact formulas. This workstream implements the formulas; see the
  deliverables above.
- ~~Storage for the local materialized `portfolio.state` view~~ **Resolved
  for Q1: in-memory, rebuilt from scratch on every restart** (a fresh,
  unique consumer group id every `hydrate()` call forces a full replay from
  the beginning of the compacted topic — ADR-0003's own stated design).
  Simple and correct for the view itself. It does **not**, however, extend
  to the tick-derived last-known-price cache — see the next item, a gap
  this resolution exposed.
- **New, discovered by this session's restart test
  (`services/pricer/tests/test_restart.py::
  test_price_cache_does_not_survive_restart`).** `PricerService`'s
  last-known-price-per-instrument cache (`_last_price`/`_last_event_time`)
  is in-memory only and has no equivalent recovery to the portfolio view's.
  On restart, the tick consumer resumes from its last *committed* offset
  (correctly, per Task 7) — but that means ticks consumed and committed
  *before* the crash are never redelivered, so their prices are gone from
  the new process's cache. A portfolio holding positions on multiple
  underlyings can silently stop producing snapshots after a restart until
  *every one* of its underlyings has ticked again post-restart — which,
  for a slow-ticking instrument, could be a long silent gap with no error
  anywhere. The portfolio-view analogy ("just replay from the start") does
  not transfer: `market.ticks` is unbounded and high-volume, not
  compacted, so replaying it in full on every restart doesn't scale.
  Real fixes (not attempted this session): persist last-known prices to a
  local embedded store checkpointed periodically, or a small
  `last-price`-per-instrument compacted topic derivable the same way
  `portfolio.state` is. Owner: Eng-B, by-when: before this pricer is run
  continuously against a real multi-hour feed (a demo/Q2 concern, not
  blocking Q1's "prove the pipe connects").
- **New.** Instrument static reference data (strike, expiry, option_type,
  contract_size, currency, underlying_id per `docs/domain-model.md
  #Instrument`) has no wire representation anywhere in `contracts/avro/` --
  `portfolio.state`'s `Position` carries only `instrument_id`/`quantity`/
  `average_cost`/`as_of_event_time`, and `market.ticks` carries only a
  price. No ADR covers where this should come from. This session's judgment
  call: a checked-in static YAML fixture
  (`services/pricer/fixtures/instruments.yaml`, loaded by
  `pricer/reference_data.py`), narrow and reversible, standing in for a
  real reference-data feed. Flagged per root `CLAUDE.md`'s "if a decision
  should exist and doesn't, stop and say so" -- this workstream could not
  literally stop (there is no pricer without *some* answer), so the
  decision is surfaced here instead, for Eng-A to turn into a real ADR
  before `core-service` needs to actually publish this data. Owner: Eng-A,
  by-when: before Q2 (when a second portfolio/instrument-consuming service
  would otherwise duplicate this same judgment call independently). The
  market-rate assumptions Black-Scholes needs (volatility, risk_free_rate,
  dividend_yield) *do* now have a wire representation: `market.curves`,
  ADR-0027, which this service consumes (see Extended scope, Q2).
- Currency: cash Greeks are summable across underlyings, not across
  currencies. A EUR position aggregated into a USD portfolio total without
  conversion is silently wrong. Deliberately NOT owned here — see root
  `PLAN.md`'s open questions, ahead of Q2 portfolio VaR.

## Session log
- 2026-08-31 (contracts session, Eng-A): `contracts/avro/risk-snapshot.avsc`
  gained real fields this session — `portfolio_value` renamed `price`,
  the `greeks` map replaced with discrete Greek fields, and `scenario_id`
  added (propagate from the `Tick`s that produced this snapshot).
- 2026-08-31 (later same session, Eng-A): those discrete Greek fields were
  still raw per-unit Greeks, which don't aggregate meaningfully across a
  portfolio's different underlyings. Resolved via ADR-0017 (cash Greeks) —
  see Open questions and the updated deliverables above.
- 2026-08-30 (this session): Built `services/pricer` end to end. Hydration
  gate (`pricer/service.py:hydrate`) blocks on `portfolio.state` reaching
  end-of-partition (via `quant_io`'s new `enable_partition_eof`/
  `PartitionEOF`) before `market.ticks` is even subscribed to — verified by
  a test producing a tick *before* hydration starts and confirming it's
  still correctly priced only after hydration completes, never before or
  twice. Reverse index (`pricer/portfolio_view.py`) keyed by
  `underlying_id`; position-removal and tombstone tests both pass,
  including one for a tombstone racing a create *before* the pricer ever
  starts (nets to "deleted," correctly).
  `oldest_input_event_time` added to `contracts/avro/risk-snapshot.avsc`
  (docs first, then schema, then `make gen` for both languages) — this also
  required fixing the two hand-written cross-language test fixtures
  (`contracts/tests/python/test_cross_language_decimal.py`,
  `contracts/generated/java/src/test/java/.../RoundTripTest.java` and
  `CrossLanguageDecimalTool.java`) that construct a `RiskSnapshot`
  positionally and don't get the new field for free.
  Both ADR-0014 and ADR-0017 regression tests were verified with teeth per
  this session's instructions: the contract-size multiplication and the
  cash-Greek aggregation were each independently deleted/replaced with the
  exact wrong-but-plausible implementation, the corresponding test was
  watched to fail, then the code was restored — see the report delivered
  alongside this commit for the exact failure output.
  Discovered and fixed a real module-name collision: `services/ingest/
  tests/kafka_helpers.py` and this workstream's own test helper module
  shared a bare module name with no package structure, so running
  `pytest libs services` together (as `make test` does) silently imported
  whichever one Python happened to cache first for both test suites. Fixed
  by renaming this workstream's helper to `pricer_test_helpers.py` rather
  than restructuring `services/ingest`'s existing tests.
  Two judgment calls without a governing ADR, both flagged in Open
  questions above: instrument static reference data / market-rate
  assumptions (a checked-in fixture, `pricer/reference_data.py`), and — not
  a judgment call so much as an honest limitation — the tick-derived
  price cache does not survive a restart, unlike the portfolio view.
  `quant_core.PRICER_VERSION` was **not** bumped: no pricing-model behavior
  changed this session (only orchestration, aggregation, and I/O around
  the existing Black-Scholes implementation). Still `0.1.0`.
