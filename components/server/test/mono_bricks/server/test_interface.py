import json
import logging
import threading
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from email.message import Message
from typing import Any

import pytest
from litestar import Litestar, get, post
from litestar.config.cors import CORSConfig
from litestar.di import NamedDependency, Provide
from mono_bricks import server, system
from mono_bricks.test_system import with_test_system

CONFIG = "server/application-test.yml"
ORIGIN = "http://localhost:3000"
LIVENESS = "/actuator/health/liveness"
READINESS = "/actuator/health/readiness"
HEALTH = "/actuator/health"
VALID_KEY = "abcdefgh_1234567"

_calls: Counter[str] = Counter()


@get("/got", sync_to_thread=True)
def read_dependencies(
    got: NamedDependency[str], this: NamedDependency[str]
) -> dict[str, str]:
    _calls["got"] += 1
    return {"got": got, "this": this}


@post(
    "/keyed",
    status_code=200,
    sync_to_thread=True,
    dependencies={"idempotency_key": Provide(server.require_idempotency_key)},
)
def keyed(idempotency_key: NamedDependency[str]) -> dict[str, str]:
    _calls["keyed"] += 1
    return {"key": idempotency_key}


def _app(ctx: server.AppCtx) -> Litestar:
    return server.app(ctx, route_handlers=[read_dependencies, keyed])


@contextmanager
def _system(
    app: Callable[[server.AppCtx], Any] = _app,
    *,
    cors: Mapping[str, Any] | None = None,
    ready: Any = None,
) -> Iterator[system.System]:
    def patch(defs: system.Defs) -> system.Defs:
        group = defs["server"]
        group["app"] = system.constant(app)
        adapter = group["uvicorn-adapter"]
        config = dict(adapter.config)
        if cors is not None:
            config["cors"] = cors
        if ready is not None:
            group["ready"] = system.constant(ready)
            config["ready_fn"] = system.LocalRef(("ready",))
        group["uvicorn-adapter"] = replace(adapter, config=config)
        return defs

    with with_test_system(CONFIG, patch) as sys:
        yield sys


def _url(sys: system.System) -> str:
    return system.instance(sys, "server", "http-url")


@pytest.fixture(scope="module")
def url() -> Iterator[str]:
    with _system() as sys:
        yield _url(sys)


@pytest.fixture(scope="module")
def cors_url() -> Iterator[str]:
    with _system(cors={"origins": [ORIGIN]}) as sys:
        yield _url(sys)


@dataclass
class Reply:
    status: int
    headers: Message
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


def _request(method: str, url: str, headers: Mapping[str, str] | None = None) -> Reply:
    request = urllib.request.Request(url, method=method, headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return Reply(response.status, response.headers, response.read())
    except urllib.error.HTTPError as e:
        with e:
            return Reply(e.code, e.headers, e.read())


def _assert_json(reply: Reply, status: int, body: Any) -> None:
    assert reply.status == status
    assert reply.headers.get_content_type() == "application/json"
    assert reply.json() == body


def _assert_problem(
    reply: Reply, status: int, title: str, type_: str, detail: str
) -> None:
    assert reply.status == status
    assert reply.headers.get_content_type() == "application/problem+json"
    body = reply.json()
    assert body["status"] == status
    assert body["title"] == title
    assert body["type"] == type_
    assert body["detail"] == detail


def _values(reply: Reply, header: str) -> set[str]:
    return {v.strip().lower() for v in reply.headers.get(header, "").split(",")}


def _errors(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno >= logging.ERROR]


def _health(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "components": {"liveness": {"status": "UP"}, "readiness": {"status": status}},
    }


# ---- health ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (LIVENESS, {"status": "UP"}),
        (READINESS, {"status": "UP"}),
        (HEALTH, _health("UP")),
    ],
)
def test_health_is_up_when_the_adapter_has_no_ready_fn(url, path, body):
    _assert_json(_request("GET", f"{url}{path}"), 200, body)


def test_readiness_follows_a_threading_event_passed_as_ready_fn():
    event = threading.Event()
    with _system(ready=event) as sys:
        url = _url(sys)
        _assert_json(_request("GET", f"{url}{READINESS}"), 503, {"status": "DOWN"})
        _assert_json(_request("GET", f"{url}{HEALTH}"), 503, _health("DOWN"))
        _assert_json(_request("GET", f"{url}{LIVENESS}"), 200, {"status": "UP"})

        event.set()
        _assert_json(_request("GET", f"{url}{READINESS}"), 200, {"status": "UP"})
        _assert_json(_request("GET", f"{url}{HEALTH}"), 200, _health("UP"))


def test_readiness_is_down_while_a_callable_ready_fn_returns_false():
    with _system(ready=lambda: False) as sys:
        url = _url(sys)
        _assert_json(_request("GET", f"{url}{READINESS}"), 503, {"status": "DOWN"})


