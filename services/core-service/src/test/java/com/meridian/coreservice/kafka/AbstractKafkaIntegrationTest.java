package com.meridian.coreservice.kafka;

import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.KafkaContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

/**
 * Shared Testcontainers Kafka + schema registry + Postgres for core-service's Kafka-consuming/
 * producing tests. The schema registry container needs to reach Kafka over the Testcontainers
 * network by its network alias, not its host-mapped port -- see {@code schemaRegistryProperties}.
 *
 * <p>{@code @DirtiesContext} (class mode defaults to AFTER_CLASS) is load-bearing, not decoration:
 * every subclass here has structurally identical {@code @SpringBootTest} config, so without it
 * Spring's test-context cache treats them as interchangeable and reuses one class's
 * ApplicationContext -- and its already-built DataSource/HikariPool -- for the next.
 * {@code @DynamicPropertySource} only runs when a *new* context is built, so a cache hit silently
 * wires the next class's tests to the *previous* class's containers, which by then have already
 * been torn down. That's exactly what "fresh Postgres container per test class" upstream (see
 * {@code AbstractPostgresIntegrationTest}) depends on NOT happening: without this, tests
 * intermittently fail with CannotGetJdbcConnection/PSQLException("Connection ... refused") pointing
 * at a port from a container that no longer exists, only under real concurrent CI load where the
 * container churn is fast enough to expose the cache reuse.
 */
@Testcontainers
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@ExtendWith(org.springframework.test.context.junit.jupiter.SpringExtension.class)
public abstract class AbstractKafkaIntegrationTest {

  private static final Network NETWORK = Network.newNetwork();

  @Container
  static final KafkaContainer KAFKA =
      new KafkaContainer(DockerImageName.parse("confluentinc/cp-kafka:7.6.1"))
          .withNetwork(NETWORK)
          .withNetworkAliases("kafka");

  @Container
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

  @Container
  static final PostgreSQLContainer<?> POSTGRES =
      new PostgreSQLContainer<>("postgres:16-alpine")
          .withDatabaseName("meridian")
          .withUsername("meridian")
          .withPassword("meridian");

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
}
