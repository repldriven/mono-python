from dataclasses import replace

import mono_bricks.clickhouse
import mono_bricks.testcontainers  # noqa: F401  (registers clickhouse/container)
import pytest
from mono_bricks import clickhouse, clickhouse_migrator, system
from mono_bricks.test_system import with_test_system

pytestmark = pytest.mark.docker

CONFIG = "clickhouse_migrator/application-test.yml"


def test_migrations_apply_when_the_system_starts():
    with with_test_system(CONFIG) as sys:
        client = system.instance(sys, "clickhouse-migrator", "migrations")
        assert client is system.instance(sys, "clickhouse", "client")
        rows = clickhouse.query(client, "SELECT name FROM greetings ORDER BY id")
        assert rows == [("hello",), ("world",)]


def test_migrate_applies_only_what_is_pending():
    with with_test_system(CONFIG, component_ids=["clickhouse"]) as sys:
        client = system.instance(sys, "clickhouse", "client")
        assert clickhouse_migrator.migrate(
            client, "clickhouse_migrator/migrations"
        ) == [1, 2]
        assert (
            clickhouse_migrator.migrate(client, "clickhouse_migrator/migrations") == []
        )
        assert clickhouse.query(client, "SELECT count() FROM greetings") == [(2,)]


def test_failed_migration_fails_the_system():
    def broken(defs):
        component = defs["clickhouse-migrator"]["migrations"]
        config = {
            **component.config,
            "migrations": ["clickhouse_migrator/broken-migrations"],
        }
        defs["clickhouse-migrator"]["migrations"] = replace(component, config=config)
        return defs

    with pytest.raises(system.StartError, match="clickhouse-migrator.migrations") as e:
        with with_test_system(CONFIG, patch=broken):
            pass
    assert isinstance(e.value.cause, clickhouse_migrator.MigrationError)
