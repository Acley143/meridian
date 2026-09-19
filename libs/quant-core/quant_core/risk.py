"""1-day 95% parametric (delta-normal) Value at Risk (ADR-0029).

`delta_normal_var_95` is a pure function of inputs the caller assembles: one
`PositionRisk` per position. It reads no history, draws from no RNG, and
consults no clock. Assembling those inputs -- pricing each position, applying
`contract_size`, converting into the portfolio's reporting currency, looking
up each underlying's volatility -- stays in `services/pricer` (ADR-0014,
ADR-0028); this module never sees a `Decimal`, a currency, or a curve.

The statistic. Each position's daily volatility is its annual volatility
scaled by `sqrt(CALENDAR_DAYS_PER_YEAR)`; multiplying by `Z_95` gives the
95% one-day relative move, and `cash_delta` (a P&L per 1% relative move,
ADR-0017) is rescaled from its 1% basis to that move. The result is a
magnitude in the same currency as `cash_delta`, as `RiskSnapshot.var_95`
requires (`docs/domain-model.md`).

Two limits are deliberate, not omissions:

- **No diversification benefit.** Per-position magnitudes are summed. A long
  and a short of equal size add, they do not cancel: without correlation data,
  netting them would claim a hedge that cannot be evidenced, so this errs
  toward overstating risk and never understates it (ADR-0029). Correlated
  netting belongs to the Q3 correlated-risk work.
- **Delta risk only.** Gamma, vega and theta are excluded; a portfolio whose
  risk is mostly convexity or volatility exposure is understated by that
  amount (ADR-0029).

A zero-volatility underlying legitimately contributes zero, and an empty
portfolio has zero VaR; neither is a stub.
"""
import math
from collections.abc import Sequence
from dataclasses import dataclass

Z_95 = 1.6448536269514722
"""The one-tailed 95% standard normal quantile, `norm.ppf(0.95)`."""

CALENDAR_DAYS_PER_YEAR = 365
"""Calendar days per year, under the ACT/365F day count of
`docs/conventions.md`. Annual volatility is scaled to one day by dividing by
`sqrt(CALENDAR_DAYS_PER_YEAR)`. The 252-trading-day convention was considered
and rejected in favour of internal consistency (ADR-0029)."""

_CASH_DELTA_BASIS = 0.01
"""`cash_delta` is P&L per 1% relative move (ADR-0017); dividing a relative
return by this rescales it to that basis."""


@dataclass(frozen=True)
class PositionRisk:
    """One position's inputs to `delta_normal_var_95`.

    `cash_delta` is this position's P&L for a 1% relative move in its
    underlying, already converted into the portfolio's reporting currency
    (ADR-0017, ADR-0028). `annual_volatility` is the implied volatility from
    the VOLATILITY curve for that underlying, a continuously compounded
    annualised decimal (`docs/conventions.md`).
    """

    cash_delta: float
    annual_volatility: float


def _validate(position: PositionRisk) -> None:
    if not math.isfinite(position.cash_delta):
        raise ValueError(f"cash_delta must be finite, got {position.cash_delta}")
    if not math.isfinite(position.annual_volatility):
        raise ValueError(f"annual_volatility must be finite, got {position.annual_volatility}")
    if position.annual_volatility < 0:
        raise ValueError(f"annual_volatility must be non-negative, got {position.annual_volatility}")


def delta_normal_var_95(positions: Sequence[PositionRisk]) -> float:
    """1-day 95% delta-normal VaR of `positions`, a non-negative magnitude in
    the currency of their `cash_delta`.

    For each position:

        daily_vol    = annual_volatility / sqrt(CALENDAR_DAYS_PER_YEAR)
        shock        = Z_95 * daily_vol                  (a relative return)
        position VaR = abs(cash_delta) * shock / 0.01    (cash_delta is per 1%)

    and the total is the sum of the position values. Magnitudes are summed
    with no diversification benefit, so opposite positions do not offset, and
    only delta risk is captured; see the module docstring (ADR-0029).

    Returns 0.0 for an empty sequence. Raises `ValueError` naming the
    offending value if any `cash_delta` or `annual_volatility` is not finite
    or any `annual_volatility` is negative (zero is legitimate).
    """
    for position in positions:
        _validate(position)

    sqrt_days = math.sqrt(CALENDAR_DAYS_PER_YEAR)
    total = 0.0
    for position in positions:
        daily_vol = position.annual_volatility / sqrt_days
        shock = Z_95 * daily_vol
        total += abs(position.cash_delta) * shock / _CASH_DELTA_BASIS
    return total
