"""Tests for SQLite database connection management."""

import sqlite3
from unittest.mock import patch


class TestGetDbPath:
    """Tests for database path resolution."""

    def test_returns_path_from_settings(self):
        """get_db_path() should return the configured database path."""
        from src.api.db import get_db_path

        path = get_db_path()
        assert str(path).endswith("db.sqlite3")


class TestGetConnection:
    """Tests for SQLite connection management."""

    def test_returns_sqlite3_connection(self, tmp_db):
        """get_connection() should return a sqlite3.Connection."""
        with patch("src.api.db.get_db_path", return_value=tmp_db):
            from src.api.db import get_connection

            conn = get_connection()
            assert isinstance(conn, sqlite3.Connection)
            conn.close()

    def test_connection_uses_wal_mode(self, tmp_db):
        """Connection should be in WAL journal mode."""
        with patch("src.api.db.get_db_path", return_value=tmp_db):
            from src.api.db import get_connection

            conn = get_connection()
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
            conn.close()

    def test_connection_has_row_factory(self, tmp_db):
        """Connection should use sqlite3.Row factory for dict-like access."""
        with patch("src.api.db.get_db_path", return_value=tmp_db):
            from src.api.db import get_connection

            conn = get_connection()
            assert conn.row_factory is sqlite3.Row
            conn.close()
