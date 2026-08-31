package com.meridian.coreservice.kafka;

import com.meridian.contracts.PortfolioState;
import com.meridian.contracts.PortfolioStateKey;
import io.confluent.kafka.serializers.AbstractKafkaSchemaSerDeConfig;
import io.confluent.kafka.serializers.KafkaAvroSerializer;
import jakarta.annotation.PreDestroy;
import java.time.Instant;
import java.util.List;
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.stereotype.Component;

/**
 * Sole producer of {@code portfolio.state} (ADR-0003), log-compacted, keyed by {@code
 * portfolio_id}. Publishes the FULL current position set on every call -- never a delta, per
 * docs/domain-model.md#portfoliostate ("Not a delta/diff against the previous message -- each
 * message is the complete state, which is what makes log compaction on portfolio_id correct").
 *
 * <p>Deletion is a Kafka tombstone: a message with the portfolio's key and a null value (see
 * portfolio-state.avsc's top-level doc and docs/domain-model.md#portfoliostate's "Tombstone
 * convention"), not a field inside {@link PortfolioState} itself.
 */
@Component
public class PortfolioStateProducer {

  private static final String TOPIC = "portfolio.state";

  private final KafkaProducer<PortfolioStateKey, PortfolioState> producer;

  public PortfolioStateProducer(KafkaProperties kafkaProperties) {
    CompactedTopicInitializer.ensureExists(kafkaProperties.getBootstrapServers(), TOPIC);

    Properties props = new Properties();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class.getName());
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class.getName());
    props.put(
        AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG,
        kafkaProperties.getSchemaRegistryUrl());
    // Every position mutation must actually reach every broker replica before the caller
    // considers the mutation durable -- this is the system of record for what a portfolio holds,
    // not a best-effort stream.
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    this.producer = new KafkaProducer<>(props);
  }

  /** Publishes the full current position set for one portfolio. Not a delta. */
  public void publish(
      String portfolioId, List<com.meridian.contracts.Position> positions, Instant eventTime) {
    PortfolioState value = new PortfolioState(portfolioId, positions, eventTime, Instant.now());
    send(portfolioId, value);
  }

  /** Tombstones a portfolio: a null-valued message on its key, per the compaction convention. */
  public void tombstone(String portfolioId) {
    send(portfolioId, null);
  }

  private void send(String portfolioId, PortfolioState value) {
    ProducerRecord<PortfolioStateKey, PortfolioState> record =
        new ProducerRecord<>(TOPIC, new PortfolioStateKey(portfolioId), value);
    try {
      producer.send(record).get();
    } catch (Exception e) {
      throw new IllegalStateException("failed to publish portfolio.state for " + portfolioId, e);
    }
  }

  @PreDestroy
  public void close() {
    producer.close();
  }
}
