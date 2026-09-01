package com.meridian.coreservice.kafka;

import jakarta.annotation.PreDestroy;
import java.time.Duration;
import java.util.Set;
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
 * {@link #lastPollLoopIterationAtEpochMilli} (a {@code volatile long}) for the indicator to read
 * safely from any thread.
 *
 * <p><b>{@code lastPollLoopIterationAtEpochMilli} proves the poll thread is iterating, nothing
 * more.</b> {@code KafkaConsumer.poll()} does not throw when the broker is unreachable -- verified
 * by hand against a real broker outage (ADR-0022's session log): it logs a connection warning and
 * returns an empty batch, which this loop correctly treats as a successful iteration. So this
 * timestamp keeps advancing through a total broker outage; it must never be read as a broker- or
 * data-reachability signal (nor conflated with {@code oldest_input_event_time}). {@link
 * #lastHeartbeatSecondsAgo} is the field that actually reflects broker/coordinator reachability,
 * because the consumer group heartbeat genuinely stops succeeding when the coordinator is
 * unreachable.
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
  // 0 means "no poll loop iteration has completed yet" -- distinct from a genuinely old timestamp.
  private volatile long lastPollLoopIterationAtEpochMilli = 0L;

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
        lastPollLoopIterationAtEpochMilli = System.currentTimeMillis();
      } catch (RuntimeException e) {
        log.error(
            "risk.snapshots poll failed; the failed record was seeked back and will be retried"
                + " on the next poll",
            e);
      }
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
   * Safe to call from any thread -- reads only the published {@code volatile}. 0 = no poll loop
   * iteration has completed yet. Proves the loop is alive; does NOT prove the broker is reachable
   * (see class doc) -- use {@link #lastHeartbeatSecondsAgo} for that.
   */
  public long lastPollLoopIterationAtEpochMilli() {
    return lastPollLoopIterationAtEpochMilli;
  }

  /**
   * Safe to call from any thread -- reads only the published {@link AtomicReference}. {@code null}
   * if the underlying Kafka metric isn't available yet (e.g. before the first group join). The
   * signal that actually reflects broker/coordinator reachability -- see class doc.
   */
  public Double lastHeartbeatSecondsAgo() {
    return lastHeartbeatSecondsAgo.get();
  }

  @PreDestroy
  public void shutdown() {
    running = false;
    if (pollThread != null) {
      pollThread.interrupt();
    }
  }
}
