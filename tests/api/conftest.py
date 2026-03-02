"""Shared fixtures for FastAPI tests.

The ``tmp_db`` fixture uses the session-cached migrated database
template (see ``tests/conftest.py``), guaranteeing schema parity
with the real database at near-zero per-test cost.
"""

import hashlib
import os
import sqlite3
from collections import namedtuple
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from ulid import ULID

from src.api.main import create_app

InsertedKey = namedtuple("InsertedKey", ["raw_key", "key_id"])


@pytest.fixture
def tmp_db(migrated_db):
    """Alias for the shared migrated_db fixture."""
    return migrated_db


@pytest.fixture
def valid_api_key(tmp_db):
    """Insert a valid API key and return an InsertedKey(raw_key, key_id)."""
    raw_key = "test-valid-api-key-1234567890abcdef"
    key_id = "01TESTKEY000000000000000001"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    now = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(str(tmp_db))
    conn.execute(
        "INSERT INTO keys_apikey"
        " (id, key_hash, key_prefix, user_id, label, is_active, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
        "INSERT INTO keys_apikey"
        " (id, key_hash, key_prefix, user_id, label, is_active, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
        "INSERT INTO keys_apikey"
        " (id, key_hash, key_prefix, user_id, label, is_active, created_at, updated_at,"
        " expires_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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


@pytest.fixture
def insert_person(tmp_db):
    """Return a callable that inserts a Person row.

    Usage::

        pid = insert_person(name="Alice", given_name="Alice", surname="Smith")
    """
    conn = sqlite3.connect(str(tmp_db))

    def _insert(
        person_id=None,
        name="John Doe",
        given_name="John",
        middle_name=None,
        surname="Doe",
    ):
        pid = person_id or str(ULID())
        conn.execute(
            "INSERT INTO persons_person"
            " (id, name, given_name, middle_name, surname,"
            "  created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (pid, name, given_name, middle_name, surname),
        )
        conn.commit()
        return pid

    yield _insert
    conn.close()


@pytest.fixture
def insert_person_name(tmp_db):
    """Return a callable that inserts a PersonName row.

    Usage::

        insert_person_name(pid, "Alice Smith", name_type="primary", is_primary=True)
    """
    conn = sqlite3.connect(str(tmp_db))

    def _insert(
        person_id,
        full_name,
        name_type="primary",
        given_name=None,
        surname=None,
        is_primary=False,
        source="test",
    ):
        name_id = str(ULID())
        conn.execute(
            "INSERT INTO persons_personname"
            " (id, person_id, name_type, full_name, given_name, surname,"
            "  is_primary, source, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (
                name_id,
                person_id,
                name_type,
                full_name,
                given_name,
                surname,
                int(is_primary),
                source,
            ),
        )
        conn.commit()
        return name_id

    yield _insert
    conn.close()
