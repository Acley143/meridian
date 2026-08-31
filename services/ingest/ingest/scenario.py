"""Scenario loading (ADR-0006, ADR-0011).

A scenario is a named, seeded, reproducible market-data recipe: the same
`scenario_id` must always yield a byte-identical tick stream. Changing any
parameter of a checked-in scenario file therefore requires a new
`scenario_id` — silently editing one under a stable id would make every
historical `Tick`/`RiskSnapshot` tagged with it a lie about what data
actually produced it. See `services/ingest/scenarios/README.md`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import yaml


@dataclass(frozen=True)
class InstrumentConfig:
    """GBM path parameters for one simulated instrument (see
    `quant_core.simulation.PathParams`, which this maps onto)."""

    s0: Decimal
    drift: float
    volatility: float
    currency: str


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    seed: int
    start_time: datetime
    tick_interval: timedelta
    tick_count: int
    instruments: dict[str, InstrumentConfig]

    def __post_init__(self) -> None:
        if self.start_time.tzinfo is None or self.start_time.tzinfo.utcoffset(self.start_time) is None:
            raise ValueError(
                f"scenario {self.scenario_id!r}: start_time must be a timezone-aware "
                "UTC datetime (ADR-0005)"
            )
        if self.tick_count < 0:
            raise ValueError(f"scenario {self.scenario_id!r}: tick_count must be non-negative")
        if self.tick_interval <= timedelta(0):
            raise ValueError(f"scenario {self.scenario_id!r}: tick_interval must be positive")
        if not self.instruments:
            raise ValueError(f"scenario {self.scenario_id!r}: must declare at least one instrument")

    def event_time(self, tick_index: int) -> datetime:
        """`event_time` of tick `tick_index`, per docs/conventions.md: derived
        purely from the scenario's declared parameters, never from the wall
        clock."""
        return self.start_time + tick_index * self.tick_interval


def load_scenario(path: Path) -> Scenario:
    raw = yaml.safe_load(path.read_text())
    start_time = raw["start_time"]
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=UTC)

    instruments = {
        instrument_id: InstrumentConfig(
            s0=Decimal(str(cfg["s0"])),
            drift=float(cfg["drift"]),
            volatility=float(cfg["volatility"]),
            currency=str(cfg["currency"]),
        )
        for instrument_id, cfg in raw["instruments"].items()
    }

    return Scenario(
        scenario_id=raw["scenario_id"],
        seed=int(raw["seed"]),
        start_time=start_time,
        tick_interval=timedelta(seconds=float(raw["tick_interval_seconds"])),
        tick_count=int(raw["tick_count"]),
        instruments=instruments,
    )


def load_all_scenarios(scenarios_dir: Path) -> list[Scenario]:
    return [load_scenario(p) for p in sorted(scenarios_dir.glob("*.yaml"))]
