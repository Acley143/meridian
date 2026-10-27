# ADR-0032: Pricer handling of invalid inputs and failed model evaluations

## Status

Accepted

## Context

ADR-0018 requires that a portfolio the pricer cannot price is reported, never silently skipped. In the pricer's per-position loop, the only exception caught around instrument pricing is UnpricableInstrumentError. A ValueError raised by quant-core's input validation therefore escapes the loop, stops the tick loop before the tick's offset is committed, and stops the process. Portfolios later in the same tick are not priced. On restart the same tick is redelivered and the failure repeats.

Two inputs reach this through ordinary Kafka data:
- a tick price that is not strictly positive, on an option's underlying (quant-core rejects a non-positive spot);
- a tick whose event time is after the expiry of a held option (quant-core rejects an expiry before the valuation time). This happens in normal operation once time passes an option's expiry.

A non-positive tick price also reaches equity positions, which are priced without validation, so the pricer publishes a snapshot with a wrong number and no error.

Curve values for rates and dividend yields are validated only as finite. Extreme values can make the pricing raise OverflowError, or produce a result that cannot be quantised to money (decimal.InvalidOperation).

ADR-0031 adds ModelDomainError for American options. Its mapping to an unpriceable reason is sequenced after this decision.

## Decision

1. Ticks are validated at consume. A tick whose price is not strictly positive is rejected: its offset is committed, the cached price is unchanged, no portfolio is priced from it, and the rejection is counted and logged. This is the handling ADR-0028 gives a tick in the wrong currency.

2. A failed model evaluation is the position's failure, not the process's. In instrument pricing, the construction of quant-core inputs and the call to the quant-core pricer are wrapped. ValueError (quant-core's input validation), OverflowError and decimal.InvalidOperation (a result that cannot be represented) are converted to UnpricableInstrumentError, with the original message in the detail. The portfolio is reported INSTRUMENT_NOT_PRICEABLE under the existing precedence, and no snapshot is produced. An option held after its expiry is reported this way: an expired position must be closed in the portfolio data, not priced.

3. The portfolio VaR statistic is treated the same way. A ValueError from the VaR computation makes the portfolio unpriceable as INSTRUMENT_NOT_PRICEABLE, naming all of its positions, with the message in the detail. This is not reachable through Kafka today; it is defence in depth.

4. Everything else still fails fast. The catches are narrow: only around quant-core calls, and only for the exception types above. Any other exception, including ZeroDivisionError, is a defect and stops the process. Handling a tick that fails for an unknown reason (skipping after repeated failures, or a dead-letter topic) is deferred to Q4.

5. With 1 to 4, one portfolio's failure does not affect the others in the same tick: the loop completes, and the tick is flushed and committed.

6. A model may define a more specific unpriceable reason in its own ADR, mapped before the general case of Decision 2. ADR-0031's OUTSIDE_MODEL_DOMAIN is the first.

## Consequences

- No new unpriceable reason; the precedence order is unchanged.
- A portfolio holding an expired option is unpriceable until the position is removed.
- Validating tick prices at the producer (ingest) and bounding curve values (rates, dividend yields and volatility) are separate decisions, not made here.
- Unpriceable reasons are still surfaced only through logs and counters.
