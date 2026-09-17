"""Components for any image, and for reading values out of a started one."""

from typing import Any, TypedDict

from mono_bricks.log import get_logger
from mono_bricks.system import REQUIRED, Component, Ctx
from mono_bricks.testcontainers import container as tc
from mono_bricks.testcontainers.container import Started

from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import PortWaitStrategy

log = get_logger(__name__)

# Functional TypedDicts keep the YAML's kebab-case keys as they are.
ContainerConfig = TypedDict(
    "ContainerConfig",
    {"docker-image-name": str, "exposed-ports": list[int], "startup-timeout": int},
)
MappedExposedPortConfig = TypedDict(
    "MappedExposedPortConfig", {"container": Any, "exposed-port": int}
)


class UriConfig(TypedDict):
    scheme: str
    host: str
    port: int
    path: str


def _start_container(ctx: Ctx) -> Started:
    config = ctx.config
    image = config["docker-image-name"]
    ports = config["exposed-ports"]
    log.info("Starting container", image=image)
    container = DockerContainer(image)
    if ports:
        container.waiting_for(
            PortWaitStrategy(ports[0]).with_startup_timeout(config["startup-timeout"])
        )
    return tc.start(container, ports)


def _stop_container(ctx: Ctx) -> None:
    log.info("Stopping container", image=ctx.config["docker-image-name"])
    tc.stop(ctx.instance)


container = Component(
    start=_start_container,
    stop=_stop_container,
    config={
        "docker-image-name": REQUIRED,
        "exposed-ports": REQUIRED,
        "startup-timeout": 60,
    },
    config_schema=ContainerConfig,
    instance_schema=Started,
)

mapped_ports = Component(
    start=lambda ctx: dict(ctx.config["container"].mapped_ports),
    config={"container": REQUIRED},
)


def _mapped_exposed_port(ctx: Ctx) -> int:
    started: Started = ctx.config["container"]
    port = ctx.config["exposed-port"]
    if port not in started.mapped_ports:
        raise ValueError(
            f"Port {port} isn't exposed; "
            f"exposed ports are {sorted(started.mapped_ports)}"
        )
    return started.mapped_ports[port]


mapped_exposed_port = Component(
    start=_mapped_exposed_port,
    config={"container": REQUIRED, "exposed-port": REQUIRED},
    config_schema=MappedExposedPortConfig,
)

host = Component(
    start=lambda ctx: ctx.config["container"].host,
    config={"container": REQUIRED},
)


def _uri(ctx: Ctx) -> str:
    c = ctx.config
    return f"{c['scheme']}://{c['host']}:{c['port']}{c['path']}"


uri = Component(
    start=_uri,
    config={"scheme": "http", "host": "localhost", "port": REQUIRED, "path": ""},
    config_schema=UriConfig,
)
