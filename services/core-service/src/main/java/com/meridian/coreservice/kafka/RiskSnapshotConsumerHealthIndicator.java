package com.meridian.coreservice.kafka;

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
 * <p><b>{@code pollThreadAlive}/{@code pollLoopIterationCount} say only that the poll loop is
 * iterating -- they do NOT indicate Kafka broker reachability.</b> {@code lastHeartbeatSecondsAgo}
 * is the field that does, because the consumer group heartbeat genuinely stops succeeding when the
 * coordinator is unreachable, unlike {@code KafkaConsumer.poll()} (which doesn't throw on an
 * unreachable broker). The explanation lives here and in {@link RiskSnapshotConsumerRunner}'s class
 * doc and the README's health section -- deliberately NOT as a prose string in the health payload
 * itself, which can't be asserted on and would drift from the field it describes. The field names
 * carry the meaning instead: {@code pollLoopIterationCount} is a bare iteration counter precisely
 * so nobody reads it as a reachability claim.
 */
@Component
public class RiskSnapshotConsumerHealthIndicator implements HealthIndicator {

  private final RiskSnapshotConsumerRunner runner;

  public RiskSnapshotConsumerHealthIndicator(RiskSnapshotConsumerRunner runner) {
    this.runner = runner;
  }

  @Override
  public Health health() {
    boolean pollThreadAlive = runner.isPollThreadAlive();
    Set<TopicPartition> assignment = runner.currentAssignment();
    Double lastHeartbeatSecondsAgo = runner.lastHeartbeatSecondsAgo();

    Health.Builder builder = pollThreadAlive ? Health.up() : Health.down();
    builder.withDetail("pollThreadAlive", pollThreadAlive);
    builder.withDetail("pollLoopIterationCount", runner.pollLoopIterationCount());
    builder.withDetail("partitionAssignment", formatAssignment(assignment));
    // Null until the consumer's first successful group join publishes a real value, or if the
    // underlying metric isn't registered at all -- see RiskSnapshotConsumerService
    // #lastHeartbeatSecondsAgo. The signal that actually reflects broker/coordinator reachability.
    builder.withDetail("lastHeartbeatSecondsAgo", lastHeartbeatSecondsAgo);
    // Disambiguates a null lastHeartbeatSecondsAgo: true means the metric is registered and this
    // consumer just hasn't heartbeated yet (startup, briefly, before the first group join) --
    // false means the signal itself is broken and will report null forever (see
    // RiskSnapshotConsumerRunner#checkHeartbeatMetricIsRegisteredOnce, which also logs this
    // loudly). Null means the one-time startup check hasn't run yet (before the first poll loop
    // iteration completes).
    builder.withDetail("heartbeatMetricRegistered", runner.heartbeatMetricRegistered());
    return builder.build();
  }

  private static List<String> formatAssignment(Set<TopicPartition> assignment) {
    return assignment.stream()
        .map(tp -> tp.topic() + "-" + tp.partition())
        .sorted(Comparator.naturalOrder())
        .toList();
  }
}
