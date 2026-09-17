"""Definitions, dependency ordering and the start/stop lifecycle."""

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from functools import cache
from graphlib import CycleError, TopologicalSorter
from typing import Any

from mono_bricks.log import get_logger
from mono_bricks.system import registry
from pydantic import TypeAdapter

log = get_logger(__name__)

ComponentId = tuple[str, str]


class _Required:
    def __repr__(self) -> str:
        return "REQUIRED"


REQUIRED: Any = _Required()
"""Marks config a component cannot start without."""


@dataclass(frozen=True)
class Ref:
    """Refers to a started instance: (group, component, *path into instance)."""

    path: tuple[str, ...]


@dataclass(frozen=True)
class LocalRef:
    """As `Ref`, but relative to the referring component's group."""

    path: tuple[str, ...]


@dataclass(frozen=True)
class ComponentDef:
    """A component as declared in config: its kind and config overrides."""

    kind: str
    config: Mapping[str, Any]


@dataclass(frozen=True)
class Ctx:
    """What a lifecycle function receives."""

    id: ComponentId
    config: Any
    instance: Any = None


@dataclass(frozen=True)
class Component:
    start: Callable[[Ctx], Any]
    stop: Callable[[Ctx], None] | None = None
    config: Any = field(default_factory=dict)
    config_schema: Any = None
    """A type the ref-resolved config is validated against, and converted
    to, before start: a TypedDict, dataclass or anything else pydantic
    validates. Hold instances from refs in `Any` fields."""
    instance_schema: type | None = None
    """The type the started instance must be."""


Defs = dict[str, dict[str, Component]]


class Error(Exception):
    """Base for system errors."""


class DefinitionError(Error):
    """The system's definitions are invalid; nothing was started."""


class StartError(Error):
    """A component failed to start. Those started before it were stopped."""

    def __init__(self, component_id: ComponentId, cause: BaseException) -> None:
        self.component_id = component_id
        self.cause = cause
        super().__init__(f"{_fmt(component_id)} failed to start: {cause!r}")


class StopError(Error):
    """One or more components failed to stop. All were attempted."""

    def __init__(self, failures: Sequence[tuple[ComponentId, BaseException]]) -> None:
        self.failures = list(failures)
        detail = "; ".join(f"{_fmt(cid)}: {e!r}" for cid, e in failures)
        super().__init__(f"System stop failed: {detail}")


@dataclass(frozen=True)
class System:
    defs: Defs
    order: tuple[ComponentId, ...]
    configs: Mapping[ComponentId, Any]
    instances: Mapping[ComponentId, Any]

    def __repr__(self) -> str:
        # Instances can be large; show the shape rather than the contents.
        started = ", ".join(_fmt(cid) for cid in self.order)
        return f"System(started=[{started}])"


# ---- definitions -----------------------------------------------------------


def defs(config: Mapping[str, Any], path: Sequence[str] = ("system",)) -> Defs:
    """Build definitions from resolved config, merging each kind's defaults."""
    node: Any = config
    for key in path:
        node = node[key]
    return {
        str(group): {str(name): _component(value) for name, value in comps.items()}
        for group, comps in node.items()
    }


def constant(value: Any) -> Component:
    """A component whose instance is `value`, with any refs in it resolved.

    Plain values in a system block become constants; a test patch can use
    this to supply what YAML can't, such as a function.
    """
    return Component(start=lambda ctx: ctx.config, config=value)


def _component(value: Any) -> Component:
    if isinstance(value, Component):
        return value
    if isinstance(value, ComponentDef):
        component = registry.lookup(value.kind)
        return replace(component, config=_deep_merge(component.config, value.config))
    return constant(value)


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, Mapping) and isinstance(override, Mapping):
        merged = dict(base)
        for k, v in override.items():
            merged[k] = _deep_merge(base[k], v) if k in base else v
        return merged
    return override


# ---- lifecycle -------------------------------------------------------------


def start(
    system_defs: Defs,
    component_ids: Iterable[str | ComponentId] | None = None,
) -> System:
    """Start the system, or only `component_ids` (groups or [group, name]
    pairs) and what they depend on. Returns the started `System`."""
    components = {
        (group, name): component
        for group, comps in system_defs.items()
        for name, component in comps.items()
    }
    graph = {
        cid: _dependencies(cid, c.config, components) for cid, c in components.items()
    }
    selected = (
        _select(component_ids, graph) if component_ids is not None else set(graph)
    )
    _check_required({cid: components[cid] for cid in selected})

    try:
        order = tuple(
            TopologicalSorter({cid: graph[cid] for cid in selected}).static_order()
        )
    except CycleError as e:
        cycle = " -> ".join(_fmt(cid) for cid in e.args[1])
        raise DefinitionError(f"Dependency cycle: {cycle}") from None

    configs: dict[ComponentId, Any] = {}
    instances: dict[ComponentId, Any] = {}
    for cid in order:
        component = components[cid]
        try:
            config = _resolve_refs(component.config, cid[0], instances)
            if component.config_schema is not None:
                config = _adapter(component.config_schema).validate_python(config)
            instance = component.start(Ctx(cid, config))
            if component.instance_schema is not None:
                _check_instance(instance, component.instance_schema)
        except Exception as e:
            log.error("Failed to start; stopping what started", component=_fmt(cid))
            started_so_far = System(system_defs, tuple(instances), configs, instances)
            try:
                stop(started_so_far)
            except StopError as stop_error:
                e.add_note(str(stop_error))
            raise StartError(cid, e) from e
        configs[cid] = config
        instances[cid] = instance
    return System(system_defs, order, configs, instances)


