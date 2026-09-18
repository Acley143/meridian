#!/usr/bin/env python3
"""Generates services/pricer/fixtures/golden_snapshots.json.

Independent of `pricer.portfolio_view`/`pricer.pricing`/`pricer.service` on
purpose -- this script re-derives "which portfolios are affected" by a
plain linear scan (not the reverse index) and re-derives each cash Greek by
writing the ADR-0014/ADR-0017 formulas out again inline (not calling
`pricer.pricing.aggregate_position`/`aggregate_portfolio`). It shares only
`quant_core` (the pricer under test doesn't reimplement Black-Scholes
either) and fixture *loading* of portfolios and ticks (`fixtures/loader.py`
-- parsing YAML isn't the logic being checked). Market inputs (volatility,
risk-free rate, dividend yield) come from `fixtures/curves.yaml`, parsed
inline here with `yaml.safe_load` rather than through the loader's curve
helper or any pricer code (ADR-0027). The golden-pipeline test in
`services/pricer/tests/test_golden_pipeline.py` runs the real
`PricerService` against these same fixtures and asserts its output matches
this file -- if the two independently-written aggregation implementations
ever agree on a wrong answer, that would be a remarkable coincidence, not a
silent tautology.

Run after changing any of fixtures/{instruments,portfolios,ticks,curves}.yaml:
    python3 services/pricer/fixtures/generate_golden_snapshots.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import yaml
from loader import PortfolioFixture, load_portfolio_fixtures, load_tick_fixtures
from quant_core import PRICER_VERSION
from quant_core.numeric import to_model, to_money
from quant_core.pricing.black_scholes import price as black_scholes_price
from quant_core.types import EuropeanOption, MarketState, OptionRight

_FIXTURES_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class _Instrument:
    instrument_type: str
    underlying_id: str
    currency: str
    contract_size: Decimal
    option_type: str | None
    strike: Decimal | None
    expiry: str | None


def _load_instruments() -> dict[str, _Instrument]:
    raw = yaml.safe_load((_FIXTURES_DIR / "instruments.yaml").read_text())
    out = {}
    for instrument_id, cfg in raw["instruments"].items():
        out[instrument_id] = _Instrument(
            instrument_type=cfg["instrument_type"],
            underlying_id=cfg["underlying_id"],
            currency=cfg["currency"],
            contract_size=Decimal(str(cfg["contract_size"])),
            option_type=cfg.get("option_type"),
            strike=Decimal(str(cfg["strike"])) if cfg.get("strike") is not None else None,
            expiry=cfg.get("expiry"),
        )
    return out


def _load_curves() -> dict[tuple[str, str], float]:
    """(kind, curve_id) -> value, parsed straight from curves.yaml."""
    raw = yaml.safe_load((_FIXTURES_DIR / "curves.yaml").read_text())
    out: dict[tuple[str, str], float] = {}
    for curve in raw["curves"]:
        key = (curve["kind"], curve["curve_id"])
        value = curve["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"curves.yaml: value for {key[0]}:{key[1]} must be a number, "
                f"got {type(value).__name__} {value!r}"
            )
        if key in out:
            raise ValueError(f"curves.yaml: duplicate curve {key[0]}:{key[1]}")
        out[key] = float(value)
    return out


def _curve(curves: dict[tuple[str, str], float], kind: str, curve_id: str) -> float:
    try:
        return curves[(kind, curve_id)]
    except KeyError:
        raise KeyError(f"curves.yaml has no curve {kind}:{curve_id}") from None


def _price_per_unit(
    instrument: _Instrument,
    spot: Decimal,
    valuation_time: datetime,
    curves: dict[tuple[str, str], float],
):
    if instrument.instrument_type == "EQUITY":
        return spot, 1.0, 0.0, 0.0, 0.0, 0.0  # price, delta, gamma, vega, theta, rho

    option = EuropeanOption(
        underlying_id=instrument.underlying_id,
        strike=instrument.strike,
        expiry=datetime.fromisoformat(instrument.expiry.replace("Z", "+00:00")),
        right=OptionRight[instrument.option_type],
    )
    market = MarketState(
        spot=spot,
        volatility=_curve(curves, "VOLATILITY", instrument.underlying_id),
        risk_free_rate=_curve(curves, "RISK_FREE_RATE", instrument.currency),
        dividend_yield=_curve(curves, "DIVIDEND_YIELD", instrument.underlying_id),
        valuation_time=valuation_time,
    )
    result = black_scholes_price(option, market)
    return result.price, result.delta, result.gamma, result.vega, result.theta, result.rho


def _affected_portfolios(
    instrument_id: str, portfolios: list[PortfolioFixture], instruments: dict[str, _Instrument]
) -> list[PortfolioFixture]:
    """Plain linear scan -- deliberately not the reverse index under test."""
    affected = []
    for portfolio in portfolios:
        for position in portfolio.positions:
            if instruments[position.instrument_id].underlying_id == instrument_id:
                affected.append(portfolio)
                break
    return affected


def main() -> None:
    instruments = _load_instruments()
    curves = _load_curves()
    portfolios = load_portfolio_fixtures()
    scenario_id, ticks = load_tick_fixtures()

    last_price: dict[str, Decimal] = {}
    last_event_time: dict[str, datetime] = {}
    golden: list[dict] = []

    for tick in ticks:
        last_price[tick.instrument_id] = tick.price
        last_event_time[tick.instrument_id] = tick.event_time

        for portfolio in _affected_portfolios(tick.instrument_id, portfolios, instruments):
            underlyings_used: set[str] = set()
            price_total = Decimal(0)
            cash_delta_total = Decimal(0)
            cash_gamma_total = Decimal(0)
            cash_vega_total = Decimal(0)
            cash_theta_total = Decimal(0)
            cash_rho_total = Decimal(0)
            skip = False

            for position in portfolio.positions:
                instrument = instruments[position.instrument_id]
                underlying_id = instrument.underlying_id
                if underlying_id not in last_price:
                    skip = True
                    break
                spot = last_price[underlying_id]

                pr_price, pr_delta, pr_gamma, pr_vega, pr_theta, pr_rho = _price_per_unit(
                    instrument, spot, tick.event_time, curves
                )

                q = to_model(position.quantity)
                c = to_model(instrument.contract_size)
                s = to_model(spot)
                mult = q * c

                price_total += to_money(to_model(pr_price) * mult)
                cash_delta_total += to_money(pr_delta * s * 0.01 * mult)
                cash_gamma_total += to_money(pr_gamma * s * s * 0.0001 * mult)
                cash_vega_total += to_money(pr_vega * mult)
                cash_theta_total += to_money(pr_theta * mult)
                cash_rho_total += to_money(pr_rho * mult)
                underlyings_used.add(underlying_id)

            if skip:
                continue

            oldest = min(last_event_time[u] for u in underlyings_used)
            golden.append(
                {
                    "portfolio_id": portfolio.portfolio_id,
                    "as_of": tick.event_time.isoformat(),
                    "pricer_version": PRICER_VERSION,
                    "price": str(price_total),
                    "cash_delta": str(cash_delta_total),
                    "cash_gamma": str(cash_gamma_total),
                    "cash_vega": str(cash_vega_total),
                    "cash_theta": str(cash_theta_total),
                    "cash_rho": str(cash_rho_total),
                    "var_95": 0.0,
                    "scenario_id": scenario_id,
                    "oldest_input_event_time": oldest.isoformat(),
                }
            )

    out_path = _FIXTURES_DIR / "golden_snapshots.json"
    out_path.write_text(json.dumps(golden, indent=2) + "\n")
    print(f"wrote {len(golden)} golden snapshot(s) to {out_path}")


if __name__ == "__main__":
    main()
