"""Containers as system components, on testcontainers-python.

Importing this brick registers:

- `testcontainers/container`, `container-mapped-ports`,
  `container-mapped-exposed-port`, `container-host` and `container-uri`, for
  any image;
- `clickhouse/container`, with `container-mapped-exposed-port`,
  `container-host` and `container-uri` alongside it.

A started container is a `Started`: the container, the host to reach it on
and its mapped ports. The smaller components read one value out of it, so
other components can ref a port or URL rather than the container.
"""

from mono_bricks import system
from mono_bricks.testcontainers.components import clickhouse, generic
from mono_bricks.testcontainers.container import Started

system.register_components(
    "testcontainers",
    {
        "container": generic.container,
        "container-mapped-ports": generic.mapped_ports,
        "container-mapped-exposed-port": generic.mapped_exposed_port,
        "container-host": generic.host,
        "container-uri": generic.uri,
    },
)

system.register_components(
    "clickhouse",
    {
        "container": clickhouse.container,
        "container-mapped-exposed-port": generic.mapped_exposed_port,
        "container-host": generic.host,
        "container-uri": generic.uri,
    },
)

__all__ = ["Started"]
