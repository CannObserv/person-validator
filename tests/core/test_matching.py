"""Tests for src.core.matching — normalize() and search()."""

import sqlite3

import pytest

from src.core.matching import normalize, search
from src.core.pipeline.base import WeightedVariant


@pytest.fixture
def conn():
    """In-memory SQLite connection with minimal schema for matching tests."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE persons_person (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE persons_personname (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            full_name TEXT NOT NULL,
            given_name TEXT,
            surname TEXT,
            name_type TEXT NOT NULL DEFAULT 'primary',
            is_primary INTEGER NOT NULL DEFAULT 0
        );
    """)
    return db


def insert_person(conn, pid, name):
    conn.execute("INSERT INTO persons_person (id, name) VALUES (?, ?)", (pid, name))
    conn.commit()


def insert_name(
    conn, nid, pid, full_name, given_name=None, surname=None, name_type="primary", is_primary=True
):
    conn.execute(
        "INSERT INTO persons_personname"
        " (id, person_id, full_name, given_name, surname, name_type, is_primary)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (nid, pid, full_name, given_name, surname, name_type, int(is_primary)),
    )
    conn.commit()


class TestNormalize:
    def test_lowercases(self):
        assert normalize("Bob Smith") == "bob smith"

    def test_strips_non_alpha(self):
        assert normalize("Dr. Smith") == "dr smith"

    def test_collapses_whitespace(self):
        assert normalize("  Bob   Smith  ") == "bob smith"


class TestSearchExactMatch:
    def test_primary_exact_match_certainty_1(self, conn):
        insert_person(conn, "p1", "Alice Jones")
        insert_name(conn, "n1", "p1", "Alice Jones", "Alice", "Jones", is_primary=True)
        results = search(conn, [WeightedVariant(name="alice jones", weight=1.0)])
        assert len(results) == 1
        assert results[0].person_id == "p1"
        assert results[0].certainty == pytest.approx(1.0)

    def test_non_primary_exact_match_certainty_09(self, conn):
        insert_person(conn, "p1", "Alice Jones")
        insert_name(
            conn, "n1", "p1", "Alice Jones", "Alice", "Jones", name_type="alias", is_primary=False
        )
        results = search(conn, [WeightedVariant(name="alice jones", weight=1.0)])
        assert results[0].certainty == pytest.approx(0.9)

    def test_weight_multiplies_base_certainty(self, conn):
        insert_person(conn, "p1", "Alice Jones")
        insert_name(conn, "n1", "p1", "Alice Jones", "Alice", "Jones", is_primary=True)
        results = search(conn, [WeightedVariant(name="alice jones", weight=0.85)])
        assert results[0].certainty == pytest.approx(1.0 * 0.85)

    def test_empty_variants_returns_empty(self, conn):
        assert search(conn, []) == []


class TestSearchPairMatch:
    def test_pair_match_primary_certainty_08(self, conn):
        insert_person(conn, "p1", "Alice Marie Jones")
        insert_name(conn, "n1", "p1", "Alice Marie Jones", "Alice", "Jones", is_primary=True)
        results = search(conn, [WeightedVariant(name="alice jones", weight=1.0)])
        assert results[0].certainty == pytest.approx(0.8)

    def test_pair_match_weight_applied(self, conn):
        insert_person(conn, "p1", "Alice Marie Jones")
        insert_name(conn, "n1", "p1", "Alice Marie Jones", "Alice", "Jones", is_primary=True)
        results = search(conn, [WeightedVariant(name="alice jones", weight=0.85)])
        assert results[0].certainty == pytest.approx(0.8 * 0.85)

    def test_exact_match_takes_priority_over_pair(self, conn):
        insert_person(conn, "p1", "Alice Jones")
        insert_name(conn, "n1", "p1", "Alice Jones", "Alice", "Jones", is_primary=True)
        results = search(conn, [WeightedVariant(name="alice jones", weight=1.0)])
        assert results[0].certainty == pytest.approx(1.0)

    def test_max_weight_used_when_multiple_variants_produce_same_pair(self, conn):
        insert_person(conn, "p1", "Alice Marie Jones")
        insert_name(conn, "n1", "p1", "Alice Marie Jones", "Alice", "Jones", is_primary=True)
        variants = [
            WeightedVariant(name="alice jones", weight=0.7),
            WeightedVariant(name="alice j jones", weight=0.9),
        ]
        results = search(conn, variants)
        # Both produce pair (alice, jones); max weight 0.9 should be used
        assert results[0].certainty == pytest.approx(0.8 * 0.9)


class TestSearchSorting:
    def test_results_sorted_by_certainty_descending(self, conn):
        insert_person(conn, "p1", "Alice Jones")
        insert_name(conn, "n1", "p1", "Alice Jones", "Alice", "Jones", is_primary=True)
        insert_person(conn, "p2", "Alice Marie Jones")
        insert_name(conn, "n2", "p2", "Alice Marie Jones", "Alice", "Jones", is_primary=True)

        results = search(conn, [WeightedVariant(name="alice jones", weight=1.0)])
        certainties = [r.certainty for r in results]
        assert certainties == sorted(certainties, reverse=True)
