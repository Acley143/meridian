"""Shared loader for services/pricer/fixtures/*.yaml -- used by both
`generate_golden_snapshots.py` and the test suite that seeds
`portfolio.state`/`market.ticks` from these files. Fixture *loading* is
shared between the generator and the tests; fixture *processing* (pricing,
aggregation, "which portfolios are affected") is deliberately not, so the
golden file is an independent check, not a tautology.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import yaml
from meridian_contracts.market_curves import CurveKind, MarketCurve
from meridian_contracts.portfolio_state import Position

FIXTURES_DIR = Path(__file__).resolve().parent


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass(frozen=True)
class PortfolioFixture:
    portfolio_id: str
    positions: list[Position]
    event_time: datetime
    base_currency: str


def load_portfolio_fixtures(path: Path = FIXTURES_DIR / "portfolios.yaml") -> list[PortfolioFixture]:
    raw = yaml.safe_load(path.read_text())
    fixtures = []
    for portfolio_id, cfg in raw["portfolios"].items():
        event_time = parse_dt(cfg["event_time"])
        positions = [
            Position(
                portfolio_id=portfolio_id,
                instrument_id=p["instrument_id"],
                quantity=Decimal(str(p["quantity"])),
                average_cost=Decimal(str(p["average_cost"])),
                as_of_event_time=event_time,
            )
            for p in cfg["positions"]
        ]
        fixtures.append(
            PortfolioFixture(
                portfolio_id=portfolio_id,
                positions=positions,
                event_time=event_time,
                base_currency=cfg["base_currency"],
            )
        )
    return fixtures


@dataclass(frozen=True)
class TickFixture:
    instrument_id: str
    price: Decimal
    currency: str
    event_time: datetime


def load_tick_fixtures(path: Path = FIXTURES_DIR / "ticks.yaml") -> tuple[str, list[TickFixture]]:
    raw = yaml.safe_load(path.read_text())
    ticks = [
        TickFixture(
            instrument_id=t["instrument_id"],
            price=Decimal(str(t["price"])),
            currency=t["currency"],
            event_time=parse_dt(t["event_time"]),
        )
        for t in raw["ticks"]
    ]
    return raw["scenario_id"], ticks


def load_curve_fixtures(path: Path = FIXTURES_DIR / "curves.yaml") -> list[MarketCurve]:
    raw = yaml.safe_load(path.read_text())
    scenario_id = raw["scenario_id"]
    event_time = parse_dt(raw["event_time"])
    return [
        MarketCurve(
            scenario_id=scenario_id,
            kind=CurveKind(c["kind"]),
            curve_id=c["curve_id"],
            value_float=float(c["value"]),
            value_decimal=None,
            event_time=event_time,
            ingest_time=event_time,
        )
        for c in raw["curves"]
    ]
