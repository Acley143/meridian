package com.meridian.coreservice.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;

/**
 * Regression test for the bug behind ADR-0022's editorial amendments: {@code
 * RiskSnapshotConsumerHealthIndicator} used to pass null detail values straight into {@code
 * Health.Builder#withDetail}, which throws {@code IllegalArgumentException("Value must not be
 * null")} on a null value -- and {@code GlobalExceptionHandler}'s then-application-wide {@code
 * IllegalArgumentException} mapping turned that into a generic {@code 400}, hiding a server fault
 * as a client fault with no stack trace logged anywhere.
 *
 * <p><b>Deliberately a fast, Docker-free unit test of the indicator directly, not an HTTP
 * integration test polling a real Kafka consumer's heartbeat.</b> An earlier version of this test
 * did exactly that, exploiting the same "first HTTP call against a freshly created context"
 * mechanism the two health integration tests relied on -- but that mechanism only holds for
 * whichever test happens to run first against the shared, cached Spring context. Once {@code
 * HealthEndpointExposureTest#aggregateHealthShowsTheKafkaConsumerDetail} was fixed to correctly
 * poll until the consumer actually heartbeats (see that class), it started running first in some
 * orderings and consuming the very "before any heartbeat" window this test depended on, breaking it
 * -- the identical class of ordering fragility this investigation kept finding elsewhere. A {@link
 * RiskSnapshotConsumerRunner} constructed here and never {@code run()} never starts its poll
 * thread, so its {@code lastHeartbeatSecondsAgo}/{@code heartbeatMetricRegistered} {@link
 * java.util.concurrent.atomic.AtomicReference}s stay at their real initial {@code null} state --
 * the exact state a fresh consumer is in for the first few seconds after startup, reproduced
 * deterministically instead of raced for.
 */
class RiskSnapshotConsumerHealthIndicatorNullDetailTest {

  @Test
  void omitsNullDetailsInsteadOfThrowing() {
    // Never .run() -- the poll loop thread is never started, so every AtomicReference stays at
    // its constructor-initialized value: exactly a fresh consumer's pre-heartbeat state. The null
    // RiskSnapshotConsumerService argument is never touched, since nothing here calls run().
    RiskSnapshotConsumerRunner freshRunner = new RiskSnapshotConsumerRunner(null);
    RiskSnapshotConsumerHealthIndicator indicator =
        new RiskSnapshotConsumerHealthIndicator(freshRunner);

    Health health = indicator.health();

    Map<String, Object> details = health.getDetails();
    assertNoNullValues(details, "$");
    assertThat(details)
        .as("riskSnapshotConsumer detail map")
        .containsEntry("pollThreadAlive", false)
        .containsEntry("pollLoopIterationCount", 0L)
        .containsEntry("partitionAssignment", List.of())
        // The load-bearing assertions: omitted entirely, not present with a null value --
        // withDetail must never have been called with null for either key.
        .doesNotContainKey("lastHeartbeatSecondsAgo")
        .doesNotContainKey("heartbeatMetricRegistered");
  }

  private static void assertNoNullValues(Object node, String path) {
    if (node instanceof Map<?, ?> map) {
      for (Map.Entry<?, ?> entry : map.entrySet()) {
        String childPath = path + "." + entry.getKey();
        assertThat(entry.getValue()).as("value at %s", childPath).isNotNull();
        assertNoNullValues(entry.getValue(), childPath);
      }
    } else if (node instanceof List<?> list) {
      for (int i = 0; i < list.size(); i++) {
        assertNoNullValues(list.get(i), path + "[" + i + "]");
      }
    }
  }
}
