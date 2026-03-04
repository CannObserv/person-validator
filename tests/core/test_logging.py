"""Tests for src.core.logging — shared JSON logging helper."""

import io
import json
import logging

import pytest

from src.core.logging import configure_logging, get_logger

_HANDLER_MARKER = "_pv_json_handler"


@pytest.fixture(autouse=True)
def _reset_root_logger():
    """Isolate root logger state for each test.

    Removes any handler carrying the ``_pv_json_handler`` marker before the
    test runs (so configure_logging() isn't blocked by the idempotency guard
    from a previous test or from Django's logging setup), then fully restores
    the original handler list and level afterwards.
    """
    root = logging.getLogger()
    original_level = root.level
    original_handlers = root.handlers[:]
    # Strip our marker handler so each test starts clean.
    root.handlers = [h for h in root.handlers if not getattr(h, _HANDLER_MARKER, False)]
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)


class TestGetLogger:
    """Tests for the get_logger() convenience function."""

    def test_returns_logger_instance(self):
        """get_logger() should return a stdlib Logger."""
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)

    def test_name_matches_argument(self):
        """get_logger(name) should return a logger with that name."""
        logger = get_logger("src.some.module")
        assert logger.name == "src.some.module"

    def test_dunder_name_pattern(self):
        """get_logger(__name__) is the expected call pattern — name must pass through."""
        name = "src.core.somemodule"
        assert get_logger(name).name == name


class TestConfigureLogging:
    """Tests for configure_logging()."""

    def test_installs_handler_on_root_logger(self):
        """configure_logging() should attach at least one handler to the root logger."""
        configure_logging()
        assert len(logging.getLogger().handlers) >= 1

    def test_output_is_valid_json(self):
        """Each log record should be a valid JSON object."""
        stream = io.StringIO()
        configure_logging(stream=stream)
        logging.getLogger("test.json").info("hello")
        line = stream.getvalue().strip()
        parsed = json.loads(line)
        assert isinstance(parsed, dict)

    def test_json_contains_message(self):
        """JSON output must include a 'message' key."""
        stream = io.StringIO()
        configure_logging(stream=stream)
        logging.getLogger("test.msg").info("expected message")
        parsed = json.loads(stream.getvalue().strip())
        assert parsed["message"] == "expected message"

    def test_json_contains_levelname(self):
        """JSON output must include a 'levelname' key."""
        stream = io.StringIO()
        configure_logging(stream=stream)
        logging.getLogger("test.level").warning("warn")
        parsed = json.loads(stream.getvalue().strip())
        assert parsed["levelname"] == "WARNING"

    def test_json_contains_name(self):
        """JSON output must include a 'name' key matching the logger name."""
        stream = io.StringIO()
        configure_logging(stream=stream)
        logging.getLogger("test.name").error("err")
        parsed = json.loads(stream.getvalue().strip())
        assert parsed["name"] == "test.name"

    def test_default_level_is_info(self, monkeypatch):
        """Without LOG_LEVEL env var, root logger should be set to INFO."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        configure_logging()
        assert logging.getLogger().level == logging.INFO

    def test_log_level_env_var_overrides_default(self, monkeypatch):
        """LOG_LEVEL=DEBUG env var should set root logger to DEBUG."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        configure_logging()
        assert logging.getLogger().level == logging.DEBUG

    def test_log_level_warning_suppresses_info(self, monkeypatch):
        """LOG_LEVEL=WARNING should suppress INFO records."""
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        stream = io.StringIO()
        configure_logging(stream=stream)
        logging.getLogger("test.suppress").info("should not appear")
        assert stream.getvalue() == ""

    def test_idempotent_on_repeated_calls(self):
        """Calling configure_logging() twice must not double-attach handlers."""
        configure_logging()
        count_after_first = len(logging.getLogger().handlers)
        configure_logging()
        assert len(logging.getLogger().handlers) == count_after_first
