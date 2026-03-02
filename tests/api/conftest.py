"""Shared fixtures for FastAPI tests."""

import hashlib
import os
import sqlite3
from collections import namedtuple
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app

_COLS = "id, key_hash, key_prefix, user_id, label, is_active, created_at, updated_at"
_COLS_WITH_EXPIRY = f"{_COLS}, expires_at"

InsertedKey = namedtuple("InsertedKey", ["raw_key", "key_id"])


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database with the keys_apikey table."""
    db_path = tmp_path / "db.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
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
    conn.execute("CREATE INDEX idx_key_hash ON keys_apikey (key_hash)")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def valid_api_key(tmp_db):
    """Insert a valid API key and return an InsertedKey(raw_key, key_id)."""
    raw_key = "test-valid-api-key-1234567890abcdef"
    key_id = "01TESTKEY000000000000000001"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    now = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        f"INSERT INTO keys_apikey ({_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (key_id, key_hash, raw_key[:8], 1, "Test Key", 1, now, now),
    )
    conn.commit()
    conn.close()
    return InsertedKey(raw_key, key_id)


@pytest.fixture
def revoked_api_key(tmp_db):
    """Insert a revoked (is_active=False) API key and return an InsertedKey."""
    raw_key = "test-revoked-key-1234567890abcdef"
    key_id = "01TESTKEY000000000000000002"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    now = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        f"INSERT INTO keys_apikey ({_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (key_id, key_hash, raw_key[:8], 1, "Revoked", 0, now, now),
    )
    conn.commit()
    conn.close()
    return InsertedKey(raw_key, key_id)


@pytest.fixture
def expired_api_key(tmp_db):
    """Insert an expired API key and return an InsertedKey."""
    raw_key = "test-expired-key-1234567890abcdef"
    key_id = "01TESTKEY000000000000000003"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    now = datetime.now(UTC).isoformat()
    expired = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        f"INSERT INTO keys_apikey ({_COLS_WITH_EXPIRY}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (key_id, key_hash, raw_key[:8], 1, "Expired", 1, now, now, expired),
    )
    conn.commit()
    conn.close()
    return InsertedKey(raw_key, key_id)


@pytest.fixture
def app(tmp_db):
    """Create a FastAPI app configured to use the temporary database."""
    os.environ["DATABASE_PATH"] = str(tmp_db)
    try:
        yield create_app()
    finally:
        del os.environ["DATABASE_PATH"]


@pytest.fixture
async def client(app):
    """Create an async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
