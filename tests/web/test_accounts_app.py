"""Tests for the accounts AppConfig startup behaviour."""

import logging

from src.core.logging import HANDLER_MARKER
from src.web.accounts.apps import AccountsConfig


class TestAccountsAppConfig:
    """AccountsConfig.ready() must wire JSON logging for the Django process."""

    def test_ready_installs_root_handler(self):
        """ready() must attach at least one handler to the root logger."""
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        root.handlers = [h for h in root.handlers if not getattr(h, HANDLER_MARKER, False)]
        try:
            AccountsConfig("src.web.accounts", __import__("src.web.accounts")).ready()
            assert any(getattr(h, HANDLER_MARKER, False) for h in root.handlers)
        finally:
            root.handlers = original_handlers

    def test_ready_is_idempotent(self):
        """Calling ready() twice must not duplicate handlers."""
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        root.handlers = [h for h in root.handlers if not getattr(h, HANDLER_MARKER, False)]
        try:
            config = AccountsConfig("src.web.accounts", __import__("src.web.accounts"))
            config.ready()
            count = len(root.handlers)
            config.ready()
            assert len(root.handlers) == count
        finally:
            root.handlers = original_handlers
