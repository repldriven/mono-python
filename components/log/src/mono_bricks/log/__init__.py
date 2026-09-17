"""Structured logging, on structlog and stdlib logging.

Bricks log through `get_logger`, with an event and key-value context:

    log = get_logger(__name__)
    log.info("Connecting to clickhouse", host=host, port=port)

Events go to stdlib logging, as every library's records do, so one config
sets handlers and levels for both. That config is a `logging.config.dictConfig`
YAML resource, applied with `configure`; it names this brick's formatters to
render events and library records alike, as JSON or as readable lines:

    formatters:
      json:
        "()": mono_bricks.log.json_formatter

Logging config belongs to whatever runs: a project, the REPL, the tests.
"""

from mono_bricks.log.core import (
    Logger,
    configure,
    console_formatter,
    get_logger,
    json_formatter,
)

__all__ = [
    "Logger",
    "configure",
    "console_formatter",
    "get_logger",
    "json_formatter",
]
