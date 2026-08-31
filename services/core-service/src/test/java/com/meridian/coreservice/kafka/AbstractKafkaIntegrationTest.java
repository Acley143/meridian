package com.meridian.coreservice.kafka;

import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.SpringBootTest;
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
 */
@Testcontainers
@SpringBootTest
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
