"""The ADR-0031 accuracy budget at 2,000 fixed points inside the validated
domain D, through the public pricer.

The points are the first 2,000 that the Step 1f sampler drew inside D
(american_domain_reference.json); the reference is the production lattice
at N=4096, and its own error is estimated as |P(4096) - P(2048)|.

Step 1f's rule: a point is resolved when the reference error is at most a
third of the measured error. A resolved point must have measured error
within the budget; an unresolved one must have measured plus reference
error within it, so a noisy reference can never hide a miss.
"""
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from quant_core.pricing import american
from quant_core.types import AmericanOption, MarketState, OptionRight

_VALUATION_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_ROWS = json.loads((Path(__file__).parent / "american_domain_reference.json").read_text())


def _within_budget(measured: float, reference_error: float, bound: float) -> bool:
    if reference_error <= measured / 3.0:
        return measured <= bound
    return measured + reference_error <= bound


def _misses(row: dict[str, Any]) -> list[str]:
    option = AmericanOption(
        underlying_id="TEST",
        strike=Decimal(str(row["strike"])),
        expiry=_VALUATION_TIME + timedelta(days=row["time_to_expiry_years"] * 365),
        right=OptionRight.CALL if row["is_call"] else OptionRight.PUT,
    )
    market = MarketState(
        spot=Decimal(str(row["spot"])),
        volatility=row["volatility"],
        risk_free_rate=row["risk_free_rate"],
        dividend_yield=row["dividend_yield"],
        valuation_time=_VALUATION_TIME,
    )
    result = american.price(option, market)  # raises ModelDomainError if the point is outside D

    price_error = abs(float(result.price) - row["p4096"])
    price_reference_error = abs(row["p4096"] - row["p2048"])
    price_bound = max(1e-2 * abs(row["p4096"]), 1e-3 * row["strike"])
    delta_error = abs(result.delta - row["d4096"])
    delta_reference_error = abs(row["d4096"] - row["d2048"])
    misses = []
    if not _within_budget(price_error, price_reference_error, price_bound):
        misses.append(f"price error {price_error} (reference error {price_reference_error}, bound {price_bound}) at {row}")
    if not _within_budget(delta_error, delta_reference_error, 2e-2):
        misses.append(f"delta error {delta_error} (reference error {delta_reference_error}) at {row}")
    return misses


def test_budget_at_every_fixed_point() -> None:
    assert len(_ROWS) == 2000
    misses = [m for row in _ROWS for m in _misses(row)]
    assert not misses, "\n".join(misses)
