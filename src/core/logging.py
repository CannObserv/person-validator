"""Shared logging configuration for Person Validator.

All modules should obtain a logger via::

    from src.core.logging import get_logger
    logger = get_logger(__name__)

Call ``configure_logging()`` once at application startup (FastAPI app
factory, Django ``AppConfig.ready()``, management commands, etc.).
Do **not** call it in library/utility modules — only in entry points.

Log level is controlled by the ``LOG_LEVEL`` environment variable
(default: ``INFO``). Both services share the same variable name so a
single ``EnvironmentFile`` entry covers both systemd units.
"""

import logging
import os
import sys
from typing import IO

from pythonjsonlogger import json as jsonlogger

_HANDLER_MARKER = "_pv_json_handler"
_DEFAULT_LEVEL = "INFO"
_FMT = "%(levelname)s %(name)s %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a stdlib Logger for *name*.

    Intended to be called at module level::

        logger = get_logger(__name__)
    """
    return logging.getLogger(name)


def configure_logging(stream: IO[str] | None = None) -> None:
    """Install a JSON console handler on the root logger.

    Idempotent — repeated calls do not add duplicate handlers. The log
    level is read from the ``LOG_LEVEL`` environment variable; if absent
    it defaults to ``INFO``.

    Args:
        stream: Output stream for the handler. Defaults to ``sys.stderr``.
                Pass an ``io.StringIO`` in tests to capture output.
    """
    root = logging.getLogger()

    # Idempotency guard — skip if we already installed our handler.
    if any(getattr(h, _HANDLER_MARKER, False) for h in root.handlers):
        return

    level_name = os.environ.get("LOG_LEVEL", _DEFAULT_LEVEL).upper()
    level = logging.getLevelName(level_name)

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(jsonlogger.JsonFormatter(fmt=_FMT))
    setattr(handler, _HANDLER_MARKER, True)

    root.setLevel(level)
    root.addHandler(handler)
