"""Systems as data: components wired by config, started and stopped as one.

A component is a `Component`: a `start` function returning an instance, an
optional `stop`, default `config`, and optional schemas. Bricks register
theirs under a namespace with `register_components`, and YAML picks one by
kind:

    container: !system/component
      system/component-kind: clickhouse/container
      docker-image-name: clickhouse/clickhouse-server:25.8

`defs` turns the `system` block of resolved config into definitions, merging
each component's defaults with its YAML. `start` resolves `!system/ref` and
`!system/local-ref` to started instances, starting components in dependency
order; `stop` stops them in reverse. Anything that goes wrong surfaces as an
`Error` subclass naming the component.

Importing this brick registers the `!system/*` tags with env.
"""

from mono_bricks.system import reader as _reader  # noqa: F401  (registers tags)
from mono_bricks.system.core import (
    REQUIRED,
    Component,
    ComponentDef,
    ComponentId,
    Ctx,
    DefinitionError,
    Defs,
    Error,
    LocalRef,
    Ref,
    StartError,
    StopError,
    System,
    config,
    constant,
    defs,
    instance,
    is_system,
    start,
    started,
    stop,
)
from mono_bricks.system.registry import register_components

__all__ = [
    "REQUIRED",
    "Component",
    "ComponentDef",
    "ComponentId",
    "Ctx",
    "DefinitionError",
    "Defs",
    "Error",
    "LocalRef",
    "Ref",
    "StartError",
    "StopError",
    "System",
    "config",
    "constant",
    "defs",
    "instance",
    "is_system",
    "register_components",
    "start",
    "started",
    "stop",
]