def stop(system: System) -> None:
    """Stop every started component, in reverse start order."""
    failures: list[tuple[ComponentId, BaseException]] = []
    for cid in reversed(system.order):
        component = system.defs[cid[0]][cid[1]]
        if component.stop is None:
            continue
        try:
            component.stop(Ctx(cid, system.configs[cid], system.instances[cid]))
        except Exception as e:
            failures.append((cid, e))
    if failures:
        raise StopError(failures)


@contextmanager
def started(
    system_defs: Defs,
    component_ids: Iterable[str | ComponentId] | None = None,
) -> Iterator[System]:
    """Start the system for the duration of the block."""
    system = start(system_defs, component_ids)
    try:
        yield system
    finally:
        stop(system)


def instance(system: System, group: str, name: str, *path: str) -> Any:
    """A started instance, or a value inside it."""
    return _walk(system.instances[(group, name)], path)


def config(system: System, group: str, name: str) -> Any:
    """The config a component was started with, refs resolved."""
    return system.configs[(group, name)]


def is_system(x: Any) -> bool:
    return isinstance(x, System)


# ---- helpers ---------------------------------------------------------------


@cache
def _adapter(schema: Any) -> TypeAdapter:
    return TypeAdapter(schema)


def _check_instance(instance: Any, schema: type) -> None:
    if not isinstance(instance, schema):
        raise TypeError(
            f"Expected {schema.__name__} instance, got {type(instance).__name__}"
        )


def _fmt(cid: ComponentId) -> str:
    return ".".join(cid)


def _target(ref: Ref | LocalRef, group: str) -> tuple[ComponentId, tuple[str, ...]]:
    path = ref.path if isinstance(ref, Ref) else (group, *ref.path)
    if len(path) < 2:
        raise DefinitionError(f"Ref {'.'.join(path)} needs a group and a component")
    return (path[0], path[1]), path[2:]


def _refs(x: Any) -> Iterator[Ref | LocalRef]:
    if isinstance(x, (Ref, LocalRef)):
        yield x
    elif isinstance(x, Mapping):
        for v in x.values():
            yield from _refs(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _refs(v)


def _dependencies(
    cid: ComponentId, config: Any, components: Mapping[ComponentId, Component]
) -> set[ComponentId]:
    deps = set()
    for ref in _refs(config):
        target, _ = _target(ref, cid[0])
        if target not in components:
            raise DefinitionError(
                f"{_fmt(cid)} refers to {_fmt(target)}, which isn't defined"
            )
        deps.add(target)
    return deps


def _select(
    ids: Iterable[str | ComponentId], graph: Mapping[ComponentId, set[ComponentId]]
) -> set[ComponentId]:
    pending: list[ComponentId] = []
    for i in ids:
        matches = [c for c in graph if c[0] == i] if isinstance(i, str) else [tuple(i)]
        if not matches or any(m not in graph for m in matches):
            raise DefinitionError(f"No component or group {i!r} to start")
        pending.extend(matches)  # type: ignore[arg-type]
    selected: set[ComponentId] = set()
    while pending:
        cid = pending.pop()
        if cid not in selected:
            selected.add(cid)
            pending.extend(graph[cid])
    return selected


def _check_required(components: Mapping[ComponentId, Component]) -> None:
    missing = []
    for cid, component in sorted(components.items()):
        for path in _required_paths(component.config, ()):
            missing.append(f"{_fmt(cid)}: {'.'.join(path) or '(config)'}")
    if missing:
        raise DefinitionError("Required config missing:\n  " + "\n  ".join(missing))


def _required_paths(x: Any, path: tuple[str, ...]) -> Iterator[tuple[str, ...]]:
    if x is REQUIRED:
        yield path
    elif isinstance(x, Mapping):
        for k, v in x.items():
            yield from _required_paths(v, (*path, str(k)))


def _resolve_refs(x: Any, group: str, instances: Mapping[ComponentId, Any]) -> Any:
    if isinstance(x, (Ref, LocalRef)):
        target, path = _target(x, group)
        return _walk(instances[target], path)
    if isinstance(x, Mapping):
        return {k: _resolve_refs(v, group, instances) for k, v in x.items()}
    if isinstance(x, list):
        return [_resolve_refs(v, group, instances) for v in x]
    return x


def _walk(value: Any, path: Sequence[str]) -> Any:
    for key in path:
        if isinstance(value, Mapping):
            if key in value:
                value = value[key]
            elif key.isdigit() and int(key) in value:
                value = value[int(key)]
            else:
                raise KeyError(key)
        else:
            value = getattr(value, key.replace("-", "_"))
    return value
