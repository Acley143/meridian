package com.meridian.coreservice.kafka;

import static io.restassured.RestAssured.given;
import static org.assertj.core.api.Assertions.assertThat;

import com.github.dockerjava.api.DockerClient;
import com.meridian.coreservice.web.AbstractRestIntegrationTest;
import io.restassured.response.Response;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.testcontainers.DockerClientFactory;

/**
 * ADR-0022 verification item 5 -- the load-bearing negative fixture. Stops the real Postgres
 * container out from under a running core-service and proves:
 *
 * <ul>
 *   <li>readiness fails closed (503 / DOWN) while Postgres is unreachable
 *   <li>liveness stays UP the entire time -- this is the assertion that actually proves liveness
 *       and readiness are not conflated. If liveness followed Postgres down, the split would be
 *       fake regardless of what application.yml claims.
 *   <li>readiness recovers to UP on its own once Postgres comes back, with no core-service restart
 * </ul>
 *
 * <p>Stops/starts the container directly via the Docker daemon (not Testcontainers' own {@code
 * stop()}, which removes the container) so the same container -- same volume, same port mapping --
 * comes back for every other test class sharing {@link AbstractKafkaIntegrationTest}'s singleton.
 * Uses its own {@code @DynamicPropertySource} to shorten Hikari's connection/validation timeouts,
 * which gives this class a separate (uncached) Spring context and connection pool from every other
 * test class -- deliberately, so this fixture's outage can't leak into a shared pool another test
 * class is mid-use of.
 */
class PostgresOutageReadinessFixtureTest extends AbstractRestIntegrationTest {

  @org.springframework.test.context.DynamicPropertySource
  static void fastFailingHikari(org.springframework.test.context.DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.hikari.connection-timeout", () -> "2000");
    registry.add("spring.datasource.hikari.validation-timeout", () -> "2000");
  }

  @Test
  void readinessFailsClosedOnPostgresOutageWhileLivenessStaysUp() {
    DockerClient docker = DockerClientFactory.instance().client();
    String containerId = postgresContainer().getContainerId();

    getReadiness().then().statusCode(200).body("status", org.hamcrest.Matchers.equalTo("UP"));

    docker.stopContainerCmd(containerId).withTimeout(10).exec();
    try {
      Response readinessDown = awaitReadinessStatus("DOWN", Duration.ofSeconds(30));
      assertThat(readinessDown.statusCode()).isEqualTo(503);

      // The load-bearing assertion: liveness must not move, checked WHILE readiness is down.
      given()
          .baseUri(baseUrl())
          .when()
          .get("/actuator/health/liveness")
          .then()
          .statusCode(200)
          .body("status", org.hamcrest.Matchers.equalTo("UP"));
    } finally {
      docker.startContainerCmd(containerId).exec();
    }

    // No core-service restart between the outage and this recovery check.
    Response readinessUp = awaitReadinessStatus("UP", Duration.ofSeconds(60));
    assertThat(readinessUp.statusCode()).isEqualTo(200);
  }

  private Response getReadiness() {
    return given().baseUri(baseUrl()).when().get("/actuator/health/readiness");
  }

  private Response awaitReadinessStatus(String expectedStatus, Duration timeout) {
    Instant deadline = Instant.now().plus(timeout);
    Response last;
    do {
      last = getReadiness();
      if (expectedStatus.equals(last.jsonPath().getString("status"))) {
        return last;
      }
      try {
        Thread.sleep(500);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new RuntimeException(e);
      }
    } while (Instant.now().isBefore(deadline));
    throw new AssertionError(
        "readiness never reached status "
            + expectedStatus
            + " within "
            + timeout
            + "; last response: "
            + last.getBody().asString());
  }
}
