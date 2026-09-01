package com.meridian.coreservice.health;

import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.notNullValue;

import com.meridian.coreservice.web.AbstractRestIntegrationTest;
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
    given()
        .baseUri(baseUrl())
        .when()
        .get("/actuator/health")
        .then()
        .statusCode(200)
        .body("components.riskSnapshotConsumer.details.pollThreadAlive", equalTo(true))
        .body("components.riskSnapshotConsumer.details.partitionAssignment", notNullValue())
        // The caveat text this ADR calls for: pollThreadAlive/lastPollLoopIterationAt* do not
        // indicate broker reachability -- see KafkaOutageReadinessExclusionFixtureTest, which
        // proves lastHeartbeatSecondsAgo is the field that actually moves during a real outage.
        .body("components.riskSnapshotConsumer.details.pollLoopIterationCaveat", notNullValue())
        .body("components.riskSnapshotConsumer.details.lastHeartbeatSecondsAgo", notNullValue());
  }

  @Test
  void nonHealthActuatorEndpointsAreNotExposed() {
    given().baseUri(baseUrl()).when().get("/actuator/env").then().statusCode(404);
    given().baseUri(baseUrl()).when().get("/actuator/beans").then().statusCode(404);
    given().baseUri(baseUrl()).when().get("/actuator/heapdump").then().statusCode(404);
  }
}
