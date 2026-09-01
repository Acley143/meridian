package com.meridian.coreservice.kafka;

import com.meridian.contracts.RiskSnapshot;
import com.meridian.contracts.RiskSnapshotKey;
import io.confluent.kafka.serializers.AbstractKafkaSchemaSerDeConfig;
import io.confluent.kafka.serializers.KafkaAvroDeserializer;
import io.confluent.kafka.serializers.KafkaAvroDeserializerConfig;
import jakarta.annotation.PreDestroy;
import java.time.Duration;
import java.util.Collections;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.Metric;
import org.apache.kafka.common.MetricName;
import org.apache.kafka.common.TopicPartition;
import org.springframework.stereotype.Component;

/**
 * Consumes {@code risk.snapshots} and writes each record to {@code risk_snapshots} via {@link
 * RiskSnapshotWriter} (05a's idempotent upsert). Manual offset commits only, never auto-commit --
 * same principle and same reasoning as the Python side (see libs/quant-io/quant_io/consumer.py's
 * module doc: "auto-commit silently converts at-least-once delivery into at-most-once -- the offset
 * advances whether or not the message was ever durably acted on"), and same shape as
 * services/pricer/pricer/service.py's per-message flow: do the durable side effect, THEN commit
 * that message's own offset, never the reverse.
 *
 * <p>Commits per-record, not per-poll-batch: if record 3 of a 10-record batch fails to write, only
 * offsets for records 1-2 are committed. On failure this class also calls {@link
 * KafkaConsumer#seek} back to the failed record's offset before rethrowing -- {@code
 * KafkaConsumer.poll()} advances the client's own in-memory fetch position for the WHOLE batch as
 * soon as it returns, independent of whether anything in that batch is ever committed. Without the
 * explicit {@code seek()}, a live consumer that catches the failure and keeps polling would never
 * re-fetch the failed record or anything after it in that batch -- only a full process restart (a
 * brand new consumer resuming from the last committed offset) would happen to recover it. That gap
 * was found by this class's own {@code OffsetCommitFailureTest}, which failed until the {@code
 * seek()} call was added -- redelivery-on-failure did not hold for a still-running consumer without
 * it.
 */
@Component
public class RiskSnapshotConsumerService {

  private static final String DEFAULT_TOPIC = "risk.snapshots";

  private final KafkaConsumer<RiskSnapshotKey, RiskSnapshot> consumer;
  private final RiskSnapshotWriter writer;

  // Explicit @Autowired: this class has further (package-private, test-only) constructors below,
  // so Spring cannot infer which one to use on its own -- without this, bean creation fails with
  // "No default constructor found" (it does not fall back to the single public one). Found by
  // actually running the full application for the first time this session, not by any test --
  // 05c's own tests always constructed this class directly (via a test constructor or
  // reflection), so this ambiguity was never exercised through the real Spring container before.
  @org.springframework.beans.factory.annotation.Autowired
  public RiskSnapshotConsumerService(KafkaProperties kafkaProperties, RiskSnapshotWriter writer) {
    this(kafkaProperties, writer, "core-service-risk-snapshots");
  }

  RiskSnapshotConsumerService(
      KafkaProperties kafkaProperties, RiskSnapshotWriter writer, String groupId) {
    this(kafkaProperties, writer, groupId, DEFAULT_TOPIC);
  }

