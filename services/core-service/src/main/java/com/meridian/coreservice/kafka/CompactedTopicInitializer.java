package com.meridian.coreservice.kafka;

import java.util.Collections;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.ExecutionException;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.Config;
import org.apache.kafka.clients.admin.ConfigEntry;
import org.apache.kafka.clients.admin.DescribeConfigsResult;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.config.ConfigResource;
import org.apache.kafka.common.errors.TopicExistsException;

/**
 * The convention this class enforces: the sole producer of a compacted topic owns that topic's
 * configuration. It creates the topic if absent, and if the topic already exists it verifies --
 * rather than assumes -- that the existing configuration matches what this class would have
 * created, refusing to start otherwise. This is deliberately not a reconciler: a mismatched
 * existing topic (e.g. auto-created by another client with Kafka's {@code delete} default before
 * core-service ever started) is a configuration error to fail loudly on, not something to silently
 * alter out from under whatever else may already be depending on it. See ADR-0003 (portfolio.state
 * is single-producer-owned), ADR-0016 (topic configuration is a deliberate, up-front decision, not
 * something adjusted casually later), and ADR-0019 (reference.instruments' compaction requirement).
 *
 * <p>Partition count is 1 for both of this class's callers' topics -- matching the single-broker
 * dev cluster in docker-compose.yml, not a considered production choice. A real multi-broker
 * deployment revisiting this is infra/PLAN.md's decision to make, at topic creation, before any
 * production data exists on either topic.
 */
final class CompactedTopicInitializer {

  private static final String CLEANUP_POLICY_CONFIG = "cleanup.policy";
  private static final String EXPECTED_CLEANUP_POLICY = "compact";
  private static final int EXPECTED_PARTITION_COUNT = 1;
  private static final short REPLICATION_FACTOR = 1;

  private CompactedTopicInitializer() {}

  static void ensureExists(String bootstrapServers, String topic) {
    Properties adminProps = new Properties();
    adminProps.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);

    try (Admin admin = Admin.create(adminProps)) {
      NewTopic newTopic =
          new NewTopic(topic, EXPECTED_PARTITION_COUNT, REPLICATION_FACTOR)
              .configs(Collections.singletonMap(CLEANUP_POLICY_CONFIG, EXPECTED_CLEANUP_POLICY));
      admin.createTopics(Collections.singletonList(newTopic)).all().get();
    } catch (ExecutionException e) {
      if (!(e.getCause() instanceof TopicExistsException)) {
        throw new IllegalStateException("failed to ensure compacted topic exists: " + topic, e);
      }
      // Topic already exists -- idempotent only if its configuration actually matches what this
      // class would have created. Verify rather than assume.
      verifyExistingTopic(bootstrapServers, topic);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException("interrupted ensuring compacted topic exists: " + topic, e);
    }
  }

  private static void verifyExistingTopic(String bootstrapServers, String topic) {
    Properties adminProps = new Properties();
    adminProps.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);

    try (Admin admin = Admin.create(adminProps)) {
      ConfigResource resource = new ConfigResource(ConfigResource.Type.TOPIC, topic);
      DescribeConfigsResult configsResult =
          admin.describeConfigs(Collections.singletonList(resource));
      Map<ConfigResource, Config> configs = configsResult.all().get();
      ConfigEntry cleanupPolicy =
          configs.get(resource).entries().stream()
              .filter(entry -> entry.name().equals(CLEANUP_POLICY_CONFIG))
              .findFirst()
              .orElseThrow();

      if (!EXPECTED_CLEANUP_POLICY.equals(cleanupPolicy.value())) {
        throw new IllegalStateException(
            "existing topic "
                + topic
                + " has cleanup.policy="
                + cleanupPolicy.value()
                + ", expected "
                + EXPECTED_CLEANUP_POLICY);
      }

      Map<String, TopicDescription> descriptions =
          admin.describeTopics(Collections.singletonList(topic)).allTopicNames().get();
      int actualPartitionCount = descriptions.get(topic).partitions().size();

      if (actualPartitionCount != EXPECTED_PARTITION_COUNT) {
        throw new IllegalStateException(
            "existing topic "
                + topic
                + " has "
                + actualPartitionCount
                + " partition(s), expected "
                + EXPECTED_PARTITION_COUNT);
      }
    } catch (ExecutionException e) {
      throw new IllegalStateException("failed to verify existing compacted topic: " + topic, e);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException(
          "interrupted verifying existing compacted topic: " + topic, e);
    }
  }
}
