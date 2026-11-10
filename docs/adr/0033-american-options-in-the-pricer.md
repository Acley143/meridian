# ADR-0033: American options in the pricer service

## Status

Accepted

## Context

ADR-0031 adds American option pricing to quant-core with a validated domain. Its Decision 6 leaves to a later change the mapping of ModelDomainError to a new unpriceable reason, OUTSIDE_MODEL_DOMAIN, and the PRICER_VERSION bump from 0.2.0 to 0.3.0. ADR-0032 Decision 6 says a model-specific reason is mapped before the general case inside instrument pricing.

Today the pricer accepts VANILLA_AMERICAN_OPTION in reference data without checking its option type, strike or expiry; requires only a volatility curve (and an FX curve when its currency differs) for it; and reports it as having no pricer. ModelDomainError is a ValueError, so without a specific mapping it would be reported as INSTRUMENT_NOT_PRICEABLE.

The precedence order among unpriceable reasons is decided in ADR-0027 and ADR-0028. No ADR places OUTSIDE_MODEL_DOMAIN in it.

## Decision

1. Reference data. An American option requires an option type, a strike and an expiry, exactly as a European option does. A missing static fails the reference-data load.

2. Curves. An American option requires the same curves as a European option: VOLATILITY for its underlying, RISK_FREE_RATE for its currency, DIVIDEND_YIELD for its underlying, and FX_RATE when its currency differs from the portfolio's. A missing curve is reported as MISSING_CURVE.

3. Pricing. An American option is priced with quant-core's American pricer (ADR-0031), under the same per-position failure handling as a European option (ADR-0032 Decision 2), except that ModelDomainError is reported as OUTSIDE_MODEL_DOMAIN, naming the position, with the violated conditions in the detail.

4. Precedence. OUTSIDE_MODEL_DOMAIN comes last: UNKNOWN_BASE_CURRENCY, NO_REFERENCE_DATA, NO_PRICE, MISSING_CURVE, INSTRUMENT_NOT_PRICEABLE, OUTSIDE_MODEL_DOMAIN. A position outside the domain has valid inputs that the model has not been validated for; any other failure in the same portfolio is a data problem to fix first. As with every reason, a portfolio produces at most one event per tick, naming every position that has the reported reason.

5. Version. PRICER_VERSION becomes 0.3.0 (ADR-0031 Decision 6). Equity and European option results are unchanged; snapshots differ from 0.2.0 only in pricer_version and in portfolios that hold American options.

## Consequences

- Every instrument type the pricer accepts now has a pricer. The "no pricer yet" path is kept only as a guard against a future type being accepted without one.
- Each American position costs about 1.6 ms to price per tick (ADR-0031, Performance). Throughput with American options is measured against docs/nfr-budget.md in Q4.
- While a higher-precedence reason applies to a portfolio, its out-of-domain positions are not reported for that tick, as with every lower-precedence reason.
- Reference data still comes from the pricer's fixture file; the pricer does not consume reference.instruments.
