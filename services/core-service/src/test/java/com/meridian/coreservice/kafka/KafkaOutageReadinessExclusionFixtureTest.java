package com.meridian.coreservice.kafka;

import static io.restassured.RestAssured.given;

import com.github.dockerjava.api.DockerClient;
import com.meridian.coreservice.web.AbstractRestIntegrationTest;
import io.restassured.response.Response;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.DockerClientFactory;

/**
 * ADR-0022 verification item 6: proves the deliberate exclusion of Kafka from readiness actually
 * holds under a real broker outage, rather than being untested intent. Stops the shared Kafka
 * container (directly via the Docker daemon, not Testcontainers' {@code stop()}, so it comes back
 * for the rest of the suite) and confirms readiness stays UP and a REST read -- served entirely
 * from Postgres -- keeps working throughout.
 *
 * <p>Does NOT assert that {@code lastPollAgeMillis} grows during the outage. Verified by hand
 * against the real {@code docker-compose.yml} stack (session log / PR description): {@code
 * KafkaConsumer.poll()} does not throw when the broker is unreachable -- it logs "Connection to
 * node N could not be established" and returns an empty batch, which {@link
 * RiskSnapshotConsumerRunner#pollLoop} correctly treats as a successful poll (see that class's
 * doc). So a full single-broker outage is, in this consumer's current design, indistinguishable
 * from a live broker with nothing new to deliver -- the health detail's freshness signal does not
 * actually surface it. That is a real, named gap (not silently assumed away), tracked alongside
 * ADR-0022's other Q2 observability gap rather than fixed here.
 */
class KafkaOutageReadinessExclusionFixtureTest extends AbstractRestIntegrationTest {

  @Autowired private JdbcTemplate jdbcTemplate;

  @Test
  void readinessAndReadsSurviveAKafkaBrokerOutage() {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES"
            + " ('PF-KAFKA-OUTAGE', 'Kafka Outage Test', 'USD', 'desk-1') ON CONFLICT DO NOTHING");
    jdbcTemplate.update(
        "INSERT INTO risk_snapshots (portfolio_id, as_of, pricer_version, price, cash_delta,"
            + " cash_gamma, cash_vega, cash_theta, cash_rho, var_95, scenario_id,"
            + " oldest_input_event_time, ingest_time) VALUES ('PF-KAFKA-OUTAGE',"
            + " '2026-08-31T12:00:00Z', 'v1.0.0', 100.00000000, 1, 1, 1, 1, 1, 0.05, 'scenario-1',"
            + " '2026-08-31T12:00:00Z', now())");

    // Baseline: the consumer has completed at least one real poll before the outage.
    awaitKafkaDetail(details -> Boolean.TRUE.equals(details.getBoolean("pollThreadAlive")));

    DockerClient docker = DockerClientFactory.instance().client();
    String kafkaContainerId = kafkaContainer().getContainerId();
    docker.stopContainerCmd(kafkaContainerId).withTimeout(10).exec();
    try {
      // Readiness must never move for a Kafka outage -- checked repeatedly across the outage
      // window, not just once, since a transient flip would be exactly the bug this ADR forbids.
      Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
      while (Instant.now().isBefore(deadline)) {
        given()
            .baseUri(baseUrl())
            .when()
            .get("/actuator/health/readiness")
            .then()
            .statusCode(200)
            .body("status", org.hamcrest.Matchers.equalTo("UP"));
        sleep(1000);
      }

      // The REST read path is unaffected -- it never touches Kafka.
      given()
          .baseUri(baseUrl())
          .when()
          .get("/api/v1/portfolios/PF-KAFKA-OUTAGE/risk")
          .then()
          .statusCode(200)
          .body("portfolio_id", org.hamcrest.Matchers.equalTo("PF-KAFKA-OUTAGE"));

      // The consumer's poll loop is still alive throughout -- it never throws on a broker outage
      // (see class doc), so this stays true rather than reflecting the outage.
      given()
          .baseUri(baseUrl())
          .when()
          .get("/actuator/health")
          .then()
          .statusCode(200)
          .body(
              "components.riskSnapshotConsumer.details.pollThreadAlive",
              org.hamcrest.Matchers.equalTo(true));
    } finally {
      docker.startContainerCmd(kafkaContainerId).exec();
    }

    // Let the consumer resume polling successfully before ending the test, so later test classes
    // in this suite see a healthy shared consumer again.
    awaitKafkaDetail(details -> details.getLong("lastPollAgeMillis") < 5000);
  }

  private void awaitKafkaDetail(
      java.util.function.Predicate<io.restassured.path.json.JsonPath> condition) {
    Instant deadline = Instant.now().plus(Duration.ofSeconds(30));
    while (Instant.now().isBefore(deadline)) {
      Response health = given().baseUri(baseUrl()).when().get("/actuator/health");
      if (condition.test(health.jsonPath().setRoot("components.riskSnapshotConsumer.details"))) {
        return;
      }
      sleep(500);
    }
    throw new AssertionError("Kafka consumer health detail condition never satisfied within 30s");
  }

  private static void sleep(long millis) {
    try {
      Thread.sleep(millis);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new RuntimeException(e);
    }
  }
}
