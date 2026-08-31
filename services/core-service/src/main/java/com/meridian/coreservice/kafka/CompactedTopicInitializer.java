package com.meridian.coreservice.kafka;

import java.util.Collections;
import java.util.Properties;
import java.util.concurrent.ExecutionException;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.errors.TopicExistsException;

/**
 * Idempotently ensures a log-compacted topic exists, with {@code cleanup.policy=compact} set
 * explicitly rather than relying on Kafka's auto-create default (which is {@code delete}, not
 * {@code compact}) -- as of this session, nothing in {@code infra/PLAN.md} (still "not started")
 * creates {@code portfolio.state} or {@code reference.instruments} with the correct policy, so
 * relying on auto-create here would silently violate ADR-0003/ADR-0016/ADR-0019's compaction
 * requirement. Each of this session's producers is the sole producer of its topic (ADR-0003,
 * ADR-0019), so each owns making sure its own topic is configured correctly on startup.
 *
 * <p>Partition count is 1 for both topics -- matching the single-broker dev cluster in
 * docker-compose.yml, not a considered production choice. ADR-0016 requires partition count be set
 * deliberately once, up front, not adjusted casually later; 1 is that deliberate up-front choice
 * for Q1's dev/test scope. A real multi-broker deployment revisiting this is infra/PLAN.md's
 * decision to make, at topic creation, before any production data exists on either topic.
 */
final class CompactedTopicInitializer {

  private CompactedTopicInitializer() {}

  static void ensureExists(String bootstrapServers, String topic) {
    Properties adminProps = new Properties();
    adminProps.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);

    try (Admin admin = Admin.create(adminProps)) {
      NewTopic newTopic =
          new NewTopic(topic, 1, (short) 1)
              .configs(Collections.singletonMap("cleanup.policy", "compact"));
      admin.createTopics(Collections.singletonList(newTopic)).all().get();
    } catch (ExecutionException e) {
      if (!(e.getCause() instanceof TopicExistsException)) {
        throw new IllegalStateException("failed to ensure compacted topic exists: " + topic, e);
      }
      // Topic already exists -- fine, this call is idempotent. Its cleanup.policy was set by
      // whichever call created it first (this class always requests "compact"), so a topic that
      // already existed with a different policy (e.g. auto-created before this code ran) is not
      // corrected here. That's a real limitation: this only guarantees the policy on first
      // creation, not a subsequent reconciliation of a misconfigured existing topic.
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException("interrupted ensuring compacted topic exists: " + topic, e);
    }
  }
}
