"""ClickHouse schema migrations, on clickhouse-migrations.

Importing this brick registers `clickhouse-migrator/migrations`, which applies each
configured directory of migrations with the given client when it starts. Its
instance is that client, so a component that refs it rather than the client
starts after the schema exists.

    clickhouse-migrator:
      migrations: !system/component
        system/component-kind: clickhouse-migrator/migrations
        client: !system/ref clickhouse.client
        migrations:
          - clickhouse/migrations
"""

from mono_bricks import system
from mono_bricks.clickhouse_migrator.core import MigrationError, migrate, migrations

system.register_components("clickhouse-migrator", {"migrations": migrations})

__all__ = ["MigrationError", "migrate", "migrations"]
