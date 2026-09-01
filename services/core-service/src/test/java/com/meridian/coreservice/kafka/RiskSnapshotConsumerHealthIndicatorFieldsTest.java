package com.meridian.coreservice.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Field;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.junit.jupiter.api.Test;

/**
 * Construction-level guard for ADR-0022's thread-safety requirement: {@code KafkaConsumer} is not
 * thread-safe, and {@link RiskSnapshotConsumerHealthIndicator} runs on an HTTP request thread, not
 * the poll loop thread. It must hold no field of type {@link KafkaConsumer} or {@link
 * RiskSnapshotConsumerService} (the class that wraps one) -- only {@link
 * RiskSnapshotConsumerRunner}, which publishes state safely across threads. A future refactor that
 * reaches for the consumer directly should fail this test at compile-adjacent review time, not
 * become a health endpoint that throws {@code ConcurrentModificationException} intermittently under
 * load.
 */
class RiskSnapshotConsumerHealthIndicatorFieldsTest {

  @Test
  void holdsNoReferenceToTheKafkaConsumerOrItsWrapper() {
    for (Field field : RiskSnapshotConsumerHealthIndicator.class.getDeclaredFields()) {
      assertThat(field.getType())
          .as("field '%s' of type %s", field.getName(), field.getType())
          .isNotEqualTo(KafkaConsumer.class)
          .isNotEqualTo(RiskSnapshotConsumerService.class);
    }
  }
}
