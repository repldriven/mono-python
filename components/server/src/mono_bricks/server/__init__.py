"""HTTP APIs as system components, on Litestar served by uvicorn.

Importing this brick registers `server/dependencies`, a mapping of name to
started instance; `server/uvicorn-adapter`, which calls the app function a base
supplies with an `AppCtx` and serves what it returns on a socket it binds, on a
thread; and `server/http-url`, the URL that adapter listens on. `app`
assembles the `Litestar` an app function returns, answering every failure as
an RFC 9457 problem-details body.

A handler receives an entry of `server/dependencies` by declaring its key as a
keyword argument, marked as Litestar's `NamedDependency`. The YAML names the
instance:

    dependencies: !system/component
      system/component-kind: server/dependencies
      store: !system/ref store.client

and the handler names the key:

    @get("/pets", sync_to_thread=True)
    def list_pets(store: NamedDependency[Store]) -> list[Pet]:
        return store.pets()
"""

from mono_bricks.server.adapter import http_local_url
from mono_bricks.server.core import AppCtx, app, default_exception_handlers, problem
from mono_bricks.server.system import dependencies, http_url, uvicorn_adapter

# Imported by name: once this brick's own system module is imported, `system`
# in this namespace is that module, not the system brick.
from mono_bricks.system import register_components

register_components(
    "server",
    {
        "dependencies": dependencies,
        "uvicorn-adapter": uvicorn_adapter,
        "http-url": http_url,
    },
)

__all__ = [
    "AppCtx",
    "app",
    "default_exception_handlers",
    "http_local_url",
    "problem",
]
