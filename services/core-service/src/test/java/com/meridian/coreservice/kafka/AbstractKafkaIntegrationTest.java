package com.meridian.coreservice.kafka;

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

  @BeforeEach
  void truncateAllTables() {
    jdbcTemplate.execute(
        "TRUNCATE audit_log, risk_snapshots, trades, positions, portfolios, instruments"
            + " RESTART IDENTITY CASCADE");
  }
}
