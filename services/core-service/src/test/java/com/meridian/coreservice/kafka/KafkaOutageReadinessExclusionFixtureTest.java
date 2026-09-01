package com.meridian.coreservice.kafka;

import static io.restassured.RestAssured.given;
import static org.assertj.core.api.Assertions.assertThat;

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
 * holds under a real broker outage, rather than being untested intent -- AND proves the Kafka
 * health detail can actually report something other than healthy during that outage. Stops the
 * shared Kafka container (directly via the Docker daemon, not Testcontainers' {@code stop()}, so it
 * comes back for the rest of the suite).
 *
 * <p>An earlier version of this test asserted {@code pollThreadAlive} stayed {@code true} and left
 * it there, which encoded a real bug as intended behavior: {@code KafkaConsumer.poll()} does not
 * throw when the broker is unreachable, so that field (and its iteration timestamp) keep advancing
 * through a total outage -- a healthy-looking field during a real failure is worse than no field,
 * since it's the first thing an on-call engineer checks. This version instead asserts on {@code
 * lastHeartbeatSecondsAgo} (published from {@code KafkaConsumer}'s own {@code
 * consumer-coordinator-metrics} group), because the consumer group heartbeat genuinely stops
 * succeeding when the coordinator is unreachable -- verified by hand against this exact fixture
 * before this assertion was written, not assumed.
 */
class KafkaOutageReadinessExclusionFixtureTest extends AbstractRestIntegrationTest {

  @Autowired private JdbcTemplate jdbcTemplate;

  @Test
  void heartbeatAgeGrowsDuringABrokerOutageWhileReadinessAndReadsAreUnaffected() {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES"
            + " ('PF-KAFKA-OUTAGE', 'Kafka Outage Test', 'USD', 'desk-1') ON CONFLICT DO NOTHING");
    jdbcTemplate.update(
        "INSERT INTO risk_snapshots (portfolio_id, as_of, pricer_version, price, cash_delta,"
            + " cash_gamma, cash_vega, cash_theta, cash_rho, var_95, scenario_id,"
            + " oldest_input_event_time, ingest_time) VALUES ('PF-KAFKA-OUTAGE',"
            + " '2026-08-31T12:00:00Z', 'v1.0.0', 100.00000000, 1, 1, 1, 1, 1, 0.05, 'scenario-1',"
            + " '2026-08-31T12:00:00Z', now())");

    // Baseline: the consumer has joined the group and has a real (small) heartbeat age.
    awaitKafkaDetail(details -> heartbeatSecondsAgo(details) != null);
    double baselineHeartbeatSecondsAgo = heartbeatSecondsAgo(currentKafkaDetail());
    assertThat(baselineHeartbeatSecondsAgo)
        .as("baseline heartbeat age should be small while the broker is healthy")
        .isLessThan(10.0);

    DockerClient docker = DockerClientFactory.instance().client();
    String kafkaContainerId = kafkaContainer().getContainerId();
    docker.stopContainerCmd(kafkaContainerId).withTimeout(10).exec();
    try {
      // Readiness must never move for a Kafka outage -- checked repeatedly across the outage
      // window, not just once, since a transient flip would be exactly the bug this ADR forbids.
      // The REST read path (served entirely from Postgres) is checked in the same window.
      Instant deadline = Instant.now().plus(Duration.ofSeconds(20));
      while (Instant.now().isBefore(deadline)) {
        given()
            .baseUri(baseUrl())
            .when()
            .get("/actuator/health/readiness")
            .then()
            .statusCode(200)
            .body("status", org.hamcrest.Matchers.equalTo("UP"));
        given()
            .baseUri(baseUrl())
            .when()
            .get("/api/v1/portfolios/PF-KAFKA-OUTAGE/risk")
            .then()
            .statusCode(200)
            .body("portfolio_id", org.hamcrest.Matchers.equalTo("PF-KAFKA-OUTAGE"));
        sleep(1000);
      }

      // The inverted assertion this fixture exists for: the heartbeat-based signal must have
      // actually moved -- proving the detail CAN report something other than healthy, unlike
      // pollThreadAlive/pollLoopIterationCount (see class doc).
      double heartbeatSecondsAgoDuringOutage = heartbeatSecondsAgo(currentKafkaDetail());
      assertThat(heartbeatSecondsAgoDuringOutage)
          .as("heartbeat age should have grown well past the pre-outage baseline")
          .isGreaterThan(baselineHeartbeatSecondsAgo + 10.0);
    } finally {
      docker.startContainerCmd(kafkaContainerId).exec();
    }

    // Let the consumer's heartbeat recover before ending the test, so later test classes in this
    // suite see a healthy shared consumer again.
    awaitKafkaDetail(
        details -> heartbeatSecondsAgo(details) != null && heartbeatSecondsAgo(details) < 10.0);
  }

  private io.restassured.path.json.JsonPath currentKafkaDetail() {
    return given()
        .baseUri(baseUrl())
        .when()
        .get("/actuator/health")
        .jsonPath()
        .setRoot("components.riskSnapshotConsumer.details");
  }

  private static Double heartbeatSecondsAgo(io.restassured.path.json.JsonPath details) {
    return details.getObject("lastHeartbeatSecondsAgo", Double.class);
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
