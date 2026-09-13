package com.meridian.coreservice.web;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * A malformed request must fail cleanly with a 4xx, never a 500/crash (ADR-0012 Task 4.3). Cases
 * mapped here:
 *
 * <ul>
 *   <li>{@link MalformedLastEventIdException} -- a malformed {@code Last-Event-ID} (SseController /
 *       SseEventId.parse).
 *   <li>{@link MissingIdempotencyKeyException} -- {@code POST /trades} missing (or blank) its
 *       required {@code Idempotency-Key} header (ADR-0023).
 *   <li>{@link MalformedTradeRequestException} -- {@code POST /trades}'s body doesn't parse into a
 *       {@code TradeRequestDto} (ADR-0023).
 *   <li>{@link DataIntegrityViolationException} -- {@code POST /trades} against an unknown {@code
 *       portfolio_id}/{@code instrument_id} (the foreign key constraints in V1__init_schema.sql
 *       reject it; no separate existence-check query is needed to surface the same 400 the spec
 *       requires).
 *   <li>{@link InvalidPortfolioRequestException} -- {@code POST /portfolios}'s body is
 *       missing/blank a required field, or {@code base_currency} doesn't match {@code ^[A-Z]{3}$}
 *       (ADR-0024).
 *   <li>{@link InvalidInstrumentRequestException} -- {@code POST /instruments}'s body is missing a
 *       required field, an enum field doesn't parse, a conditional-field rule is violated, or
 *       {@code currency}/{@code contract_size} fail validation (ADR-0025).
 * </ul>
 *
 * <p>The two {@code POST /trades} cases are separate types, not one shared catch-all, even though
 * both are currently client mistakes on the same endpoint: a missing header and an unparseable body
 * are distinct things a client got wrong, and collapsing them back into one broad type is the same
 * mistake bare {@link IllegalArgumentException} made, just at a smaller scale.
 *
 * <p>Deliberately does NOT map the bare {@link IllegalArgumentException} superclass. It used to --
 * that mapping was written only for {@link MalformedLastEventIdException}'s predecessor, but
 * {@code @ExceptionHandler(IllegalArgumentException.class)} matches every subtype, including ones
 * thrown by unrelated Spring/JDK internals for reasons that have nothing to do with a malformed
 * client request. That hid a real bug across three PRs: {@code RiskSnapshotConsumerHealthIndicator}
 * passed a legitimately-null {@code lastHeartbeatSecondsAgo} into {@code
 * Health.Builder#withDetail}, which throws {@code IllegalArgumentException("Value must not be
 * null")} -- this handler caught it and rendered a server-side bug as a generic client-fault 400,
 * with no stack trace logged anywhere. See ADR-0022's editorial amendments. An unrelated {@code
 * IllegalArgumentException} now falls through to Spring's default handling (500), which is what a
 * server fault should render as. Every new client-error case added here must be its own type, per
 * that history -- never a re-added mapping on the superclass.
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

  @ExceptionHandler(MalformedLastEventIdException.class)
  public ResponseEntity<String> handleMalformedLastEventId(MalformedLastEventIdException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(e.getMessage());
  }

  @ExceptionHandler(MissingIdempotencyKeyException.class)
  public ResponseEntity<String> handleMissingIdempotencyKey(MissingIdempotencyKeyException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(e.getMessage());
  }

  @ExceptionHandler(MalformedTradeRequestException.class)
  public ResponseEntity<String> handleMalformedTradeRequest(MalformedTradeRequestException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(e.getMessage());
  }

  @ExceptionHandler(DataIntegrityViolationException.class)
  public ResponseEntity<String> handleDataIntegrityViolation(DataIntegrityViolationException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST)
        .body("malformed trade: unknown portfolio_id or instrument_id");
  }

  @ExceptionHandler(InvalidPortfolioRequestException.class)
  public ResponseEntity<String> handleInvalidPortfolioRequest(InvalidPortfolioRequestException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(e.getMessage());
  }

  @ExceptionHandler(InvalidInstrumentRequestException.class)
  public ResponseEntity<String> handleInvalidInstrumentRequest(
      InvalidInstrumentRequestException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(e.getMessage());
  }
}
