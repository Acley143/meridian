package com.meridian.coreservice.health;

import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.notNullValue;

import com.meridian.coreservice.web.AbstractRestIntegrationTest;
import org.junit.jupiter.api.Test;

/**
 * ADR-0022, task 5: Kafka is a health-body detail, never a readiness-group member. This is the test
 * the ADR calls for explicitly -- a future change that adds {@code riskSnapshotConsumer} to {@code
 * management.endpoint.health.group.readiness.include} in application.yml must fail this test, not
 * silently pull core-service out of the load balancer over a consumer rebalance.
 */
class RiskSnapshotConsumerReadinessExclusionTest extends AbstractRestIntegrationTest {

  @Test
  void kafkaConsumerDetailIsAbsentFromTheReadinessGroupButPresentOnTheAggregate() {
    given()
        .baseUri(baseUrl())
        .when()
        .get("/actuator/health/readiness")
        .then()
        .statusCode(200)
        // Only readinessState + db belong here, per application.yml's readiness group. If this
        // starts returning a non-null riskSnapshotConsumer component, the exclusion regressed.
        .body("components.riskSnapshotConsumer", equalTo(null));

    given()
        .baseUri(baseUrl())
        .when()
        .get("/actuator/health")
        .then()
        .statusCode(200)
        .body("components.riskSnapshotConsumer", notNullValue());
  }
}
