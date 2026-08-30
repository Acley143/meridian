# core-service

Java service layer: owns portfolio/trade state, produces `portfolio.state`
(ADR-0003), exposes REST + SSE to the dashboard (ADR-0009), writes the
hash-chained audit log (ADR-0008). Java 21, Spring Boot.

- Money fields are `BigDecimal` end to end — never let one decay to `double`
  on the way through a repository or DTO (ADR-0004).
- All persisted/produced timestamps are `java.time.Instant`, never
  `LocalDateTime` (ADR-0005) — `LocalDateTime` has no timezone and is exactly
  the naive-datetime bug this project forbids, just in Java's clothing.
- This service is the sole producer of `portfolio.state`; it never consumes
  it back and never calls the pricer synchronously (ADR-0003).
- Local build/test: `mvn -pl services/core-service verify`. Formatting is
  enforced by `spotless:check` in CI — run `mvn spotless:apply` before
  committing rather than hand-fixing formatting diffs.
- The one mistake most likely here: computing `entry_hash`/`prev_hash` for
  the audit log (ADR-0008) over a Java object's default `toString()`/JSON
  serialization instead of the defined canonical form — any non-deterministic
  field order silently breaks the hash chain for every future verifier.
