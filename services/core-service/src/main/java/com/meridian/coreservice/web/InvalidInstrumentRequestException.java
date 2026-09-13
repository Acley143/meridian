package com.meridian.coreservice.web;

/**
 * Thrown only when {@code POST /instruments}'s request body is missing a required field, {@code
 * instrument_type}/{@code option_type} doesn't parse into the generated Avro enum, a
 * conditional-field rule (option-bearing fields required together, absent otherwise) is violated,
 * {@code currency} doesn't match {@code ^[A-Z]{3}$}, {@code contract_size} isn't strictly positive,
 * or {@code strike} is present on a non-option (ADR-0025) -- see {@link InstrumentController}.
 *
 * <p>Its own type rather than a bare {@link IllegalArgumentException} or a reuse of {@link
 * InvalidPortfolioRequestException}, per {@link GlobalExceptionHandler}'s doc: every client-error
 * case is mapped to {@code 400} by its own specific type, never by a shared superclass or an
 * unrelated endpoint's exception.
 */
public class InvalidInstrumentRequestException extends IllegalArgumentException {

  public InvalidInstrumentRequestException(String message) {
    super(message);
  }
}
