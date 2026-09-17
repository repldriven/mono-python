from dataclasses import dataclass
from typing import TypedDict

import pytest
from mono_bricks import env, system
from pydantic import ValidationError


@dataclass
class FakeServer:
    name: str
    running: bool = True


def fake_kinds(events):
    def server_start(ctx):
        events.append(("start", ctx.id))
        return FakeServer(ctx.config["name"])

    def server_stop(ctx):
        events.append(("stop", ctx.id))
        ctx.instance.running = False

    def recording(start):
        def stop(ctx):
            events.append(("stop", ctx.id))

        def wrapped(ctx):
            events.append(("start", ctx.id))
            return start(ctx)

        return wrapped, stop

    port_start, port_stop = recording(lambda ctx: 5432)
    client_start, client_stop = recording(lambda ctx: dict(ctx.config))

    system.register_components(
        "test",
        {
            "server": system.Component(
                server_start, server_stop, config={"name": system.REQUIRED}
            ),
            "port": system.Component(
                port_start, port_stop, config={"server": system.REQUIRED}
            ),
            "client": system.Component(
                client_start,
                client_stop,
                config={"port": system.REQUIRED, "retries": {"count": 3, "backoff": 1}},
            ),
        },
    )


@pytest.fixture
def events():
    events = []
    fake_kinds(events)
    return events


def load_defs():
    return system.defs(env.config("system/application-test.yml", "test"))


def test_starts_in_dependency_order_and_stops_in_reverse(events):
    with system.started(load_defs()) as sys:
        starts = [cid for kind, cid in events if kind == "start"]
        assert starts.index(("db", "server")) < starts.index(("db", "port"))
        assert starts.index(("db", "port")) < starts.index(("app", "client"))
        server = system.instance(sys, "db", "server")
    stops = [cid for kind, cid in events if kind == "stop"]
    assert stops == list(reversed(starts))
    assert server.running is False


def test_refs_resolve_to_instances_and_into_them(events):
    with system.started(load_defs()) as sys:
        client = system.instance(sys, "app", "client")
        assert client["port"] == 5432
        assert client["server-name"] == "db"
        assert client["greeting"] == "hello"
        assert system.instance(sys, "app", "settings", "greeting") == "hello"


def test_defaults_deep_merge_with_config(events):
    client = system.ComponentDef("test/client", {"port": 1, "retries": {"count": 5}})
    defs = system.defs({"system": {"app": {"client": client}}})
    assert defs["app"]["client"].config["retries"] == {"count": 5, "backoff": 1}


def test_missing_required_config_fails_before_anything_starts(events):
    defs = system.defs(
        {
            "system": {
                "g": {
                    "server": system.ComponentDef("test/server", {"name": "a"}),
                    "port": system.ComponentDef("test/port", {}),
                }
            }
        }
    )
    with pytest.raises(system.DefinitionError, match=r"g\.port: server"):
        system.start(defs)
    assert events == []


def test_unknown_kind_and_dangling_ref(events):
    with pytest.raises(system.DefinitionError, match="Unknown component kind"):
        system.defs({"system": {"g": {"c": system.ComponentDef("nope/nope", {})}}})
    defs = system.defs(
        {
            "system": {
                "g": {
                    "p": system.ComponentDef(
                        "test/port", {"server": system.LocalRef(("missing",))}
                    )
                }
            }
        }
    )
    with pytest.raises(system.DefinitionError, match="g.missing, which isn't defined"):
        system.start(defs)


def test_cycle_is_a_definition_error(events):
    defs = system.defs(
        {"system": {"g": {"a": system.Ref(("g", "b")), "b": system.Ref(("g", "a"))}}}
    )
    with pytest.raises(system.DefinitionError, match="cycle"):
        system.start(defs)


def test_failed_start_stops_what_started_in_reverse(events):
    def boom(ctx):
        raise RuntimeError("no")

    defs = load_defs()
    defs["app"]["client"] = system.Component(
        boom, config={"port": system.Ref(("db", "port"))}
    )
    with pytest.raises(system.StartError) as e:
        system.start(defs)
    assert e.value.component_id == ("app", "client")
    assert isinstance(e.value.cause, RuntimeError)
    assert events == [
        ("start", ("db", "server")),
        ("start", ("db", "port")),
        ("stop", ("db", "port")),
        ("stop", ("db", "server")),
    ]


def test_stop_attempts_every_component_and_reports_failures(events):
    def bad_stop(ctx):
        raise RuntimeError("stuck")

    defs = load_defs()
    port = defs["db"]["port"]
    defs["db"]["port"] = system.Component(port.start, bad_stop, port.config)
    sys = system.start(defs)
    with pytest.raises(system.StopError, match="db.port"):
        system.stop(sys)
    assert ("stop", ("db", "server")) in events


def test_subset_starts_dependencies_only(events):
    with system.started(load_defs(), [("db", "port")]) as sys:
        assert set(sys.instances) == {("db", "server"), ("db", "port")}
    with system.started(load_defs(), ["db"]) as sys:
        assert set(sys.instances) == {("db", "server"), ("db", "port")}


def test_config_schema_validates_resolved_config(events):
    class Config(TypedDict):
        port: int

    defs = load_defs()
    defs["app"]["client"] = system.Component(
        start=lambda ctx: ctx.config,
        config={"port": system.Ref(("db", "server"))},  # a FakeServer, not an int
        config_schema=Config,
    )
    with pytest.raises(system.StartError) as e:
        system.start(defs)
    assert isinstance(e.value.cause, ValidationError)


def test_config_schema_converts_config(events):
    class Config(TypedDict):
        port: int

    defs = load_defs()
    defs["app"]["client"] = system.Component(
        start=lambda ctx: ctx.config,
        config={"port": "8123"},
        config_schema=Config,
    )
    with system.started(defs) as sys:
        assert system.config(sys, "app", "client") == {"port": 8123}


def test_instance_schema_checks_the_started_instance(events):
    defs = load_defs()
    defs["app"]["client"] = system.Component(
        start=lambda ctx: "not a server", instance_schema=FakeServer
    )
    with pytest.raises(system.StartError, match="Expected FakeServer") as e:
        system.start(defs)
    assert isinstance(e.value.cause, TypeError)


def test_constant_and_repr(events):
    defs = load_defs()
    defs["app"]["settings"] = system.constant({"greeting": "hi"})
    with system.started(defs) as sys:
        assert system.is_system(sys)
        assert system.config(sys, "app", "client")["greeting"] == "hi"
        assert repr(sys).startswith("System(started=[")
