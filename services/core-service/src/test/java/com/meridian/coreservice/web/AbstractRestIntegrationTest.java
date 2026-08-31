package com.meridian.coreservice.web;

import com.meridian.coreservice.kafka.AbstractKafkaIntegrationTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

/**
 * REST/SSE tests need a real embedded HTTP server (Task 4.4: an actual request/response over the
 * wire, not MockMvc) plus the same Kafka + schema registry + Postgres stack 05c's tests use --
 * {@code POST /trades} goes through {@code PortfolioMutationService}, which publishes to {@code
 * portfolio.state} and needs a live broker to construct its producer at all.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
public abstract class AbstractRestIntegrationTest extends AbstractKafkaIntegrationTest {

  @LocalServerPort protected int port;

  protected String baseUrl() {
    return "http://localhost:" + port;
  }
}
