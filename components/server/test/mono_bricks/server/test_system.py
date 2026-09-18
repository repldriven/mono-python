import json
import logging
import re
import socket
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from email.message import Message
from typing import Any
from urllib.parse import urlsplit

import pytest
from litestar import Litestar, get, post
from litestar.di import NamedDependency
from litestar.exceptions import NotAuthorizedException
from mono_bricks import log, server, system
from mono_bricks.test_system import with_test_system

CONFIG = "server/application-test.yml"


@dataclass
class Pet:
    name: str
    age: int


@get("/got", sync_to_thread=True)
def read_dependencies(
    got: NamedDependency[str], this: NamedDependency[str]
) -> dict[str, str]:
    return {"got": got, "this": this}


@post("/pets", status_code=200, sync_to_thread=True)
def create_pet(data: Pet) -> Pet:
    return data


@get("/bad-response", sync_to_thread=True)
def bad_response() -> dict[str, str]:
    return object()  # type: ignore[return-value]


@get("/boom", sync_to_thread=True)
def boom() -> None:
    raise RuntimeError("boom")


@get("/unauthorized", sync_to_thread=True)
def unauthorized() -> None:
    raise NotAuthorizedException()


def _app(ctx: server.AppCtx) -> Litestar:
    return server.app(
        ctx,
        route_handlers=[
            read_dependencies,
            create_pet,
            bad_response,
            boom,
            unauthorized,
        ],
    )


@contextmanager
def _test_system(
    app: Callable[[server.AppCtx], Any] = _app,
) -> Iterator[system.System]:
    def patch(defs: system.Defs) -> system.Defs:
        defs["server"]["app"] = system.constant(app)
        return defs

    with with_test_system(CONFIG, patch) as sys:
        yield sys


@pytest.fixture(scope="module")
def url() -> Iterator[str]:
    with _test_system() as sys:
        yield system.instance(sys, "server", "http-url")


@dataclass
class Reply:
    status: int
    headers: Message
    body: Any


def _request(method: str, url: str, body: bytes | None = None) -> Reply:
    headers = {} if body is None else {"Content-Type": "application/json"}
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return Reply(response.status, response.headers, json.loads(response.read()))
    except urllib.error.HTTPError as e:
        with e:
            return Reply(e.code, e.headers, json.loads(e.read()))


def _assert_problem(reply: Reply, status: int, title: str, type_: str) -> None:
    assert reply.status == status
    assert reply.headers.get_content_type() == "application/problem+json"
    assert reply.body["status"] == status
    assert reply.body["title"] == title
    assert reply.body["type"] == type_


