package com.meridian.coreservice.web;

import static io.restassured.RestAssured.given;
import static org.assertj.core.api.Assertions.assertThat;

import com.meridian.coreservice.audit.AuditChainVerifier;
import io.restassured.response.Response;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * ADR-0023: {@code Idempotency-Key} on {@code POST /trades}. Each test seeds its own
 * portfolio/instrument pair so the trade/audit-row counts asserted below are exact -- no shared
 * fixture state from another test class can add an extra row.
 */
class IdempotentTradeBookingTest extends AbstractRestIntegrationTest {

  @Autowired private JdbcTemplate jdbcTemplate;
  @Autowired private AuditChainVerifier auditChainVerifier;

  private void seedPortfolioAndInstrument(String portfolioId, String instrumentId) {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES (?, ?, 'USD',"
            + " 'desk-1') ON CONFLICT DO NOTHING",
        portfolioId,
        portfolioId);
    jdbcTemplate.update(
        "INSERT INTO instruments (instrument_id, underlying_id, instrument_type, currency,"
            + " contract_size) VALUES (?, ?, 'EQUITY', 'USD', 1) ON CONFLICT DO NOTHING",
        instrumentId,
        instrumentId);
  }

  private String tradeBody(String portfolioId, String instrumentId, String quantity) {
    return """
        {
          "portfolio_id": "%s",
          "instrument_id": "%s",
          "quantity": "%s",
          "price": "10.00000000",
          "event_time": "2026-09-11T09:00:00Z"
        }
        """
        .formatted(portfolioId, instrumentId, quantity);
  }

  private int tradeCount(String portfolioId) {
    Integer count =
        jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM trades WHERE portfolio_id = ?", Integer.class, portfolioId);
    return count;
  }

