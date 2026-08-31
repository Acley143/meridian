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
  #Instrument`) and the market-rate assumptions Black-Scholes needs
  (volatility, risk_free_rate, dividend_yield) have no wire representation
  anywhere in `contracts/avro/` — `portfolio.state`'s `Position` carries
  only `instrument_id`/`quantity`/`average_cost`/`as_of_event_time`, and
  `market.ticks` carries only a price. No ADR covers where this should come
  from. This session's judgment call: a checked-in static YAML fixture
  (`services/pricer/fixtures/instruments.yaml`, loaded by
  `pricer/reference_data.py`), narrow and reversible, standing in for a
  real reference-data feed. Flagged per root `CLAUDE.md`'s "if a decision
  should exist and doesn't, stop and say so" — this workstream could not
  literally stop (there is no pricer without *some* answer), so the
  decision is surfaced here instead, for Eng-A to turn into a real ADR
  before `core-service` needs to actually publish this data. Owner: Eng-A,
  by-when: before Q2 (when a second portfolio/instrument-consuming service
  would otherwise duplicate this same judgment call independently).
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
