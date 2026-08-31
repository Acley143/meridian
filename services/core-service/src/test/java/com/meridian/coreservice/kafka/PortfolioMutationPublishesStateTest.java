package com.meridian.coreservice.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import com.meridian.contracts.PortfolioState;
import com.meridian.contracts.PortfolioStateKey;
import com.meridian.coreservice.service.PortfolioMutationService;
import io.confluent.kafka.serializers.AbstractKafkaSchemaSerDeConfig;
import io.confluent.kafka.serializers.KafkaAvroDeserializer;
import io.confluent.kafka.serializers.KafkaAvroDeserializerConfig;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.Collections;
import java.util.Properties;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * A portfolio mutation (trade booking) appears on portfolio.state with the correct key
 * (portfolio_id) and correct full-state content (ADR-0008 Task 4.3 -- Task 2's producer, exercised
 * through the real internal mutation path, not called directly).
 */
class PortfolioMutationPublishesStateTest extends AbstractKafkaIntegrationTest {

  @Autowired private PortfolioMutationService portfolioMutationService;
  @Autowired private KafkaProperties kafkaProperties;
  @Autowired private JdbcTemplate jdbcTemplate;

  @Test
  void tradeBookingPublishesFullPortfolioStateUnderTheCorrectKey() {
    jdbcTemplate.update(
        "INSERT INTO portfolios (portfolio_id, name, base_currency, owner) VALUES (?, ?, ?, ?)",
        "PF-STATE-TEST",
        "State Publish Test",
        "USD",
        "desk-1");
    jdbcTemplate.update(
        "INSERT INTO instruments (instrument_id, underlying_id, instrument_type, currency,"
            + " contract_size) VALUES ('AAPL', 'AAPL', 'EQUITY', 'USD', 1)");

    Properties props = new Properties();
    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
    props.put(ConsumerConfig.GROUP_ID_CONFIG, "portfolio-state-assert-" + System.nanoTime());
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, KafkaAvroDeserializer.class.getName());
    props.put(
        ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, KafkaAvroDeserializer.class.getName());
    props.put(
        AbstractKafkaSchemaSerDeConfig.SCHEMA_REGISTRY_URL_CONFIG,
        kafkaProperties.getSchemaRegistryUrl());
    props.put(KafkaAvroDeserializerConfig.SPECIFIC_AVRO_READER_CONFIG, true);
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

    try (KafkaConsumer<PortfolioStateKey, PortfolioState> consumer = new KafkaConsumer<>(props)) {
      consumer.subscribe(Collections.singletonList("portfolio.state"));
      // Skip past anything earlier test classes left on the shared portfolio.state topic before
      // triggering this test's own mutation -- otherwise this fresh, earliest-reset consumer
      // group reads that leftover history too.
      seekToEnd(consumer);

      Instant eventTime = Instant.parse("2026-08-31T12:00:00Z");
      portfolioMutationService.applyTrade(
          "trade-1",
          "PF-STATE-TEST",
          "AAPL",
          new BigDecimal("100.00000000"),
          new BigDecimal("150.00000000"),
          eventTime,
          Instant.now());

      ConsumerRecord<PortfolioStateKey, PortfolioState> found = null;
      long deadline = System.currentTimeMillis() + Duration.ofSeconds(30).toMillis();
      while (found == null && System.currentTimeMillis() < deadline) {
        ConsumerRecords<PortfolioStateKey, PortfolioState> records =
            consumer.poll(Duration.ofSeconds(2));
        for (ConsumerRecord<PortfolioStateKey, PortfolioState> record : records) {
          if ("PF-STATE-TEST".equals(record.key().getPortfolioId())) {
            found = record;
          }
        }
      }

      assertThat(found).as("portfolio.state message for PF-STATE-TEST").isNotNull();
      assertThat(found.key().getPortfolioId()).isEqualTo("PF-STATE-TEST");
      PortfolioState value = found.value();
      assertThat(value.getPortfolioId()).isEqualTo("PF-STATE-TEST");
      assertThat(value.getPositions()).hasSize(1);
      assertThat(value.getPositions().get(0).getInstrumentId()).isEqualTo("AAPL");
      assertThat(value.getPositions().get(0).getQuantity())
          .isEqualByComparingTo(new BigDecimal("100.00000000"));
      assertThat(value.getPositions().get(0).getAverageCost())
          .isEqualByComparingTo(new BigDecimal("150.00000000"));
      assertThat(value.getEventTime()).isEqualTo(eventTime);
    }
  }
}
