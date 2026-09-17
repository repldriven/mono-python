import uuid

import pytest
from mono_bricks import env


def write(tmp_path, name, text):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_profile_picks_branch_then_default():
    test = env.config("env/application-test.yml", "test")
    default = env.config("env/application-test.yml")
    assert isinstance(test["system"]["port"], int) and test["system"]["port"] > 0
    assert default["system"]["port"] == 80
    assert test["system"]["config"] == {"key": "value", "nested-key": {"key": "value"}}


def test_classpath_prefix_and_include():
    included = env.config("classpath:env/include-test.yml")["included"]
    assert included["system"]["port"] == 80


def test_profile_only_resolves_the_branch_it_picks(tmp_path):
    path = write(tmp_path, "c.yml", "x: !profile {default: 1, prod: !unknown-tag y}")
    assert env.config(path) == {"x": 1}


def test_env_or_long_join(tmp_path, monkeypatch):
    monkeypatch.setenv("MONO_TEST_PORT", "9000")
    monkeypatch.delenv("MONO_TEST_ABSENT", raising=False)
    path = write(
        tmp_path,
        "c.yml",
        """
        present: !long [!or [!env MONO_TEST_PORT, 8080]]
        absent: !long [!or [!env MONO_TEST_ABSENT, 8080]]
        joined: !join ["meta-", !env MONO_TEST_PORT]
        kw: !keyword [!or [!env MONO_TEST_ABSENT, starttls]]
        """,
    )
    assert env.config(path) == {
        "present": 9000,
        "absent": 8080,
        "joined": "meta-9000",
        "kw": "starttls",
    }


def test_uuids_and_concat(tmp_path):
    path = write(
        tmp_path,
        "c.yml",
        """
        literal: !uuid "0192d4e0-0000-7000-8000-000000000000"
        generated: !random-uuid ""
        items: !concat [[1, 2], [3]]
        '"quoted"': 1
        """,
    )
    c = env.config(path)
    assert c["literal"] == uuid.UUID("0192d4e0-0000-7000-8000-000000000000")
    assert c["generated"].version == 7
    assert c["items"] == [1, 2, 3]
    assert c["quoted"] == 1


def test_resource_root_scopes_lookup(tmp_path):
    write(tmp_path, "scoped/only-here.yml", "a: 1")
    with env.resource_root(tmp_path):
        assert env.config("scoped/only-here.yml") == {"a": 1}
    with pytest.raises(env.ConfigError, match="not found"):
        env.config("scoped/only-here.yml")


def test_find_resource_dir_finds_directories_only(tmp_path):
    write(tmp_path, "scoped/migrations/001_init.sql", "SELECT 1")
    with env.resource_root(tmp_path):
        assert env.find_resource_dir("scoped/migrations") == (
            tmp_path.resolve() / "scoped/migrations"
        )
        with pytest.raises(FileNotFoundError):
            env.find_resource_dir("scoped/migrations/001_init.sql")


def test_unknown_tag_names_the_tag(tmp_path):
    path = write(tmp_path, "c.yml", "a: !nope 1")
    with pytest.raises(env.ConfigError, match="!nope"):
        env.config(path)


def test_register_tag(tmp_path):
    env.register_tag("!upper", lambda v, r: str(r.resolve(v)).upper())
    path = write(tmp_path, "c.yml", "a: !upper shout")
    assert env.config(path) == {"a": "SHOUT"}
