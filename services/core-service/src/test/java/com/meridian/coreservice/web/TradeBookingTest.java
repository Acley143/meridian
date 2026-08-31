package com.meridian.coreservice.web;

import static io.restassured.RestAssured.given;
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.equalTo;

import com.atlassian.oai.validator.restassured.OpenApiValidationFilter;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/** {@code POST /trades} -- the first real caller of PortfolioMutationService.applyTrade. */
class TradeBookingTest extends AbstractRestIntegrationTest {

  @Autowired private JdbcTemplate jdbcTemplate;

  private static final OpenApiValidationFilter OPENAPI_FILTER =
      new OpenApiValidationFilter(
          Path.of("..", "..", "contracts", "openapi", "service-api.yaml").normalize().toString());

  @Test
  void bookingATradeUpdatesPositionsAndReturns201() {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES"
            + " ('PF-TRADE-TEST', 'Trade Test', 'USD', 'desk-1') ON CONFLICT DO NOTHING");
    jdbcTemplate.update(
        "INSERT INTO instruments (instrument_id, underlying_id, instrument_type, currency,"
            + " contract_size) VALUES ('TRADE-INSTR', 'TRADE-INSTR', 'EQUITY', 'USD', 1) ON"
            + " CONFLICT DO NOTHING");

    String requestBody =
        """
        {
          "portfolio_id": "PF-TRADE-TEST",
          "instrument_id": "TRADE-INSTR",
          "quantity": "50.00000000",
          "price": "123.45000000",
          "event_time": "2026-08-31T09:00:00Z"
        }
        """;

    given()
        .filter(OPENAPI_FILTER)
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(requestBody)
        .when()
        .post("/trades")
        .then()
        .statusCode(201)
        .body("portfolio_id", equalTo("PF-TRADE-TEST"))
        .body("quantity", equalTo("50.00000000"));

    java.math.BigDecimal quantity =
        jdbcTemplate.queryForObject(
            "SELECT quantity FROM positions WHERE portfolio_id = 'PF-TRADE-TEST' AND"
                + " instrument_id = 'TRADE-INSTR'",
            java.math.BigDecimal.class);
    assertThat(quantity).isEqualByComparingTo("50.00000000");
  }

  @Test
  void bookingATradeAgainstAnUnknownPortfolioReturns400() {
    String requestBody =
        """
        {
          "portfolio_id": "PF-DOES-NOT-EXIST",
          "instrument_id": "TRADE-INSTR",
          "quantity": "1.00000000",
          "price": "1.00000000",
          "event_time": "2026-08-31T09:00:00Z"
        }
        """;

    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(requestBody)
        .when()
        .post("/trades")
        .then()
        .statusCode(400);
  }

  @Test
  void bookingATradeWritesATradeBookedAuditEntryVisibleThroughTheAuditEndpoint() {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES"
            + " ('PF-AUDIT-TEST', 'Audit Test', 'USD', 'desk-1') ON CONFLICT DO NOTHING");
    jdbcTemplate.update(
        "INSERT INTO instruments (instrument_id, underlying_id, instrument_type, currency,"
            + " contract_size) VALUES ('AUDIT-INSTR', 'AUDIT-INSTR', 'EQUITY', 'USD', 1) ON"
            + " CONFLICT DO NOTHING");

    String requestBody =
        """
        {
          "portfolio_id": "PF-AUDIT-TEST",
          "instrument_id": "AUDIT-INSTR",
          "quantity": "10.00000000",
          "price": "5.00000000",
          "event_time": "2026-08-31T09:00:00Z"
        }
        """;

    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(requestBody)
        .when()
        .post("/trades")
        .then()
        .statusCode(201);

    given()
        .filter(OPENAPI_FILTER)
        .baseUri(baseUrl())
        .when()
        .get("/portfolios/PF-AUDIT-TEST/audit")
        .then()
        .statusCode(200)
        .body("[0].entry_type", equalTo("trade_booked"));
  }
}
