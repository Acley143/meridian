package com.meridian.coreservice.kafka;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.meridian.contracts.RiskSnapshot;
import com.meridian.contracts.RiskSnapshotKey;
import com.meridian.coreservice.persistence.repository.RiskSnapshotRepository;
import io.confluent.kafka.serializers.AbstractKafkaSchemaSerDeConfig;
import io.confluent.kafka.serializers.KafkaAvroSerializer;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicBoolean;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Offsets do not advance past a failed write, verified with teeth (ADR-0008 Task 4.2): inject a
 * failure on a specific "poisoned" record, confirm the write before it landed but the poisoned one
 * and everything after it in the batch did NOT, then flip the poison off and prove the exact same
 * poisoned record is genuinely REdelivered (not skipped) on the next poll -- not just that commit
 * wasn't called.
 *
 * <p>Produces to and consumes from a private topic ({@link #TOPIC}), not the real {@code
 * risk.snapshots}: the real {@link RiskSnapshotConsumerRunner} bean is live for the life of this
 * class's shared {@code @SpringBootTest} context and keeps polling {@code risk.snapshots} under its
 * own consumer group throughout the whole suite. Kafka delivers to every consumer group
 * independently, so a record produced to the real topic gets written for real by that background
 * consumer's genuine, unsubstituted writer regardless of what this test's poisoned writer does --
 * this test's own assertions on {@link RiskSnapshotRepository#countByIdentity} were racing that
 * background write and losing. A private topic the production consumer never subscribes to makes
 * that race structurally impossible instead of merely unlikely.
 */
class OffsetCommitFailureTest extends AbstractKafkaIntegrationTest {

  private static final String TOPIC = "risk.snapshots.offset-commit-failure-test";

  @Autowired private KafkaProperties kafkaProperties;
  @Autowired private RiskSnapshotRepository riskSnapshotRepository;
  @Autowired private JdbcTemplate jdbcTemplate;

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
  void failedWriteBlocksTheCommitAndTheSameMessageIsRedeliveredNotSkipped() throws Exception {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES (?, ?, ?, ?)",
        "PF-POISON",
        "Poison Test",
        "USD",
        "desk-1");

    Instant asOf1 = Instant.parse("2026-08-31T12:00:00Z");
    Instant asOf2 = Instant.parse("2026-08-31T12:01:00Z"); // the poisoned one
    Instant asOf3 = Instant.parse("2026-08-31T12:02:00Z");

    AtomicBoolean poisoned = new AtomicBoolean(true);
    RiskSnapshotWriter poisonableWriter =
        snapshot -> {
          if (poisoned.get() && snapshot.getAsOf().equals(asOf2)) {
            throw new RuntimeException("simulated write failure for as_of=" + asOf2);
          }
          riskSnapshotRepository.upsert(
              new com.meridian.coreservice.persistence.domain.RiskSnapshotRecord(
                  snapshot.getPortfolioId(),
                  snapshot.getAsOf(),
                  snapshot.getPricerVersion(),
                  snapshot.getPrice(),
                  snapshot.getCashDelta(),
                  snapshot.getCashGamma(),
                  snapshot.getCashVega(),
                  snapshot.getCashTheta(),
                  snapshot.getCashRho(),
                  snapshot.getVar95(),
                  snapshot.getScenarioId(),
                  snapshot.getOldestInputEventTime(),
                  snapshot.getIngestTime()));
        };

    RiskSnapshotConsumerService consumer =
        new RiskSnapshotConsumerService(
            kafkaProperties, poisonableWriter, "poison-test-group", TOPIC);
    try {
      // TOPIC is private to this test class, but Kafka topics still aren't truncated between
      // test runs the way Postgres is -- a rerun against the same containers (e.g. local dev
      // iteration) could otherwise see this test's own leftover records from a prior run. Skip
      // past anything already on TOPIC before producing this run's records.
      consumer.seekToEnd();

      Properties props = new Properties();
      props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
      props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class.getName());
      props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class.getName());
      props.put(
          AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG,
          kafkaProperties.getSchemaRegistryUrl());
      try (KafkaProducer<RiskSnapshotKey, RiskSnapshot> producer = new KafkaProducer<>(props)) {
        RiskSnapshotKey key = new RiskSnapshotKey("PF-POISON");
        producer.send(new ProducerRecord<>(TOPIC, key, sampleSnapshot("PF-POISON", asOf1))).get();
        producer.send(new ProducerRecord<>(TOPIC, key, sampleSnapshot("PF-POISON", asOf2))).get();
        producer.send(new ProducerRecord<>(TOPIC, key, sampleSnapshot("PF-POISON", asOf3))).get();
      }

      // Poll until the batch containing all three records arrives, then process it. The first
      // record (asOf1) must write+commit; the second (asOf2, poisoned) must throw, which must
      // propagate out of pollOnce -- proving the loop stopped there rather than swallowing the
      // failure and moving on.
      assertThatThrownBy(() -> pollUntilThrowsOrRecords(consumer, 1))
          .isInstanceOf(RuntimeException.class)
          .hasMessageContaining("simulated write failure");

      assertThat(riskSnapshotRepository.countByIdentity("PF-POISON", asOf1, "v1.0.0")).isEqualTo(1);
      assertThat(riskSnapshotRepository.countByIdentity("PF-POISON", asOf2, "v1.0.0")).isEqualTo(0);
      assertThat(riskSnapshotRepository.countByIdentity("PF-POISON", asOf3, "v1.0.0")).isEqualTo(0);

      // Fix the downstream failure and prove the poisoned message (and the one after it) is
      // actually REdelivered, not silently skipped: the same consumer, same group, resumes at
      // the committed offset (right before asOf2) and this poll must still see asOf2 and asOf3.
      poisoned.set(false);
      int written = 0;
      long deadline = System.currentTimeMillis() + Duration.ofSeconds(30).toMillis();
      while (written < 2 && System.currentTimeMillis() < deadline) {
        written += consumer.pollOnce(Duration.ofSeconds(2));
      }
      assertThat(written).isEqualTo(2);

      assertThat(riskSnapshotRepository.countByIdentity("PF-POISON", asOf2, "v1.0.0")).isEqualTo(1);
      assertThat(riskSnapshotRepository.countByIdentity("PF-POISON", asOf3, "v1.0.0")).isEqualTo(1);
    } finally {
      consumer.close();
    }
  }

  private void pollUntilThrowsOrRecords(
      RiskSnapshotConsumerService consumer, int minRecordsBeforePoison) {
    // The poisoned record is second in the batch; a single poll(Duration) against a
    // freshly-subscribed consumer with a small backlog reliably returns all three in one batch
    // in this test's setup, so one pollOnce() call is expected to throw. If the broker happens to
    // split them across polls, retrying pollOnce until it throws still proves the same property.
    long deadline = System.currentTimeMillis() + Duration.ofSeconds(30).toMillis();
    while (System.currentTimeMillis() < deadline) {
      consumer.pollOnce(Duration.ofSeconds(2));
    }
    throw new IllegalStateException("poisoned record was never encountered within the wait window");
  }
}
