package com.meridian.coreservice.audit;

import static org.assertj.core.api.Assertions.assertThat;

import com.meridian.coreservice.persistence.AbstractPostgresIntegrationTest;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/** A chain of many appended rows verifies cleanly (ADR-0008 Task 4.1). */
class AuditChainVerificationTest extends AbstractPostgresIntegrationTest {

  @Autowired private AuditLogRepository repository;
  @Autowired private AuditChainVerifier verifier;
  @Autowired private JdbcTemplate jdbcTemplate;

  @Test
  void chainOfFiftyRowsVerifies() {
    for (int i = 0; i < 50; i++) {
      repository.append(
          "entry-" + i,
          "trade_booked",
          "{\"index\":" + i + "}",
          Instant.parse("2026-08-31T00:00:00Z"));
    }

    AuditChainVerifier.Result result = verifier.verify();

    assertThat(result.valid()).isTrue();
    assertThat(result.brokenAtSeq()).isNull();
  }

  @Test
  void emptyChainVerifiesTrivially() {
    AuditChainVerifier.Result result = verifier.verify();
    assertThat(result.valid()).isTrue();
  }

  @Test
  void firstAppendedRowIsGenesisWithEmptyPrevHash() {
    repository.append("genesis-entry", "trade_booked", "{}", Instant.parse("2026-08-31T00:00:00Z"));

    String prevHash =
        jdbcTemplate.queryForObject(
            "SELECT prev_hash FROM audit_log ORDER BY seq ASC LIMIT 1", String.class);

    assertThat(prevHash).isEmpty();
  }
}
