package com.meridian.coreservice.kafka;

import static io.restassured.RestAssured.given;
import static org.assertj.core.api.Assertions.assertThat;

import com.atlassian.oai.validator.restassured.OpenApiValidationFilter;
import com.meridian.contracts.PortfolioState;
import com.meridian.contracts.PortfolioStateKey;
import com.meridian.coreservice.audit.AuditChainVerifier;
import com.meridian.coreservice.web.AbstractRestIntegrationTest;
import io.confluent.kafka.serializers.AbstractKafkaSchemaSerDeConfig;
import io.confluent.kafka.serializers.KafkaAvroDeserializer;
import io.confluent.kafka.serializers.KafkaAvroDeserializerConfig;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Collections;
import java.util.Properties;
import java.util.UUID;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * {@code POST /api/v1/portfolios} (ADR-0024). Lives in the {@code kafka} package (not {@code web},
 * where {@link com.meridian.coreservice.web.TradeBookingTest} lives) because the load-bearing
 * assertion needs a raw {@link KafkaConsumer} against {@code portfolio.state} plus this package's
 * package-private {@link AbstractKafkaIntegrationTest#seekToEnd}, the same as {@link
 * PortfolioMutationPublishesStateTest}.
 */
class PortfolioCreationTest extends AbstractRestIntegrationTest {

  @Autowired private JdbcTemplate jdbcTemplate;
  @Autowired private AuditChainVerifier auditChainVerifier;
  @Autowired private KafkaProperties kafkaProperties;

  private static final OpenApiValidationFilter OPENAPI_FILTER =
      new OpenApiValidationFilter(
          Path.of("..", "..", "contracts", "openapi", "service-api.yaml").normalize().toString());

  private String requestBody(String portfolioId, String name, String baseCurrency, String owner) {
    return """
        {
          "portfolio_id": "%s",
          "name": "%s",
          "base_currency": "%s",
          "owner": "%s"
        }
        """
        .formatted(portfolioId, name, baseCurrency, owner);
  }

