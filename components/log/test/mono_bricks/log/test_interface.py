import json
import logging
from pathlib import Path

from mono_bricks import env, log


def write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def config(formatter: str = "json", app_level: str = "INFO") -> str:
    # Shaped like a project's config, but on loggers of its own so the
    # workspace's logging is left alone.
    return f"""
version: 1
formatters:
  out:
    "()": mono_bricks.log.{formatter}_formatter
handlers:
  out:
    class: logging.StreamHandler
    stream: ext://sys.stdout
    formatter: out
loggers:
  logtest:
    level: {app_level}
    handlers: [out]
    propagate: false
  logtest.lib:
    level: WARNING
"""


def lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_events_render_as_json_with_context(tmp_path, capsys):
    log.configure(write(tmp_path, "logging.yml", config()))
    log.get_logger("logtest.app").info("Connecting", host="localhost", port=8123)
    [line] = lines(capsys)
    assert line.pop("timestamp").endswith("Z")
    assert line == {
        "event": "Connecting",
        "level": "info",
        "logger": "logtest.app",
        "host": "localhost",
        "port": 8123,
    }


def test_library_records_render_as_events_do(tmp_path, capsys):
    log.configure(write(tmp_path, "logging.yml", config()))
    logging.getLogger("logtest.lib").warning("Pulled %s", "image")
    [line] = lines(capsys)
    assert "timestamp" in line
    assert (line["event"], line["level"], line["logger"]) == (
        "Pulled image",
        "warning",
        "logtest.lib",
    )


def test_percent_style_args_render(tmp_path, capsys):
    log.configure(write(tmp_path, "logging.yml", config()))
    log.get_logger("logtest.app").info("Connecting to %s:%s", "localhost", 8123)
    [line] = lines(capsys)
    assert line["event"] == "Connecting to localhost:8123"


def test_levels_come_from_config(tmp_path, capsys):
    log.configure(write(tmp_path, "logging.yml", config()))
    log.get_logger("logtest.app").debug("dropped")
    logging.getLogger("logtest.lib").info("dropped")
    log.get_logger("logtest.lib").warning("kept")
    assert [line["event"] for line in lines(capsys)] == ["kept"]


def test_exceptions_render_their_traceback(tmp_path, capsys):
    log.configure(write(tmp_path, "logging.yml", config()))
    try:
        raise ValueError("bad value")
    except ValueError:
        log.get_logger("logtest.app").exception("Failed")
    [line] = lines(capsys)
    assert line["level"] == "error"
    assert "ValueError: bad value" in line["exception"]


def test_console_formatter_renders_readable_lines(tmp_path, capsys):
    log.configure(write(tmp_path, "logging.yml", config("console")))
    log.get_logger("logtest.app").info("Connecting", port=8123)
    out = capsys.readouterr().out
    assert "[info" in out
    assert "Connecting" in out
    assert "[logtest.app]" in out
    assert "port=8123" in out


def test_configure_finds_a_resource_and_resolves_its_profile(tmp_path, capsys):
    level = "!profile {default: INFO, test: ERROR}"
    write(tmp_path, "logtest/logging.yml", config(app_level=level))
    with env.resource_root(tmp_path):
        log.configure("logtest/logging.yml", "test")
    app = log.get_logger("logtest.app")
    app.info("dropped")
    app.error("kept")
    assert [line["event"] for line in lines(capsys)] == ["kept"]
