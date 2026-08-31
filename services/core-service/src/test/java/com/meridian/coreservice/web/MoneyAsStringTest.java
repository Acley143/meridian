package com.meridian.coreservice.web;

import static io.restassured.RestAssured.given;
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.equalTo;

import com.atlassian.oai.validator.restassured.OpenApiValidationFilter;
import java.math.BigDecimal;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Money serializes as a JSON string, never a number (Task 1) -- tested against a value that
 * demonstrably loses precision as a double, the same style of value 05a's NUMERIC(38,8) round-trip
 * test used. Also the primary Task 3 (OpenAPI conformance) and Task 4.4 (real HTTP client)
 * coverage: a real request over the wire, validated against contracts/openapi/service-api.yaml
 * itself via the same swagger-request-validator tool the pom now depends on for exactly this.
 */
class MoneyAsStringTest extends AbstractRestIntegrationTest {

  private static final String DOUBLE_LOSSY_VALUE = "79228162514.26433759";

  @Autowired private JdbcTemplate jdbcTemplate;

  private static final OpenApiValidationFilter OPENAPI_FILTER =
      new OpenApiValidationFilter(
          Path.of("..", "..", "contracts", "openapi", "service-api.yaml").normalize().toString());

  @Test
  void positionQuantitySerializesAsAQuotedStringNotANumber() {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES ('PF-MONEY',"
            + " 'Money Test', 'USD', 'desk-1') ON CONFLICT DO NOTHING");
    jdbcTemplate.update(
        "INSERT INTO instruments (instrument_id, underlying_id, instrument_type, currency,"
            + " contract_size) VALUES ('MONEY-INSTR', 'MONEY-INSTR', 'EQUITY', 'USD', 1) ON"
            + " CONFLICT DO NOTHING");
    jdbcTemplate.update(
        "INSERT INTO positions (portfolio_id, instrument_id, quantity, average_cost,"
            + " as_of_event_time) VALUES ('PF-MONEY', 'MONEY-INSTR', ?, 1.00000000,"
            + " '2026-08-31T00:00:00Z') ON CONFLICT (portfolio_id, instrument_id) DO UPDATE SET"
            + " quantity = EXCLUDED.quantity",
        new BigDecimal(DOUBLE_LOSSY_VALUE));

    String rawBody =
        given()
            .filter(OPENAPI_FILTER)
            .baseUri(baseUrl())
            .when()
            .get("/portfolios/PF-MONEY/positions")
            .then()
            .statusCode(200)
            .extract()
            .asString();

    // Assert against the RAW JSON text, not a deserialized value -- the whole point is that the
    // number appears as a quoted string with no reformatting, not that some client's parser
    // happens to reconstruct the right BigDecimal despite a lossy JSON number in between.
    assertThat(rawBody).contains("\"" + DOUBLE_LOSSY_VALUE + "\"");
    assertThat(rawBody)
        .doesNotContain(":" + DOUBLE_LOSSY_VALUE); // would be an unquoted JSON number

    // And the money-round-trips-through-a-real-HTTP-client half (Task 4.4): parse the string back
    // and assert exact BigDecimal equality with the value that would have lost precision as a
    // double.
    io.restassured.response.Response response =
        given().baseUri(baseUrl()).when().get("/portfolios/PF-MONEY/positions");
    String quantityField = response.jsonPath().getString("[0].quantity");
    assertThat(new BigDecimal(quantityField))
        .isEqualByComparingTo(new BigDecimal(DOUBLE_LOSSY_VALUE));
    assertThat(quantityField).isEqualTo(DOUBLE_LOSSY_VALUE);
  }

  @Test
  void getPortfolioResponseMatchesOpenApiSchema() {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES"
            + " ('PF-CONFORMANCE', 'Conformance Test', 'USD', 'desk-1') ON CONFLICT DO NOTHING");

    given()
        .filter(OPENAPI_FILTER)
        .baseUri(baseUrl())
        .when()
        .get("/portfolios/PF-CONFORMANCE")
        .then()
        .statusCode(200)
        .body("portfolio_id", equalTo("PF-CONFORMANCE"));
  }

  @Test
  void unknownPortfolioReturns404MatchingOpenApiSchema() {
    given()
        .filter(OPENAPI_FILTER)
        .baseUri(baseUrl())
        .when()
        .get("/portfolios/PF-DOES-NOT-EXIST")
        .then()
        .statusCode(404);
  }
}
