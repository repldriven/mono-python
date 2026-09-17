import os
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from functools import cache
from pathlib import Path

from mono_bricks import env, system


def parse_permits(s: str | None) -> int | None:
    """A positive permit count from `s`, or None for no bound."""
    if s is None:
        return None
    try:
        n = int(s.strip())
    except ValueError:
        return None
    return n if n > 0 else None


@cache
def _permits() -> threading.BoundedSemaphore | None:
    n = parse_permits(os.environ.get("TEST_SYSTEM_PERMITS"))
    return threading.BoundedSemaphore(n) if n else None


@contextmanager
def with_permit(semaphore: threading.BoundedSemaphore | None) -> Iterator[None]:
    """Hold one of `semaphore`'s permits, or nothing when it's None."""
    if semaphore is None:
        yield
        return
    with semaphore:
        yield


@contextmanager
def with_test_system(
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
    with with_permit(_permits()), system.started(defs, component_ids) as sys:
        yield sys
