# ADR-0013: Decimal precision (supersedes ADR-0004)

## Status
Accepted. Supersedes ADR-0004.

## Context
ADR-0004 fixed the *scale* (8) for all monetary and quantity decimals but
did not fix the *precision* (total significant digits). Avro's `decimal`
logical type requires both `precision` and `scale` to be specified together
— `scale` alone is not a complete type. Left unspecified, a
precision-defaulting choice made independently by the Python and Java
binding generators could differ, producing a silent cross-language rounding
or overflow divergence in the money type — exactly the class of bug ADR-0004
was written to prevent.

## Decision
All monetary and quantity decimals are **precision 38, scale 8**, specified
identically in every `.avsc` schema, every DDL column, and both generated
language bindings. Everything else in ADR-0004 (the decimal/float64 split
itself, and the fields on each side of it) stands unchanged.

## Consequences
- `precision: 38` is the largest precision `BigDecimal`-backed Avro decimal
  tooling commonly supports without falling back to arbitrary-precision
  storage tricks, giving ample headroom (30 digits before the decimal point,
  at scale 8) for any notional Meridian will realistically handle.
- Every `.avsc` field using the decimal logical type must declare both
  `precision: 38` and `scale: 8` explicitly — a schema with `scale` alone is
  now understood to be incomplete, not merely terse.
- Java's `BigDecimal` and Python's `Decimal` both support this precision
  natively; no additional conversion logic is needed at the language
  boundary beyond what ADR-0004 already required.

## Alternatives considered
- **Leave precision unspecified, rely on generator defaults.** Rejected:
  this is the bug being fixed — an unspecified precision is exactly what let
  Python and Java tooling default differently in the first place.
- **Smaller precision (e.g. 18, fitting a 64-bit-backed decimal).**
  Rejected: 18 total digits at scale 8 leaves only 10 digits before the
  decimal point, which is tight for aggregated portfolio-level notionals;
  38 costs nothing extra in either language's native decimal type.
