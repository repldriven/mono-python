"""YAML parsing, tag readers and profile resolution."""

import os
import socket
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from mono_bricks.env.resources import find_resource


class ConfigError(Exception):
    """Config could not be found, parsed or resolved."""


@dataclass(frozen=True)
class Tagged:
    """A tagged YAML value, as parsed and before resolution."""

    tag: str
    value: Any


class Resolver:
    """Resolves parsed config for one profile. Passed to every tag reader."""

    def __init__(self, profile: str) -> None:
        self.profile = profile

    def resolve(self, x: Any) -> Any:
        if isinstance(x, Mapping):
            return {_key(k): self.resolve(v) for k, v in x.items()}
        if isinstance(x, list):
            return [self.resolve(v) for v in x]
        if isinstance(x, Tagged):
            reader = _readers.get(x.tag)
            if reader is None:
                raise ConfigError(
                    f"No reader for tag {x.tag}. Is the brick that defines it imported?"
                )
            return reader(x.value, self)
        return x

    def load(self, name: str) -> Any:
        """Parse and resolve the resource `name` with this profile."""
        return self.resolve(_parse(find_resource(name)))


TagReader = Callable[[Any, Resolver], Any]
_readers: dict[str, TagReader] = {}


def register_tag(tag: str, reader: TagReader) -> None:
    """Register `reader` for `tag` (e.g. "!system/ref"), replacing any other."""
    _readers[tag] = reader


def config(source: str | Path, profile: str = "default") -> dict[str, Any]:
    """Load config from a file path or resource name, resolved for `profile`."""
    try:
        path = Path(source)
        if not path.is_file():
            path = find_resource(str(source))
        return Resolver(profile).resolve(_parse(path))
    except ConfigError:
        raise
    except Exception as e:
        raise ConfigError(f"Failed to load config {source!s}: {e}") from e


# ---- parsing ---------------------------------------------------------------


class _Loader(yaml.SafeLoader):
    pass


def _construct_tagged(loader: _Loader, suffix: str, node: yaml.Node) -> Tagged:
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        value = loader.construct_mapping(node, deep=True)
    return Tagged("!" + suffix, value)


_Loader.add_multi_constructor("!", _construct_tagged)


def _parse(path: Path) -> Any:
    with open(path) as f:
        return yaml.load(f, Loader=_Loader)


def _key(k: Any) -> Any:
    # Every key is a string already, so a key written '"name"' just has its
    # quotes dropped.
    if isinstance(k, str) and len(k) > 1 and k[0] == k[-1] == '"':
        return k[1:-1]
    return k


# ---- built-in tag readers --------------------------------------------------


def _unwrap(value: Any) -> Any:
    # `!long [!or [...]]`: a one-item sequence lets a tag wrap another tag.
    return value[0] if isinstance(value, list) else value


def _profile(value: Any, r: Resolver) -> Any:
    if not isinstance(value, Mapping):
        raise ConfigError(f"!profile needs a mapping, got {value!r}")
    if r.profile in value:
        return r.resolve(value[r.profile])
    return r.resolve(value.get("default"))


def _or(value: Any, r: Resolver) -> Any:
    for item in value:
        resolved = r.resolve(item)
        if resolved is not None:
            return resolved
    return None


def _long(value: Any, r: Resolver) -> int | None:
    resolved = r.resolve(_unwrap(value))
    return None if resolved is None else int(resolved)


def _port(value: Any, r: Resolver) -> int | None:
    port = _long(value, r)
    if port != 0:
        return port
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _join(value: Any, r: Resolver) -> str:
    return "".join("" if v is None else str(v) for v in r.resolve(value))


def _keyword(value: Any, r: Resolver) -> str | None:
    # Keywords and strings are one type in Python.
    resolved = r.resolve(_unwrap(value))
    return None if resolved is None else str(resolved)


register_tag("!profile", _profile)
register_tag("!include", lambda v, r: r.load(v))
register_tag("!env", lambda v, r: os.environ.get(str(r.resolve(v))))
register_tag("!or", _or)
register_tag("!join", _join)
register_tag("!long", _long)
register_tag("!port", _port)
register_tag("!keyword", _keyword)
register_tag("!keywords", lambda v, r: r.resolve(v))
register_tag("!str", lambda v, r: str(r.resolve(v)))
register_tag("!strs", lambda v, r: r.resolve(v))
register_tag("!uuid", lambda v, r: uuid.UUID(str(r.resolve(v))))
# Time-ordered.
register_tag("!random-uuid", lambda v, r: uuid.uuid7())
register_tag("!concat", lambda v, r: [i for seq in r.resolve(v) for i in seq])
