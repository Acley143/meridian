package com.meridian.coreservice.persistence;

import com.meridian.coreservice.kafka.AbstractKafkaIntegrationTest;

/**
 * Shared Testcontainers Postgres for core-service persistence tests. Extends {@link
 * AbstractKafkaIntegrationTest} rather than declaring its own lone Postgres container: a plain
 * {@code @SpringBootTest} boots the *full* application context, which includes
 * {@code PortfolioStateProducer}/{@code ReferenceInstrumentProducer} -- both create their Kafka
 * topic eagerly in their constructor (Task 1: real CI execution surfaced this the first time these
 * tests actually ran -- every persistence-only test using a Postgres-only base timed out for ~70s
 * trying to reach a Kafka broker that was never started, then failed context load entirely). A
 * fresh Postgres container per test class (not reused across classes) so "migrations apply cleanly
 * from empty" is actually exercised by every test class's context startup, not assumed from one
 * earlier run -- unchanged from before, just inherited now.
 */
public abstract class AbstractPostgresIntegrationTest extends AbstractKafkaIntegrationTest {}
