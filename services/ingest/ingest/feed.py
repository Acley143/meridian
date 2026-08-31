"""The tick feed: scenario -> simulated path -> `Tick` -> `market.ticks`.

This is the one place a `Tick` is constructed (ADR-0011, ADR-0005) and
therefore the one place `event_time` is set. `event_time` comes from
`Scenario.event_time(i)` — scenario arithmetic, never the wall clock
(docs/conventions.md). `ingest_time` is stamped here, at the moment of
production, via `quant_io.clock.now_utc`.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from enum import Enum
from logging import LoggerAdapter

from meridian_contracts.tick import Tick
from quant_core.simulation import PathParams, simulate_path
from quant_io.clock import now_utc
from quant_io.tick_producer import TickProducer

from ingest.logging_config import get_scenario_logger
from ingest.scenario import InstrumentConfig, Scenario
from ingest.seeding import derive_path_seed

_SECONDS_PER_YEAR = 365 * 24 * 3600


class PacingMode(str, Enum):
    """Two pacing modes producing identical data, differing only in
    wall-clock timing (docs/conventions.md). Pacing must never touch
    `event_time` — if changing modes changes the data, the mode is a bug."""

    REALTIME = "realtime"
    REPLAY = "replay"


def _path_params(instrument: InstrumentConfig, scenario: Scenario) -> PathParams:
    dt_years = scenario.tick_interval.total_seconds() / _SECONDS_PER_YEAR
    return PathParams(
        s0=instrument.s0,
        drift=instrument.drift,
        volatility=instrument.volatility,
        dt=dt_years,
    )


def run_feed(
    scenario: Scenario,
    producer: TickProducer,
    pacing: PacingMode,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = now_utc,
    logger: LoggerAdapter | None = None,
) -> int:
    """Produce every tick of `scenario` to `producer`, in event-time order
    per instrument (ADR-0016). Returns the number of ticks produced."""
    log = logger or get_scenario_logger(scenario.scenario_id)

    paths: dict[str, list[Decimal]] = {
        instrument_id: list(
            simulate_path(
                derive_path_seed(
                    scenario_id=scenario.scenario_id,
                    scenario_seed=scenario.seed,
                    instrument_id=instrument_id,
                ),
                _path_params(instrument, scenario),
                scenario.tick_count,
            )
        )
        for instrument_id, instrument in scenario.instruments.items()
    }

    log.info(
        "starting feed: %d instruments, %d ticks each, pacing=%s",
        len(paths),
        scenario.tick_count,
        pacing.value,
    )

    start_clock = clock()
    produced = 0
    for tick_index in range(scenario.tick_count):
        if pacing is PacingMode.REALTIME:
            target = start_clock + tick_index * scenario.tick_interval.total_seconds()
            delay = target - clock()
            if delay > 0:
                sleep(delay)

        event_time = scenario.event_time(tick_index)
        for instrument_id, instrument in scenario.instruments.items():
            tick = Tick(
                instrument_id=instrument_id,
                price=paths[instrument_id][tick_index],
                currency=instrument.currency,
                event_time=event_time,
                ingest_time=now(),
                scenario_id=scenario.scenario_id,
            )
            producer.produce_tick(tick)
            produced += 1

    producer.flush()
    log.info("feed complete: %d ticks produced", produced)
    return produced
