package com.meridian.coreservice.kafka;

import static io.restassured.RestAssured.given;
import static org.assertj.core.api.Assertions.assertThat;

import com.github.dockerjava.api.DockerClient;
import io.restassured.response.Response;
import java.sql.Connection;
import java.sql.DriverManager;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.PostgreSQLContainer;

/**
 * ADR-0022 verification item 5 -- the load-bearing negative fixture. Stops a Postgres container out
 * from under a running core-service and proves:
 *
 * <ul>
 *   <li>readiness fails closed (503 / DOWN) while Postgres is unreachable
 *   <li>liveness stays UP the entire time -- this is the assertion that actually proves liveness
 *       and readiness are not conflated. If liveness followed Postgres down, the split would be
 *       fake regardless of what application.yml claims.
 *   <li>readiness recovers to UP on its own once Postgres comes back, with no core-service restart
 * </ul>
 *
 * <p><b>Runs against its own private Postgres, not {@link AbstractKafkaIntegrationTest}'s shared
 * singleton.</b> An earlier version of this fixture stopped and restarted the *shared* Postgres
 * container that every other test class's `DataSource` depends on. A real CI run caught why that's
 * unsafe -- the exact same shape as the Kafka fixture's fix (see {@link
 * KafkaOutageReadinessExclusionFixtureTest}'s class doc): a cold Postgres restart took longer on a
 * GitHub Actions runner than this fixture's own recovery timeout, so readiness never reached UP
 * within 60s and the fixture failed -- but because the shared container was the one stopped,
 * Postgres never came back in time for the *next* three test classes either
 * (`DecimalRoundTripTest`, `RiskSnapshotUpsertTest`, `MigrationTest`), each burning 90s/60s/60s on
 * `CannotGetJdbcConnectionException` before failing. A longer timeout here would not have prevented
 * that -- the next slow restart reproduces the same blast radius. This fixture now starts and tears
 * down its own private Postgres, reusing the shared Kafka/schema-registry singleton directly (this
 * fixture never touches those, so isolating them would buy nothing) -- no other test's `DataSource`
 * can be affected by what this one does to its own database, structurally.
 *
 * <p><b>Simulates the outage with {@code docker pause}/{@code unpause}, not {@code stop}/{@code
 * start}.</b> A stopped Postgres has to run its own startup sequence (including WAL recovery) on
 * restart -- an uncontrolled cost that has already blown through a 30s and then a 90s recovery
 * budget in CI, the identical failure shape documented on the Kafka fixture above. {@code pause}
 * freezes the Postgres process via the cgroup freezer instead of killing it, so {@code unpause}
 * resumes it mid-state with no startup sequence at all. Existing connections held by Hikari during
 * a pause simply hang rather than being refused, which is exactly what the {@code
 * connection-timeout}/{@code validation-timeout} overrides below already exist to bound -- no new
 * tuning needed. Requires freezer cgroup support in the CI runner; if a runner lacks it, {@code
 * pauseContainerCmd}/{@code unpauseContainerCmd} fail immediately with a clear Docker API error
 * rather than hanging, which is a legible failure mode.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ExtendWith(SpringExtension.class)
class PostgresOutageReadinessFixtureTest {

  private static final PostgreSQLContainer<?> PRIVATE_POSTGRES =
      new PostgreSQLContainer<>("postgres:16-alpine")
          .withDatabaseName("meridian")
          .withUsername("meridian")
          .withPassword("meridian");

  static {
    PRIVATE_POSTGRES.start();
  }

  @DynamicPropertySource
  static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", PRIVATE_POSTGRES::getJdbcUrl);
    registry.add("spring.datasource.username", PRIVATE_POSTGRES::getUsername);
    registry.add("spring.datasource.password", PRIVATE_POSTGRES::getPassword);
    // Fast-failing Hikari settings so the outage window (below) doesn't spend most of its time
    // blocked in a single slow connection attempt.
    registry.add("spring.datasource.hikari.connection-timeout", () -> "2000");
    registry.add("spring.datasource.hikari.validation-timeout", () -> "2000");
    // Reuses the shared singleton Kafka/schema registry directly -- this fixture never stops
    // them, so giving them their own private containers too would only add startup cost.
    registry.add(
        "meridian.kafka.bootstrap-servers",
        AbstractKafkaIntegrationTest.KAFKA::getBootstrapServers);
    registry.add(
        "meridian.kafka.schema-registry-url",
        () ->
            "http://"
                + AbstractKafkaIntegrationTest.SCHEMA_REGISTRY.getHost()
                + ":"
                + AbstractKafkaIntegrationTest.SCHEMA_REGISTRY.getMappedPort(8081));
  }

  @LocalServerPort private int port;

  private String baseUrl() {
    return "http://localhost:" + port;
  }

  @Test
  void readinessFailsClosedOnPostgresOutageWhileLivenessStaysUp() {
    DockerClient docker = DockerClientFactory.instance().client();
    String containerId = PRIVATE_POSTGRES.getContainerId();

    getReadiness().then().statusCode(200).body("status", org.hamcrest.Matchers.equalTo("UP"));

    docker.pauseContainerCmd(containerId).exec();
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
      docker.unpauseContainerCmd(containerId).exec();
    }

    // Two separate signals, two separate failure messages, on purpose -- same reasoning as
    // KafkaOutageReadinessExclusionFixtureTest: conflating "Postgres itself is back" with "the
    // app's readiness recovered through it" would make a slow-but-healthy cold restart and a
    // genuinely broken reconnect path indistinguishable from the failure message alone. Unpausing
    // resumes Postgres mid-state (no startup sequence, no WAL recovery), so this window is
    // generous only as a safety margin -- a raw JDBC connection attempt against the container
    // directly, independent of core-service's own pool/state.
    awaitPostgresReachable(Duration.ofSeconds(90));
    // No core-service restart between the outage and this recovery check. Once Postgres itself is
    // confirmed up, Hikari's next connection attempt is due almost immediately -- 30s is still
    // generous, but a failure here now means something in the app's OWN reconnect path.
    Response readinessUp = awaitReadinessStatus("UP", Duration.ofSeconds(30));
    assertThat(readinessUp.statusCode()).isEqualTo(200);
  }

  private void awaitPostgresReachable(Duration timeout) {
    Instant deadline = Instant.now().plus(timeout);
    Exception lastFailure = null;
    while (Instant.now().isBefore(deadline)) {
      try (Connection connection =
          DriverManager.getConnection(
              PRIVATE_POSTGRES.getJdbcUrl(),
              PRIVATE_POSTGRES.getUsername(),
              PRIVATE_POSTGRES.getPassword())) {
        if (connection.isValid(2)) {
          return;
        }
      } catch (Exception e) {
        lastFailure = e;
      }
      sleep(1000);
    }
    throw new AssertionError(
        "Postgres itself did not become reachable within " + timeout, lastFailure);
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
      sleep(500);
    } while (Instant.now().isBefore(deadline));
    throw new AssertionError(
        "readiness never reached status "
            + expectedStatus
            + " within "
            + timeout
            + "; last response: "
            + last.getBody().asString());
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
