package com.meridian.coreservice.kafka;

import com.meridian.contracts.ReferenceInstrument;
import com.meridian.contracts.ReferenceInstrumentKey;
import io.confluent.kafka.serializers.AbstractKafkaSchemaSerDeConfig;
import io.confluent.kafka.serializers.KafkaAvroSerializer;
import jakarta.annotation.PreDestroy;
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.stereotype.Component;

/**
 * Sole producer of {@code reference.instruments} (ADR-0019), log-compacted, keyed by {@code
 * instrument_id}. Per docs/domain-model.md#instrument, an instrument never changes once created --
 * a new expiry/strike is a new instrument -- so this only ever gains keys; it never needs to
 * republish an existing key with different content.
 */
@Component
public class ReferenceInstrumentProducer {

  private static final String TOPIC = "reference.instruments";

  private final KafkaProducer<ReferenceInstrumentKey, ReferenceInstrument> producer;

  public ReferenceInstrumentProducer(KafkaProperties kafkaProperties) {
    CompactedTopicInitializer.ensureExists(kafkaProperties.getBootstrapServers(), TOPIC);

    Properties props = new Properties();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class.getName());
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, KafkaAvroSerializer.class.getName());
    props.put(
        AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG,
        kafkaProperties.getSchemaRegistryUrl());
    props.put(ProducerConfig.ACKS_CONFIG, "all");
    this.producer = new KafkaProducer<>(props);
  }

  public void publish(ReferenceInstrument instrument) {
    ProducerRecord<ReferenceInstrumentKey, ReferenceInstrument> record =
        new ProducerRecord<>(
            TOPIC, new ReferenceInstrumentKey(instrument.getInstrumentId()), instrument);
    try {
      producer.send(record).get();
    } catch (Exception e) {
      throw new IllegalStateException(
          "failed to publish reference.instruments for " + instrument.getInstrumentId(), e);
    }
  }

  @PreDestroy
  public void close() {
    producer.close();
  }
}