  private int auditCount(String portfolioId) {
    Integer count =
        jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM audit_log WHERE portfolio_id = ? AND entry_type ="
                + " 'trade_booked'",
            Integer.class,
            portfolioId);
    return count;
  }

  // 1. Same key, same body, twice -> identical response both times, one trade row, one audit
  // entry.
  @Test
  void sameKeySameBodyTwiceReplaysIdenticalResponse() {
    String portfolioId = "PF-IDEM-1-" + UUID.randomUUID();
    String instrumentId = "INSTR-IDEM-1";
    seedPortfolioAndInstrument(portfolioId, instrumentId);
    String key = "key-" + UUID.randomUUID();
    String body = tradeBody(portfolioId, instrumentId, "10.00000000");

    Response first =
        given()
            .baseUri(baseUrl())
            .header("Idempotency-Key", key)
            .contentType("application/json")
            .body(body)
            .when()
            .post("/api/v1/trades");
    Response second =
        given()
            .baseUri(baseUrl())
            .header("Idempotency-Key", key)
            .contentType("application/json")
            .body(body)
            .when()
            .post("/api/v1/trades");

    assertThat(first.statusCode()).isEqualTo(201);
    assertThat(second.statusCode()).isEqualTo(201);
    assertThat(second.body().asString()).isEqualTo(first.body().asString());
    assertThat(first.jsonPath().getString("trade_id"))
        .isEqualTo(second.jsonPath().getString("trade_id"));

    assertThat(tradeCount(portfolioId)).isEqualTo(1);
    assertThat(auditCount(portfolioId)).isEqualTo(1);
  }

  // 2. Same key, different body -> 409. No second trade, no second audit entry.
  @Test
  void sameKeyDifferentBodyReturns409WithoutASecondTradeOrAuditEntry() {
    String portfolioId = "PF-IDEM-2-" + UUID.randomUUID();
    String instrumentId = "INSTR-IDEM-2";
    seedPortfolioAndInstrument(portfolioId, instrumentId);
    String key = "key-" + UUID.randomUUID();

    Response first =
        given()
            .baseUri(baseUrl())
            .header("Idempotency-Key", key)
            .contentType("application/json")
            .body(tradeBody(portfolioId, instrumentId, "10.00000000"))
            .when()
            .post("/api/v1/trades");
    Response second =
        given()
            .baseUri(baseUrl())
            .header("Idempotency-Key", key)
            .contentType("application/json")
            .body(tradeBody(portfolioId, instrumentId, "99.00000000"))
            .when()
            .post("/api/v1/trades");

    assertThat(first.statusCode()).isEqualTo(201);
    assertThat(second.statusCode()).isEqualTo(409);
    assertThat(tradeCount(portfolioId)).isEqualTo(1);
    assertThat(auditCount(portfolioId)).isEqualTo(1);
  }

  // 3. Different keys, identical bodies -> two trades. Proves it keys on the header, not content.
  @Test
  void differentKeysIdenticalBodiesBookTwoTrades() {
    String portfolioId = "PF-IDEM-3-" + UUID.randomUUID();
    String instrumentId = "INSTR-IDEM-3";
    seedPortfolioAndInstrument(portfolioId, instrumentId);
    String body = tradeBody(portfolioId, instrumentId, "10.00000000");

    Response first =
        given()
            .baseUri(baseUrl())
            .header("Idempotency-Key", "key-" + UUID.randomUUID())
            .contentType("application/json")
            .body(body)
            .when()
            .post("/api/v1/trades");
    Response second =
        given()
            .baseUri(baseUrl())
            .header("Idempotency-Key", "key-" + UUID.randomUUID())
            .contentType("application/json")
            .body(body)
            .when()
            .post("/api/v1/trades");

    assertThat(first.statusCode()).isEqualTo(201);
    assertThat(second.statusCode()).isEqualTo(201);
    assertThat(first.jsonPath().getString("trade_id"))
        .isNotEqualTo(second.jsonPath().getString("trade_id"));
    assertThat(tradeCount(portfolioId)).isEqualTo(2);
    assertThat(auditCount(portfolioId)).isEqualTo(2);
  }

  // 4. Missing header -> 400. Empty header -> 400.
  @Test
  void missingIdempotencyKeyHeaderReturns400() {
    String portfolioId = "PF-IDEM-4-" + UUID.randomUUID();
    String instrumentId = "INSTR-IDEM-4";
    seedPortfolioAndInstrument(portfolioId, instrumentId);

    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(tradeBody(portfolioId, instrumentId, "10.00000000"))
        .when()
        .post("/api/v1/trades")
        .then()
        .statusCode(400);

    assertThat(tradeCount(portfolioId)).isEqualTo(0);
  }

  @Test
  void emptyIdempotencyKeyHeaderReturns400() {
    String portfolioId = "PF-IDEM-4B-" + UUID.randomUUID();
    String instrumentId = "INSTR-IDEM-4B";
    seedPortfolioAndInstrument(portfolioId, instrumentId);

    given()
        .baseUri(baseUrl())
        .header("Idempotency-Key", "")
        .contentType("application/json")
        .body(tradeBody(portfolioId, instrumentId, "10.00000000"))
        .when()
        .post("/api/v1/trades")
        .then()
        .statusCode(400);

    assertThat(tradeCount(portfolioId)).isEqualTo(0);
  }

  // 5. Two concurrent requests, same key, separate threads -> exactly one trade, one audit entry,
  // both callers get a coherent response. Run repeatedly, not once.
  @Test
  void concurrentRequestsSameKeyProduceExactlyOneTrade() throws Exception {
    ExecutorService pool = Executors.newFixedThreadPool(2);
    try {
      for (int iteration = 0; iteration < 10; iteration++) {
        String portfolioId = "PF-IDEM-5-" + iteration + "-" + UUID.randomUUID();
        String instrumentId = "INSTR-IDEM-5-" + iteration;
        seedPortfolioAndInstrument(portfolioId, instrumentId);
        String key = "key-" + UUID.randomUUID();
        String body = tradeBody(portfolioId, instrumentId, "10.00000000");

        CountDownLatch start = new CountDownLatch(1);
        Future<Response> callA =
            pool.submit(
                () -> {
                  start.await();
                  return given()
                      .baseUri(baseUrl())
                      .header("Idempotency-Key", key)
                      .contentType("application/json")
                      .body(body)
                      .when()
                      .post("/api/v1/trades");
                });
        Future<Response> callB =
            pool.submit(
                () -> {
                  start.await();
                  return given()
                      .baseUri(baseUrl())
                      .header("Idempotency-Key", key)
                      .contentType("application/json")
                      .body(body)
                      .when()
                      .post("/api/v1/trades");
                });
        start.countDown();

        Response responseA = callA.get(30, TimeUnit.SECONDS);
        Response responseB = callB.get(30, TimeUnit.SECONDS);

        assertThat(responseA.statusCode())
            .as("iteration %d caller A status", iteration)
            .isEqualTo(201);
        assertThat(responseB.statusCode())
            .as("iteration %d caller B status", iteration)
            .isEqualTo(201);
        assertThat(responseA.jsonPath().getString("trade_id"))
            .as("iteration %d: both callers see the same trade_id", iteration)
            .isEqualTo(responseB.jsonPath().getString("trade_id"));
        assertThat(tradeCount(portfolioId)).as("iteration %d trade count", iteration).isEqualTo(1);
        assertThat(auditCount(portfolioId)).as("iteration %d audit count", iteration).isEqualTo(1);
      }
    } finally {
      pool.shutdownNow();
    }
  }

  // 6. Rollback releases the key -- force the trade insert to fail (unknown portfolio_id, the
  // same FK violation TradeBookingTest already exercises) after the idempotency row is written,
  // inside the same transaction. Confirm the key is absent afterwards and a retry with the same
  // key succeeds.
  @Test
  void rollbackReleasesTheIdempotencyKey() {
    String portfolioId = "PF-IDEM-6-" + UUID.randomUUID();
    String instrumentId = "INSTR-IDEM-6";
    String key = "key-" + UUID.randomUUID();
    String body = tradeBody(portfolioId, instrumentId, "10.00000000");

    // portfolioId/instrumentId do not exist yet -- the trade insert's FK constraint fails inside
    // applyTrade, after the idempotency claim has already been inserted in the same transaction.
    given()
        .baseUri(baseUrl())
        .header("Idempotency-Key", key)
        .contentType("application/json")
        .body(body)
        .when()
        .post("/api/v1/trades")
        .then()
        .statusCode(400);

    List<String> keyRows =
        jdbcTemplate.query(
            "SELECT idempotency_key FROM idempotency_keys WHERE endpoint = 'POST /api/v1/trades'"
                + " AND idempotency_key = ?",
            (rs, rowNum) -> rs.getString("idempotency_key"),
            key);
    assertThat(keyRows)
        .as("idempotency row must not survive the rolled-back transaction")
        .isEmpty();

    // Now the portfolio/instrument exist -- a retry with the *same* key must succeed, proving the
    // key was actually released, not just that a fresh key would have worked.
    seedPortfolioAndInstrument(portfolioId, instrumentId);

    given()
        .baseUri(baseUrl())
        .header("Idempotency-Key", key)
        .contentType("application/json")
        .body(body)
        .when()
        .post("/api/v1/trades")
        .then()
        .statusCode(201);

    assertThat(tradeCount(portfolioId)).isEqualTo(1);
  }

  // 7. Audit chain prev_hash linkage intact after all of the above -- run last (JUnit's default
  // per-class ordering runs methods in a deterministic, not-source order, so this also asserts
  // the chain independently of what ran before it within this class; it re-verifies the whole
  // table, not just this class's own rows).
  @Test
  void auditChainRemainsValidAfterIdempotencyTraffic() {
    String portfolioId = "PF-IDEM-7-" + UUID.randomUUID();
    String instrumentId = "INSTR-IDEM-7";
    seedPortfolioAndInstrument(portfolioId, instrumentId);
    String key = "key-" + UUID.randomUUID();
    String body = tradeBody(portfolioId, instrumentId, "10.00000000");

    given()
        .baseUri(baseUrl())
        .header("Idempotency-Key", key)
        .contentType("application/json")
        .body(body)
        .when()
        .post("/api/v1/trades")
        .then()
        .statusCode(201);
    // replay
    given()
        .baseUri(baseUrl())
        .header("Idempotency-Key", key)
        .contentType("application/json")
        .body(body)
        .when()
        .post("/api/v1/trades")
        .then()
        .statusCode(201);

    AuditChainVerifier.Result result = auditChainVerifier.verify();
    assertThat(result.valid()).as(result.detail()).isTrue();
  }
}
