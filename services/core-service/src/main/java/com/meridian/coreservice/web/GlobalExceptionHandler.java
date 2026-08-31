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
 *   <li>{@link IllegalArgumentException} -- a malformed {@code Last-Event-ID} (SseController /
 *       SseEventId.parse).
 *   <li>{@link DataIntegrityViolationException} -- {@code POST /trades} against an unknown {@code
 *       portfolio_id}/{@code instrument_id} (the foreign key constraints in V1__init_schema.sql
 *       reject it; no separate existence-check query is needed to surface the same 400 the spec
 *       requires).
 * </ul>
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

  @ExceptionHandler(IllegalArgumentException.class)
  public ResponseEntity<String> handleIllegalArgument(IllegalArgumentException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(e.getMessage());
  }

  @ExceptionHandler(DataIntegrityViolationException.class)
  public ResponseEntity<String> handleDataIntegrityViolation(DataIntegrityViolationException e) {
    return ResponseEntity.status(HttpStatus.BAD_REQUEST)
        .body("malformed trade: unknown portfolio_id or instrument_id");
  }
}
