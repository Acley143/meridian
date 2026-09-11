package com.meridian.coreservice.health;

import static io.restassured.RestAssured.given;
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.equalTo;

import com.meridian.coreservice.web.AbstractRestIntegrationTest;
import io.restassured.path.json.JsonPath;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

/**
 * ADR-0022 verification items 1-4: liveness/readiness are exposed as distinct endpoints, the
 * Postgres readiness contribution is actually wired into the readiness GROUP (not merely the
 * aggregate {@code /actuator/health}), the Kafka consumer appears as a body detail on the aggregate
 * endpoint, and no non-health actuator endpoint is exposed.
 */
class HealthEndpointExposureTest extends AbstractRestIntegrationTest {

  @Test
  void livenessIsUpAndDependsOnNothingExternal() {
    given()
        .baseUri(baseUrl())
        .when()
        .get("/actuator/health/liveness")
        .then()
        .statusCode(200)
        .body("status", equalTo("UP"));
  }

  @Test
  void readinessIsUpAndShowsThePostgresContribution() {
    // A bare {"status":"UP"} would not prove the "db" indicator is a member of the readiness
    // GROUP (as opposed to merely existing on the aggregate /actuator/health) -- assert its
    // component is actually present in this response body.
    given()
        .baseUri(baseUrl())
        .when()
        .get("/actuator/health/readiness")
        .then()
        .statusCode(200)
        .body("status", equalTo("UP"))
        .body("components.db.status", equalTo("UP"))
        .body("components.db.details.database", equalTo("PostgreSQL"));
  }

  @Test
  void aggregateHealthShowsTheKafkaConsumerDetail() {
    // lastHeartbeatSecondsAgo is null by design until the consumer's first successful Kafka group
    // join (RiskSnapshotConsumerHealthIndicator's class doc; see ADR-0022's editorial amendments)
    // -- a real few-second delay after every fresh startup, not something a fixed sleep or an
    // immediate assertion can paper over. This test used to assert on it immediately and pass only
    // because a since-fixed bug (RiskSnapshotConsumerHealthIndicator/GlobalExceptionHandler; see
    // ADR-0022) made every early call to this endpoint fail with a 400 before this assertion body
    // ever ran -- this method's own assertion had never actually executed. Poll for the real
    // condition instead, the same bounded-timeout pattern
    // KafkaOutageReadinessExclusionFixtureTest#awaitKafkaDetail uses.
    JsonPath details = awaitNonNullHeartbeat(Duration.ofSeconds(30));

    assertThat(details.getBoolean("pollThreadAlive")).isTrue();
    assertThat(details.<Object>get("partitionAssignment")).isNotNull();
    // pollLoopIterationCount only proves the loop is iterating -- see
    // KafkaOutageReadinessExclusionFixtureTest, which proves lastHeartbeatSecondsAgo is the
    // field that actually moves during a real broker outage.
    assertThat(details.<Object>get("pollLoopIterationCount")).isNotNull();
    assertThat(details.<Object>get("lastHeartbeatSecondsAgo")).isNotNull();
    // Disambiguates a null lastHeartbeatSecondsAgo ("hasn't heartbeated yet" vs "the signal
    // is broken") -- true here since the metric is genuinely registered on a healthy run.
    assertThat(details.getBoolean("heartbeatMetricRegistered")).isTrue();
  }

  @Test
  void nonHealthActuatorEndpointsAreNotExposed() {
    given().baseUri(baseUrl()).when().get("/actuator/env").then().statusCode(404);
    given().baseUri(baseUrl()).when().get("/actuator/beans").then().statusCode(404);
    given().baseUri(baseUrl()).when().get("/actuator/heapdump").then().statusCode(404);
  }

  private JsonPath awaitNonNullHeartbeat(Duration timeout) {
    Instant deadline = Instant.now().plus(timeout);
    JsonPath last = null;
    while (Instant.now().isBefore(deadline)) {
      last =
          given()
              .baseUri(baseUrl())
              .when()
              .get("/actuator/health")
              .jsonPath()
              .setRoot("components.riskSnapshotConsumer.details");
      if (last.get("lastHeartbeatSecondsAgo") != null) {
        return last;
      }
      sleep(500);
    }
    throw new AssertionError(
        "riskSnapshotConsumer never reported a heartbeat within "
            + timeout
            + "; last details: "
            + (last == null ? "none" : last.getMap("")));
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
