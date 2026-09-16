# Scenarios

A scenario is a named, seeded, reproducible tick stream: `scenario_id`,
`seed`, `start_time` (UTC), `tick_interval_seconds`, `tick_count`, and
per-instrument `PathParams` (`s0`, `drift`, `volatility`, `currency`).

A scenario may also declare an optional top-level `curves` list: the
`market.curves` values (ADR-0027) `services/ingest` publishes once, before
that scenario's first tick. Each entry has exactly the keys `kind`,
`curve_id`, `value`. `kind` is one of `RISK_FREE_RATE`, `VOLATILITY`,
`DIVIDEND_YIELD`, `FX_RATE`; `curve_id` means an ISO 4217 currency code for
`RISK_FREE_RATE`, an `underlying_id` for `VOLATILITY`/`DIVIDEND_YIELD`, and
a six-letter `FROMTO` pair for `FX_RATE`. `value` for `FX_RATE` must be a
quoted YAML string (parsed as `Decimal`); for every other kind, `value`
must be an unquoted number (parsed as `float`). Absent `curves` means the
scenario declares no curves.

**Changing any parameter of a scenario requires a new `scenario_id`.** A
scenario id names a specific reproducible tick stream — every consumer that
has ever seen ticks or derived `RiskSnapshot`s tagged with a given
`scenario_id` is entitled to assume that id always means the same market
data. Editing a checked-in scenario file's parameters under its existing
`scenario_id` breaks that assumption silently: every historical snapshot
tagged with it becomes a lie about what data actually produced it. To
change parameters, add a new file with a new `scenario_id` (e.g. bump a
trailing `-v2`) and leave the old one in place.

`test_scenarios.py` (in `services/ingest/tests/`) asserts every scenario
file in this directory has a unique `scenario_id`.

## Files

- `small-deterministic.yaml` — a handful of ticks across two instruments,
  for unit/contract tests.
- `small-deterministic-v2.yaml` — the same tick data as
  `small-deterministic.yaml`, plus a `curves` section (ADR-0027).
- `throughput-1000.yaml` — sized for the 1,000 ticks/sec sustained-throughput
  NFR (`docs/nfr-budget.md`): enough instruments and ticks that a `replay`
  pacing run of this scenario is a meaningful throughput sample, not a burst
  that finishes before steady state.
