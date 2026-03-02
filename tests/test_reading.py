"""Tests for src.core.reading module."""

import sqlite3

from ulid import ULID

from src.core.reading import read_person


class TestReadPerson:
    """Unit tests for the read_person query function."""

    def test_returns_none_for_missing_id(self, migrated_db):
        """A nonexistent ID should return None."""
        conn = sqlite3.connect(str(migrated_db))
        conn.row_factory = sqlite3.Row
        result = read_person(conn, str(ULID()))
        conn.close()
        assert result is None

    def test_returns_person_detail(self, migrated_db):
        """An existing person should return a PersonDetail with names."""
        conn = sqlite3.connect(str(migrated_db))
        conn.row_factory = sqlite3.Row

        pid = str(ULID())
        conn.execute(
            "INSERT INTO persons_person"
            " (id, name, given_name, surname, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            (pid, "Jane Doe", "Jane", "Doe"),
        )
        nid = str(ULID())
        conn.execute(
            "INSERT INTO persons_personname"
            " (id, person_id, name_type, full_name, given_name, surname,"
            "  is_primary, source, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (nid, pid, "primary", "Jane Doe", "Jane", "Doe", 1, "manual"),
        )
        conn.commit()

        detail = read_person(conn, pid)
        conn.close()

        assert detail is not None
        assert detail.person.id == pid
        assert detail.person.name == "Jane Doe"
        assert len(detail.names) == 1
        assert detail.names[0].full_name == "Jane Doe"
        assert detail.names[0].is_primary is True
        assert detail.attributes == []

    def test_returns_attributes(self, migrated_db):
        """Attributes should be included in the result."""
        conn = sqlite3.connect(str(migrated_db))
        conn.row_factory = sqlite3.Row

        pid = str(ULID())
        conn.execute(
            "INSERT INTO persons_person"
            " (id, name, given_name, surname, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            (pid, "Jane Doe", "Jane", "Doe"),
        )
        nid = str(ULID())
        conn.execute(
            "INSERT INTO persons_personname"
            " (id, person_id, name_type, full_name, given_name, surname,"
            "  is_primary, source, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (nid, pid, "primary", "Jane Doe", "Jane", "Doe", 1, "manual"),
        )
        aid = str(ULID())
        conn.execute(
            "INSERT INTO persons_personattribute"
            " (id, person_id, source, key, value, confidence, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (aid, pid, "test", "employer", "Acme", 0.9),
        )
        conn.commit()

        detail = read_person(conn, pid)
        conn.close()

        assert len(detail.attributes) == 1
        assert detail.attributes[0].key == "employer"
        assert detail.attributes[0].value == "Acme"
        assert detail.attributes[0].confidence == 0.9
