package com.meridian.coreservice.kafka;

import static io.restassured.RestAssured.given;
import static org.assertj.core.api.Assertions.assertThat;

import com.atlassian.oai.validator.restassured.OpenApiValidationFilter;
import com.meridian.contracts.ReferenceInstrument;
import com.meridian.contracts.ReferenceInstrumentKey;
import com.meridian.coreservice.audit.AuditChainVerifier;
import com.meridian.coreservice.web.AbstractRestIntegrationTest;
import io.confluent.kafka.serializers.AbstractKafkaSchemaSerDeConfig;
import io.confluent.kafka.serializers.KafkaAvroDeserializer;
import io.confluent.kafka.serializers.KafkaAvroDeserializerConfig;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
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
 * {@code POST /api/v1/instruments} (ADR-0025). Lives in the {@code kafka} package, same reasoning
 * as {@link PortfolioCreationTest}: the load-bearing assertion needs a raw {@link KafkaConsumer}
 * against {@code reference.instruments} plus this package's package-private {@link
 * AbstractKafkaIntegrationTest#seekToEnd}.
 *
 * <p>Unlike {@code PortfolioCreationTest}, there is no audit/published-message {@code event_time}
 * equality assertion here: {@code contracts/avro/reference-instruments.avsc} carries no {@code
 * event_time}/{@code ingest_time} field at all (see ADR-0025's open question), so there is nothing
 * on the wire to compare the audit entry's {@code event_time} against.
 */
class InstrumentCreationTest extends AbstractRestIntegrationTest {

  @Autowired private JdbcTemplate jdbcTemplate;
  @Autowired private AuditChainVerifier auditChainVerifier;
  @Autowired private KafkaProperties kafkaProperties;

  private static final OpenApiValidationFilter OPENAPI_FILTER =
      new OpenApiValidationFilter(
          Path.of("..", "..", "contracts", "openapi", "service-api.yaml").normalize().toString());

  private String equityRequestBody(String instrumentId, String underlyingId, String contractSize) {
    return """
        {
          "instrument_id": "%s",
          "underlying_id": "%s",
          "instrument_type": "EQUITY",
          "currency": "USD",
          "contract_size": "%s"
        }
        """
        .formatted(instrumentId, underlyingId, contractSize);
  }

  private String optionRequestBody(
      String instrumentId,
      String underlyingId,
      String instrumentType,
      String optionType,
      String strike,
      String expiry,
      String contractSize) {
    return """
        {
          "instrument_id": "%s",
          "underlying_id": "%s",
          "instrument_type": "%s",
          "option_type": "%s",
          "strike": "%s",
          "expiry": "%s",
          "currency": "USD",
          "contract_size": "%s"
        }
        """
        .formatted(
            instrumentId, underlyingId, instrumentType, optionType, strike, expiry, contractSize);
  }

  private int auditCount(String instrumentId) {
    Integer count =
        jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM audit_log WHERE entry_type = 'instrument_created' AND"
                + " portfolio_id IS NULL AND payload LIKE ?",
            Integer.class,
            "%\"" + instrumentId + "\"%");
    return count;
  }

  private int instrumentRowCount(String instrumentId) {
    Integer count =
        jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM instruments WHERE instrument_id = ?",
            Integer.class,
            instrumentId);
    return count;
  }

  private KafkaConsumer<ReferenceInstrumentKey, ReferenceInstrument> referenceInstrumentConsumer() {
    Properties props = new Properties();
    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "instrument-creation-assert-" + System.nanoTime());
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

  private ConsumerRecord<ReferenceInstrumentKey, ReferenceInstrument> pollForKey(
      KafkaConsumer<ReferenceInstrumentKey, ReferenceInstrument> consumer,
      String instrumentId,
      Duration timeout) {
    ConsumerRecord<ReferenceInstrumentKey, ReferenceInstrument> found = null;
    long deadline = System.currentTimeMillis() + timeout.toMillis();
    while (found == null && System.currentTimeMillis() < deadline) {
      ConsumerRecords<ReferenceInstrumentKey, ReferenceInstrument> records =
          consumer.poll(Duration.ofSeconds(1));
      for (ConsumerRecord<ReferenceInstrumentKey, ReferenceInstrument> record : records) {
        if (instrumentId.equals(record.key().getInstrumentId())) {
          found = record;
        }
      }
    }
    return found;
  }

  // LOAD-BEARING: a 201 status is not evidence that anything was published -- consume the actual
  // message and assert every field matches.
  @Test
  void creatingAnEquityPublishesAMatchingReferenceInstrumentRecord() {
    String instrumentId = "INSTR-CREATE-EQUITY-" + UUID.randomUUID();

    try (KafkaConsumer<ReferenceInstrumentKey, ReferenceInstrument> consumer =
        referenceInstrumentConsumer()) {
      consumer.subscribe(Collections.singletonList("reference.instruments"));
      AbstractKafkaIntegrationTest.seekToEnd(consumer);

      given()
          .filter(OPENAPI_FILTER)
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(equityRequestBody(instrumentId, instrumentId, "100.00000000"))
          .when()
          .post("/api/v1/instruments")
          .then()
          .statusCode(201)
          .body("instrument_id", org.hamcrest.Matchers.equalTo(instrumentId))
          .body("instrument_type", org.hamcrest.Matchers.equalTo("EQUITY"))
          .body("option_type", org.hamcrest.Matchers.nullValue())
          .body("strike", org.hamcrest.Matchers.nullValue())
          .body("expiry", org.hamcrest.Matchers.nullValue());

      ConsumerRecord<ReferenceInstrumentKey, ReferenceInstrument> found =
          pollForKey(consumer, instrumentId, Duration.ofSeconds(30));

      assertThat(found).as("reference.instruments message for %s", instrumentId).isNotNull();
      ReferenceInstrument value = found.value();
      assertThat(value).as("reference.instruments value must not be a tombstone").isNotNull();
      assertThat(value.getInstrumentId()).isEqualTo(instrumentId);
      assertThat(value.getUnderlyingId()).isEqualTo(instrumentId);
      assertThat(value.getInstrumentType()).isEqualTo(com.meridian.contracts.InstrumentType.EQUITY);
      assertThat(value.getOptionType()).isNull();
      assertThat(value.getStrike()).isNull();
      assertThat(value.getExpiry()).isNull();
      assertThat(value.getCurrency()).isEqualTo("USD");
      assertThat(value.getContractSize()).isEqualByComparingTo("100.00000000");
    }
  }

  // A2: VANILLA_EUROPEAN_OPTION with a valid strike/option_type/expiry returns 201 and publishes
  // correctly -- both option-bearing types must be exercised, not just VANILLA_AMERICAN_OPTION.
  @Test
  void creatingAEuropeanOptionPublishesAMatchingReferenceInstrumentRecord() {
    String instrumentId = "INSTR-CREATE-EURO-" + UUID.randomUUID();
    String underlyingId = "UNDERLYING-" + UUID.randomUUID();
    String expiry = "2027-06-18T00:00:00Z";

    try (KafkaConsumer<ReferenceInstrumentKey, ReferenceInstrument> consumer =
        referenceInstrumentConsumer()) {
      consumer.subscribe(Collections.singletonList("reference.instruments"));
      AbstractKafkaIntegrationTest.seekToEnd(consumer);

      given()
          .filter(OPENAPI_FILTER)
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(
              optionRequestBody(
                  instrumentId,
                  underlyingId,
                  "VANILLA_EUROPEAN_OPTION",
                  "CALL",
                  "150.00000000",
                  expiry,
                  "100.00000000"))
          .when()
          .post("/api/v1/instruments")
          .then()
          .statusCode(201)
          .body("instrument_type", org.hamcrest.Matchers.equalTo("VANILLA_EUROPEAN_OPTION"))
          .body("option_type", org.hamcrest.Matchers.equalTo("CALL"))
          .body("strike", org.hamcrest.Matchers.equalTo("150.00000000"));

      ConsumerRecord<ReferenceInstrumentKey, ReferenceInstrument> found =
          pollForKey(consumer, instrumentId, Duration.ofSeconds(30));

      assertThat(found).as("reference.instruments message for %s", instrumentId).isNotNull();
      ReferenceInstrument value = found.value();
      assertThat(value.getInstrumentType())
          .isEqualTo(com.meridian.contracts.InstrumentType.VANILLA_EUROPEAN_OPTION);
      assertThat(value.getOptionType()).isEqualTo(com.meridian.contracts.OptionType.CALL);
      assertThat(value.getStrike()).isEqualByComparingTo("150.00000000");
      assertThat(value.getExpiry()).isEqualTo(Instant.parse(expiry));
      assertThat(value.getUnderlyingId()).isEqualTo(underlyingId);
      assertThat(value.getContractSize()).isEqualByComparingTo("100.00000000");
    }
  }

  @Test
  void repeatedIdenticalCreationReturns200WithNoSecondMessageOrAuditEntry() {
    String instrumentId = "INSTR-CREATE-REPEAT-" + UUID.randomUUID();
    String body = equityRequestBody(instrumentId, instrumentId, "1.00000000");

    try (KafkaConsumer<ReferenceInstrumentKey, ReferenceInstrument> consumer =
        referenceInstrumentConsumer()) {
      consumer.subscribe(Collections.singletonList("reference.instruments"));
      AbstractKafkaIntegrationTest.seekToEnd(consumer);

      given()
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(body)
          .when()
          .post("/api/v1/instruments")
          .then()
          .statusCode(201);

      ConsumerRecord<ReferenceInstrumentKey, ReferenceInstrument> first =
          pollForKey(consumer, instrumentId, Duration.ofSeconds(30));
      assertThat(first).as("first creation's reference.instruments message").isNotNull();

      given()
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(body)
          .when()
          .post("/api/v1/instruments")
          .then()
          .statusCode(200)
          .body("instrument_id", org.hamcrest.Matchers.equalTo(instrumentId));

      ConsumerRecord<ReferenceInstrumentKey, ReferenceInstrument> second =
          pollForKey(consumer, instrumentId, Duration.ofSeconds(5));
      assertThat(second).as("no second reference.instruments message after a 200 replay").isNull();

      assertThat(auditCount(instrumentId)).isEqualTo(1);
      assertThat(instrumentRowCount(instrumentId)).isEqualTo(1);
    }
  }

  @Test
  void sameIdWithADifferentContractSizeReturns409WithNoAuditEntryOrMessage() {
    String instrumentId = "INSTR-CREATE-CONFLICT-" + UUID.randomUUID();

    try (KafkaConsumer<ReferenceInstrumentKey, ReferenceInstrument> consumer =
        referenceInstrumentConsumer()) {
      consumer.subscribe(Collections.singletonList("reference.instruments"));
      AbstractKafkaIntegrationTest.seekToEnd(consumer);

      given()
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(equityRequestBody(instrumentId, instrumentId, "1.00000000"))
          .when()
          .post("/api/v1/instruments")
          .then()
          .statusCode(201);

      ConsumerRecord<ReferenceInstrumentKey, ReferenceInstrument> first =
          pollForKey(consumer, instrumentId, Duration.ofSeconds(30));
      assertThat(first).as("first creation's reference.instruments message").isNotNull();

      given()
          .baseUri(baseUrl())
          .contentType("application/json")
          .body(equityRequestBody(instrumentId, instrumentId, "2.00000000"))
          .when()
          .post("/api/v1/instruments")
          .then()
          .statusCode(409);

      ConsumerRecord<ReferenceInstrumentKey, ReferenceInstrument> second =
          pollForKey(consumer, instrumentId, Duration.ofSeconds(5));
      assertThat(second).as("no reference.instruments message resulted from the 409").isNull();

      assertThat(auditCount(instrumentId)).isEqualTo(1);
      assertThat(instrumentRowCount(instrumentId)).isEqualTo(1);
    }
  }

  @Test
  void unknownInstrumentTypeReturns400() {
    String instrumentId = "INSTR-CREATE-BADTYPE-" + UUID.randomUUID();
    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(
            """
            {
              "instrument_id": "%s",
              "underlying_id": "%s",
              "instrument_type": "NOT_A_REAL_TYPE",
              "currency": "USD",
              "contract_size": "1.00000000"
            }
            """
                .formatted(instrumentId, instrumentId))
        .when()
        .post("/api/v1/instruments")
        .then()
        .statusCode(400);
    assertThat(instrumentRowCount(instrumentId)).isEqualTo(0);
  }

  @Test
  void americanOptionMissingExpiryReturns400() {
    String instrumentId = "INSTR-CREATE-NOEXPIRY-" + UUID.randomUUID();
    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(
            """
            {
              "instrument_id": "%s",
              "underlying_id": "%s",
              "instrument_type": "VANILLA_AMERICAN_OPTION",
              "option_type": "PUT",
              "strike": "50.00000000",
              "currency": "USD",
              "contract_size": "100.00000000"
            }
            """
                .formatted(instrumentId, instrumentId))
        .when()
        .post("/api/v1/instruments")
        .then()
        .statusCode(400);
    assertThat(instrumentRowCount(instrumentId)).isEqualTo(0);
  }

  // A2: the American option type must also be exercised for the missing-required-field case, not
  // only the European one.
  @Test
  void americanOptionMissingStrikeReturns400() {
    String instrumentId = "INSTR-CREATE-NOSTRIKE-" + UUID.randomUUID();
    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(
            """
            {
              "instrument_id": "%s",
              "underlying_id": "%s",
              "instrument_type": "VANILLA_AMERICAN_OPTION",
              "option_type": "PUT",
              "expiry": "2027-01-01T00:00:00Z",
              "currency": "USD",
              "contract_size": "100.00000000"
            }
            """
                .formatted(instrumentId, instrumentId))
        .when()
        .post("/api/v1/instruments")
        .then()
        .statusCode(400);
    assertThat(instrumentRowCount(instrumentId)).isEqualTo(0);
  }

  @Test
  void equityCarryingAStrikeReturns400() {
    String instrumentId = "INSTR-CREATE-EQUITYSTRIKE-" + UUID.randomUUID();
    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(
            """
            {
              "instrument_id": "%s",
              "underlying_id": "%s",
              "instrument_type": "EQUITY",
              "strike": "50.00000000",
              "currency": "USD",
              "contract_size": "1.00000000"
            }
            """
                .formatted(instrumentId, instrumentId))
        .when()
        .post("/api/v1/instruments")
        .then()
        .statusCode(400);
    assertThat(instrumentRowCount(instrumentId)).isEqualTo(0);
  }

  @Test
  void zeroContractSizeReturns400() {
    String instrumentId = "INSTR-CREATE-ZEROSIZE-" + UUID.randomUUID();
    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(equityRequestBody(instrumentId, instrumentId, "0"))
        .when()
        .post("/api/v1/instruments")
        .then()
        .statusCode(400);
    assertThat(instrumentRowCount(instrumentId)).isEqualTo(0);
  }

  @Test
  void negativeContractSizeReturns400() {
    String instrumentId = "INSTR-CREATE-NEGSIZE-" + UUID.randomUUID();
    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(equityRequestBody(instrumentId, instrumentId, "-1.00000000"))
        .when()
        .post("/api/v1/instruments")
        .then()
        .statusCode(400);
    assertThat(instrumentRowCount(instrumentId)).isEqualTo(0);
  }

  @Test
  void badCurrencyReturns400() {
    String instrumentId = "INSTR-CREATE-BADCCY-" + UUID.randomUUID();
    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(
            """
            {
              "instrument_id": "%s",
              "underlying_id": "%s",
              "instrument_type": "EQUITY",
              "currency": "usd",
              "contract_size": "1.00000000"
            }
            """
                .formatted(instrumentId, instrumentId))
        .when()
        .post("/api/v1/instruments")
        .then()
        .statusCode(400);
    assertThat(instrumentRowCount(instrumentId)).isEqualTo(0);
  }

  @Test
  void auditEntryExistsHasNullPortfolioIdAndChainsFromThePreviousHead() {
    String instrumentId = "INSTR-CREATE-AUDIT-" + UUID.randomUUID();

    given()
        .baseUri(baseUrl())
        .contentType("application/json")
        .body(equityRequestBody(instrumentId, instrumentId, "1.00000000"))
        .when()
        .post("/api/v1/instruments")
        .then()
        .statusCode(201);

    assertThat(auditCount(instrumentId)).isEqualTo(1);

    Integer nullPortfolioScoped =
        jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM audit_log WHERE entry_type = 'instrument_created' AND"
                + " portfolio_id IS NULL AND payload LIKE ?",
            Integer.class,
            "%\"" + instrumentId + "\"%");
    assertThat(nullPortfolioScoped).isEqualTo(1);

    AuditChainVerifier.Result result = auditChainVerifier.verify();
    assertThat(result.valid()).as(result.detail()).isTrue();
  }
}
