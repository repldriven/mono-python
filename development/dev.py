"""REPL helpers for the development environment.

`just repl` runs this file with `python -i`, so its helpers and the bricks
it imports are in the REPL namespace already:

$ just repl
>>> go("clickhouse/application-test.yml", "test")
>>> client = instance("clickhouse", "client")
>>> clickhouse.query(client, "SELECT version()")
>>> halt()
"""

from pathlib import Path
from typing import Any

from mono_bricks import (  # noqa: F401  (for the REPL; registers components)
    clickhouse,
    clickhouse_migrator,
    env,
    log,
    system,
    testcontainers,
)

ROOT = Path(__file__).resolve().parents[1]

for resources in sorted(ROOT.glob("*/*/test-resources")):
    env.add_resource_root(resources)
env.add_resource_root(ROOT / "development" / "resources")

log.configure("log/logging-test.yml")

current: system.System | None = None


def go(config_file: str, profile: str = "default", component_ids=None) -> system.System:
    """Start the system in `config_file`, stopping any already running."""
    global current
    halt()
    current = system.start(system.defs(env.config(config_file, profile)), component_ids)
    return current


def halt() -> None:
    """Stop the running system, if there is one."""
    global current
    if current is not None:
        system.stop(current)
        current = None


def instance(group: str, name: str, *path: str) -> Any:
    if current is None:
        raise RuntimeError("No system running; call go(...) first")
    return system.instance(current, group, name, *path)
