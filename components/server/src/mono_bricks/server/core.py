from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import msgspec
from litestar import Litestar, Request, Response
from litestar.di import Provide
from litestar.exceptions import (
    ClientException,
    MethodNotAllowedException,
    NotFoundException,
    SerializationException,
    ValidationException,
)
from litestar.openapi import OpenAPIConfig
from litestar.plugins.problem_details import (
    ProblemDetailsConfig,
    ProblemDetailsException,
    ProblemDetailsPlugin,
)
from litestar.types import ControllerRouterHandler, ExceptionHandler
from mono_bricks.log import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class AppCtx:
    """What the adapter hands the app function."""

    dependencies: Mapping[str, Any]
    """Name to started instance; a handler receives one by naming it."""
    ready_fn: Callable[[], bool]
    """Whether the service is ready to take traffic."""
    cors: Mapping[str, Any] | None
    """The adapter's `cors` config, or None."""


def problem(status: int, title: str, type: str, detail: str) -> ProblemDetailsException:
    """An RFC 9457 problem in mono's shape, rendered as
    `application/problem+json`: raise it, or answer with its `to_response`."""
    return ProblemDetailsException(
        status_code=status, title=title, type_=type, detail=detail
    )


def _answer(
    request: Request, status: int, title: str, type: str, detail: str
) -> Response:
    return problem(status, title, type, detail).to_response(request)


def _bad_request(request: Request, exc: ValidationException) -> Response:
    extra = exc.extra if isinstance(exc.extra, list) else []
    fields = [
        f"{e['key']}: {e.get('message', '')}"
        for e in extra
        if isinstance(e, Mapping) and "key" in e
    ]
    detail = "; ".join(fields) or exc.detail
    return _answer(request, 400, "REJECTED", "mono/bad-request", detail)


def _client_error(request: Request, exc: ClientException) -> Response:
    # Litestar raises a body that does not parse as a ClientException caused
    # by the SerializationException.
    if isinstance(exc.__cause__, SerializationException):
        return _answer(request, 400, "REJECTED", "mono/malformed-body", exc.detail)
    # Any other client error is answered as the problem-details plugin
    # answers every HTTPException.
    return ProblemDetailsException(
        status_code=exc.status_code,
        title=exc.detail,
        extra=exc.extra,
        headers=exc.headers,
    ).to_response(request)


def _not_found(request: Request, exc: NotFoundException) -> Response:
    return _answer(request, 404, "NOT_FOUND", "server/not-found", exc.detail)


def _method_not_allowed(request: Request, exc: MethodNotAllowedException) -> Response:
    return _answer(
        request, 405, "METHOD_NOT_ALLOWED", "server/method-not-allowed", exc.detail
    )


def _serialization_error(request: Request, exc: SerializationException) -> Response:
    # Decoding fails on a body a handler reads itself; encoding on a return
    # value msgspec cannot serialise.
    if isinstance(exc.__cause__, msgspec.DecodeError):
        return _answer(request, 400, "REJECTED", "mono/malformed-body", exc.detail)
    return _answer(
        request,
        500,
        "FAILED",
        "mono/bad-response",
        "The response could not be serialised",
    )


def _internal_error(request: Request, exc: Exception) -> Response:
    log.error(
        "Unhandled exception",
        exc_info=exc,
        method=request.method,
        path=request.url.path,
    )
    return _answer(
        request, 500, "FAILED", "server/internal-error", "Internal Server Error"
    )


default_exception_handlers: dict[type[Exception], ExceptionHandler] = {
    ValidationException: _bad_request,
    ClientException: _client_error,
    NotFoundException: _not_found,
    MethodNotAllowedException: _method_not_allowed,
    SerializationException: _serialization_error,
    Exception: _internal_error,
}
"""Exception type to handler, each answering through `problem`. Litestar
picks the first key in the exception's MRO; only `Exception`'s logs."""


def _provide(value: Any) -> Provide:
    # Litestar reads a provider's parameters as request parameters, so the
    # provider takes none.
    def provide() -> Any:
        return value

    return Provide(provide, sync_to_thread=False)


def app(
    ctx: AppCtx,
    route_handlers: Sequence[ControllerRouterHandler],
    *,
    exception_handlers: Mapping[Any, Any] | None = None,
    openapi_config: OpenAPIConfig | None = None,
    **litestar_kwargs: Any,
) -> Litestar:
    """The standard `Litestar` over `route_handlers`.

    Each of `ctx.dependencies` is a dependency on the application layer;
    every failure is answered as a problem-details body, through
    `default_exception_handlers` with `exception_handlers` merged over them
    by key; and Litestar configures no logging of its own. `dependencies` and
    `plugins` are added to the brick's; any other keyword reaches `Litestar`
    as given.
    """
    kwargs = dict(litestar_kwargs)
    dependencies: dict[str, Any] = {
        name: _provide(value) for name, value in ctx.dependencies.items()
    }
    dependencies.update(kwargs.pop("dependencies", None) or {})
    plugins = [
        ProblemDetailsPlugin(ProblemDetailsConfig(enable_for_all_http_exceptions=True)),
        *(kwargs.pop("plugins", None) or []),
    ]
    if openapi_config is not None:
        kwargs["openapi_config"] = openapi_config
    return Litestar(
        route_handlers=list(route_handlers),
        dependencies=dependencies,
        plugins=plugins,
        exception_handlers={**default_exception_handlers, **(exception_handlers or {})},
        logging_config=None,
        **kwargs,
    )
