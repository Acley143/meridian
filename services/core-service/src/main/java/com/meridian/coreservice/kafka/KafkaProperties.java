package com.meridian.coreservice.kafka;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** {@code meridian.kafka.*} from application.yml -- bootstrap servers and schema registry URL. */
@Component
@ConfigurationProperties(prefix = "meridian.kafka")
public class KafkaProperties {

  private String bootstrapServers;
  private String schemaRegistryUrl;

  public String getBootstrapServers() {
    return bootstrapServers;
  }

  public void setBootstrapServers(String bootstrapServers) {
    this.bootstrapServers = bootstrapServers;
  }

  public String getSchemaRegistryUrl() {
    return schemaRegistryUrl;
  }

  public void setSchemaRegistryUrl(String schemaRegistryUrl) {
    this.schemaRegistryUrl = schemaRegistryUrl;
  }
}
