import pytest
from mono_bricks import (  # noqa: F401  (registers components)
    env,
    system,
    test_system,
    testcontainers,
)


def test_clickhouse_defs_build_without_docker():
    config = {
        "system": {
            "clickhouse-server": env.config(
                "testcontainers/clickhouse-test.yml", "test"
            )
        }
    }
    defs = system.defs(config)
    container = defs["clickhouse-server"]["container"]
    assert container.config["exposed-ports"] == [8123, 9000]
    assert container.config["docker-image-name"].startswith(
        "clickhouse/clickhouse-server:"
    )


@pytest.mark.docker
def test_generic_container_provides_mapped_ports():
    with test_system.started("testcontainers/application-test.yml") as sys:
        ports = system.instance(sys, "helloworld", "container-mapped-ports")
        assert sorted(ports) == [8080, 8081]
        assert (
            system.instance(sys, "helloworld", "container-mapped-exposed-port")
            == ports[8080]
        )


@pytest.mark.docker
def test_clickhouse_container_provides_host_and_http_port():
    defs = system.defs(
        {
            "system": {
                "clickhouse-server": env.config(
                    "testcontainers/clickhouse-test.yml", "test"
                )
            }
        }
    )
    with system.started(defs) as sys:
        started = system.instance(sys, "clickhouse-server", "container")
        port = system.instance(sys, "clickhouse-server", "container-http-port")
        assert port == started.mapped_ports[8123]
        assert (
            system.instance(sys, "clickhouse-server", "container-host") == started.host
        )
