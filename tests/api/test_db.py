"""Tests for SQLite database connection management."""

import os
import sqlite3

import pytest
from ulid import ULID

from src.api.db import get_connection, get_db_path


class TestGetDbPath:
    """Tests for database path resolution."""

    def test_returns_default_path(self):
        """get_db_path() should return a path ending in db.sqlite3."""
        path = get_db_path()
        assert str(path).endswith("db.sqlite3")

    def test_respects_env_var(self, tmp_path):
        """get_db_path() should honour the DATABASE_PATH env var."""
        custom = tmp_path / "custom.db"
        os.environ["DATABASE_PATH"] = str(custom)
        try:
            assert get_db_path() == custom
        finally:
            del os.environ["DATABASE_PATH"]


class TestGetConnection:
    """Tests for SQLite connection management."""

    def test_returns_sqlite3_connection(self, tmp_db):
        """get_connection() should return a sqlite3.Connection."""
        os.environ["DATABASE_PATH"] = str(tmp_db)
        try:
            conn = get_connection()
            assert isinstance(conn, sqlite3.Connection)
            conn.close()
        finally:
            del os.environ["DATABASE_PATH"]

    def test_connection_uses_wal_mode(self, tmp_db):
        """Connection should be in WAL journal mode."""
        os.environ["DATABASE_PATH"] = str(tmp_db)
        try:
            conn = get_connection()
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
            conn.close()
        finally:
            del os.environ["DATABASE_PATH"]

    def test_connection_has_row_factory(self, tmp_db):
        """Connection should use sqlite3.Row factory for dict-like access."""
        os.environ["DATABASE_PATH"] = str(tmp_db)
        try:
            conn = get_connection()
            assert conn.row_factory is sqlite3.Row
            conn.close()
        finally:
            del os.environ["DATABASE_PATH"]

    def test_foreign_keys_enforced(self, tmp_db):
        """Connection must have PRAGMA foreign_keys = ON."""
        os.environ["DATABASE_PATH"] = str(tmp_db)
        try:
            conn = get_connection()
            result = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            conn.close()
            assert result == 1
        finally:
            del os.environ["DATABASE_PATH"]

    def test_fk_violation_raises_integrity_error(self, tmp_db):
        """Inserting a PersonAttribute with a non-existent person_id raises IntegrityError."""
        os.environ["DATABASE_PATH"] = str(tmp_db)
        conn = get_connection()
        try:
            bogus_person_id = str(ULID())
            attr_id = str(ULID())
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO persons_personattribute"
                    " (id, person_id, value_type, value, metadata, created_at, updated_at)"
                    " VALUES (?, ?, 'text', 'hello', '{}', datetime('now'), datetime('now'))",
                    (attr_id, bogus_person_id),
                )
                conn.commit()
        finally:
            conn.close()
            del os.environ["DATABASE_PATH"]
