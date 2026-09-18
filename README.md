# mono-python

Systems as data, on the [Polylith](https://davidvujic.github.io/python-polylith-docs/)
architecture. A Python port of the system-building core of
[repldriven/mono](https://github.com/repldriven/mono).

A system is a YAML file you can read, definitions you can print at the REPL,
and a lifecycle you start and stop.

## Components

```text
  brick                library                purpose
  --------------------------------------------------------------------------------
  env                  PyYAML                 Config loading, tags, default/test profiles
  log                  structlog              Structured logging via stdlib, JSON or console
  system               graphlib (stdlib)      Lifecycle management, systems as data
  test_system          -                      Systems under test
  testcontainers       testcontainers-python  Containers as components (generic, ClickHouse)
  clickhouse           clickhouse-connect     ClickHouse client component
  clickhouse_migrator  clickhouse-migrations  ClickHouse schema migrations, run at start
```

## Layout

The workspace uses the python-polylith `tdd` theme, so every brick keeps the
same shape:

```text
components/<brick>/
  src/mono_bricks/<brick>/     the brick's code; __init__.py is its interface
  test/mono_bricks/<brick>/    its tests
  test-resources/              YAML and other files put on the resource path in tests
```

The `test-resources` directories make up a shared resource path: the workspace
`conftest.py` adds each one to it, so `!include
testcontainers/clickhouse-test.yml` resolves however deep the including file
sits. A brick's production resources go in
`src/mono_bricks/<brick>/resources/` and are found without any setup.

## Getting started

```sh
just sync                   # uv sync
just test                   # starts containers; skips them without Docker
just test -m "not docker"   # leaves out tests marked as needing Docker
just check                  # ruff and poly check
just repl
```

## A system

```yaml
# components/clickhouse/test-resources/clickhouse/application-test.yml
system:
  clickhouse-server: !include testcontainers/clickhouse-test.yml
  clickhouse: !include clickhouse/client-test.yml

  clickhouse-migrator:
    migrations: !system/component
      system/component-kind: clickhouse-migrator/migrations
      client: !system/ref clickhouse.client
      migrations:
        - clickhouse/migrations
```

```python
# clickhouse_migrator and testcontainers are imported for the components
# they register; the system refers to them by kind, not by name.
from mono_bricks import (
    clickhouse,
    clickhouse_migrator,
    system,
    test_system,
    testcontainers,
)

with test_system.started("clickhouse/application-test.yml") as sys:
    client = system.instance(sys, "clickhouse-migrator", "migrations")
    clickhouse.query(client, "SELECT count() FROM pets")
```

Starting the system applies the `{VERSION}_{name}.sql` files in the
`clickhouse/migrations` resource directory that haven't been applied yet. The
migrations component's instance is the client it migrated with, so a
component that refs `clickhouse-migrator.migrations` instead of `clickhouse.client`
starts after the schema exists.

## Logging

Bricks log events with key-value context, and don't know it's structlog:

```python
from mono_bricks.log import get_logger

log = get_logger(__name__)
log.info("Connecting to clickhouse", host=host, port=port)
```

Events go through stdlib logging, as every library's records do, so one
`logging.config.dictConfig` YAML sets handlers and levels for both. Whatever
runs owns that config and applies it with `log.configure(resource, profile)`:
each project its own resource, the REPL and tests
`development/resources/log/logging-test.yml`. Its formatters come from the log
brick, rendering events and library records alike:

```yaml
formatters:
  json:
    "()": mono_bricks.log.json_formatter    # or mono_bricks.log.console_formatter
```

## Using the bricks from another workspace

The bricks ship as one distribution, `mono-bricks`, from `projects/bricks`.
There is no package index involved: consumers add it as a git dependency,
pinned to a release tag.

```sh
uv add "mono-bricks @ git+https://github.com/repldriven/mono-python#subdirectory=projects/bricks" --tag vX.Y.Z
uv add --dev "mono-bricks[test] @ git+https://github.com/repldriven/mono-python#subdirectory=projects/bricks" --tag vX.Y.Z
```

`uv.lock` pins the tag to the commit it names. The bricks import as
`mono_bricks`, the distribution's name spelled for Python (as
`clickhouse-connect` imports as `clickhouse_connect`):
`from mono_bricks import system`.

Test support (`test_system`, `testcontainers`) is in the same wheel, with its
libraries behind the `test` extra, so Docker and testcontainers stay out of a
consumer's runtime environment; importing `mono_bricks.testcontainers` there
fails.
The shared test config in `test-resources` doesn't ship: a consumer wires its
own systems.

To take an upstream fix, bump the tag. Published tags never move; cut a new
one instead.

## Adding a brick

```sh
just poly create component --name <brick>
```

Then add its `src` directory to `dev-mode-dirs` in `pyproject.toml` (hatch
doesn't expand globs there), run `just poly sync` and `just sync`. If the
brick ships, check `just poly info` shows it in `mono-bricks`, listing it in
`projects/bricks/pyproject.toml` if not, and keep that file's
dependencies in step with the workspace's (`just poly libs` compares them).
