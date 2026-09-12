package com.meridian.coreservice.web;

/**
 * Thrown only when {@code POST /trades}'s required {@code Idempotency-Key} header is missing or
 * blank (ADR-0023) -- see {@link TradeController}.
 *
 * <p>Deliberately its own type rather than a bare {@link IllegalArgumentException}: {@link
 * GlobalExceptionHandler} maps each client-error case to {@code 400} by its specific type, never by
 * the generic superclass -- see that class's doc for why a shared catch-all is the same problem
 * {@link MalformedLastEventIdException} was introduced to fix, just smaller. This is also a
 * different case from {@link MalformedTradeRequestException} on purpose: a missing header and an
 * unparseable body are distinct client mistakes, not two spellings of the same one.
 */
public class MissingIdempotencyKeyException extends IllegalArgumentException {

  public MissingIdempotencyKeyException(String message) {
    super(message);
  }
}