  private int auditCount(String portfolioId) {
    Integer count =
        jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM audit_log WHERE portfolio_id = ? AND entry_type ="
                + " 'portfolio_created'",
            Integer.class,
            portfolioId);
    return count;
  }

  private Instant auditEventTime(String portfolioId) {
    return jdbcTemplate.queryForObject(
        "SELECT event_time FROM audit_log WHERE portfolio_id = ? AND entry_type ="
            + " 'portfolio_created'",
        (rs, rowNum) -> rs.getTimestamp("event_time").toInstant(),
        portfolioId);
  }

  private int portfolioRowCount(String portfolioId) {
    Integer count =
        jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM portfolios WHERE portfolio_id = ?", Integer.class, portfolioId);
    return count;
  }

  private KafkaConsumer<PortfolioStateKey, PortfolioState> portfolioStateConsumer() {
    Properties props = new Properties();
    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "portfolio-creation-assert-" + System.nanoTime());
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, KafkaAvroDeserializer.class.getName());
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, KafkaAvroDeserializer.class.getName());
    props.put(
        AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG,
        kafkaProperties.getSchemaRegistryUrl());
    props.put(KafkaAvroDeserializerConfig.SPECIFIC_AVRO_READER_CONFIG, true);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
    return new KafkaConsumer<>(props);
  }

  /**
   * Polls until a message keyed on {@code portfolioId} is found or the deadline passes. Returns
   * {@code null} on timeout -- used both to find the expected message (load-bearing test) and, with
   * a short deadline, to confirm no additional message ever arrives after a 200/409 response.
   */
  private ConsumerRecord<PortfolioStateKey, PortfolioState> pollForKey(
      KafkaConsumer<PortfolioStateKey, PortfolioState> consumer,
      String portfolioId,
      Duration timeout) {
    ConsumerRecord<PortfolioStateKey, PortfolioState> found = null;
    long deadline = System.currentTimeMillis() + timeout.toMillis();
    while (found == null && System.currentTimeMillis() < deadline) {
      ConsumerRecords<PortfolioStateKey, PortfolioState> records =
          consumer.poll(Duration.ofSeconds(1));
      for (ConsumerRecord<PortfolioStateKey, PortfolioState> record : records) {
        if (portfolioId.equals(record.key().getPortfolioId())) {
          found = record;
        }
      }
    }
    return found;
  }

  // LOAD-BEARING: a 201 status is not evidence that anything was published -- consume the actual
  // message and assert on it.
  @Test
  void creatingAPortfolioPublishesAnEmptyPositionsPortfolioStateRecord() {
    String portfolioId = "PF-CREATE-STATE-" + UUID.randomUUID();

    try (KafkaConsumer<PortfolioStateKey, PortfolioState> consumer = portfolioStateConsumer()) {
      consumer.subscribe(Collections.singletonList("portfolio.state"));
      AbstractKafkaIntegrationTest.seekToEnd(consumer);

      given()
          .filter(OPENAPI_FILTER)
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(requestBody(portfolioId, "Create State Test", "USD", "desk-1"))
          .when()
          .post("/api/v1/portfolios")
          .then()
          .statusCode(201)
          .body("portfolio_id", org.hamcrest.Matchers.equalTo(portfolioId));

      ConsumerRecord<PortfolioStateKey, PortfolioState> found =
          pollForKey(consumer, portfolioId, Duration.ofSeconds(30));

      assertThat(found).as("portfolio.state message for %s", portfolioId).isNotNull();
      assertThat(found.key().getPortfolioId()).isEqualTo(portfolioId);
      PortfolioState value = found.value();
      assertThat(value).as("portfolio.state value must not be a tombstone").isNotNull();
      assertThat(value.getPortfolioId()).isEqualTo(portfolioId);
      assertThat(value.getPositions()).as("positions must be present and empty").isEmpty();
    }
  }

  @Test
  void repeatedIdenticalCreationReturns200WithNoSecondPortfolioStateOrAuditEntry() {
    String portfolioId = "PF-CREATE-REPEAT-" + UUID.randomUUID();
    String body = requestBody(portfolioId, "Repeat Test", "USD", "desk-1");

    try (KafkaConsumer<PortfolioStateKey, PortfolioState> consumer = portfolioStateConsumer()) {
      consumer.subscribe(Collections.singletonList("portfolio.state"));
      AbstractKafkaIntegrationTest.seekToEnd(consumer);

      given()
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(body)
          .when()
          .post("/api/v1/portfolios")
          .then()
          .statusCode(201);

      ConsumerRecord<PortfolioStateKey, PortfolioState> first =
          pollForKey(consumer, portfolioId, Duration.ofSeconds(30));
      assertThat(first).as("first creation's portfolio.state message").isNotNull();

      given()
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(body)
          .when()
          .post("/api/v1/portfolios")
          .then()
          .statusCode(200)
          .body("portfolio_id", org.hamcrest.Matchers.equalTo(portfolioId))
          .body("name", org.hamcrest.Matchers.equalTo("Repeat Test"));

      ConsumerRecord<PortfolioStateKey, PortfolioState> second =
          pollForKey(consumer, portfolioId, Duration.ofSeconds(5));
      assertThat(second).as("no second portfolio.state message after a 200 replay").isNull();

      assertThat(auditCount(portfolioId)).isEqualTo(1);
      assertThat(portfolioRowCount(portfolioId)).isEqualTo(1);
    }
  }

  @Test
  void sameIdWithADifferentNameReturns409WithNoAuditEntryOrPortfolioState() {
    String portfolioId = "PF-CREATE-CONFLICT-" + UUID.randomUUID();

    try (KafkaConsumer<PortfolioStateKey, PortfolioState> consumer = portfolioStateConsumer()) {
      consumer.subscribe(Collections.singletonList("portfolio.state"));
      AbstractKafkaIntegrationTest.seekToEnd(consumer);

      given()
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(requestBody(portfolioId, "Original Name", "USD", "desk-1"))
          .when()
          .post("/api/v1/portfolios")
          .then()
          .statusCode(201);

      ConsumerRecord<PortfolioStateKey, PortfolioState> first =
          pollForKey(consumer, portfolioId, Duration.ofSeconds(30));
      assertThat(first).as("first creation's portfolio.state message").isNotNull();

      given()
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(requestBody(portfolioId, "Different Name", "USD", "desk-1"))
          .when()
          .post("/api/v1/portfolios")
          .then()
          .statusCode(409);

      ConsumerRecord<PortfolioStateKey, PortfolioState> second =
          pollForKey(consumer, portfolioId, Duration.ofSeconds(5));
      assertThat(second).as("no portfolio.state message resulted from the 409").isNull();

      assertThat(auditCount(portfolioId)).isEqualTo(1);
      assertThat(portfolioRowCount(portfolioId)).isEqualTo(1);
    }
  }

  @Test
  void blankFieldReturns400() {
    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(requestBody("PF-CREATE-BLANK-" + UUID.randomUUID(), "", "USD", "desk-1"))
        .when()
        .post("/api/v1/portfolios")
        .then()
        .statusCode(400);
  }

  @Test
  void lowercaseBaseCurrencyReturns400() {
    String portfolioId = "PF-CREATE-BADCCY-1-" + UUID.randomUUID();
    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(requestBody(portfolioId, "Bad Currency", "usd", "desk-1"))
        .when()
        .post("/api/v1/portfolios")
        .then()
        .statusCode(400);
    assertThat(portfolioRowCount(portfolioId)).isEqualTo(0);
  }

  @Test
  void twoLetterBaseCurrencyReturns400() {
    String portfolioId = "PF-CREATE-BADCCY-2-" + UUID.randomUUID();
    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(requestBody(portfolioId, "Bad Currency", "US", "desk-1"))
        .when()
        .post("/api/v1/portfolios")
        .then()
        .statusCode(400);
    assertThat(portfolioRowCount(portfolioId)).isEqualTo(0);
  }

  @Test
  void fourLetterBaseCurrencyReturns400() {
    String portfolioId = "PF-CREATE-BADCCY-3-" + UUID.randomUUID();
    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(requestBody(portfolioId, "Bad Currency", "USDD", "desk-1"))
        .when()
        .post("/api/v1/portfolios")
        .then()
        .statusCode(400);
    assertThat(portfolioRowCount(portfolioId)).isEqualTo(0);
  }

  @Test
  void auditEntryExistsIsPortfolioScopedAndChainsFromThePreviousHead() {
    String portfolioId = "PF-CREATE-AUDIT-" + UUID.randomUUID();

    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(requestBody(portfolioId, "Audit Test", "USD", "desk-1"))
        .when()
        .post("/api/v1/portfolios")
        .then()
        .statusCode(201);

    given()
        .filter(OPENAPI_FILTER)
        .baseUri(baseUrl())
        .when()
        .get("/api/v1/portfolios/" + portfolioId + "/audit")
        .then()
        .statusCode(200)
        .body("[0].entry_type", org.hamcrest.Matchers.equalTo("portfolio_created"));

    assertThat(auditCount(portfolioId)).isEqualTo(1);

    AuditChainVerifier.Result result = auditChainVerifier.verify();
    assertThat(result.valid()).as(result.detail()).isTrue();
  }

  // This is the assertion that catches a second Instant.now() creeping in: the audit entry's
  // event_time and the published portfolio.state message's event_time must be the exact same
  // captured instant (truncated to microsecond precision independently by Postgres and by the
  // Avro timestamp-micros logical type -- not by two separate calls to Instant.now()).
  @Test
  void auditEntryEventTimeMatchesPublishedPortfolioStateEventTime() {
    String portfolioId = "PF-CREATE-TS-" + UUID.randomUUID();

    try (KafkaConsumer<PortfolioStateKey, PortfolioState> consumer = portfolioStateConsumer()) {
      consumer.subscribe(Collections.singletonList("portfolio.state"));
      AbstractKafkaIntegrationTest.seekToEnd(consumer);

      given()
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(requestBody(portfolioId, "Timestamp Test", "USD", "desk-1"))
          .when()
          .post("/api/v1/portfolios")
          .then()
          .statusCode(201);

      ConsumerRecord<PortfolioStateKey, PortfolioState> found =
          pollForKey(consumer, portfolioId, Duration.ofSeconds(30));
      assertThat(found).isNotNull();

      Instant publishedEventTime = found.value().getEventTime();
      Instant storedAuditEventTime = auditEventTime(portfolioId);

      assertThat(publishedEventTime.truncatedTo(ChronoUnit.MICROS))
          .as("audit entry event_time must equal the published portfolio.state event_time")
          .isEqualTo(storedAuditEventTime.truncatedTo(ChronoUnit.MICROS));
    }
  }
}
