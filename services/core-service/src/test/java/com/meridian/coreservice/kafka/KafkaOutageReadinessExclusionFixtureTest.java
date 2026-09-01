package com.meridian.coreservice.kafka;

import static io.restassured.RestAssured.given;
import static org.assertj.core.api.Assertions.assertThat;

import com.github.dockerjava.api.DockerClient;
import io.restassured.response.Response;
import java.time.Duration;
import java.time.Instant;
import java.util.Properties;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.utility.DockerImageName;

/**
 * ADR-0022 verification item 6: proves the deliberate exclusion of Kafka from readiness actually
 * holds under a real broker outage, rather than being untested intent -- AND proves the Kafka
 * health detail can actually report something other than healthy during that outage.
 *
 * <p><b>Runs against its own private Kafka + schema registry, not {@link
 * AbstractKafkaIntegrationTest}'s shared singleton.</b> A real CI run caught why this matters: a
 * cold {@code docker stop}/{@code start} of a KRaft Kafka broker re-runs its full boot sequence
 * (controller election, log recovery), which took long enough on a GitHub Actions runner that this
 * fixture's own recovery assertion timed out and failed -- honestly, in ~61s, not a hang. But
 * because the earlier version of this test stopped and restarted the *shared* singleton container,
 * the still-recovering broker then wedged the very next (unrelated, pre-existing) test in the
 * suite, {@code OffsetCommitFailureTest}, for the remaining ~11 minutes of the job until the
 * workflow's timeout killed it. Lengthening this fixture's own timeout would not have fixed that --
 * the next slow recovery would reproduce the exact same blast radius. Giving this fixture a private
 * container makes that class of failure structurally impossible: whatever this test does to its own
 * broker, no other test's Kafka consumer can be affected by it, because no other test talks to this
 * container. Reuses the suite's shared Postgres singleton ({@link
 * AbstractKafkaIntegrationTest#postgresContainer()}) directly, since Postgres is never touched by
 * this fixture and isolating it would buy nothing.
 *
 * <p><b>Simulates the outage with {@code docker pause}/{@code unpause}, not {@code stop}/{@code
 * start}.</b> A stopped KRaft broker has to re-run controller election and log recovery on restart
 * -- an uncontrolled cost that had already blown through a 30s and then a 90s recovery budget in CI
 * (see the sibling {@code PostgresOutageReadinessFixtureTest}'s doc for the same failure shape
 * against Postgres). {@code pause} freezes the broker process via the cgroup freezer instead of
 * killing it, so {@code unpause} resumes it mid-state with no boot sequence at all -- the thing we
 * actually want to simulate ("the broker is unreachable") without paying for a cold restart to
 * prove it. This requires freezer cgroup support in the CI runner; if a runner lacks it, {@code
 * pauseContainerCmd}/{@code unpauseContainerCmd} fail immediately with a clear Docker API error
 * rather than hanging, which is a legible failure mode.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ExtendWith(SpringExtension.class)
class KafkaOutageReadinessExclusionFixtureTest {

  private static final Network NETWORK = Network.newNetwork();

  private static final KafkaContainer PRIVATE_KAFKA =
      new KafkaContainer(DockerImageName.parse("confluentinc/cp-kafka:7.6.1"))
          .withNetwork(NETWORK)
          .withNetworkAliases("kafka");

  private static final GenericContainer<?> PRIVATE_SCHEMA_REGISTRY =
      new GenericContainer<>(DockerImageName.parse("confluentinc/cp-schema-registry:7.6.1"))
          .withNetwork(NETWORK)
          .withNetworkAliases("schema-registry")
          .withExposedPorts(8081)
          .withEnv("SCHEMA_REGISTRY_HOST_NAME", "schema-registry")
          .withEnv("SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS", "PLAINTEXT://kafka:9092")
          .withEnv("SCHEMA_REGISTRY_LISTENERS", "http://0.0.0.0:8081")
          .dependsOn(PRIVATE_KAFKA);

  static {
    PRIVATE_KAFKA.start();
    PRIVATE_SCHEMA_REGISTRY.start();
  }

  @DynamicPropertySource
  static void properties(DynamicPropertyRegistry registry) {
    // TEMPORARY DIAGNOSTIC -- Session P follow-up, discriminating experiment for the boot-race
    // hypothesis (eager DispatcherServlet init instead of lazy-on-first-request). Remove after
    // the experiment, whichever way it comes out.
    registry.add("spring.mvc.servlet.load-on-startup", () -> "1");
    registry.add(
        "spring.datasource.url", AbstractKafkaIntegrationTest.postgresContainer()::getJdbcUrl);
    registry.add(
        "spring.datasource.username",
        AbstractKafkaIntegrationTest.postgresContainer()::getUsername);
    registry.add(
        "spring.datasource.password",
        AbstractKafkaIntegrationTest.postgresContainer()::getPassword);
    registry.add("meridian.kafka.bootstrap-servers", PRIVATE_KAFKA::getBootstrapServers);
    registry.add(
        "meridian.kafka.schema-registry-url",
        () ->
            "http://"
                + PRIVATE_SCHEMA_REGISTRY.getHost()
                + ":"
                + PRIVATE_SCHEMA_REGISTRY.getMappedPort(8081));
  }

  @LocalServerPort private int port;
  @Autowired private JdbcTemplate jdbcTemplate;

  private String baseUrl() {
    return "http://localhost:" + port;
  }

  // This class gets its OWN Spring context (different bootstrap-servers/schema-registry-url than
  // every other test class), so it doesn't share table state with the shared-singleton classes --
  // but still needs its own clean start.
  @BeforeEach
  void truncateAllTables() {
    jdbcTemplate.execute(
        "TRUNCATE audit_log, risk_snapshots, trades, positions, portfolios, instruments"
            + " RESTART IDENTITY CASCADE");
  }

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
    awaitKafkaDetail(
        details -> heartbeatSecondsAgo(details) != null,
        Duration.ofSeconds(30),
        "consumer never reported an initial heartbeat");
    double baselineHeartbeatSecondsAgo = heartbeatSecondsAgo(currentKafkaDetail());
    assertThat(baselineHeartbeatSecondsAgo)
        .as("baseline heartbeat age should be small while the broker is healthy")
        .isLessThan(10.0);

    DockerClient docker = DockerClientFactory.instance().client();
    String kafkaContainerId = PRIVATE_KAFKA.getContainerId();
    docker.pauseContainerCmd(kafkaContainerId).exec();
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
      // pollThreadAlive/pollLoopIterationCount (see RiskSnapshotConsumerRunner's class doc).
      double heartbeatSecondsAgoDuringOutage = heartbeatSecondsAgo(currentKafkaDetail());
      assertThat(heartbeatSecondsAgoDuringOutage)
          .as("heartbeat age should have grown well past the pre-outage baseline")
          .isGreaterThan(baselineHeartbeatSecondsAgo + 10.0);
    } finally {
      docker.unpauseContainerCmd(kafkaContainerId).exec();
    }

    // Two separate signals, two separate failure messages, on purpose -- conflating "the broker
    // is back" with "this consumer's heartbeat has recovered" would make a slow-but-healthy
    // broker restart and a genuinely broken reconnect indistinguishable from the failure message
    // alone. Unpausing resumes the broker mid-state (no controller election, no log recovery), so
    // this window is generous only as a safety margin, not because a boot sequence is expected --
    // checked directly via an admin client against ITS bootstrap servers, independent of this
    // consumer's own state.
    awaitBrokerReachable(Duration.ofSeconds(90));
    // Once the broker itself is confirmed up, the consumer's next heartbeat is due within
    // heartbeat.interval.ms (3s default) plus reconnect backoff -- 30s is still generous, but a
    // failure here now means something in the app's OWN reconnect path, not "the broker was slow."
    awaitKafkaDetail(
        details -> heartbeatSecondsAgo(details) != null && heartbeatSecondsAgo(details) < 10.0,
        Duration.ofSeconds(30),
        "broker is reachable again but this consumer's heartbeat never recovered");
  }

  private void awaitBrokerReachable(Duration timeout) {
    Properties props = new Properties();
    props.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, PRIVATE_KAFKA.getBootstrapServers());
    props.put(AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG, "2000");
    Instant deadline = Instant.now().plus(timeout);
    Exception lastFailure = null;
    while (Instant.now().isBefore(deadline)) {
      try (Admin admin = Admin.create(props)) {
        admin.listTopics().names().get(2, TimeUnit.SECONDS);
        return;
      } catch (Exception e) {
        lastFailure = e;
        sleep(1000);
      }
    }
    throw new AssertionError(
        "Kafka broker itself did not become reachable within " + timeout, lastFailure);
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
      java.util.function.Predicate<io.restassured.path.json.JsonPath> condition,
      Duration timeout,
      String failureDescription) {
    Instant deadline = Instant.now().plus(timeout);
    while (Instant.now().isBefore(deadline)) {
      Response health = given().baseUri(baseUrl()).when().get("/actuator/health");
      if (condition.test(health.jsonPath().setRoot("components.riskSnapshotConsumer.details"))) {
        return;
      }
      sleep(500);
    }
    throw new AssertionError(failureDescription + " (waited " + timeout + ")");
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
