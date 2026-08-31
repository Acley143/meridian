package com.meridian.coreservice.persistence.repository;

import com.meridian.coreservice.persistence.domain.RiskSnapshotRecord;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
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

  private static final RowMapper<RiskSnapshotRecord> ROW_MAPPER = RiskSnapshotRepository::mapRow;

  private static RiskSnapshotRecord mapRow(ResultSet rs, int rowNum) throws SQLException {
    return new RiskSnapshotRecord(
        rs.getString("portfolio_id"),
        rs.getTimestamp("as_of").toInstant(),
        rs.getString("pricer_version"),
        rs.getBigDecimal("price"),
        rs.getBigDecimal("cash_delta"),
        rs.getBigDecimal("cash_gamma"),
        rs.getBigDecimal("cash_vega"),
        rs.getBigDecimal("cash_theta"),
        rs.getBigDecimal("cash_rho"),
        rs.getDouble("var_95"),
        rs.getString("scenario_id"),
        rs.getTimestamp("oldest_input_event_time").toInstant(),
        rs.getTimestamp("ingest_time").toInstant());
  }

  /**
   * Most recently ingested snapshot for a portfolio -- see {@code RiskController} for why "most
   * recently ingested" is what "latest, under the latest pricer_version" means here.
   */
  public Optional<RiskSnapshotRecord> findLatest(String portfolioId) {
    List<RiskSnapshotRecord> rows =
        jdbcTemplate.query(
            "SELECT * FROM risk_snapshots WHERE portfolio_id = ? ORDER BY ingest_time DESC LIMIT 1",
            ROW_MAPPER,
            portfolioId);
    return rows.stream().findFirst();
  }

  /** {@code GET /portfolios/{id}/risk/history}: as_of in [from, to], most recent first, capped. */
  public List<RiskSnapshotRecord> findHistory(
      String portfolioId, Instant from, Instant to, int limit) {
    return jdbcTemplate.query(
        "SELECT * FROM risk_snapshots WHERE portfolio_id = ? AND as_of >= ? AND as_of <= ?"
            + " ORDER BY as_of DESC LIMIT ?",
        ROW_MAPPER,
        portfolioId,
        Timestamp.from(from),
        Timestamp.from(to),
        limit);
  }

  /** Snapshots strictly after {@code afterAsOf}, ascending -- SSE replay order (ADR-0012). */
  public List<RiskSnapshotRecord> findAfter(String portfolioId, Instant afterAsOf) {
    return jdbcTemplate.query(
        "SELECT * FROM risk_snapshots WHERE portfolio_id = ? AND as_of > ? ORDER BY as_of ASC",
        ROW_MAPPER,
        portfolioId,
        Timestamp.from(afterAsOf));
  }

  /**
   * Count of snapshots strictly after {@code afterAsOf} -- the 500-snapshot half of ADR-0012's
   * bound.
   */
  public long countAfter(String portfolioId, Instant afterAsOf) {
    Long count =
        jdbcTemplate.queryForObject(
            "SELECT count(*) FROM risk_snapshots WHERE portfolio_id = ? AND as_of > ?",
            Long.class,
            portfolioId,
            Timestamp.from(afterAsOf));
    return count == null ? 0 : count;
  }
}
