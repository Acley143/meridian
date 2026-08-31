package com.meridian.coreservice.web;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.module.SimpleModule;
import java.io.IOException;
import java.math.BigDecimal;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Two rules matching contracts/openapi/service-api.yaml exactly:
 *
 * <ul>
 *   <li><b>Field names are snake_case</b> ({@code portfolio_id}, not {@code portfolioId}) --
 *       matches the OpenAPI schema property names verbatim rather than requiring a
 *       {@code @JsonProperty} on every DTO field.
 *   <li><b>Every {@link BigDecimal} serializes as a JSON string</b>, via {@link
 *       BigDecimal#toPlainString()} -- never a JSON number. An IEEE-754 double cannot represent a
 *       scale-8 decimal exactly, and a JavaScript client's default {@code JSON.parse} numeric
 *       coercion would silently corrupt it. {@code toPlainString()} specifically (not {@code
 *       toString()}) to avoid scientific notation for very large/small magnitudes -- the OpenAPI
 *       spec's money fields are meant to be read directly into a decimal library, not re-parsed as
 *       a float first.
 * </ul>
 */
@Configuration
public class JacksonConfig {

  @Bean
  public Jackson2ObjectMapperBuilderCustomizer moneyAsStringAndSnakeCase() {
    return builder -> {
      builder.propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
      SimpleModule module = new SimpleModule("meridian-money");
      module.addSerializer(
          BigDecimal.class,
          new com.fasterxml.jackson.databind.JsonSerializer<BigDecimal>() {
            @Override
            public void serialize(
                BigDecimal value,
                com.fasterxml.jackson.core.JsonGenerator gen,
                com.fasterxml.jackson.databind.SerializerProvider serializers)
                throws IOException {
              gen.writeString(value.toPlainString());
            }
          });
      builder.modulesToInstall(module);
    };
  }
}
