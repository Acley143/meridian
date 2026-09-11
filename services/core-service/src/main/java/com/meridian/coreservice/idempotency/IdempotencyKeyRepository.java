package com.meridian.coreservice.idempotency;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Savepoint;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * ADR-0023's insert-first concurrency mechanism. {@link #tryClaim} is the only way a caller
 * discovers whether it is the first request for a given (endpoint, key) -- there is deliberately no
 * read-then-write "does this key already exist?" query, because that check-then-act pair is exactly
 * the TOCTOU race two concurrent retries would hit. The unique constraint on {@code
 * idempotency_keys(endpoint, idempotency_key)} (V4 migration) is the actual lock: a second INSERT
 * for the same pair blocks on that row until the first transaction commits or rolls back, then
 * either fails (row exists -- caller must {@link #find} it to decide replay vs. conflict) or
 * succeeds (the first request rolled back, freeing the key).
 */
@Repository
public class IdempotencyKeyRepository {

  private static final String UNIQUE_VIOLATION_SQLSTATE = "23505";

  private final JdbcTemplate jdbcTemplate;

  public IdempotencyKeyRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  /**
   * Attempts to claim (endpoint, key) with the given fingerprint. Returns {@code true} if this call
   * was the first writer (the caller now owns proceeding with the request), {@code false} if a row
   * already existed for this pair (the caller must {@link #find} it to decide whether this is a
   * replay or a conflict).
   *
   * <p>A failed INSERT aborts the rest of the enclosing Postgres transaction (every later statement
   * errors with "current transaction is aborted" until a ROLLBACK) -- Postgres, unlike some other
   * engines, cannot just shrug off one failed statement and keep going. The caller still needs to
   * run {@link #find} in the very same transaction afterward to decide replay vs. conflict, so this
   * method sets a {@code SAVEPOINT} immediately before the INSERT and rolls back to it (not the
   * whole transaction) on a unique-constraint violation, leaving the transaction usable for
   * everything that follows.
   */
  public boolean tryClaim(String endpoint, String key, String requestFingerprint) {
    return jdbcTemplate.execute(
        (ConnectionCallback<Boolean>)
            con -> {
              Savepoint savepoint = con.setSavepoint();
              try (PreparedStatement ps =
                  con.prepareStatement(
                      "INSERT INTO idempotency_keys (endpoint, idempotency_key,"
                          + " request_fingerprint, created_at) VALUES (?, ?, ?, ?)")) {
                ps.setString(1, endpoint);
                ps.setString(2, key);
                ps.setString(3, requestFingerprint);
                ps.setTimestamp(4, Timestamp.from(Instant.now()));
                ps.executeUpdate();
                return true;
              } catch (SQLException e) {
                if (UNIQUE_VIOLATION_SQLSTATE.equals(e.getSQLState())) {
                  con.rollback(savepoint);
                  return false;
                }
                throw e;
              }
            });
  }

  public Optional<IdempotencyKeyRow> find(String endpoint, String key) {
    List<IdempotencyKeyRow> rows =
        jdbcTemplate.query(
            "SELECT request_fingerprint, response_status, response_body FROM idempotency_keys"
                + " WHERE endpoint = ? AND idempotency_key = ?",
            (rs, rowNum) ->
                new IdempotencyKeyRow(
                    rs.getString("request_fingerprint"),
                    (Integer) rs.getObject("response_status"),
                    rs.getString("response_body")),
            endpoint,
            key);
    return rows.stream().findFirst();
  }

  /** Fills in the response columns left null by {@link #tryClaim}, once one exists. */
  public void storeResponse(String endpoint, String key, int responseStatus, String responseBody) {
    jdbcTemplate.update(
        "UPDATE idempotency_keys SET response_status = ?, response_body = ? WHERE endpoint = ?"
            + " AND idempotency_key = ?",
        responseStatus,
        responseBody,
        endpoint,
        key);
  }
}
