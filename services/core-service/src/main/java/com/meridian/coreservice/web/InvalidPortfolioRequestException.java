package com.meridian.coreservice.web;

/**
 * Thrown only when {@code POST /portfolios}'s request body is missing/blank a required field, or
 * has a {@code base_currency} that doesn't match {@code ^[A-Z]{3}$} (ADR-0024) -- see {@link
 * PortfolioController}.
 *
 * <p>Its own type rather than a bare {@link IllegalArgumentException}, per {@link
 * GlobalExceptionHandler}'s doc: every client-error case is mapped to {@code 400} by its specific
 * type, never by the generic superclass.
 */
public class InvalidPortfolioRequestException extends IllegalArgumentException {

  public InvalidPortfolioRequestException(String message) {
    super(message);
  }
}
