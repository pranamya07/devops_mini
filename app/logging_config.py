"""Application logging: UTC timestamps, log levels, and errors on stderr.

Every log line looks like:
    2026-11-26T14:05:09.123Z | INFO     | app.requests | GET /api/v1/tasks 200 3.1ms ...

INFO and WARNING go to stdout, ERROR and CRITICAL go to stderr, so error logs
can be filtered separately (e.g. `docker compose logs api 2>&1 >/dev/null`).
"""

import logging
import logging.config
import time

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


class UTCFormatter(logging.Formatter):
    """ISO 8601 timestamps in UTC with milliseconds, e.g. 2026-11-26T14:05:09.123Z."""

    converter = time.gmtime

    def formatTime(self, record, datefmt=None):  # noqa: N802 (overrides logging API)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S", self.converter(record.created))
        return f"{stamp}.{int(record.msecs):03d}Z"


class BelowLevelFilter(logging.Filter):
    """Let through only records below a level (keeps errors out of stdout)."""

    def __init__(self, level: str):
        super().__init__()
        self.levelno = logging.getLevelName(level)

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < self.levelno


def build_logging_config(level: str = "INFO") -> dict:
    level = level.upper()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"below_error": {"()": BelowLevelFilter, "level": "ERROR"}},
        "formatters": {"standard": {"()": UTCFormatter, "format": LOG_FORMAT}},
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "standard",
                "filters": ["below_error"],
            },
            "stderr": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
                "formatter": "standard",
                "level": "ERROR",
            },
        },
        "root": {"level": level, "handlers": ["stdout", "stderr"]},
        "loggers": {
            # Send uvicorn's own messages through the same format.
            "uvicorn": {"level": level, "handlers": [], "propagate": True},
            "uvicorn.error": {"level": level, "handlers": [], "propagate": True},
            # The app logs every request itself (with timing and request ID).
            "uvicorn.access": {"level": "WARNING", "handlers": [], "propagate": False},
        },
    }


def setup_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(build_logging_config(level))
