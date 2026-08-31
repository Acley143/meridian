package com.meridian.coreservice.audit;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * Walks the {@code audit_log} hash chain in insertion order ({@code seq}, see
 * docs/domain-model.md#auditentry's "Ordering") and reports the first broken link, if any.
 *
 * <p>Deliberately does not call {@link CanonicalForm} or {@link AuditLogRepository} -- it
 * reimplements docs/domain-model.md#auditentry's canonical-form specification independently, from
 * raw column values read directly off the JDBC {@code ResultSet}. The whole point of a second,
 * separately-written implementation is that a bug in the write path's hashing (a miscounted length
 * prefix, a swapped field order) does not automatically pass verification just because both sides
 * call the same buggy code.
 */
@Component
public class AuditChainVerifier {

  public record Result(boolean valid, Long brokenAtSeq, String detail) {
    static Result ok() {
      return new Result(true, null, "");
    }

    static Result brokenAt(long seq, String detail) {
      return new Result(false, seq, detail);
    }
  }

  private record Row(
      long seq,
      String entryId,
      String entryType,
      String payload,
      String prevHash,
      String entryHash) {}

  private final JdbcTemplate jdbcTemplate;

  public AuditChainVerifier(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public Result verify() {
    List<Row> rows =
        jdbcTemplate.query(
            "SELECT seq, entry_id, entry_type, payload, prev_hash, entry_hash FROM audit_log"
                + " ORDER BY seq ASC",
            (rs, rowNum) ->
                new Row(
                    rs.getLong("seq"),
                    rs.getString("entry_id"),
                    rs.getString("entry_type"),
                    rs.getString("payload"),
                    rs.getString("prev_hash"),
                    rs.getString("entry_hash")));

    String expectedPrevHash = "";
    for (Row row : rows) {
      if (!row.prevHash().equals(expectedPrevHash)) {
        return Result.brokenAt(
            row.seq(),
            "prev_hash mismatch at seq="
                + row.seq()
                + ": expected '"
                + expectedPrevHash
                + "', found '"
                + row.prevHash()
                + "'");
      }

      String recomputed = recomputeEntryHash(row.entryId(), row.entryType(), row.payload());
      if (!recomputed.equals(row.entryHash())) {
        return Result.brokenAt(
            row.seq(),
            "entry_hash does not match recomputed canonical hash at seq="
                + row.seq()
                + ": stored '"
                + row.entryHash()
                + "', recomputed '"
                + recomputed
                + "'");
      }

      expectedPrevHash = row.entryHash();
    }
    return Result.ok();
  }

  private String recomputeEntryHash(String entryId, String entryType, String payload) {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    appendLengthPrefixed(out, entryId);
    appendLengthPrefixed(out, entryType);
    appendLengthPrefixed(out, payload);

    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hash = digest.digest(out.toByteArray());
      StringBuilder hex = new StringBuilder(hash.length * 2);
      for (byte b : hash) {
        hex.append(Character.forDigit((b >> 4) & 0xF, 16));
        hex.append(Character.forDigit(b & 0xF, 16));
      }
      return hex.toString();
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 unavailable", e);
    }
  }

  private void appendLengthPrefixed(ByteArrayOutputStream out, String value) {
    byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);
    String lengthPrefix = utf8.length + ":";
    try {
      out.write(lengthPrefix.getBytes(StandardCharsets.US_ASCII));
      out.write(utf8);
    } catch (IOException e) {
      throw new java.io.UncheckedIOException(e);
    }
  }
}
