from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from mono_bricks.log import get_logger
from mono_bricks.system import REQUIRED, Component, Ctx

log = get_logger(__name__)


class ClientConfig(TypedDict):
    host: str
    port: int
    username: str
    password: str
    database: str
    secure: bool


def _start(ctx: Ctx) -> Client:
    c = ctx.config
    log.info("Connecting to clickhouse", host=c["host"], port=c["port"])
    return clickhouse_connect.get_client(
        host=c["host"],
        port=c["port"],
        username=c["username"],
        password=c["password"],
        database=c["database"],
        secure=c["secure"],
    )


def _stop(ctx: Ctx) -> None:
    ctx.instance.close()


client = Component(
    start=_start,
    stop=_stop,
    config={
        "host": REQUIRED,
        "port": REQUIRED,
        "username": "default",
        "password": "",
        "database": "default",
        "secure": False,
    },
    config_schema=ClientConfig,
    instance_schema=Client,
)


def query(
    client: Client, sql: str, parameters: Mapping[str, Any] | None = None
) -> Sequence[Sequence[Any]]:
    """Rows returned by `sql`."""
    return client.query(sql, parameters=parameters).result_rows


def command(
    client: Client, sql: str, parameters: Mapping[str, Any] | None = None
) -> Any:
    """Run `sql` for its effect (DDL, inserts from select and the like)."""
    return client.command(sql, parameters=parameters)
