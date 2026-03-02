"""Shared fixtures for FastAPI tests.

The ``tmp_db`` fixture creates a temporary SQLite database by running
Django migrations via subprocess, guaranteeing schema parity with the
real database without triggering pytest-django's DB access guard.
"""

import hashlib
import os
import sqlite3
import subprocess
import sys
from collections import namedtuple
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app

InsertedKey = namedtuple("InsertedKey", ["raw_key", "key_id"])

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_django_migrations(db_path):
    """Run Django migrations in a subprocess against the given database."""
    env = {**os.environ, "DATABASE_PATH": str(db_path)}
    # Override the Django database NAME via an env var that settings.py
    # doesn't read directly — instead, we set it in a tiny script.
    script = (
        "import django, os; "
        "os.environ['DJANGO_SETTINGS_MODULE'] = 'src.web.config.settings'; "
        "django.setup(); "
        "from django.conf import settings; "
        f"settings.DATABASES['default']['NAME'] = '{db_path}'; "
        "from django.core.management import call_command; "
        "call_command('migrate', '--run-syncdb', verbosity=0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Django migrations failed:\n{result.stderr}")


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database via Django migrations.

    Runs migrations in a subprocess to avoid pytest-django's DB access
    guard while guaranteeing schema parity with the real database.
    """
    db_path = tmp_path / "db.sqlite3"
    _run_django_migrations(db_path)

    # Insert a dummy auth_user row so foreign keys to user_id resolve.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO auth_user"
        " (id, username, password, is_superuser, is_staff, is_active,"
        "  first_name, last_name, email, date_joined)"
        " VALUES (1, 'testuser', '', 0, 0, 1, '', '', 'test@example.com',"
        "  datetime('now'))"
    )
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
