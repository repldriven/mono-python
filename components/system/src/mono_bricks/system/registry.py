"""Component kinds, registered by the bricks that implement them."""

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mono_bricks.system.core import Component

_components: dict[str, Component] = {}


def register_components(namespace: str, components: Mapping[str, Component]) -> None:
    """Register each component as kind "<namespace>/<name>".

    Registering a kind again replaces it, so a reloaded module takes effect.
    """
    for name, component in components.items():
        _components[f"{namespace}/{name}"] = component


def lookup(kind: str) -> Component:
    from mono_bricks.system.core import DefinitionError

    try:
        return _components[kind]
    except KeyError:
        known = ", ".join(sorted(_components)) or "none"
        raise DefinitionError(
            f"Unknown component kind {kind!r}. Is the brick that registers it "
            f"imported? Known kinds: {known}"
        ) from None
