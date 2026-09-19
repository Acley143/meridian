"""The Decimal<->float64 boundary (ADR-0004, ADR-0013).

Money, notionals, and quantities are `Decimal` (precision 38, scale 8);
Greeks, volatilities, and rates are `float64`. The conversion between them
is the single most likely source of a cross-language divergence in
Meridian, so it happens in exactly one place: here. No other module in
`quant_core` may call `float()` or `Decimal()` on a value crossing the
boundary — enforced by `tools/schema-lint/check_quant_core_boundary.py` in
CI, since import-linter checks imports, not calls.
"""
from decimal import ROUND_HALF_EVEN, Decimal

_MONEY_QUANTUM = Decimal("1E-8")


def to_model(d: Decimal) -> float:
    """Entry conversion: a Decimal money/quantity value into the float64
    domain a pricing formula operates in. Boundary-only — never call this
    on a value that isn't crossing from the Decimal side."""
    return float(d)


def to_money(f: float) -> Decimal:
    """Exit conversion: a float64 result back into Decimal money, quantised
    to scale 8 with banker's rounding (ROUND_HALF_EVEN).

    Half-up rounding accumulates a directional bias across a large book;
    banker's rounding does not, which is exactly the kind of thing a
    reviewer would ask about."""
    return Decimal(f).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def convert_money(amount: Decimal, rate: Decimal) -> Decimal:
    """Convert a `Decimal` cash amount into another currency at `rate` (units
    of the target currency per one unit of the amount's currency, ADR-0027
    Decision 2), quantised once to scale 8 with banker's rounding
    (ROUND_HALF_EVEN) -- the same quantum `to_money` uses.

    ADR-0028 Decision 5: conversion is decimal throughout, with no float
    round trip, so floats never touch cash (ADR-0004). Callers round per
    position, before summing, so a portfolio total does not depend on
    summation order.

    Raises `ValueError` naming the rate if it is not finite or not strictly
    positive: a zero rate would silently zero a book and a negative one
    would flip its sign, and the curve validator permits any finite decimal,
    so this is the last line of defence."""
    if not rate.is_finite() or rate <= 0:
        raise ValueError(f"FX rate must be finite and strictly positive, got {rate}")
    return (amount * rate).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)
