package com.meridian.coreservice.kafka;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import org.apache.kafka.common.TopicPartition;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

/**
 * Reports the {@code risk.snapshots} consumer as a health-body <em>detail</em>, per ADR-0022 -- it
 * must never gate readiness. Core-service's REST reads are served from Postgres; a dead or
 * rebalancing consumer leaves them working, only stale (the dashboard already renders that via
 * {@code oldest_input_event_time}). Pulling the service from the load balancer over a Kafka blip
 * would turn a degraded read into an absent one, which is worse. This bean's id ({@code
 * riskSnapshotConsumer}, from its class name) is deliberately excluded from {@code
 * management.endpoint.health.group.readiness.include} in application.yml -- see that file's comment
 * and {@code RiskSnapshotConsumerReadinessExclusionTest}, which fails if a future change adds it
 * back.
 *
 * <p>Holds no reference to {@link RiskSnapshotConsumerService} or its underlying {@code
 * KafkaConsumer} -- only to {@link RiskSnapshotConsumerRunner}, which is the sole thread permitted
 * to touch the consumer (see that class's doc). This indicator runs on an HTTP request thread and
 * only ever reads state {@code RiskSnapshotConsumerRunner} has already published.
 *
 * <p><b>{@code pollThreadAlive} and {@code lastPollLoopIterationAt*} say only that the poll loop is
 * iterating -- they do NOT indicate Kafka broker reachability.</b> Verified by hand against a real
 * broker outage: {@code KafkaConsumer.poll()} does not throw when the broker is unreachable, so
 * those fields keep advancing through a total outage (see {@code pollLoopIterationCaveat} in the
 * body, and {@code RiskSnapshotConsumerRunner}'s class doc). {@code lastHeartbeatSecondsAgo} is the
 * field that actually reflects broker/coordinator reachability, because the consumer group
 * heartbeat genuinely stops succeeding when the coordinator is unreachable.
 */
@Component
public class RiskSnapshotConsumerHealthIndicator implements HealthIndicator {

  private static final String POLL_LOOP_ITERATION_CAVEAT =
      "true/recent only means the poll loop is iterating -- it does NOT indicate Kafka broker"
          + " reachability, since KafkaConsumer.poll() does not throw on an unreachable broker."
          + " See lastHeartbeatSecondsAgo for that.";

  private final RiskSnapshotConsumerRunner runner;

  public RiskSnapshotConsumerHealthIndicator(RiskSnapshotConsumerRunner runner) {
    this.runner = runner;
  }

  @Override
  public Health health() {
    boolean pollThreadAlive = runner.isPollThreadAlive();
    long lastPollLoopIterationAtEpochMilli = runner.lastPollLoopIterationAtEpochMilli();
    Set<TopicPartition> assignment = runner.currentAssignment();
    Double lastHeartbeatSecondsAgo = runner.lastHeartbeatSecondsAgo();

    Health.Builder builder = pollThreadAlive ? Health.up() : Health.down();
    builder.withDetail("pollThreadAlive", pollThreadAlive);
    builder.withDetail("pollLoopIterationCaveat", POLL_LOOP_ITERATION_CAVEAT);
    builder.withDetail("partitionAssignment", formatAssignment(assignment));
    if (lastPollLoopIterationAtEpochMilli == 0L) {
      builder.withDetail("lastPollLoopIterationAt", null);
      builder.withDetail("lastPollLoopIterationAgeMillis", null);
    } else {
      builder.withDetail(
          "lastPollLoopIterationAt", Instant.ofEpochMilli(lastPollLoopIterationAtEpochMilli));
      builder.withDetail(
          "lastPollLoopIterationAgeMillis",
          System.currentTimeMillis() - lastPollLoopIterationAtEpochMilli);
    }
    // Null until the consumer's first successful group join publishes the metric -- see
    // RiskSnapshotConsumerService#lastHeartbeatSecondsAgo. The signal that actually reflects
    // broker/coordinator reachability.
    builder.withDetail("lastHeartbeatSecondsAgo", lastHeartbeatSecondsAgo);
    return builder.build();
  }

  private static List<String> formatAssignment(Set<TopicPartition> assignment) {
    return assignment.stream()
        .map(tp -> tp.topic() + "-" + tp.partition())
        .sorted(Comparator.naturalOrder())
        .toList();
  }
}
