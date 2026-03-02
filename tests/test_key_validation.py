"""Tests for the shared API key validation logic in src.core.key_validation."""

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from src.core.key_validation import KeyValidationResult, validate_api_key


@pytest.fixture
def conn(tmp_path):
    """Create a temporary SQLite database with the keys_apikey table."""
    db_path = tmp_path / "db.sqlite3"
    c = sqlite3.connect(str(db_path))
    c.execute("PRAGMA journal_mode=WAL")
    c.row_factory = sqlite3.Row
    c.execute(
        """
        CREATE TABLE keys_apikey (
            id TEXT PRIMARY KEY,
            key_hash TEXT NOT NULL,
            key_prefix TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT,
            last_used_at TEXT
        )
        """
    )
    c.commit()
    yield c
    c.close()


def _insert_key(conn, raw_key, key_id, *, is_active=1, expires_at=None):
    """Helper to insert a key into the test database."""
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO keys_apikey"
        " (id, key_hash, key_prefix, user_id, label, is_active,"
        "  created_at, updated_at, expires_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (key_id, key_hash, raw_key[:8], 1, "Test", is_active, now, now, expires_at),
    )
    conn.commit()


class TestValidateApiKey:
    """Tests for the validate_api_key function."""

    def test_valid_key_returns_valid_result(self, conn):
        """A correct active key returns is_valid=True."""
        _insert_key(conn, "good-key", "KEY001")
        result = validate_api_key("good-key", conn)
        assert result.is_valid is True
        assert result.key_id == "KEY001"
        assert result.rejection_reason is None

    def test_unknown_key_returns_invalid(self, conn):
        """An unknown key returns is_valid=False with reason 'invalid'."""
        result = validate_api_key("no-such-key", conn)
        assert result.is_valid is False
        assert result.rejection_reason == "invalid"

    def test_revoked_key_returns_revoked(self, conn):
        """A revoked (is_active=False) key returns reason 'revoked'."""
        _insert_key(conn, "revoked-key", "KEY002", is_active=0)
        result = validate_api_key("revoked-key", conn)
        assert result.is_valid is False
        assert result.rejection_reason == "revoked"

    def test_expired_key_returns_expired(self, conn):
        """An expired key returns reason 'expired'."""
        expired = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        _insert_key(conn, "expired-key", "KEY003", expires_at=expired)
        result = validate_api_key("expired-key", conn)
        assert result.is_valid is False
        assert result.rejection_reason == "expired"

    def test_future_expiry_is_valid(self, conn):
        """A key with a future expiry is valid."""
        future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        _insert_key(conn, "future-key", "KEY004", expires_at=future)
        result = validate_api_key("future-key", conn)
        assert result.is_valid is True

    def test_valid_key_updates_last_used_at(self, conn):
        """Successful validation bumps last_used_at."""
        _insert_key(conn, "used-key", "KEY005")
        before = datetime.now(UTC)
        validate_api_key("used-key", conn)
        row = conn.execute(
            "SELECT last_used_at FROM keys_apikey WHERE id = ?", ("KEY005",)
        ).fetchone()
        assert row["last_used_at"] is not None
        last_used = datetime.fromisoformat(row["last_used_at"])
        assert last_used >= before

    def test_invalid_key_does_not_update_last_used(self, conn):
        """Failed validation does not touch any rows."""
        _insert_key(conn, "untouched-key", "KEY006")
        validate_api_key("wrong-key", conn)
        row = conn.execute(
            "SELECT last_used_at FROM keys_apikey WHERE id = ?", ("KEY006",)
        ).fetchone()
        assert row["last_used_at"] is None

    def test_naive_expires_at_handled(self, conn):
        """A naive (no tzinfo) expires_at in the past is treated as expired."""
        # Store a naive ISO string (no +00:00 or Z suffix)
        naive_past = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        _insert_key(conn, "naive-key", "KEY007", expires_at=naive_past)
        result = validate_api_key("naive-key", conn)
        assert result.is_valid is False
        assert result.rejection_reason == "expired"


class TestKeyValidationResult:
    """Tests for the KeyValidationResult dataclass."""

    def test_is_frozen(self):
        """Result should be immutable."""
        result = KeyValidationResult(key_id="X", is_valid=True)
        with pytest.raises(AttributeError):
            result.is_valid = False

    def test_default_rejection_reason_is_none(self):
        """rejection_reason defaults to None."""
        result = KeyValidationResult(key_id="X", is_valid=True)
        assert result.rejection_reason is None
