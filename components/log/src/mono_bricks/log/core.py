import logging
import logging.config
from pathlib import Path
from typing import Any, Protocol

import structlog
from mono_bricks import env
from structlog.stdlib import ProcessorFormatter

# Run on structlog events as they're logged, and on records from stdlib
# loggers (libraries) as they're formatted, so both render the same.
_shared_processors: list[Any] = [
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]

# Events always go to stdlib logging, which owns handlers and levels. Without
# a `configure` they reach stdlib's last-resort handler, as a library's would.
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        *_shared_processors,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


class Logger(Protocol):
    """Logs an event, with %-style args and key-value context."""

    def debug(self, event: str | None = None, *args: Any, **kw: Any) -> Any: ...

    def info(self, event: str | None = None, *args: Any, **kw: Any) -> Any: ...

    def warning(self, event: str | None = None, *args: Any, **kw: Any) -> Any: ...

    def error(self, event: str | None = None, *args: Any, **kw: Any) -> Any: ...

    def exception(self, event: str | None = None, *args: Any, **kw: Any) -> Any: ...

    def bind(self, **kw: Any) -> Logger: ...


def get_logger(name: str) -> Logger:
    """The logger for `name`, usually a module's `__name__`."""
    return structlog.stdlib.get_logger(name)


def json_formatter() -> logging.Formatter:
    """One JSON object per line, with event, level, logger and timestamp."""
    return ProcessorFormatter(
        foreign_pre_chain=_shared_processors,
        processors=[
            ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )


def console_formatter(colors: bool = False) -> logging.Formatter:
    """Readable lines, for the REPL and test output."""
    return ProcessorFormatter(
        foreign_pre_chain=_shared_processors,
        processors=[
            ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=colors),
        ],
    )


def configure(source: str | Path, profile: str = "default") -> None:
    """Configure logging from a `logging.config.dictConfig` YAML file or
    resource, resolved for `profile`."""
    config = env.config(source, profile)
    # Loggers are created as modules import; disabling them would silence
    # every brick imported before this call.
    config.setdefault("disable_existing_loggers", False)
    logging.config.dictConfig(config)
    logging.captureWarnings(True)