def _errors(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


def _events(caplog: pytest.LogCaptureFixture, logger: str) -> list[dict[str, Any]]:
    return [
        r.msg
        for r in caplog.records
        if r.name == logger and r.levelno == logging.INFO and isinstance(r.msg, dict)
    ]


def _access_lines(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [e for e in _events(caplog, "mono_bricks.server.adapter") if "status" in e]


# ---- lifecycle -------------------------------------------------------------


def test_binds_port_0_exclusively_and_releases_it_on_stop():
    with _test_system() as sys:
        adapter = system.instance(sys, "server", "uvicorn-adapter")
        url = system.instance(sys, "server", "http-url")
        assert system.config(sys, "server", "uvicorn-adapter")["options"]["port"] == 0
        sock = adapter.socket
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
        parts = urlsplit(url)
        assert parts.port > 0
        assert _request("GET", f"{url}/got").status == 200

    assert not adapter.thread.is_alive()
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection((parts.hostname, parts.port), timeout=1).close()


def test_a_started_adapter_logs_listening_on_its_url(caplog):
    with _test_system() as sys:
        url = system.instance(sys, "server", "http-url")

    events = [e["event"] for e in _events(caplog, "mono_bricks.server.adapter")]
    assert f"Listening on {url}" in events


def test_an_app_that_raises_fails_start_naming_the_adapter():
    def broken(ctx: server.AppCtx) -> Litestar:
        raise RuntimeError("no app")

    with pytest.raises(system.StartError) as e:
        with _test_system(broken):
            pass
    assert e.value.component_id == ("server", "uvicorn-adapter")
    assert isinstance(e.value.cause, RuntimeError)


def test_an_app_whose_startup_fails_fails_start_naming_the_adapter():
    def fail() -> None:
        raise RuntimeError("startup failed")

    def failing(ctx: server.AppCtx) -> Litestar:
        return server.app(ctx, route_handlers=[read_dependencies], on_startup=[fail])

    with pytest.raises(system.StartError) as e:
        with _test_system(failing):
            pass
    assert e.value.component_id == ("server", "uvicorn-adapter")
    assert str(e.value.cause) == "uvicorn did not start"
    assert isinstance(e.value.cause.__cause__, SystemExit)


# ---- dependencies and bodies -----------------------------------------------


def test_a_dependency_reaches_the_handler_that_names_it(url):
    reply = _request("GET", f"{url}/got")
    assert reply.status == 200
    assert reply.body == {"got": "me", "this": "time"}


def test_a_valid_body_is_200(url):
    reply = _request("POST", f"{url}/pets", b'{"name": "Rex", "age": 3}')
    assert reply.status == 200
    assert reply.body == {"name": "Rex", "age": 3}


# ---- error bodies ----------------------------------------------------------


def test_an_invalid_body_is_400_bad_request_naming_the_field(url, caplog):
    reply = _request("POST", f"{url}/pets", b'{"name": "Rex", "age": "old"}')
    _assert_problem(reply, 400, "REJECTED", "mono/bad-request")
    assert "age" in reply.body["detail"]
    assert _errors(caplog) == []


def test_a_body_that_is_not_json_is_400_malformed_body(url, caplog):
    reply = _request("POST", f"{url}/pets", b"{not json")
    _assert_problem(reply, 400, "REJECTED", "mono/malformed-body")
    assert reply.body["detail"]
    assert _errors(caplog) == []


def test_an_unknown_path_is_404_not_found(url, caplog):
    reply = _request("GET", f"{url}/nope")
    _assert_problem(reply, 404, "NOT_FOUND", "server/not-found")
    assert _errors(caplog) == []


def test_a_wrong_method_is_405_method_not_allowed(url, caplog):
    reply = _request("DELETE", f"{url}/got")
    _assert_problem(reply, 405, "METHOD_NOT_ALLOWED", "server/method-not-allowed")
    assert _errors(caplog) == []


def test_any_other_client_error_is_a_problem_with_its_own_status(url, caplog):
    reply = _request("GET", f"{url}/unauthorized")
    assert reply.status == 401
    assert reply.headers.get_content_type() == "application/problem+json"
    assert reply.body["status"] == 401
    assert reply.body["title"] == "Unauthorized"
    assert "type" not in reply.body
    assert _errors(caplog) == []


def test_a_return_value_that_cannot_be_serialised_is_500_bad_response(url):
    reply = _request("GET", f"{url}/bad-response")
    _assert_problem(reply, 500, "FAILED", "mono/bad-response")


def test_a_handler_that_raises_is_500_internal_error_logged_once(url, caplog):
    reply = _request("GET", f"{url}/boom")
    _assert_problem(reply, 500, "FAILED", "server/internal-error")
    assert reply.body["detail"] == "Internal Server Error"

    (record,) = _errors(caplog)
    assert record.name == "mono_bricks.server.core"
    assert record.msg["method"] == "GET"
    assert record.msg["path"] == "/boom"
    assert isinstance(record.msg["exc_info"], RuntimeError)
    assert "Traceback" in log.console_formatter().format(record)


# ---- request log -----------------------------------------------------------


def test_a_request_logs_one_access_line(url, caplog):
    _request("GET", f"{url}/got")
    (line,) = _access_lines(caplog)
    assert re.fullmatch(r"GET /got 200 \d+\.\dms", line["event"])
    assert line["method"] == "GET"
    assert line["path"] == "/got"
    assert line["status"] == 200
    assert line["ms"] >= 0


def test_a_request_the_router_refuses_logs_its_line(url, caplog):
    _request("GET", f"{url}/nope")
    (line,) = _access_lines(caplog)
    assert re.fullmatch(r"GET /nope 404 \d+\.\dms", line["event"])
    assert line["status"] == 404
