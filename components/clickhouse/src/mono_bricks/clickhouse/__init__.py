"""ClickHouse clients as system components, on clickhouse-connect.

Importing this brick registers `clickhouse/client`, an HTTP client for the
configured server. `query` and `command` are thin conveniences over it.
"""

from mono_bricks import system
from mono_bricks.clickhouse.core import Client, client, command, query

system.register_components("clickhouse", {"client": client})

__all__ = ["Client", "client", "command", "query"]
