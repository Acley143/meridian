package com.meridian.coreservice.service;

import com.meridian.coreservice.web.dto.TradeDto;

/** Result of {@link PortfolioMutationService#applyTradeIdempotent}, per ADR-0023. */
public sealed interface TradeBookingOutcome {

  /** No prior claim on this key: the trade was booked fresh. */
  record Created(TradeDto trade) implements TradeBookingOutcome {}

  /** Same key, same request fingerprint: the original response, replayed verbatim. */
  record Replayed(int status, String body) implements TradeBookingOutcome {}

  /** Same key, different request fingerprint: rejected, never replayed. */
  record Conflict() implements TradeBookingOutcome {}
}
