package com.meridian.coreservice.idempotency;

/**
 * One row of {@code idempotency_keys}, per (endpoint, idempotency_key). {@code responseStatus}/
 * {@code responseBody} are {@code null} only in the (never externally observable) instant between a
 * claiming request's own INSERT and its own later UPDATE -- every other reader either blocked on
 * the row lock until that UPDATE committed, or is the same request that just claimed it and has not
 * looked itself up.
 */
public record IdempotencyKeyRow(
    String requestFingerprint, Integer responseStatus, String responseBody) {}
