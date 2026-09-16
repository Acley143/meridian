"""The tick feed: scenario -> simulated path -> `Tick` -> `market.ticks`.

This is the one place a `Tick` is constructed (ADR-0011, ADR-0005) and
therefore the one place `event_time` is set. `event_time` comes from
`Scenario.event_time(i)` — scenario arithmetic, never the wall clock
(docs/conventions.md). `ingest_time` is stamped here, at the moment of
production, via `quant_io.clock.now_utc`.

Per ADR-0027 Decision 4, a scenario's declared curves are published once,
as a single batch, before any tick is produced — `event_time` for every
curve is the scenario's `start_time`, not per-tick. If the batch does not
deliver, `publish_scenario_curves` raises and no tick is produced either.

After the tick loop, `producer.flush()`'s outstanding count is checked: a
dropped tick is a permanent gap in risk history, so any undelivered tick
raises `DeliveryError` rather than being silently swallowed.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from enum import Enum
from logging import LoggerAdapter

from meridian_contracts.market_curves import CurveKind, MarketCurve
from meridian_contracts.tick import Tick
from quant_core.simulation import PathParams, simulate_path
from quant_io.clock import now_utc
from quant_io.market_curve_io import MarketCurveProducer
from quant_io.producer import DeliveryError
from quant_io.tick_producer import TickProducer

from ingest.logging_config import get_scenario_logger
from ingest.scenario import CurveConfig, InstrumentConfig, Scenario
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


def _market_curve(scenario: Scenario, curve: CurveConfig, ingest_time: datetime) -> MarketCurve:
    return MarketCurve(
        scenario_id=scenario.scenario_id,
        kind=CurveKind(curve.kind),
        curve_id=curve.curve_id,
        value_float=curve.value_float,
        value_decimal=curve.value_decimal,
        event_time=scenario.start_time,
        ingest_time=ingest_time,
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
    curve_producer: MarketCurveProducer | None = None,
) -> int:
    """Produce every tick of `scenario` to `producer`, in event-time order
    per instrument (ADR-0016). Returns the number of ticks produced."""
    log = logger or get_scenario_logger(scenario.scenario_id)

    if scenario.curves:
        if curve_producer is None:
            raise ValueError(f"scenario {scenario.scenario_id} declares curves but no curve producer was given")
        curves = [_market_curve(scenario, curve, now()) for curve in scenario.curves]
        curve_producer.publish_scenario_curves(curves)
        log.info("published %d curves", len(curves))
    else:
        log.info("no curves declared")

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

    outstanding = producer.flush()
    if outstanding != 0:
        raise DeliveryError(f"{outstanding} market.ticks message(s) not delivered after flush")
    log.info("feed complete: %d ticks produced", produced)
    return produced
