package com.meridian.coreservice.service;

import com.meridian.coreservice.web.dto.PortfolioDto;

/**
 * Result of {@link PortfolioMutationService#createPortfolio}, per ADR-0024. Unlike {@link
 * TradeBookingOutcome}, duplicate detection here compares the persisted row's fields, not a raw
 * request-byte fingerprint -- see ADR-0024 for why {@code POST /trades}'s idempotency-key mechanism
 * doesn't transfer to a resource that is fully identified by its own content.
 */
public sealed interface PortfolioCreationOutcome {

  /** No existing row for this {@code portfolio_id}: the portfolio was created fresh. */
  record Created(PortfolioDto portfolio) implements PortfolioCreationOutcome {}

  /** A row already exists for this {@code portfolio_id} and every field matches the request. */
  record Existing(PortfolioDto portfolio) implements PortfolioCreationOutcome {}

  /** A row already exists for this {@code portfolio_id} but at least one field differs. */
  record Conflict() implements PortfolioCreationOutcome {}
}