# ---- idempotency key -------------------------------------------------------


def test_a_missing_idempotency_key_is_400_and_the_handler_does_not_run(url, caplog):
    before = _calls["keyed"]
    reply = _request("POST", f"{url}/keyed")
    _assert_problem(
        reply,
        400,
        "REJECTED",
        "mono/missing-idempotency-key",
        "Missing Idempotency-Key header",
    )
    assert _calls["keyed"] == before
    assert _errors(caplog) == []


@pytest.mark.parametrize("key", ["short-key", "abcdefgh.1234567", "", "a" * 256])
def test_a_malformed_idempotency_key_is_400_and_the_handler_does_not_run(
    url, caplog, key
):
    before = _calls["keyed"]
    reply = _request("POST", f"{url}/keyed", {"Idempotency-Key": key})
    _assert_problem(
        reply,
        400,
        "REJECTED",
        "mono/invalid-idempotency-key",
        "Idempotency-Key must be 16-255 URL-safe ASCII chars",
    )
    assert _calls["keyed"] == before
    assert _errors(caplog) == []


def test_a_valid_idempotency_key_reaches_the_handler(url, caplog):
    before = _calls["keyed"]
    reply = _request("POST", f"{url}/keyed", {"Idempotency-Key": VALID_KEY})
    _assert_json(reply, 200, {"key": VALID_KEY})
    assert _calls["keyed"] == before + 1
    assert _errors(caplog) == []


# ---- CORS over TCP ---------------------------------------------------------


def test_an_allowed_origin_is_echoed_with_vary_origin(cors_url):
    reply = _request("GET", f"{cors_url}/got", {"Origin": ORIGIN})
    assert reply.status == 200
    assert reply.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert "origin" in _values(reply, "Vary")


def test_an_unlisted_origin_gets_no_allow_origin(cors_url):
    reply = _request("GET", f"{cors_url}/got", {"Origin": "http://evil.example"})
    assert reply.status == 200
    assert "Access-Control-Allow-Origin" not in reply.headers


def test_a_request_without_an_origin_gets_no_cors_headers(cors_url):
    reply = _request("GET", f"{cors_url}/got")
    assert reply.status == 200
    assert [k for k in reply.headers if k.lower().startswith("access-control-")] == []


@pytest.mark.parametrize("path", ["/got", "/nope"])
def test_a_preflight_from_an_allowed_origin_is_204_on_any_path(cors_url, path):
    before = _calls["got"]
    reply = _request(
        "OPTIONS",
        f"{cors_url}{path}",
        {"Origin": ORIGIN, "Access-Control-Request-Method": "DELETE"},
    )
    assert reply.status == 204
    assert reply.body == b""
    assert reply.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert "delete" in _values(reply, "Access-Control-Allow-Methods")
    assert "authorization" in _values(reply, "Access-Control-Allow-Headers")
    assert reply.headers["Access-Control-Max-Age"] == "3600"
    assert _calls["got"] == before


def test_without_a_cors_block_an_origin_gets_no_allow_origin(url):
    reply = _request("GET", f"{url}/got", {"Origin": ORIGIN})
    assert reply.status == 200
    assert "Access-Control-Allow-Origin" not in reply.headers


# ---- CORS config -----------------------------------------------------------


def _cors_config(cors: Mapping[str, Any] | None, **kwargs: Any) -> CORSConfig | None:
    return server.app(server.AppCtx({}, lambda: True, cors), [], **kwargs).cors_config


@pytest.mark.parametrize(
    "cors",
    [None, {}, {"origins": ""}, {"origins": []}, {"origins": ["", " "]}],
)
def test_no_origin_gives_no_cors_config(cors):
    assert _cors_config(cors) is None


def test_a_bare_string_origin_takes_the_mono_defaults():
    config = _cors_config({"origins": ORIGIN})
    assert config.allow_origins == [ORIGIN]
    assert config.allow_methods == ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    assert [h.lower() for h in config.allow_headers] == [
        "accept",
        "authorization",
        "content-type",
    ]
    assert config.max_age == 3600
    assert config.allow_credentials is False


def test_each_cors_key_overrides_its_default():
    config = _cors_config(
        {
            "origins": [ORIGIN],
            "methods": ["GET"],
            "request_headers": ["X-Thing"],
            "max_age": 60,
            "credentials": True,
        }
    )
    assert config.allow_methods == ["GET"]
    assert [h.lower() for h in config.allow_headers] == ["x-thing"]
    assert config.max_age == 60
    assert config.allow_credentials is True


def test_a_cors_config_the_caller_passes_is_used_over_ctx_cors():
    own = CORSConfig(allow_origins=["http://a"])
    assert _cors_config({"origins": [ORIGIN]}, cors_config=own) is own
