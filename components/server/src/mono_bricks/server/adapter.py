"""The listener: a socket the brick binds, served by uvicorn on a thread."""

import asyncio
import socket
import threading
import time
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

import uvicorn
from mono_bricks.log import get_logger

log = get_logger(__name__)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_BACKLOG = 2048  # uvicorn's default
_TIMEOUT = 10.0  # seconds to wait for uvicorn to start, and to stop
_WILDCARD_HOSTS = ("0.0.0.0", "::", "")


def bind(host: str, port: int) -> socket.socket:
    """A listening socket on `host` and `port`.

    On port 0 `SO_REUSEADDR` stays off, so the kernel never hands out a port
    another socket holds; on a fixed port it is set, so a restart reclaims the
    port from `TIME_WAIT`.
    """
    family, type_, proto, _, address = socket.getaddrinfo(
        host or None, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
    )[0]
    sock = socket.socket(family, type_, proto)
    try:
        if port != 0:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(address)
        sock.listen(_BACKLOG)
    except BaseException:
        sock.close()
        raise
    return sock


class RequestLog:
    """ASGI middleware logging one line per HTTP request, access-log shaped.

    It wraps the whole app, so a request the router answers 404 or 405 is
    logged too. The line is logged before the final body message is sent, so
    it exists by the time a client has read the response.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status: int | None = None
        logged = False

        def log_line() -> None:
            nonlocal logged
            logged = True
            method, path = scope["method"], scope["path"]
            code = 500 if status is None else status
            ms = round((time.perf_counter() - started) * 1000, 1)
            log.info(
                f"{method} {path} {code} {ms:.1f}ms",
                method=method,
                path=path,
                status=code,
                ms=ms,
            )

        async def send_logged(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            elif (
                message["type"] == "http.response.body"
                and not message.get("more_body", False)
                and not logged
            ):
                log_line()
            await send(message)

        try:
            await self.app(scope, receive, send_logged)
        finally:
            if not logged:
                log_line()


@dataclass
class Server:
    """A started adapter: the uvicorn server, its thread and its socket."""

    server: uvicorn.Server
    thread: threading.Thread
    socket: socket.socket


def serve(asgi_app: ASGIApp, options: Mapping[str, Any]) -> Server:
    """Bind `options`' host and port and serve `asgi_app` on a daemon thread.

    `options` is merged into `uvicorn.Config`. Returns once uvicorn is
    listening, or raises if it did not start.
    """
    host, port = options["host"], options["port"]
    log.info("Starting uvicorn", host=host, port=port)
    sock = bind(host, port)
    try:
        server = uvicorn.Server(
            uvicorn.Config(
                RequestLog(asgi_app), log_config=None, access_log=False, **options
            )
        )
    except BaseException:
        sock.close()
        raise

    failure: list[BaseException] = []

    def run() -> None:
        # Off the main thread uvicorn installs no signal handlers. A failed
        # startup ends serve with SystemExit, hence BaseException.
        try:
            asyncio.run(server.serve(sockets=[sock]))
        except BaseException as e:
            failure.append(e)

    thread = threading.Thread(target=run, name="uvicorn", daemon=True)
    thread.start()
    deadline = time.monotonic() + _TIMEOUT
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        thread.join(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(_TIMEOUT)
        sock.close()
        raise RuntimeError("uvicorn did not start") from (
            failure[0] if failure else None
        )

    started = Server(server, thread, sock)
    url = http_local_url(started)
    log.info("Listening on %s", url, url=url)
    return started


def shutdown(server: Server) -> None:
    """Stop serving, letting in-flight requests finish, and release the port."""
    server.server.should_exit = True
    server.thread.join(_TIMEOUT)
    server.socket.close()
    if server.thread.is_alive():
        raise RuntimeError(f"uvicorn did not stop within {_TIMEOUT:g}s")


def http_local_url(server: Server) -> str:
    """The URL of a started adapter, a wildcard host rendered as localhost."""
    host, port = server.socket.getsockname()[:2]
    if host in _WILDCARD_HOSTS:
        host = "localhost"
    elif ":" in host:
        host = f"[{host}]"
    return f"http://{host}:{port}"
