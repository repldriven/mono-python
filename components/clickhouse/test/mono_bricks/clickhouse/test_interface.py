import pytest
from mono_bricks import (  # noqa: F401  (registers components)
    clickhouse,
    clickhouse_migrator,
    system,
    testcontainers,
)
from mono_bricks.test_system import with_test_system

pytestmark = pytest.mark.docker

CONFIG = "clickhouse/application-test.yml"


def test_client_queries_the_containerised_server():
    with with_test_system(CONFIG) as sys:
        client = system.instance(sys, "clickhouse", "client")
        assert clickhouse.query(client, "SELECT 1") == [(1,)]


def test_insert_select_on_migrated_table():
    with with_test_system(CONFIG) as sys:
        # The pets table comes from clickhouse/migrations, applied as the
        # system started.
        client = system.instance(sys, "clickhouse-migrator", "migrations")
        client.insert("pets", [[1, "Rex"], [2, "Tiddles"]], column_names=["id", "name"])
        rows = clickhouse.query(
            client, "SELECT name FROM pets WHERE id = {id:UInt32}", {"id": 2}
        )
        assert rows == [("Tiddles",)]
