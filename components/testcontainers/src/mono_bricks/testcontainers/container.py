"""Starting and stopping a testcontainers-python container."""

from collections.abc import Sequence
from dataclasses import dataclass

from testcontainers.core.container import DockerContainer


@dataclass(frozen=True)
class Started:
    """A started container, the host to reach it on, and its mapped ports."""

    container: DockerContainer
    host: str
    mapped_ports: dict[int, int]


def start(container: DockerContainer, exposed_ports: Sequence[int]) -> Started:
    container.with_exposed_ports(*exposed_ports).start()
    return Started(
        container=container,
        # The Docker host isn't always localhost (Docker-in-Docker, remote
        # daemons), so ask rather than assume.
        host=container.get_container_host_ip(),
        mapped_ports={p: int(container.get_exposed_port(p)) for p in exposed_ports},
    )


def stop(started: Started | None) -> None:
    if started is not None:
        started.container.stop()
