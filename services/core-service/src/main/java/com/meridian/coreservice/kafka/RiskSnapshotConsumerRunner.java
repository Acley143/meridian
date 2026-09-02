package com.meridian.coreservice.kafka;

import jakarta.annotation.PreDestroy;
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/**
 * Drives {@link RiskSnapshotConsumerService#pollOnce}, continuously, on a dedicated background
 * thread for the lifetime of the application.
 *
 * <p>Found missing during Session 05d's manual verification -- 05c built and thoroughly tested
 * {@link RiskSnapshotConsumerService} itself, but nothing in {@code services/core-service} ever
 * called {@code pollOnce()} outside a test. Running the actual application for the first time (to
 * hand-verify the REST/SSE layer against a real stack, since Testcontainers is unavailable in this
 * environment) surfaced it: the consumer subscribed to {@code risk.snapshots} on startup but never
 * polled, so no snapshot would ever actually reach {@code risk_snapshots} in a real deployment.
 *
 * <p>A poll failure (a write that throws) is logged and the loop continues -- {@link
 * RiskSnapshotConsumerService#pollOnce} already seeks back to the failed record before rethrowing
 * (05c's own fix), so the very next {@code pollOnce()} call redelivers it. A transient failure
 * (e.g. the database is briefly unavailable) is retried indefinitely by this loop rather than
 * crashing the application; nothing here silently drops a record.
 *
 * <p>Also the sole publisher of this consumer's health-detail state (ADR-0022). {@code
 * KafkaConsumer} is not thread-safe, so {@link RiskSnapshotConsumerHealthIndicator} -- which runs
 * on an HTTP request thread -- must never call {@link
 * RiskSnapshotConsumerService#currentAssignment} or {@link
 * RiskSnapshotConsumerService#lastHeartbeatSecondsAgo} itself; only this class's own poll-loop
 * thread does, immediately after each {@code pollOnce()} returns, publishing the results into
 * {@link #lastAssignment} and {@link #lastHeartbeatSecondsAgo} (both {@link AtomicReference}) and
 * {@link #pollLoopIterationCount} (an {@link AtomicLong}) for the indicator to read safely from any
 * thread.
 *
 * <p><b>{@code pollLoopIterationCount} proves the loop is iterating, nothing more -- it is
 * deliberately a bare counter, not a timestamp.</b> An earlier version of this field was a
 * last-iteration timestamp/age, which read (and was misread, in review) as a plausible
 * broker-reachability signal even though it wasn't one: {@code KafkaConsumer.poll()} does not throw
 * when the broker is unreachable -- verified by hand against a real broker outage (ADR-0022's
 * session log) -- it logs a connection warning and returns an empty batch, which this loop
 * correctly treats as a successful iteration, so a timestamp kept advancing through a total broker
 * outage. A monotonic count of loop iterations invites no such reading; nobody expects "how many
 * times has this loop run" to imply anything about a remote broker. See ADR-0022 and the README's
 * health section for the fuller writeup -- this class carries only the mechanism, not the
 * explanation, so the two can't drift apart. {@link #lastHeartbeatSecondsAgo} is the field that
 * actually reflects broker/coordinator reachability, because the consumer group heartbeat genuinely
 * stops succeeding when the coordinator is unreachable.
 */
@Component
public class RiskSnapshotConsumerRunner implements ApplicationRunner {

  private static final Logger log = LoggerFactory.getLogger(RiskSnapshotConsumerRunner.class);
  private static final Duration POLL_TIMEOUT = Duration.ofSeconds(1);

  private final RiskSnapshotConsumerService consumerService;
  private volatile boolean running = true;
  private Thread pollThread;

  private final AtomicReference<Set<TopicPartition>> lastAssignment =
      new AtomicReference<>(Set.of());
  private final AtomicReference<Double> lastHeartbeatSecondsAgo = new AtomicReference<>(null);
  private final AtomicLong pollLoopIterationCount = new AtomicLong(0);
  // null = not checked yet (before the first poll loop iteration completes); true/false = whether
  // HEARTBEAT_METRIC_NAME was found at that one-time check. Lets a reader of the health detail
  // tell "hasn't heartbeated yet" (registered, still null) apart from "the signal itself is
  // broken" (not registered, will stay null forever) -- both otherwise collapse to the same null
  // lastHeartbeatSecondsAgo.
  private final AtomicReference<Boolean> heartbeatMetricRegistered = new AtomicReference<>(null);
  private volatile boolean heartbeatMetricCheckedAtStartup = false;