  /**
   * Test-only: lets a test give its consumer a private topic instead of the real {@code
   * risk.snapshots}. The real {@link RiskSnapshotConsumerRunner} bean is live for the life of a
   * shared {@code @SpringBootTest} context (see {@code AbstractKafkaIntegrationTest}'s class doc)
   * and keeps polling {@code risk.snapshots} under its own consumer group throughout every test in
   * the suite -- Kafka delivers to every consumer group independently, so a test that produces to
   * the real topic gets its records written for real by that background consumer's own (genuine,
   * unsubstituted) writer, regardless of what the test's own consumer group does. A test that
   * injects a write failure to prove commit-after-write (e.g. {@code OffsetCommitFailureTest}) must
   * use a topic the production consumer never subscribes to, or its assertions race a real write
   * they have no way to prevent. Tests that deliberately want to observe the shared topic's history
   * (e.g. {@code RiskSnapshotConsumptionTest}) use the 3-arg constructor above instead.
   */
  RiskSnapshotConsumerService(
      KafkaProperties kafkaProperties, RiskSnapshotWriter writer, String groupId, String topic) {
    this.writer = writer;

    Properties props = new Properties();
    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
    props.put(ConsumerConfig.GROUP_ID_CONFIG, groupId);
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, KafkaAvroDeserializer.class.getName());
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, KafkaAvroDeserializer.class.getName());
    props.put(
        AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG,
        kafkaProperties.getSchemaRegistryUrl());
    props.put(KafkaAvroDeserializerConfig.SPECIFIC_AVRO_READER_CONFIG, true);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
    // Never auto-commit -- see class doc. Every commit in this class is an explicit, synchronous
    // commitSync() issued only after the record's write has actually succeeded.
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

    this.consumer = new KafkaConsumer<>(props);
    consumer.subscribe(Collections.singletonList(topic));
  }

  /**
   * Polls once and processes whatever batch comes back, writing and committing one record at a
   * time. Stops (without committing) at the first record whose write fails, so that record and
   * everything after it in the batch is redelivered on the next poll. Returns the number of records
   * successfully written and committed.
   */
  public int pollOnce(Duration timeout) {
    ConsumerRecords<RiskSnapshotKey, RiskSnapshot> records = consumer.poll(timeout);
    int written = 0;
    for (ConsumerRecord<RiskSnapshotKey, RiskSnapshot> record : records) {
      TopicPartition partition = new TopicPartition(record.topic(), record.partition());
      try {
        writer.write(record.value());
      } catch (RuntimeException e) {
        // Roll the client's own fetch position back to the failed record: poll() already
        // advanced it past the whole batch, so without this, the next poll() would fetch only
        // NEW records and silently never redeliver this one (see the class doc).
        consumer.seek(partition, record.offset());
        throw e;
      }
      consumer.commitSync(
          Collections.singletonMap(partition, new OffsetAndMetadata(record.offset() + 1)));
      written++;
    }
    return written;
  }

  /**
   * Returns the consumer's current partition assignment. Safe to call ONLY from the thread that
   * drives {@link #pollOnce} -- {@code KafkaConsumer} is not thread-safe, and calling this from any
   * other thread (e.g. directly from an actuator {@code HealthIndicator} on an HTTP request thread)
   * races the poll loop and throws {@code ConcurrentModificationException} intermittently. {@link
   * RiskSnapshotConsumerRunner} calls this from inside its own poll loop and publishes the result
   * for other threads to read safely; nothing else should call it.
   */
  Set<TopicPartition> currentAssignment() {
    return consumer.assignment();
  }

  static final String HEARTBEAT_METRIC_NAME = "last-heartbeat-seconds-ago";

  /**
   * Returns the consumer's own {@code last-heartbeat-seconds-ago} metric (group {@code
   * consumer-coordinator-metrics}), or {@code null} if the metric isn't present or hasn't reported
   * a meaningful reading yet. This includes a real, confirmed case, not a hypothetical one: {@code
   * kafka-clients} 3.7.0's own {@code AbstractCoordinator} returns the literal sentinel {@code
   * -1.0} for this metric when no heartbeat has ever been sent (decompiled and confirmed by
   * inspection -- {@code Heartbeat.lastHeartbeatSend() == 0 ⇒ -1.0}, not {@code NaN} as first
   * assumed and caught only by actually reading this method's own output against a running
   * consumer: {@code -1.0} showed up in a real {@code /actuator/health} response at startup, before
   * this guard existed). A valid reading is never negative, so any negative value, {@code NaN},
   * {@code Infinite}, a non-numeric value, or a lookup miss (the metric isn't present under this
   * name at all -- {@link #heartbeatMetricIsRegistered} lets a caller check that specific case) all
   * surface as {@code null} -- deliberately never as a number a reader could mistake for "just
   * heartbeated," which would reproduce this exact class's own bug (a signal that reads as healthy
   * when it isn't) in the signal meant to replace it.
   *
   * <p>Unlike {@link #pollOnce}, which does not throw when the broker is unreachable (it logs a
   * connection warning and returns an empty batch -- verified by hand against a real broker outage,
   * see ADR-0022), the group heartbeat genuinely stops succeeding when the coordinator can't be
   * reached, so this is the signal that actually reflects broker/coordinator reachability rather
   * than merely "the poll loop is iterating." Safe to call ONLY from the poll-loop thread -- same
   * constraint as {@link #currentAssignment}.
   */
  Double lastHeartbeatSecondsAgo() {
    return extractHeartbeatSecondsAgo(consumer.metrics());
  }

  /**
   * {@code true} iff a metric named {@link #HEARTBEAT_METRIC_NAME} is registered at all, regardless
   * of its current value. {@link RiskSnapshotConsumerRunner} checks this once at startup and logs
   * loudly if it's ever {@code false} -- that would mean the underlying Kafka client no longer
   * exposes this metric under this name (e.g. a version upgrade renamed it), which would silently
   * degrade {@link #lastHeartbeatSecondsAgo} to always-null without anything failing loudly on its
   * own. Safe to call ONLY from the poll-loop thread -- same constraint as {@link
   * #currentAssignment}.
   */
  boolean heartbeatMetricIsRegistered() {
    return consumer.metrics().keySet().stream()
        .anyMatch(name -> HEARTBEAT_METRIC_NAME.equals(name.name()));
  }

  /**
   * Pure parsing logic, extracted so it's unit-testable without a real {@code KafkaConsumer} (see
   * {@code RiskSnapshotConsumerHeartbeatMetricParsingTest}). See {@link #lastHeartbeatSecondsAgo}
   * for the null-on-anything-uncertain contract.
   */
  static Double extractHeartbeatSecondsAgo(Map<MetricName, ? extends Metric> metrics) {
    for (Map.Entry<MetricName, ? extends Metric> entry : metrics.entrySet()) {
      if (HEARTBEAT_METRIC_NAME.equals(entry.getKey().name())) {
        Object value = entry.getValue().metricValue();
        if (value instanceof Number number) {
          double d = number.doubleValue();
          // A real "seconds ago" reading is never negative. kafka-clients' own -1.0
          // never-heartbeated sentinel (see this method's doc) is caught by d < 0 here, along
          // with any other implementation's negative sentinel -- not just the one observed.
          return Double.isNaN(d) || Double.isInfinite(d) || d < 0 ? null : d;
        }
        return null;
      }
    }
    return null;
  }

  /**
   * Test-only: waits for this consumer's partition assignment then seeks to the end of each
   * assigned partition, so it only sees records produced after this call -- not leftover messages
   * earlier test classes left on the shared {@code risk.snapshots} topic (Kafka isn't truncated
   * between tests, only Postgres is). Call right after construction, before producing the test's
   * own records.
   */
  void seekToEnd() {
    Set<TopicPartition> assignment = consumer.assignment();
    while (assignment.isEmpty()) {
      consumer.poll(Duration.ofMillis(100));
      assignment = consumer.assignment();
    }
    consumer.seekToEnd(assignment);
    for (TopicPartition partition : assignment) {
      consumer.position(partition);
    }
  }

  @PreDestroy
  public void close() {
    consumer.close();
  }
}
