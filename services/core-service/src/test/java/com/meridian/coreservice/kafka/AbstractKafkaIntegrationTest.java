package com.meridian.coreservice.kafka;

import java.time.Duration;
import java.util.Set;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.TopicPartition;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

/**
 * Shared Testcontainers Kafka + schema registry + Postgres for core-service's Kafka-consuming/
 * producing tests. The schema registry container needs to reach Kafka over the Testcontainers
 * network by its network alias, not its host-mapped port -- see {@code schemaRegistryProperties}.
 *
 * <p>These containers are deliberately unmanaged singletons, not
 * {@code @Testcontainers}/{@code @Container}-scoped: they are started once in a static initializer
 * and never stopped by this class (Ryuk reaps them at JVM exit). Every subclass shares the exact
 * same running containers and therefore the exact same {@code @DynamicPropertySource} values for
 * the life of the test run, so Spring's test-context cache reusing an ApplicationContext across
 * these structurally-identical {@code @SpringBootTest} classes is correct and safe -- the cached
 * DataSource/HikariPool always still points at a live container, because the container is never
 * torn down out from under it. (Contrast the per-class-fresh-container design this replaced: there,
 * the same cache reuse wired a class's tests to a *previous* class's already-stopped container,
 * producing intermittent CannotGetJdbcConnection failures under CI load. Singletons make that class
 * of bug structurally impossible instead of disabling the cache with {@code @DirtiesContext}.)
 *
 * <p>Sharing one Postgres container across every test class means rows from one class's tests would
 * otherwise still be there for the next -- AuditChainTamperDetectionTest deliberately corrupts its
 * chain, AuditLogAppendOnlyEnforcementTest leaves rows behind, and AuditChainVerificationTest
 * depends on starting from an empty audit_log. The {@code @BeforeEach} below truncates every table
 * before each test method to restore that isolation. TRUNCATE does not fire row-level DELETE
 * triggers (only an explicit {@code FOR EACH STATEMENT ON TRUNCATE} trigger would, and V2's
 * append-only trigger is {@code FOR EACH ROW} on UPDATE/DELETE only), so this does not need to --
 * and must not -- go around ADR-0008's append-only guarantee.
 */
@SpringBootTest
@ExtendWith(org.springframework.test.context.junit.jupiter.SpringExtension.class)
public abstract class AbstractKafkaIntegrationTest {

  private static final Network NETWORK = Network.newNetwork();

  static final KafkaContainer KAFKA =
      new KafkaContainer(DockerImageName.parse("confluentinc/cp-kafka:7.6.1"))
          .withNetwork(NETWORK)
          .withNetworkAliases("kafka");

  static final org.testcontainers.containers.GenericContainer<?> SCHEMA_REGISTRY =
      new org.testcontainers.containers.GenericContainer<>(
              DockerImageName.parse("confluentinc/cp-schema-registry:7.6.1"))
          .withNetwork(NETWORK)
          .withNetworkAliases("schema-registry")
          .withExposedPorts(8081)
          .withEnv("SCHEMA_REGISTRY_HOST_NAME", "schema-registry")
          .withEnv("SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS", "PLAINTEXT://kafka:9092")
          .withEnv("SCHEMA_REGISTRY_LISTENERS", "http://0.0.0.0:8081")
          .dependsOn(KAFKA);

  static final PostgreSQLContainer<?> POSTGRES =
      new PostgreSQLContainer<>("postgres:16-alpine")
          .withDatabaseName("meridian")
          .withUsername("meridian")
          .withPassword("meridian");

  static {
    KAFKA.start();
    SCHEMA_REGISTRY.start();
    POSTGRES.start();
  }

  @DynamicPropertySource
  static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
    registry.add("spring.datasource.username", POSTGRES::getUsername);
    registry.add("spring.datasource.password", POSTGRES::getPassword);
    registry.add("meridian.kafka.bootstrap-servers", KAFKA::getBootstrapServers);
    registry.add(
        "meridian.kafka.schema-registry-url",
        () -> "http://" + SCHEMA_REGISTRY.getHost() + ":" + SCHEMA_REGISTRY.getMappedPort(8081));
  }

  @Autowired private JdbcTemplate jdbcTemplate;

  // Do NOT "fix" test isolation by giving each class its own database/schema on this shared
  // container instead of truncating. It does not work, and it's the same bug Session C found:
  // @DynamicPropertySource values are not part of Spring's test-context cache key, so a class
  // whose Spring context gets a cache HIT (structurally identical @SpringBootTest config, which is
  // every subclass here) reuses the PREVIOUS class's already-built DataSource/HikariPool -- i.e.
  // its previous class's database -- no matter what a fresh @DynamicPropertySource call registers.
  // Per-class databases only actually isolate anything if paired with a per-class context, which
  // means @DirtiesContext, which is the ~6-minute-job regression this file exists to avoid (see the
  // class javadoc above). TRUNCATE-between-tests is the isolation strategy precisely because it
  // works with one shared container AND one cached context, sidestepping the cache-key problem
  // entirely instead of re-triggering it.
  //
  // Do NOT "fix" Kafka isolation (see seekToEnd below) by deleting and recreating topics between
  // tests as the Kafka-side symmetric answer to the truncation above, either. The Spring-managed
  // consumer bean (RiskSnapshotConsumerService's production instance, group
  // core-service-risk-snapshots) is live and already subscribed for the life of this shared
  // context; topic deletion is asynchronous on the broker, and pulling a topic out from under a
  // running, subscribed consumer triggers rebalances and unpredictable UNKNOWN_TOPIC_OR_PARTITION/
  // timeout errors on whichever test happens to be running when the deletion lands. That trades
  // this class's current deterministic failure for a flaky one, which is worse, not better.
  // seekToEnd (below) fixes this on the read side, per test-created consumer, instead.
  @BeforeEach
  void truncateAllTables() {
    jdbcTemplate.execute(
        "TRUNCATE audit_log, risk_snapshots, trades, positions, portfolios, instruments"
            + " RESTART IDENTITY CASCADE");
  }

  // Kafka topics are shared across every test class in this suite and are never truncated the
  // way the tables above are -- only Postgres is reset per test. A brand-new consumer group with
  // auto.offset.reset=earliest on a shared topic (portfolio.state, risk.snapshots) therefore reads
  // every earlier test class's leftover messages too, including ones whose Postgres rows this
  // @BeforeEach has since wiped. Call this right after subscribe (i.e. right after constructing
  // the consumer, before producing the test's OWN records) so it only ever sees what this test
  // produces. Do not call this on a consumer meant to read history that predates its own creation
  // -- that is the intended, real behavior for a small number of tests (e.g.
  // RiskSnapshotConsumptionTest simulating a consumer-group offset reset over an
  // already-produced message), not a bug seekToEnd should paper over.
  static void seekToEnd(KafkaConsumer<?, ?> consumer) {
    Set<TopicPartition> assignment = consumer.assignment();
    while (assignment.isEmpty()) {
      consumer.poll(Duration.ofMillis(100));
      assignment = consumer.assignment();
    }
    consumer.seekToEnd(assignment);
    for (TopicPartition partition : assignment) {
      consumer.position(partition); // force the lazy seek to resolve before returning
    }
  }
}
