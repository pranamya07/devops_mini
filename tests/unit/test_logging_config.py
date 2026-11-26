"""Unit tests for the log format and the stdout/stderr split.

Each check runs in a fresh Python process so it can't disturb pytest's own logging.
"""

import logging
import re
import subprocess
import sys

from app.logging_config import BelowLevelFilter, UTCFormatter, build_logging_config

LINE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z \| (INFO|WARNING|ERROR) +\| demo \| .+$"
)


def run_logging(level, *calls):
    script = "\n".join(
        [
            "import logging",
            "from app.logging_config import setup_logging",
            f"setup_logging({level!r})",
            "log = logging.getLogger('demo')",
            *calls,
        ]
    )
    return subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )


def test_info_goes_to_stdout_and_errors_to_stderr():
    result = run_logging("INFO", "log.info('task saved')", "log.error('database down')")

    assert "task saved" in result.stdout and "database down" not in result.stdout
    assert "database down" in result.stderr and "task saved" not in result.stderr


def test_lines_have_utc_timestamp_level_and_logger_name():
    result = run_logging("INFO", "log.warning('slow request')")

    [line] = result.stdout.splitlines()
    assert LINE.match(line), line
    assert line.endswith("| WARNING  | demo | slow request")


def test_log_level_setting_hides_lower_levels():
    result = run_logging("WARNING", "log.info('hidden')", "log.warning('shown')")

    assert "hidden" not in result.stdout
    assert "shown" in result.stdout


def test_utc_formatter_ends_with_z():
    record = logging.LogRecord("demo", logging.INFO, __file__, 1, "msg", None, None)
    record.created, record.msecs = 0.0, 5.0

    assert UTCFormatter().formatTime(record) == "1970-01-01T00:00:00.005Z"


def test_below_level_filter():
    keep_below_error = BelowLevelFilter("ERROR")

    def record(level):
        return logging.LogRecord("demo", level, __file__, 1, "msg", None, None)

    assert keep_below_error.filter(record(logging.WARNING))
    assert not keep_below_error.filter(record(logging.ERROR))


def test_uvicorn_access_log_is_replaced_by_app_request_log():
    config = build_logging_config("info")

    assert config["root"]["level"] == "INFO"
    assert config["loggers"]["uvicorn.access"]["propagate"] is False
