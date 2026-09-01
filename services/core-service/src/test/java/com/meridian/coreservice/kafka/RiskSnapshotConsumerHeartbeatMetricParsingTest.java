package com.meridian.coreservice.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.kafka.common.Metric;
import org.apache.kafka.common.MetricName;
import org.junit.jupiter.api.Test;

/**
 * Unit-level guard for {@link RiskSnapshotConsumerService#extractHeartbeatSecondsAgo}, run without
 * a real {@code KafkaConsumer} (no Docker needed). Exists because a naive implementation could
 * silently fall back to a plausible-looking number on a lookup miss or an uninitialized metric --
 * which would reproduce this exact ADR's "reads as healthy when it isn't" bug in a new place, and
 * the end-to-end broker-outage fixture only proves growth during an outage, not that a
 * permanently-wrong-but-plausible field would be caught. The {@code -1.0} case below is not
 * hypothetical: it's {@code kafka-clients} 3.7.0's own real never-heartbeated sentinel, found by
 * reading this consumer's actual {@code /actuator/health} output at startup (before this guard
 * existed) rather than assumed. This test asserts every miss/uncertain case returns {@code null},
 * never a number a reader could mistake for "just heartbeated."
 */
class RiskSnapshotConsumerHeartbeatMetricParsingTest {

  private static final String OTHER_METRIC_NAME = "commit-latency-avg";

  @Test
  void returnsTheValueWhenTheMetricIsPresentWithARealNumber() {
    Map<MetricName, Metric> metrics = new LinkedHashMap<>();
    metrics.put(heartbeatMetricName(), fakeMetric(heartbeatMetricName(), 4.5));

    Double result = RiskSnapshotConsumerService.extractHeartbeatSecondsAgo(metrics);

    assertThat(result).isEqualTo(4.5);
  }

  @Test
  void returnsNullRatherThanZeroWhenTheMetricNameIsNotRegisteredAtAll() {
    // Simulates a kafka-clients version that renamed or removed the metric -- must not be
    // confused with "metric present but reporting a small number."
    MetricName unrelated =
        new MetricName(
            OTHER_METRIC_NAME, "consumer-coordinator-metrics", "", Collections.emptyMap());
    Map<MetricName, Metric> metrics = new LinkedHashMap<>();
    metrics.put(unrelated, fakeMetric(unrelated, 0.0));

    Double result = RiskSnapshotConsumerService.extractHeartbeatSecondsAgo(metrics);

    assertThat(result).isNull();
  }

  @Test
  void returnsNullWhenTheMetricsMapIsEmpty() {
    Double result = RiskSnapshotConsumerService.extractHeartbeatSecondsAgo(Collections.emptyMap());

    assertThat(result).isNull();
  }

  @Test
  void returnsNullRatherThanNaNWhenTheMetricHasNotReportedARealValueYet() {
    // Kafka Measurable metrics can report NaN before enough samples exist (e.g. before the first
    // group join). NaN must not leak out as a JSON-serializable "number" a reader could mistake
    // for a real reading.
    Map<MetricName, Metric> metrics = new LinkedHashMap<>();
    metrics.put(heartbeatMetricName(), fakeMetric(heartbeatMetricName(), Double.NaN));

    Double result = RiskSnapshotConsumerService.extractHeartbeatSecondsAgo(metrics);

    assertThat(result).isNull();
  }

  @Test
  void returnsNullRatherThanNegativeOneForKafkasOwnNeverHeartbeatedSentinel() {
    // kafka-clients 3.7.0's AbstractCoordinator returns the literal value -1.0 for this metric
    // when Heartbeat.lastHeartbeatSend() == 0 (no heartbeat ever sent) -- decompiled and
    // confirmed, and separately observed live in a real /actuator/health response at consumer
    // startup. -1.0 is a plausible-looking, JSON-serializable double; an implementation that
    // returned it verbatim would report a consumer that has never heartbeated as "reachable",
    // which is the exact failure this field exists to prevent.
    Map<MetricName, Metric> metrics = new LinkedHashMap<>();
    metrics.put(heartbeatMetricName(), fakeMetric(heartbeatMetricName(), -1.0));

    Double result = RiskSnapshotConsumerService.extractHeartbeatSecondsAgo(metrics);

    assertThat(result).isNull();
  }

  @Test
  void returnsNullWhenTheMetricValueIsNotNumeric() {
    Map<MetricName, Metric> metrics = new LinkedHashMap<>();
    metrics.put(heartbeatMetricName(), fakeMetric(heartbeatMetricName(), "not-a-number"));

    Double result = RiskSnapshotConsumerService.extractHeartbeatSecondsAgo(metrics);

    assertThat(result).isNull();
  }

  private static MetricName heartbeatMetricName() {
    return new MetricName(
        RiskSnapshotConsumerService.HEARTBEAT_METRIC_NAME,
        "consumer-coordinator-metrics",
        "",
        Collections.emptyMap());
  }

  private static Metric fakeMetric(MetricName name, Object value) {
    return new Metric() {
      @Override
      public MetricName metricName() {
        return name;
      }

      @Override
      public Object metricValue() {
        return value;
      }
    };
  }
}
