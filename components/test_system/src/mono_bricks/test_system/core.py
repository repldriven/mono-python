from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from mono_bricks import env, system


@contextmanager
def started(
    config_file: str | Path,
    patch: Callable[[system.Defs], system.Defs] | None = None,
    component_ids: Iterable[str | system.ComponentId] | None = None,
    profile: str = "test",
) -> Iterator[system.System]:
    """Start the system in `config_file` for the block, then stop it.

    `patch` receives the definitions before start and returns them, for
    supplying what config can't express (a handler function, a fake).
    """
    defs = system.defs(env.config(config_file, profile))
    if patch is not None:
        defs = patch(defs)
    with system.started(defs, component_ids) as sys:
        yield sys
