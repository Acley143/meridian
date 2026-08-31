package com.meridian.coreservice.audit;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.meridian.coreservice.persistence.AbstractPostgresIntegrationTest;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Append-only is enforced at the database level (V2__audit_log_hash_chain.sql's triggers), not by
 * application convention -- these tests go around {@link AuditLogRepository} entirely and issue raw
 * UPDATE/DELETE statements directly, confirming Postgres itself rejects them.
 */
class AuditLogAppendOnlyEnforcementTest extends AbstractPostgresIntegrationTest {

  @Autowired private AuditLogRepository repository;
  @Autowired private JdbcTemplate jdbcTemplate;

  @Test
  void databaseRejectsUpdateEvenWithoutAnyApplicationCodePath() {
    repository.append(
        "enforce-update", "trade_booked", "{}", Instant.parse("2026-08-31T00:00:00Z"));

    assertThatThrownBy(
            () ->
                jdbcTemplate.update(
                    "UPDATE audit_log SET payload = '{}' WHERE entry_id = 'enforce-update'"))
        .isInstanceOf(DataAccessException.class)
        .hasMessageContaining("append-only");
  }

  @Test
  void databaseRejectsDeleteEvenWithoutAnyApplicationCodePath() {
    repository.append(
        "enforce-delete", "trade_booked", "{}", Instant.parse("2026-08-31T00:00:00Z"));

    assertThatThrownBy(
            () -> jdbcTemplate.update("DELETE FROM audit_log WHERE entry_id = 'enforce-delete'"))
        .isInstanceOf(DataAccessException.class)
        .hasMessageContaining("append-only");
  }
}
