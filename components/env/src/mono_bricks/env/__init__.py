"""Configuration loading from YAML, resolved for a profile.

Loading happens in two phases. Parsing turns every `!tag` into a `Tagged`
value without interpreting it; resolution then walks the tree for one
profile, handing each tag's raw value to its reader. A reader decides what,
and whether, to resolve inside its value, so `!profile` only resolves the
branch it picks and `!or` stops at the first value that resolves.

Built-in tags: `!profile`, `!include`, `!env`, `!or`, `!join`, `!long`,
`!port`, `!keyword`, `!keywords`, `!str`, `!strs`, `!uuid`, `!random-uuid`
and `!concat`. Other bricks add their own with `register_tag`, as the system
brick does for `!system/*`.

Names given to `config` and `!include` are found on the resource path: every
brick's `resources` directory, plus any roots added with `add_resource_root`
(the workspace conftest adds each brick's `test-resources`).
"""

from mono_bricks.env.core import (
    ConfigError,
    Resolver,
    Tagged,
    TagReader,
    config,
    register_tag,
)
from mono_bricks.env.resources import (
    add_resource_root,
    find_resource,
    find_resource_dir,
    resource_root,
    resource_roots,
)

__all__ = [
    "ConfigError",
    "Resolver",
    "TagReader",
    "Tagged",
    "add_resource_root",
    "config",
    "find_resource",
    "find_resource_dir",
    "register_tag",
    "resource_root",
    "resource_roots",
]
