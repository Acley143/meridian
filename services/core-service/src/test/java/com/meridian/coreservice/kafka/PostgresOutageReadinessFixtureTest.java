package com.meridian.coreservice.kafka;

import static io.restassured.RestAssured.given;
import static org.assertj.core.api.Assertions.assertThat;

import com.github.dockerjava.api.DockerClient;
import io.restassured.response.Response;
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
 * `CannotGetJdbcConnectionException` before failing. This fixture starts its own private Postgres,
 * reusing the shared Kafka/schema-registry singleton directly (this fixture never touches those, so
 * isolating them would buy nothing) -- no other test's `DataSource` can be affected by what this
 * one does to its own database, structurally.
 *
 * <p><b>Asserts the outage direction only -- it never restarts the container and never checks
 * recovery.</b> Two approaches were tried and rejected for the recovery half of this fixture. (1)
 * {@code stop}/{@code start}: a cold Postgres restart (startup sequence, WAL recovery) is an
 * uncontrolled cost that blew through a 30s and then a 90s recovery budget in CI -- the next slow
 * restart would always reproduce the same failure, no matter how generous the timeout. (2) {@code
 * pause}/{@code unpause} (tried as the fix for (1)): this made the fixture hang for 8+ minutes
 * instead, past the workflow's job timeout, with no exception and no useful log output. The working
 * theory is that a paused container's kernel-level TCP stack can still complete a new connection's
 * handshake even though the userspace Postgres process is frozen, so a fresh Hikari/PgJDBC
 * connection attempt appears to connect and then blocks indefinitely waiting for a wire-protocol
 * response that will never come -- a stage Hikari's {@code connection-timeout}/{@code
 * validation-timeout} do not actually bound, since that requires the driver's own {@code
 * connectTimeout}/{@code socketTimeout} properties, which are unset. Not verified against PgJDBC's
 * source; not chased further. Given both recovery-simulation approaches failed in incompatible
 * ways, this fixture proves only what ADR-0022 is actually accountable for -- readiness fails
 * closed during an outage, liveness does not -- and leaves recovery-under-outage unverified by an
 * automated fixture. The private container is simply discarded, stopped, at class teardown.
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

    // Not restarted -- see class doc. The container is simply discarded, stopped, at teardown.
    docker.stopContainerCmd(containerId).withTimeout(10).exec();

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
