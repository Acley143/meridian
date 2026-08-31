package com.meridian.coreservice.web;

import java.time.Instant;

/**
 * The ADR-0007 identity tuple, formatted as SSE's {@code id:} field per ADR-0012: {@code
 * {portfolio_id}:{as_of_micros}:{pricer_version}}.
 */
public record SseEventId(String portfolioId, Instant asOf, String pricerVersion) {

  public String format() {
    return portfolioId + ":" + asOfMicros(asOf) + ":" + pricerVersion;
  }

  public static long asOfMicros(Instant instant) {
    return instant.getEpochSecond() * 1_000_000L + instant.getNano() / 1_000L;
  }

  /**
   * Parses a {@code Last-Event-ID} header value. Throws {@link IllegalArgumentException} (mapped to
   * a 400 by the controller, per ADR-0012 Task 4.3 -- a malformed id must be rejected cleanly, not
   * crash) on anything that isn't exactly {@code portfolio_id:as_of_micros:pricer_version} with a
   * numeric middle field.
   */
  public static SseEventId parse(String raw) {
    if (raw == null) {
      throw new IllegalArgumentException("Last-Event-ID must not be null");
    }
    String[] parts = raw.split(":", -1);
    if (parts.length != 3 || parts[0].isEmpty() || parts[1].isEmpty() || parts[2].isEmpty()) {
      throw new IllegalArgumentException(
          "malformed Last-Event-ID (expected portfolio_id:as_of_micros:pricer_version): " + raw);
    }
    long micros;
    try {
      micros = Long.parseLong(parts[1]);
    } catch (NumberFormatException e) {
      throw new IllegalArgumentException(
          "malformed Last-Event-ID: as_of_micros is not numeric: " + raw, e);
    }
    Instant asOf = Instant.ofEpochSecond(micros / 1_000_000L, (micros % 1_000_000L) * 1_000L);
    return new SseEventId(parts[0], asOf, parts[2]);
  }
}
