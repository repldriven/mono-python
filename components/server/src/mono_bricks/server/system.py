import threading
from typing import Any, TypedDict

from mono_bricks.server import adapter
from mono_bricks.server.core import AppCtx
from mono_bricks.system import REQUIRED, Component, Ctx


class AdapterConfig(TypedDict):
    app: Any
    dependencies: dict[str, Any] | None
    ready_fn: Any
    cors: Any
    options: dict[str, Any]


def _always_ready() -> bool:
    return True


def _start_adapter(ctx: Ctx) -> adapter.Server:
    c = ctx.config
    ready_fn = c["ready_fn"]
    if ready_fn is None:
        ready_fn = _always_ready
    elif isinstance(ready_fn, threading.Event):
        ready_fn = ready_fn.is_set
    app_ctx = AppCtx(
        dependencies=c["dependencies"] or {}, ready_fn=ready_fn, cors=c["cors"]
    )
    return adapter.serve(c["app"](app_ctx), c["options"])


def _stop_adapter(ctx: Ctx) -> None:
    adapter.shutdown(ctx.instance)


dependencies = Component(
    start=lambda ctx: dict(ctx.config),
    config={},
    instance_schema=dict,
)

uvicorn_adapter = Component(
    start=_start_adapter,
    stop=_stop_adapter,
    config={
        "app": REQUIRED,
        "dependencies": None,
        "ready_fn": None,
        "cors": None,
        "options": {"host": "0.0.0.0", "port": 0},
    },
    config_schema=AdapterConfig,
    instance_schema=adapter.Server,
)

http_url = Component(
    start=lambda ctx: adapter.http_local_url(ctx.config["uvicorn-adapter"]),
    config={"uvicorn-adapter": REQUIRED},
    instance_schema=str,
)
