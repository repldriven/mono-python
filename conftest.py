"""Workspace-wide pytest setup.

Puts every brick's test-resources on the resource path, configures logging
from development's log/logging-test.yml, and skips tests marked `docker` when no
Docker daemon answers (unless CI is set, where a missing daemon should fail
loudly rather than skip quietly).
"""

import os
from functools import cache
from pathlib import Path

import pytest
from mono_bricks import env, log

ROOT = Path(__file__).parent

for resources in sorted(
    [*ROOT.glob("components/*/test-resources"), *ROOT.glob("bases/*/test-resources")]
):
    env.add_resource_root(resources)
env.add_resource_root(ROOT / "development" / "resources")

log.configure("log/logging-test.yml", "test")


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    # pytest reports captured logs with its own handlers; render them as the
    # REPL does, rather than as the raw event dicts structlog hands to logging.
    plugin = config.pluginmanager.get_plugin("logging-plugin")
    if plugin is None:
        return
    formatter = log.console_formatter()
    for handler in (
        plugin.caplog_handler,
        plugin.report_handler,
        plugin.log_cli_handler,
        plugin.log_file_handler,
    ):
        handler.setFormatter(formatter)


@cache
def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    if os.environ.get("CI"):
        return
    skip = pytest.mark.skip(reason="no Docker daemon available")
    for item in items:
        if "docker" in item.keywords and not _docker_available():
            item.add_marker(skip)
