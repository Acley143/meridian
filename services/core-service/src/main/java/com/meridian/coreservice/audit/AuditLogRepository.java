package com.meridian.coreservice.audit;

import java.sql.Timestamp;
import java.time.Instant;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * Append path for the hash-chained audit log (ADR-0008). Every append reads the current chain
 * head's {@code entry_hash} (or the genesis {@code ""} if the table is empty,
 * docs/domain-model.md#auditentry's "Genesis row"), uses it as the new row's {@code prev_hash}, and
 * computes the new row's own {@code entry_hash} from {@link CanonicalForm}.
 *
 * <p>{@code synchronized}: appends must be strictly serialized within this JVM, since each one
 * depends on reading the previous append's result -- two concurrent appends racing to read the same
 * "current head" would both compute the same {@code prev_hash} and corrupt the chain into a fork.
 * This does not serialize across multiple service instances/JVMs; that's out of scope for this
 * session (core-service has no multi-instance deployment yet) and is a known limitation, not a
 * hidden one.
 */
@Repository
public class AuditLogRepository {

  static final String GENESIS_PREV_HASH = "";

  private final JdbcTemplate jdbcTemplate;

  public AuditLogRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  public synchronized void append(
      String entryId, String entryType, String payload, Instant eventTime) {
    String prevHash = currentHead();
    String entryHash = CanonicalForm.sha256Hex(CanonicalForm.bytes(entryId, entryType, payload));
    Instant ingestTime = Instant.now();

    jdbcTemplate.update(
        "INSERT INTO audit_log (entry_id, entry_type, payload, prev_hash, entry_hash,"
            + " event_time, ingest_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
        entryId,
        entryType,
        payload,
        prevHash,
        entryHash,
        Timestamp.from(eventTime),
        Timestamp.from(ingestTime));
  }

  private String currentHead() {
    java.util.List<String> heads =
        jdbcTemplate.query(
            "SELECT entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1",
            (rs, rowNum) -> rs.getString("entry_hash"));
    return heads.isEmpty() ? GENESIS_PREV_HASH : heads.get(0);
  }
}
