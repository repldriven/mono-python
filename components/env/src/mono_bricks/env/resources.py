"""The resource path: where config names and `!include` names are looked up."""

import importlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

_NAMESPACE = __name__.split(".")[0]
_extra_roots: list[Path] = []


def add_resource_root(path: str | Path) -> None:
    """Add a directory to the resource path, after any added before it."""
    root = Path(path).resolve()
    if root not in _extra_roots:
        _extra_roots.append(root)


@contextmanager
def resource_root(path: str | Path) -> Iterator[None]:
    """Add `path` to the resource path for the duration of the block."""
    root = Path(path).resolve()
    added = root not in _extra_roots
    if added:
        _extra_roots.append(root)
    try:
        yield
    finally:
        if added:
            _extra_roots.remove(root)


def _brick_roots() -> list[Path]:
    # The namespace package spans one directory per brick in development and
    # a single site-packages directory when a project is installed; either way
    # a brick's resources sit beside its modules.
    namespace = importlib.import_module(_NAMESPACE)
    roots = []
    for base in namespace.__path__:
        for brick in sorted(Path(base).iterdir()):
            if (brick / "resources").is_dir():
                roots.append(brick / "resources")
    return roots


def resource_roots() -> list[Path]:
    """Every directory on the resource path, in lookup order."""
    return [*_extra_roots, *_brick_roots()]


def find_resource(name: str) -> Path:
    """The first file on the resource path matching `name`.

    A `resource:` prefix is accepted and ignored. It makes the lookup
    explicit: `config` tries the filesystem before the resource path, and a
    prefixed name has no filesystem reading, so it always comes from here.
    """
    return _find(name, Path.is_file)


def find_resource_dir(name: str) -> Path:
    """As `find_resource`, for a directory (of migrations, say)."""
    return _find(name, Path.is_dir)


def _find(name: str, matches: Callable[[Path], bool]) -> Path:
    name = name.removeprefix("resource:")
    roots = resource_roots()
    for root in roots:
        candidate = root / name
        if matches(candidate):
            return candidate
    searched = "\n  ".join(str(r) for r in roots) or "(no roots)"
    raise FileNotFoundError(f"Resource {name!r} not found on:\n  {searched}")
