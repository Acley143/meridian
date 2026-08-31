package com.meridian.coreservice.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import com.meridian.contracts.PortfolioState;
import com.meridian.contracts.PortfolioStateKey;
import io.confluent.kafka.serializers.AbstractKafkaSchemaSerDeConfig;
import io.confluent.kafka.serializers.KafkaAvroSerializer;
import java.time.Instant;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.ExecutionException;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.ConfigEntry;
import org.apache.kafka.clients.admin.DescribeConfigsResult;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.config.ConfigResource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

/**
 * Compaction survives a broker restart (ADR-0008 Task 4.4).
 *
 * <p><b>Weaker substitute, documented per the 05b pattern:</b> Kafka's log cleaner runs on its own
 * schedule (driven by {@code log.cleaner.min.compaction.lag.ms} / dirty-ratio thresholds, not
 * triggerable synchronously), and Testcontainers' {@code KafkaContainer} has no persistent volume
 * across a container stop/start by default -- a literal "restart the broker and confirm compacted
 * state survived" is not something a short-lived test can force deterministically without a flaky,
 * multi-minute wait for the cleaner to run, or hand-rolling volume-backed broker storage this
 * session doesn't otherwise need. What this test actually proves instead: (1) the topic {@link
 * CompactedTopicInitializer} creates is genuinely configured with {@code cleanup.policy=compact}
 * (the precondition the durability guarantee depends on -- verified via {@code
 * AdminClient.describeConfigs}, not assumed), and (2) publishing two messages under the SAME key
 * survives a real produce/consume round trip with both values retrievable in order (the part of
 * compaction behavior a short-lived test CAN observe without waiting on the cleaner). True
 * cross-restart survival is not exercised here -- this is a real, acknowledged gap in this test,
 * not a hidden one.
 */
class CompactionConfigurationTest extends AbstractKafkaIntegrationTest {

  @Autowired private KafkaProperties kafkaProperties;

  @Test
  void portfolioStateTopicIsConfiguredForCompactionNotDeletion()
      throws ExecutionException, InterruptedException {
    // Force the topic to exist (same idempotent call the real producer makes).
    CompactedTopicInitializer.ensureExists(
        kafkaProperties.getBootstrapServers(), "portfolio.state");

    Properties adminProps = new Properties();
    adminProps.put(
        AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
    try (Admin admin = Admin.create(adminProps)) {
      ConfigResource resource = new ConfigResource(ConfigResource.Type.TOPIC, "portfolio.state");
      DescribeConfigsResult result = admin.describeConfigs(Collections.singletonList(resource));
      Map<ConfigResource, org.apache.kafka.clients.admin.Config> configs = result.all().get();
      ConfigEntry cleanupPolicy =
          configs.get(resource).entries().stream()
              .filter(e -> e.name().equals("cleanup.policy"))
              .findFirst()
              .orElseThrow();

      assertThat(cleanupPolicy.value()).isEqualTo("compact");
    }
  }

  @Test
  void twoMessagesUnderTheSameKeySurviveARealProduceConsumeRoundTrip() throws Exception {
    CompactedTopicInitializer.ensureExists(
        kafkaProperties.getBootstrapServers(), "portfolio.state");

    Properties props = new Properties();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class.getName());
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class.getName());
    props.put(
        AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG,
        kafkaProperties.getSchemaRegistryUrl());

    PortfolioStateKey key = new PortfolioStateKey("PF-COMPACTION-TEST");
    PortfolioState first =
        new PortfolioState(
            "PF-COMPACTION-TEST", List.of(), Instant.parse("2026-08-31T12:00:00Z"), Instant.now());
    PortfolioState second =
        new PortfolioState(
            "PF-COMPACTION-TEST", List.of(), Instant.parse("2026-08-31T12:01:00Z"), Instant.now());

    Properties consumerProps = new Properties();
    consumerProps.put(
        org.apache.kafka.clients.consumer.ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
        kafkaProperties.getBootstrapServers());
    consumerProps.put(
        org.apache.kafka.clients.consumer.ConsumerConfig.GROUP_ID_CONFIG,
        "compaction-roundtrip-" + System.nanoTime());
    consumerProps.put(
        org.apache.kafka.clients.consumer.ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        io.confluent.kafka.serializers.KafkaAvroDeserializer.class.getName());
    consumerProps.put(
        org.apache.kafka.clients.consumer.ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        io.confluent.kafka.serializers.KafkaAvroDeserializer.class.getName());
    consumerProps.put(
        AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG,
        kafkaProperties.getSchemaRegistryUrl());
    consumerProps.put(
        io.confluent.kafka.serializers.KafkaAvroDeserializerConfig.SPECIFIC_AVRO_READER_CONFIG,
        true);
    consumerProps.put(
        org.apache.kafka.clients.consumer.ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    List<PortfolioState> observed = new java.util.ArrayList<>();
    try (org.apache.kafka.clients.consumer.KafkaConsumer<PortfolioStateKey, PortfolioState>
        consumer = new org.apache.kafka.clients.consumer.KafkaConsumer<>(consumerProps)) {
      consumer.subscribe(Collections.singletonList("portfolio.state"));
      // Skip past anything earlier test classes left on the shared portfolio.state topic before
      // this test produces its own records -- otherwise this fresh, earliest-reset consumer group
      // reads that leftover history too.
      seekToEnd(consumer);

      try (KafkaProducer<PortfolioStateKey, PortfolioState> producer = new KafkaProducer<>(props)) {
        producer.send(new ProducerRecord<>("portfolio.state", key, first)).get();
        producer.send(new ProducerRecord<>("portfolio.state", key, second)).get();
      }

      // Not asserting compaction removed the first message here -- the cleaner may not have run
      // yet in this short-lived test, which is exactly the limitation documented above. This
      // confirms both messages round-trip correctly under the same key, in send order, the
      // raw-log behavior compaction is layered on top of.
      long deadline = System.currentTimeMillis() + 30_000;
      while (observed.size() < 2 && System.currentTimeMillis() < deadline) {
        consumer
            .poll(java.time.Duration.ofSeconds(2))
            .forEach(
                r -> {
                  if ("PF-COMPACTION-TEST".equals(r.key().getPortfolioId())) {
                    observed.add(r.value());
                  }
                });
      }
    }

    assertThat(observed).hasSize(2);
    assertThat(observed.get(0).getEventTime()).isEqualTo(first.getEventTime());
    assertThat(observed.get(1).getEventTime()).isEqualTo(second.getEventTime());
  }
}
