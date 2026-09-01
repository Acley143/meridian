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
 * RiskSnapshotConsumerService#currentAssignment} itself; only this class's own poll-loop thread
 * does, immediately after each {@code pollOnce()} returns, publishing the result into {@link
 * #lastAssignment} (an {@link AtomicReference}) and {@link #lastPollCompletedAtEpochMilli} (a
 * {@code volatile long}) for the indicator to read safely from any thread.
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
  // 0 means "no poll has completed yet" -- distinct from a genuinely old timestamp.
  private volatile long lastPollCompletedAtEpochMilli = 0L;

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
        // A poll that returns zero records still completed successfully -- this timestamp proves
        // the loop is alive, it is not a data-freshness signal (do not conflate it with
        // oldest_input_event_time). Read from this same thread only; see class doc.
        lastAssignment.set(consumerService.currentAssignment());
        lastPollCompletedAtEpochMilli = System.currentTimeMillis();
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
   * Safe to call from any thread -- reads only the published {@code volatile}. 0 = never polled.
   */
  public long lastPollCompletedAtEpochMilli() {
    return lastPollCompletedAtEpochMilli;
  }

  @PreDestroy
  public void shutdown() {
    running = false;
    if (pollThread != null) {
      pollThread.interrupt();
    }
  }
}
