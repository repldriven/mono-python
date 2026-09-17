"""The `!system/*` YAML tags."""

from collections.abc import Mapping
from typing import Any

from mono_bricks import env
from mono_bricks.system.core import REQUIRED, ComponentDef, LocalRef, Ref

KIND_KEY = "system/component-kind"


def _component(value: Any, r: env.Resolver) -> ComponentDef:
    if not isinstance(value, Mapping) or KIND_KEY not in value:
        raise env.ConfigError(f"!system/component needs a {KIND_KEY} key: {value!r}")
    config = {k: v for k, v in value.items() if k != KIND_KEY}
    return ComponentDef(kind=str(r.resolve(value[KIND_KEY])), config=r.resolve(config))


def _path(value: Any) -> tuple[str, ...]:
    return tuple(str(value).split("."))


env.register_tag("!system/component", _component)
env.register_tag("!system/ref", lambda v, r: Ref(_path(v)))
env.register_tag("!system/local-ref", lambda v, r: LocalRef(_path(v)))
env.register_tag("!system/required-component", lambda v, r: REQUIRED)