  public RiskSnapshotConsumerRunner(RiskSnapshotConsumerService consumerService) {
    this.consumerService = consumerService;
  }

  @Override
  public void run(ApplicationArguments args) {
    pollThread = new Thread(this::pollLoop, "risk-snapshots-consumer");
    pollThread.setDaemon(true);
    pollThread.start();
  }

  private void pollLoop() {
    while (running) {
      try {
        consumerService.pollOnce(POLL_TIMEOUT);
        // See class doc: this proves the LOOP is iterating, not that the broker is reachable.
        lastAssignment.set(consumerService.currentAssignment());
        lastHeartbeatSecondsAgo.set(consumerService.lastHeartbeatSecondsAgo());
        pollLoopIterationCount.incrementAndGet();
        checkHeartbeatMetricIsRegisteredOnce();
      } catch (RuntimeException e) {
        log.error(
            "risk.snapshots poll failed; the failed record was seeked back and will be retried"
                + " on the next poll",
            e);
      }
    }
  }

  /**
   * Runs once, after the first successful poll loop iteration. Confirms {@link
   * RiskSnapshotConsumerService#HEARTBEAT_METRIC_NAME} is actually registered by name on this Kafka
   * client, and logs loudly if it isn't -- a metric rename across a future kafka-clients upgrade
   * would otherwise silently degrade {@code lastHeartbeatSecondsAgo} to always-null without
   * anything failing loudly on its own, reproducing this exact ADR's "field reads as fine when it
   * isn't" failure in a new form.
   */
  private void checkHeartbeatMetricIsRegisteredOnce() {
    if (heartbeatMetricCheckedAtStartup) {
      return;
    }
    heartbeatMetricCheckedAtStartup = true;
    boolean registered = consumerService.heartbeatMetricIsRegistered();
    heartbeatMetricRegistered.set(registered);
    if (registered) {
      log.info(
          "risk.snapshots consumer: '{}' metric is registered -- Kafka broker/coordinator"
              + " reachability will be reported via lastHeartbeatSecondsAgo",
          RiskSnapshotConsumerService.HEARTBEAT_METRIC_NAME);
    } else {
      log.error(
          "risk.snapshots consumer: expected Kafka metric '{}' was NOT found on this client --"
              + " lastHeartbeatSecondsAgo will report null indefinitely instead of reflecting"
              + " broker/coordinator reachability. This likely means the metric was renamed in the"
              + " kafka-clients version in use; RiskSnapshotConsumerService needs updating.",
          RiskSnapshotConsumerService.HEARTBEAT_METRIC_NAME);
    }
  }

  /** Safe to call from any thread -- {@link Thread#isAlive()} makes no thread-affinity promise. */
  public boolean isPollThreadAlive() {
    return pollThread != null && pollThread.isAlive();
  }

  /** Safe to call from any thread -- reads only the published {@link AtomicReference}. */
  public Set<TopicPartition> currentAssignment() {
    return lastAssignment.get();
  }

  /**
   * Safe to call from any thread -- reads only the published {@link AtomicLong}. A bare count of
   * completed poll loop iterations since this runner started; proves the loop is alive, does NOT
   * prove the broker is reachable (see class doc) -- use {@link #lastHeartbeatSecondsAgo} for that.
   */
  public long pollLoopIterationCount() {
    return pollLoopIterationCount.get();
  }

  /**
   * Safe to call from any thread -- reads only the published {@link AtomicReference}. {@code null}
   * if the underlying Kafka metric isn't registered, or hasn't reported a real number yet (e.g.
   * before the first group join). The signal that actually reflects broker/coordinator reachability
   * -- see class doc.
   */
  public Double lastHeartbeatSecondsAgo() {
    return lastHeartbeatSecondsAgo.get();
  }

  /**
   * Safe to call from any thread -- reads only the published {@link AtomicReference}. {@code null}
   * before the one-time startup check has run; {@code true}/{@code false} after, for whether {@link
   * RiskSnapshotConsumerService#HEARTBEAT_METRIC_NAME} was found. Lets a caller distinguish a
   * {@code null} {@link #lastHeartbeatSecondsAgo} that means "hasn't heartbeated yet" (registered)
   * from one that means "this signal is broken" (not registered) -- see field doc.
   */
  public Boolean heartbeatMetricRegistered() {
    return heartbeatMetricRegistered.get();
  }

  @PreDestroy
  public void shutdown() {
    running = false;
    if (pollThread != null) {
      pollThread.interrupt();
    }
  }
}
