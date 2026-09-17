from pathlib import Path
from typing import Any, TypedDict

from clickhouse_migrations.connection import ClickhouseConnectConnection
from clickhouse_migrations.migration import MigrationStorage
from clickhouse_migrations.migrator import Migrator
from mono_bricks import env
from mono_bricks.clickhouse import Client
from mono_bricks.log import get_logger
from mono_bricks.system import REQUIRED, Component, Ctx

log = get_logger(__name__)


class MigrationError(Exception):
    """A directory of migrations failed to apply."""


class MigrationsConfig(TypedDict):
    client: Any
    migrations: list[str]


def migrate(client: Client, migrations: str | Path) -> list[int]:
    """Apply the migrations in `migrations` not yet applied to the client's
    database, returning the versions applied.

    `migrations` is a directory, or a resource name for one, of
    `{VERSION}_{name}.sql` files.
    """
    path = Path(migrations)
    if not path.is_dir():
        path = env.find_resource_dir(str(migrations))
    log.info("Applying clickhouse migrations", path=str(path))
    try:
        # The connection isn't entered as a context manager: leaving it would
        # close the client, which belongs to whoever passed it in.
        migrator = Migrator(ClickhouseConnectConnection(client))
        migrator.init_schema()
        applied = migrator.apply_migration(
            MigrationStorage(path).migrations(), multi_statement=True
        )
    except Exception as e:
        raise MigrationError(f"Failed to apply migrations from {path}: {e}") from e
    return [m.version for m in applied]


def _start(ctx: Ctx) -> Client:
    client = ctx.config["client"]
    for migrations in ctx.config["migrations"]:
        migrate(client, migrations)
    return client


migrations = Component(
    start=_start,
    config={"client": REQUIRED, "migrations": REQUIRED},
    config_schema=MigrationsConfig,
    instance_schema=Client,
)
