package com.meridian.coreservice.kafka;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Collections;
import java.util.Map;
import java.util.Properties;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.Config;
import org.apache.kafka.clients.admin.ConfigEntry;
import org.apache.kafka.clients.admin.DescribeConfigsResult;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.config.ConfigResource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

/**
 * {@link CompactedTopicInitializer#ensureExists} against the shared Testcontainers broker: an
 * absent topic is created per the declared spec, and an existing topic that does not match the
 * declared spec (wrong cleanup.policy, wrong partition count, or a compound cleanup.policy value
 * that merely contains "compact") fails startup loudly instead of being silently accepted or
 * reconciled. Kept separate from {@link CompactionConfigurationTest}, which exercises the
 * already-correct topic's actual compaction/round-trip behavior -- this class exercises the
 * verify-on-conflict decision itself, including the negative cases that prove the check can fail.
 */
class CompactedTopicInitializerTest extends AbstractKafkaIntegrationTest {

  @Autowired private KafkaProperties kafkaProperties;

  @Test
  void absentTopicIsCreatedPerTheDeclaredSpec() throws Exception {
    String topic = "compacted-topic-initializer-test-absent-" + System.nanoTime();

    CompactedTopicInitializer.ensureExists(kafkaProperties.getBootstrapServers(), topic);

    Properties adminProps = new Properties();
    adminProps.put(
        AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
    try (Admin admin = Admin.create(adminProps)) {
      assertThat(cleanupPolicyOf(admin, topic)).isEqualTo("compact");
      assertThat(partitionCountOf(admin, topic)).isEqualTo(1);
    }
  }

  @Test
  void existingTopicWithDeletePolicyIsRejected() throws Exception {
    String topic = "compacted-topic-initializer-test-delete-policy-" + System.nanoTime();
    createTopic(topic, 1, Map.of("cleanup.policy", "delete"));

    assertThatThrownBy(
            () ->
                CompactedTopicInitializer.ensureExists(
                    kafkaProperties.getBootstrapServers(), topic))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining(topic)
        .hasMessageContaining("has cleanup.policy=delete, expected compact")
        .hasMessageNotContaining("failed to verify");
  }

  @Test
  void existingTopicWithWrongPartitionCountIsRejected() throws Exception {
    String topic = "compacted-topic-initializer-test-wrong-partitions-" + System.nanoTime();
    createTopic(topic, 2, Map.of("cleanup.policy", "compact"));

    assertThatThrownBy(
            () ->
                CompactedTopicInitializer.ensureExists(
                    kafkaProperties.getBootstrapServers(), topic))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining(topic)
        .hasMessageContaining("has 2 partition(s), expected 1")
        .hasMessageNotContaining("failed to verify");
  }

  @Test
  void existingTopicWithCompoundCleanupPolicyIsRejected() throws Exception {
    String topic = "compacted-topic-initializer-test-compound-policy-" + System.nanoTime();
    createTopic(topic, 1, Map.of("cleanup.policy", "compact,delete"));

    assertThatThrownBy(
            () ->
                CompactedTopicInitializer.ensureExists(
                    kafkaProperties.getBootstrapServers(), topic))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining(topic)
        .hasMessageContaining("has cleanup.policy=compact,delete, expected compact")
        .hasMessageNotContaining("failed to verify");
  }

  @Test
  void existingTopicMatchingTheSpecIsAcceptedIdempotently() throws Exception {
    String topic = "compacted-topic-initializer-test-matching-" + System.nanoTime();
    createTopic(topic, 1, Map.of("cleanup.policy", "compact"));

    CompactedTopicInitializer.ensureExists(kafkaProperties.getBootstrapServers(), topic);
    CompactedTopicInitializer.ensureExists(kafkaProperties.getBootstrapServers(), topic);
  }

  private void createTopic(String topic, int partitions, Map<String, String> configs)
      throws Exception {
    Properties adminProps = new Properties();
    adminProps.put(
        AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, kafkaProperties.getBootstrapServers());
    try (Admin admin = Admin.create(adminProps)) {
      NewTopic newTopic = new NewTopic(topic, partitions, (short) 1).configs(configs);
      admin.createTopics(Collections.singletonList(newTopic)).all().get();
    }
  }

  private static String cleanupPolicyOf(Admin admin, String topic) throws Exception {
    ConfigResource resource = new ConfigResource(ConfigResource.Type.TOPIC, topic);
    DescribeConfigsResult result = admin.describeConfigs(Collections.singletonList(resource));
    Map<ConfigResource, Config> configs = result.all().get();
    ConfigEntry entry =
        configs.get(resource).entries().stream()
            .filter(e -> e.name().equals("cleanup.policy"))
            .findFirst()
            .orElseThrow();
    return entry.value();
  }

  private static int partitionCountOf(Admin admin, String topic) throws Exception {
    Map<String, TopicDescription> descriptions =
        admin.describeTopics(Collections.singletonList(topic)).allTopicNames().get();
    return descriptions.get(topic).partitions().size();
  }
}
