"""Session-scoped real Kafka + schema-registry stack for contract/integration
tests (docs/test-strategy.md: "contract tests ... against a real local
schema registry ... not a mock of either"). Shared by `libs/quant-io` and
`services/ingest` tests so the whole `pytest libs services` run pays the
container-startup cost once.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest

_SCHEMA_REGISTRY_IMAGE = "confluentinc/cp-schema-registry:7.6.1"
_KAFKA_NETWORK_ALIAS = "kafka"
_KAFKA_BROKER_PORT = 9092  # testcontainers' internal "BROKER" listener


@dataclass(frozen=True)
class KafkaStack:
    bootstrap_servers: str
    schema_registry_url: str


@pytest.fixture(scope="session")
def kafka_stack() -> Iterator[KafkaStack]:
    pytest.importorskip("testcontainers", reason="integration deps not installed in this job")
    from testcontainers.community.kafka import KafkaContainer
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.network import Network
    from testcontainers.core.waiting_utils import wait_for_logs

    network = Network()
    network.create()
    try:
        kafka = (
            KafkaContainer()
            .with_kraft()
            .with_network(network)
            .with_network_aliases(_KAFKA_NETWORK_ALIAS)
        )
        kafka.start()
        try:
            registry = (
                DockerContainer(_SCHEMA_REGISTRY_IMAGE)
                .with_network(network)
                .with_network_aliases("schema-registry")
                .with_exposed_ports(8081)
                .with_env("SCHEMA_REGISTRY_HOST_NAME", "schema-registry")
                .with_env(
                    "SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS",
                    f"PLAINTEXT://{_KAFKA_NETWORK_ALIAS}:{_KAFKA_BROKER_PORT}",
                )
                .with_env("SCHEMA_REGISTRY_LISTENERS", "http://0.0.0.0:8081")
            )
            registry.start()
            try:
                wait_for_logs(registry, r".*Server started, listening for requests.*", timeout=60)
                registry_url = (
                    f"http://{registry.get_container_host_ip()}:"
                    f"{registry.get_exposed_port(8081)}"
                )
                yield KafkaStack(
                    bootstrap_servers=kafka.get_bootstrap_server(),
                    schema_registry_url=registry_url,
                )
            finally:
                registry.stop()
        finally:
            kafka.stop()
    finally:
        network.remove()
