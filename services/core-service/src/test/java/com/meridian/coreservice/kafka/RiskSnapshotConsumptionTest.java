package com.meridian.coreservice.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import com.meridian.contracts.RiskSnapshot;
import com.meridian.contracts.RiskSnapshotKey;
import com.meridian.coreservice.persistence.repository.RiskSnapshotRepository;
import io.confluent.kafka.serializers.AbstractKafkaSchemaSerDeConfig;
import io.confluent.kafka.serializers.KafkaAvroSerializer;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * A snapshot consumed twice writes exactly one row (ADR-0008 Task 4.1, but end-to-end through the
 * real Kafka consumer this time, not just the repository directly as in 05a).
 */
class RiskSnapshotConsumptionTest extends AbstractKafkaIntegrationTest {

  @Autowired private KafkaProperties kafkaProperties;
  @Autowired private RiskSnapshotRepository riskSnapshotRepository;
  @Autowired private JdbcTemplate jdbcTemplate;

  private KafkaProducer<RiskSnapshotKey, RiskSnapshot> producer;

  private KafkaProducer<RiskSnapshotKey, RiskSnapshot> producer() {
    if (producer == null) {
      Properties props = new Properties();
      props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
      props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class.getName());
      props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class.getName());
      props.put(
          AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG,
          kafkaProperties.getSchemaRegistryUrl());
      producer = new KafkaProducer<>(props);
    }
    return producer;
  }

  @AfterEach
  void closeProducer() {
    if (producer != null) {
      producer.close();
    }
  }

  private RiskSnapshot sampleSnapshot(String portfolioId, Instant asOf) {
    return new RiskSnapshot(
        portfolioId,
        asOf,
        "v1.0.0",
        new BigDecimal("100.00000000"),
        BigDecimal.ONE,
        BigDecimal.ONE,
        BigDecimal.ONE,
        BigDecimal.ONE,
        BigDecimal.ONE,
        0.05,
        "scenario-1",
        asOf,
        Instant.now());
  }

  @Test
  void snapshotRedeliveredThroughARealConsumerGroupResetWritesExactlyOneRow() throws Exception {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES (?, ?, ?, ?)",
        "PF-KAFKA-DEDUPE",
        "Kafka Dedupe Test",
        "USD",
        "desk-1");

    Instant asOf = Instant.parse("2026-08-31T12:00:00Z");
    RiskSnapshot snapshot = sampleSnapshot("PF-KAFKA-DEDUPE", asOf);
    producer()
        .send(
            new ProducerRecord<>(
                "risk.snapshots", new RiskSnapshotKey("PF-KAFKA-DEDUPE"), snapshot))
        .get();

    RiskSnapshotRepositoryWriter writer = new RiskSnapshotRepositoryWriter(riskSnapshotRepository);

    // First consumption (a fresh consumer group starting from earliest).
    RiskSnapshotConsumerService firstConsumer =
        new RiskSnapshotConsumerService(kafkaProperties, writer, "dedupe-test-group-1");
    waitForRecords(firstConsumer, 1);
    firstConsumer.close();

    assertThat(riskSnapshotRepository.countByIdentity("PF-KAFKA-DEDUPE", asOf, "v1.0.0"))
        .isEqualTo(1);

    // Simulate redelivery of the same message -- a second consumer group also starting from
    // earliest (e.g. an operational offset reset, or a second instance backfilling), landing on
    // the exact same broker-side message a second time through the real Kafka consumer path.
    RiskSnapshotConsumerService secondConsumer =
        new RiskSnapshotConsumerService(kafkaProperties, writer, "dedupe-test-group-2");
    waitForRecords(secondConsumer, 1);
    secondConsumer.close();

    assertThat(riskSnapshotRepository.countByIdentity("PF-KAFKA-DEDUPE", asOf, "v1.0.0"))
        .isEqualTo(1);
  }

  private void waitForRecords(RiskSnapshotConsumerService consumer, int expected) {
    int written = 0;
    long deadline = System.currentTimeMillis() + Duration.ofSeconds(30).toMillis();
    while (written < expected && System.currentTimeMillis() < deadline) {
      written += consumer.pollOnce(Duration.ofSeconds(2));
    }
    assertThat(written).as("records written within the wait window").isEqualTo(expected);
  }
}
