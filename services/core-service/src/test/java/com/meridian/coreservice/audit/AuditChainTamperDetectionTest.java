package com.meridian.coreservice.audit;

import static org.assertj.core.api.Assertions.assertThat;

import com.meridian.coreservice.persistence.AbstractPostgresIntegrationTest;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Mutating one row mid-chain is detected, at the correct position (ADR-0008 Task 4.2). The mutation
 * itself has to bypass {@code audit_log}'s append-only trigger (V2 migration) -- the whole point of
 * this test is to model exactly the privileged-bypass scenario ADR-0008's editorial amendment names
 * as the chain's real limit ("an attacker with full write access"), not to prove the trigger is
 * absent. The trigger is disabled only for the single mutating statement and re-enabled immediately
 * after, in the same test.
 */
class AuditChainTamperDetectionTest extends AbstractPostgresIntegrationTest {

  @Autowired private AuditLogRepository repository;
  @Autowired private AuditChainVerifier verifier;
  @Autowired private JdbcTemplate jdbcTemplate;

  @Test
  void mutatingOneRowMidChainIsDetectedAtTheCorrectPosition() {
    for (int i = 0; i < 20; i++) {
      repository.append(
          "tamper-entry-" + i,
          "trade_booked",
          "{\"index\":" + i + "}",
          Instant.parse("2026-08-31T00:00:00Z"));
    }

    Long tamperedSeq =
        jdbcTemplate.queryForObject(
            "SELECT seq FROM audit_log WHERE entry_id = 'tamper-entry-10'", Long.class);

    jdbcTemplate.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_reject_update");
    try {
      jdbcTemplate.update(
          "UPDATE audit_log SET payload = '{\"index\":999999}' WHERE entry_id = 'tamper-entry-10'");
    } finally {
      jdbcTemplate.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_reject_update");
    }

    AuditChainVerifier.Result result = verifier.verify();

    assertThat(result.valid()).isFalse();
    assertThat(result.brokenAtSeq()).isEqualTo(tamperedSeq);
  }
}
