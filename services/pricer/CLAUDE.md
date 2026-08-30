# pricer

Python service that consumes `portfolio.state` and the tick stream,
materializes a local portfolio view, calls into `libs/quant-core` for
pricing, and produces `RiskSnapshot`s. Python 3.12.

- This service never calls back into `core-service` (ADR-0003) — all the
  state it needs arrives via Kafka. If you find yourself wanting a REST call
  back to the service, the design is wrong, not the code.
- All pricing math is delegated to `quant-core`; this service's own code is
  I/O, materialization, and orchestration only. If you're writing a pricing
  formula here instead of in `quant-core`, stop.
- Monte Carlo pricers must derive their seed exactly per ADR-0006
  (`blake2b(instrument_id ‖ as_of ‖ pricer_version)`) — never thread a random
  seed through from elsewhere.
- Produced `RiskSnapshot`s must be idempotent upserts keyed on
  `(portfolio_id, as_of_event_time, pricer_version)` (ADR-0007) — at-least-
  once delivery is assumed, not treated as a bug to work around.
- Local test command: `pytest services/pricer -q`.
- The one mistake most likely here: building the local `portfolio.state`
  materialized view as an accumulating diff instead of replacing it wholesale
  on each message — each `PortfolioState` message is the full current state,
  not a delta (see `docs/domain-model.md#portfoliostate`).
