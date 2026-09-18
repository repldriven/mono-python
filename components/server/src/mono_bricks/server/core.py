import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import msgspec
from litestar import Litestar, Request, Response, get
from litestar.config.cors import CORSConfig
from litestar.di import Provide
from litestar.exceptions import (
    ClientException,
    MethodNotAllowedException,
    NotFoundException,
    SerializationException,
    ValidationException,
)
from litestar.handlers import HTTPRouteHandler
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import ScalarRenderPlugin
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


def health_routes(ready_fn: Callable[[], bool]) -> list[HTTPRouteHandler]:
    """mono's actuator handlers, left out of the OpenAPI document:

    - `/actuator/health/liveness`: 200 `UP`, without calling `ready_fn`.
    - `/actuator/health/readiness`: 200 `UP` or 503 `DOWN` by `ready_fn()`.
    - `/actuator/health`: readiness's status, with both under `components`.

    Readiness and the aggregate call `ready_fn` once per request, in the
    thread pool; liveness answers on the event loop.
    """

    def readiness_status() -> tuple[str, int]:
        return ("UP", 200) if ready_fn() else ("DOWN", 503)

    @get("/actuator/health/liveness", include_in_schema=False, sync_to_thread=False)
    def liveness() -> dict[str, str]:
        return {"status": "UP"}

    @get("/actuator/health/readiness", include_in_schema=False, sync_to_thread=True)
    def readiness() -> Response[dict[str, str]]:
        status, code = readiness_status()
        return Response({"status": status}, status_code=code)

    @get("/actuator/health", include_in_schema=False, sync_to_thread=True)
    def health() -> Response[dict[str, Any]]:
        status, code = readiness_status()
        components = {"liveness": {"status": "UP"}, "readiness": {"status": status}}
        return Response({"status": status, "components": components}, status_code=code)

    return [liveness, readiness, health]


_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9_-]{16,255}")


async def require_idempotency_key(request: Request) -> str:
    """The request's `Idempotency-Key` header, once it is 16 to 255 URL-safe
    ASCII characters; otherwise a 400 `REJECTED` problem, and the handler does
    not run.

    A route declares it as
    `dependencies={"idempotency_key": Provide(require_idempotency_key)}` and
    its handler names `idempotency_key: NamedDependency[str]`. It is `async`
    and blocks on nothing, so Litestar calls it on the event loop.
    """
    key = request.headers.get("idempotency-key")
    if key is None:
        raise problem(
            400,
            "REJECTED",
            "mono/missing-idempotency-key",
            "Missing Idempotency-Key header",
        )
    if not _IDEMPOTENCY_KEY.fullmatch(key):
        raise problem(
            400,
            "REJECTED",
            "mono/invalid-idempotency-key",
            "Idempotency-Key must be 16-255 URL-safe ASCII chars",
        )
    return key


# mono's cors.clj defaults, in place of CORSConfig's "*" and 600.
_CORS_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
_CORS_HEADERS = ("Accept", "Authorization", "Content-Type")
_CORS_MAX_AGE = 3600


def _cors_config(cors: Mapping[str, Any] | None) -> CORSConfig | None:
    # As cors.clj: origins are one string or many, with blanks dropped; a key
    # that is absent takes its default, and an empty list is kept.
    if cors is None:
        return None
    origins = cors.get("origins")
    if isinstance(origins, str):
        origins = [origins]
    allow_origins = [o for o in origins or [] if isinstance(o, str) and o.strip()]
    if not allow_origins:
        return None

    def given(key: str, default: Any) -> Any:
        value = cors.get(key)
        return default if value is None else value

    return CORSConfig(
        allow_origins=allow_origins,
        allow_methods=list(given("methods", _CORS_METHODS)),
        allow_headers=list(given("request_headers", _CORS_HEADERS)),
        max_age=given("max_age", _CORS_MAX_AGE),
        allow_credentials=bool(cors.get("credentials")),
    )


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
    by key; and Litestar configures no logging of its own. `health_routes`
    are served beside `route_handlers`, from `ctx.ready_fn`. `ctx.cors`
    becomes the `CORSConfig`, unless the caller passes `cors_config`, which is
    used as given. The OpenAPI document is at `/schema/openapi.json` and its
    Scalar page at `/schema`, unless the caller passes `openapi_config`.
    `dependencies` and `plugins` are added to the brick's; any other keyword
    reaches `Litestar` as given.
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
    kwargs["openapi_config"] = (
        openapi_config
        if openapi_config is not None
        else OpenAPIConfig(
            title="Litestar API",
            version="1.0.0",
            render_plugins=[ScalarRenderPlugin()],
        )
    )
    if "cors_config" not in kwargs:
        kwargs["cors_config"] = _cors_config(ctx.cors)
    return Litestar(
        route_handlers=[*route_handlers, *health_routes(ctx.ready_fn)],
        dependencies=dependencies,
        plugins=plugins,
        exception_handlers={**default_exception_handlers, **(exception_handlers or {})},
        logging_config=None,
        **kwargs,
    )
