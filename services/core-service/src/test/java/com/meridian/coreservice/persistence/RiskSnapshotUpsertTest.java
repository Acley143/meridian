package com.meridian.coreservice.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import com.meridian.coreservice.persistence.domain.RiskSnapshotRecord;
import com.meridian.coreservice.persistence.repository.RiskSnapshotRepository;
import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/** Upserting the same ADR-0007 identity (portfolio_id, as_of, pricer_version) twice is a no-op. */
class RiskSnapshotUpsertTest extends AbstractPostgresIntegrationTest {

  @Autowired private RiskSnapshotRepository repository;
  @Autowired private JdbcTemplate jdbcTemplate;

  private static final String PORTFOLIO_ID = "PF-UPSERT-TEST";
  private static final Instant AS_OF = Instant.parse("2026-08-31T12:00:00Z");
  private static final String PRICER_VERSION = "v1.0.0";

  private RiskSnapshotRecord snapshot(BigDecimal price) {
    return new RiskSnapshotRecord(
        PORTFOLIO_ID,
        AS_OF,
        PRICER_VERSION,
        price,
        BigDecimal.ONE,
        BigDecimal.ONE,
        BigDecimal.ONE,
        BigDecimal.ONE,
        BigDecimal.ONE,
        0.05,
        "scenario-1",
        AS_OF,
        Instant.parse("2026-08-31T12:00:01Z"));
  }

  @Test
  void redeliveringTheSameIdentityYieldsOneRow() {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES (?, ?, ?, ?)",
        PORTFOLIO_ID,
        "Upsert Test Portfolio",
        "USD",
        "desk-1");

    repository.upsert(snapshot(new BigDecimal("100.00000000")));
    repository.upsert(snapshot(new BigDecimal("100.00000000")));

    long count = repository.countByIdentity(PORTFOLIO_ID, AS_OF, PRICER_VERSION);
    assertThat(count).isEqualTo(1);
  }

  @Test
  void redeliveryWithARevisedValueOverwritesRatherThanDuplicating() {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES (?, ?, ?, ?)",
        "PF-UPSERT-TEST-2",
        "Upsert Test Portfolio 2",
        "USD",
        "desk-1");

    RiskSnapshotRecord first =
        new RiskSnapshotRecord(
            "PF-UPSERT-TEST-2",
            AS_OF,
            PRICER_VERSION,
            new BigDecimal("100.00000000"),
            BigDecimal.ONE,
            BigDecimal.ONE,
            BigDecimal.ONE,
            BigDecimal.ONE,
            BigDecimal.ONE,
            0.05,
            "scenario-1",
            AS_OF,
            Instant.parse("2026-08-31T12:00:01Z"));
    RiskSnapshotRecord revised =
        new RiskSnapshotRecord(
            "PF-UPSERT-TEST-2",
            AS_OF,
            PRICER_VERSION,
            new BigDecimal("101.50000000"),
            BigDecimal.ONE,
            BigDecimal.ONE,
            BigDecimal.ONE,
            BigDecimal.ONE,
            BigDecimal.ONE,
            0.05,
            "scenario-1",
            AS_OF,
            Instant.parse("2026-08-31T12:00:02Z"));

    repository.upsert(first);
    repository.upsert(revised);

    assertThat(repository.countByIdentity("PF-UPSERT-TEST-2", AS_OF, PRICER_VERSION)).isEqualTo(1);

    BigDecimal storedPrice =
        jdbcTemplate.queryForObject(
            "SELECT price FROM risk_snapshots WHERE portfolio_id = ? AND as_of = ? AND"
                + " pricer_version = ?",
            BigDecimal.class,
            "PF-UPSERT-TEST-2",
            java.sql.Timestamp.from(AS_OF),
            PRICER_VERSION);
    assertThat(storedPrice).isEqualByComparingTo("101.50000000");
  }
}
