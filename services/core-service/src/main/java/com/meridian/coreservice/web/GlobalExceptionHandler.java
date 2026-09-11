package com.meridian.coreservice.web;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * A malformed request must fail cleanly with a 4xx, never a 500/crash (ADR-0012 Task 4.3). Two
 * cases mapped here:
 *
 * <ul>
 *   <li>{@link MalformedLastEventIdException} -- a malformed {@code Last-Event-ID} (SseController /
 *       SseEventId.parse).
 *   <li>{@link DataIntegrityViolationException} -- {@code POST /trades} against an unknown {@code
 *       portfolio_id}/{@code instrument_id} (the foreign key constraints in V1__init_schema.sql
 *       reject it; no separate existence-check query is needed to surface the same 400 the spec
 *       requires).
 * </ul>
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
 * server fault should render as.
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

  @ExceptionHandler(MalformedLastEventIdException.class)
  public ResponseEntity<String> handleMalformedLastEventId(MalformedLastEventIdException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(e.getMessage());
  }

  @ExceptionHandler(DataIntegrityViolationException.class)
  public ResponseEntity<String> handleDataIntegrityViolation(DataIntegrityViolationException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST)
        .body("malformed trade: unknown portfolio_id or instrument_id");
  }
}
