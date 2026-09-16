"""Scenario loading (ADR-0006, ADR-0011).

A scenario is a named, seeded, reproducible market-data recipe: the same
`scenario_id` must always yield a byte-identical tick stream. Changing any
parameter of a checked-in scenario file therefore requires a new
`scenario_id` — silently editing one under a stable id would make every
historical `Tick`/`RiskSnapshot` tagged with it a lie about what data
actually produced it. See `services/ingest/scenarios/README.md`.

A scenario may also declare an optional top-level `curves` list: the
`market.curves` values (ADR-0027) that `ingest/feed.py` publishes once,
before that scenario's first tick. Each entry has exactly the keys `kind`,
`curve_id`, `value`. `kind` must be one of `meridian_contracts.market_curves
.CurveKind`'s values. For `FX_RATE`, `value` must be a YAML string (parsed
as `Decimal`); for every other kind, `value` must be a YAML int or float
(a YAML boolean is rejected, even though `bool` is a Python `int` subclass)
and is parsed as `float`. A `curves` list is optional; a scenario that omits
it declares no curves. No further validation happens here — the shared
`quant_io.market_curve_io.validate_market_curve` validator runs before any
curve is produced.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from meridian_contracts.market_curves import CurveKind

_CURVE_KIND_VALUES = {kind.value for kind in CurveKind}


@dataclass(frozen=True)
class InstrumentConfig:
    """GBM path parameters for one simulated instrument (see
    `quant_core.simulation.PathParams`, which this maps onto)."""

    s0: Decimal
    drift: float
    volatility: float
    currency: str


@dataclass(frozen=True)
class CurveConfig:
    """One `market.curves` value a scenario declares (ADR-0027). Exactly one
    of `value_float` / `value_decimal` is set, mirroring `MarketCurve`'s own
    exactly-one-of rule."""

    kind: str
    curve_id: str
    value_float: float | None
    value_decimal: Decimal | None


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    seed: int
    start_time: datetime
    tick_interval: timedelta
    tick_count: int
    instruments: dict[str, InstrumentConfig]
    curves: tuple[CurveConfig, ...] = ()

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


def _load_curves(scenario_id: str, raw_curves: list[dict[str, Any]] | None) -> tuple[CurveConfig, ...]:
    if not raw_curves:
        return ()

    seen: set[tuple[str, str]] = set()
    curves: list[CurveConfig] = []
    for entry in raw_curves:
        kind = entry["kind"]
        curve_id = entry["curve_id"]
        value = entry["value"]

        if kind not in _CURVE_KIND_VALUES:
            raise ValueError(f"scenario {scenario_id!r}: curve entry {entry!r} has unknown kind {kind!r}")

        dup_key = (kind, curve_id)
        if dup_key in seen:
            raise ValueError(
                f"scenario {scenario_id!r}: curve entry {entry!r} repeats (kind, curve_id) {dup_key}"
            )
        seen.add(dup_key)

        if kind == CurveKind.FX_RATE.value:
            if not isinstance(value, str):
                raise ValueError(
                    f"scenario {scenario_id!r}: curve entry {entry!r}: FX_RATE value must be a quoted string"
                )
            curves.append(
                CurveConfig(kind=kind, curve_id=curve_id, value_float=None, value_decimal=Decimal(value))
            )
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"scenario {scenario_id!r}: curve entry {entry!r}: {kind} value must be a number"
                )
            curves.append(
                CurveConfig(kind=kind, curve_id=curve_id, value_float=float(value), value_decimal=None)
            )
    return tuple(curves)


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
        curves=_load_curves(raw["scenario_id"], raw.get("curves")),
    )


def load_all_scenarios(scenarios_dir: Path) -> list[Scenario]:
    return [load_scenario(p) for p in sorted(scenarios_dir.glob("*.yaml"))]
