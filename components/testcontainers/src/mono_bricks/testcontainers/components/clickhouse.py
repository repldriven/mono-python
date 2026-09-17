"""ClickHouse server container.

Only the container's lifecycle lives here. Connecting to it is the clickhouse
brick's job.
"""

from typing import TypedDict

from mono_bricks.log import get_logger
from mono_bricks.system import Component, Ctx
from mono_bricks.testcontainers import container as tc
from mono_bricks.testcontainers.container import Started

from testcontainers.community.clickhouse import ClickHouseContainer

log = get_logger(__name__)

HTTP_PORT = 8123
NATIVE_PORT = 9000

ClickHouseConfig = TypedDict(
    "ClickHouseConfig",
    {
        "docker-image-name": str,
        "exposed-ports": list[int],
        "username": str,
        "password": str,
        "database": str,
    },
)


def _start(ctx: Ctx) -> Started:
    config = ctx.config
    log.info("Starting clickhouse container")
    # ClickHouseContainer exposes both ports itself, and waits until the HTTP
    # interface answers before start returns.
    container = ClickHouseContainer(
        image=config["docker-image-name"],
        username=config["username"],
        password=config["password"],
        dbname=config["database"],
    )
    return tc.start(container, config["exposed-ports"])


def _stop(ctx: Ctx) -> None:
    log.info("Stopping clickhouse container")
    tc.stop(ctx.instance)


container = Component(
    start=_start,
    stop=_stop,
    config={
        "docker-image-name": "clickhouse/clickhouse-server:25.8",
        "exposed-ports": [HTTP_PORT, NATIVE_PORT],
        "username": "test",
        "password": "test",
        "database": "test",
    },
    config_schema=ClickHouseConfig,
    instance_schema=Started,
)
