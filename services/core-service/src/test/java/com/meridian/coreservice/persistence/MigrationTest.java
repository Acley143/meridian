package com.meridian.coreservice.persistence;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/** V1__init_schema.sql applies cleanly against a fresh, empty Postgres. */
class MigrationTest extends AbstractPostgresIntegrationTest {

  @Autowired private JdbcTemplate jdbcTemplate;

  @Test
  void allSixTablesExistAfterMigration() {
    List<String> tables =
        jdbcTemplate.queryForList(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                + " ORDER BY table_name",
            String.class);

    assertThat(tables)
        .contains(
            "instruments", "portfolios", "positions", "trades", "risk_snapshots", "audit_log");
  }

  @Test
  void riskSnapshotsIdentityUniqueConstraintExists() {
    List<String> constraintNames =
        jdbcTemplate.queryForList(
            "SELECT constraint_name FROM information_schema.table_constraints"
                + " WHERE table_name = 'risk_snapshots' AND constraint_type = 'UNIQUE'",
            String.class);

    assertThat(constraintNames).contains("uq_risk_snapshots_identity");
  }
}
