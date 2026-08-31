package com.meridian.coreservice.persistence.repository;

import com.meridian.coreservice.persistence.domain.RiskSnapshotRecord;
import java.sql.Timestamp;
import java.time.Instant;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * Idempotent persistence for {@link RiskSnapshotRecord} on the ADR-0007 identity (portfolio_id,
 * as_of, pricer_version), backed by the {@code uq_risk_snapshots_identity} UNIQUE constraint
 * (V1__init_schema.sql).
 */
@Repository
public class RiskSnapshotRepository {

  // Redelivery under Kafka's at-least-once semantics (ADR-0007's whole reason for existing) must
  // be a no-op: the same identity redelivered with byte-identical content should not create a
  // second row and should not error. DO NOTHING would satisfy that, but it would also silently
  // keep a stale row if a producer ever legitimately redelivers a corrected value under the same
  // identity (e.g. a bug in a still-in-flight pricer_version fixed and reprocessed before that
  // version is retired) -- ADR-0007 does not forbid this, it only says the same identity
  // overwrites itself. DO UPDATE SET is idempotent either way: byte-identical content makes the
  // UPDATE a no-op in effect, and a legitimate correction under the same identity is honoured
  // (latest write wins) instead of the database silently discarding it. That strictly dominates
  // DO NOTHING for the same cost, so DO UPDATE SET is what's used here.
  private static final String UPSERT_SQL =
      """
      INSERT INTO risk_snapshots (
        portfolio_id, as_of, pricer_version, price, cash_delta, cash_gamma, cash_vega,
        cash_theta, cash_rho, var_95, scenario_id, oldest_input_event_time, ingest_time
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT (portfolio_id, as_of, pricer_version) DO UPDATE SET
        price = EXCLUDED.price,
        cash_delta = EXCLUDED.cash_delta,
        cash_gamma = EXCLUDED.cash_gamma,
        cash_vega = EXCLUDED.cash_vega,
        cash_theta = EXCLUDED.cash_theta,
        cash_rho = EXCLUDED.cash_rho,
        var_95 = EXCLUDED.var_95,
        scenario_id = EXCLUDED.scenario_id,
        oldest_input_event_time = EXCLUDED.oldest_input_event_time,
        ingest_time = EXCLUDED.ingest_time
      """;

  private static final String COUNT_BY_IDENTITY_SQL =
      """
      SELECT count(*) FROM risk_snapshots
      WHERE portfolio_id = ? AND as_of = ? AND pricer_version = ?
      """;

  private final JdbcTemplate jdbcTemplate;

  public RiskSnapshotRepository(JdbcTemplate jdbcTemplate) {
    this.jdbcTemplate = jdbcTemplate;
  }

  /** Idempotent upsert on the ADR-0007 identity. Safe to call any number of times. */
  public void upsert(RiskSnapshotRecord snapshot) {
    jdbcTemplate.update(
        UPSERT_SQL,
        snapshot.portfolioId(),
        Timestamp.from(snapshot.asOf()),
        snapshot.pricerVersion(),
        snapshot.price(),
        snapshot.cashDelta(),
        snapshot.cashGamma(),
        snapshot.cashVega(),
        snapshot.cashTheta(),
        snapshot.cashRho(),
        snapshot.var95(),
        snapshot.scenarioId(),
        Timestamp.from(snapshot.oldestInputEventTime()),
        Timestamp.from(snapshot.ingestTime()));
  }

  /** Row count for one ADR-0007 identity -- used to assert upsert idempotency in tests. */
  public long countByIdentity(String portfolioId, Instant asOf, String pricerVersion) {
    Long count =
        jdbcTemplate.queryForObject(
            COUNT_BY_IDENTITY_SQL, Long.class, portfolioId, Timestamp.from(asOf), pricerVersion);
    return count == null ? 0 : count;
  }
}
