# ADR-0004: Numeric type policy

## Status
Accepted

## Context
Meridian handles two categorically different kinds of numbers: cash amounts
(money, notionals, quantities), where binary floating point rounding error is
unacceptable, and continuous risk quantities (Greeks, volatilities, rates,
correlations), where float64 precision is sufficient and required for
numerical routines (optimization, root-finding, Monte Carlo) that decimal
types can't support efficiently.

## Decision
Money, notionals, and quantities are decimal: `Decimal` in Python,
`BigDecimal` in Java, Avro `bytes` with `logicalType: decimal` and `scale: 8`
on the wire. Greeks, volatilities, rates, and correlations are `float64`
everywhere. Floats never touch a cash amount; decimals never enter a
numerical routine.

## Consequences
- Every Avro schema field must be classified into one bucket or the other at
  design time in `docs/domain-model.md`; there is no third option.
- Conversions at the boundary (e.g. decimal notional feeding into a float
  pricing formula) must be explicit and are a deliberate, reviewable act, not
  an implicit cast.
- Decimal arithmetic in Python/Java is slower than float; this is accepted
  because cash fields are not on the numerically-hot path (pricing loops
  operate on floats).

## Alternatives considered
- **Float everywhere with fixed rounding at output.** Rejected: binary float
  cannot represent most decimal fractions exactly, and rounding only at
  output still accumulates error through intermediate cash arithmetic
  (position aggregation, P&L).
- **Decimal everywhere, including Greeks/vols.** Rejected: numerical routines
  (Monte Carlo, calibration) need float64 performance and the standard
  numerical libraries (NumPy, Apache Commons Math) assume it.
