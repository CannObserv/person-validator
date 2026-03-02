"""Tests for POST /v1/find endpoint."""

import sqlite3

import pytest
from ulid import ULID


def _insert_person(db_path, person_id=None, name="John Doe", given_name="John", surname="Doe"):
    """Insert a Person row and return the person_id."""
    person_id = person_id or str(ULID())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO persons_person (id, name, given_name, surname, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
        (person_id, name, given_name, surname),
    )
    conn.commit()
    conn.close()
    return person_id


def _insert_person_name(
    db_path,
    person_id,
    full_name,
    name_type="primary",
    given_name=None,
    surname=None,
    is_primary=False,
    source="test",
):
    """Insert a PersonName row."""
    name_id = str(ULID())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO persons_personname"
        " (id, person_id, name_type, full_name, given_name, surname,"
        "  is_primary, source, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (name_id, person_id, name_type, full_name, given_name, surname, int(is_primary), source),
    )
    conn.commit()
    conn.close()
    return name_id


class TestFindEndpointValidation:
    """Validation and auth tests for POST /v1/find."""

    @pytest.mark.anyio
    async def test_empty_name_returns_422(self, client, valid_api_key):
        """An empty name string should return a 422 validation error."""
        resp = await client.post(
            "/v1/find",
            json={"name": ""},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_whitespace_only_name_returns_422(self, client, valid_api_key):
        """A whitespace-only name string should return a 422 validation error."""
        resp = await client.post(
            "/v1/find",
            json={"name": "   "},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_missing_name_field_returns_422(self, client, valid_api_key):
        """A request body without 'name' should return 422."""
        resp = await client.post(
            "/v1/find",
            json={},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_no_api_key_returns_401(self, client):
        """Missing API key should return 401."""
        resp = await client.post("/v1/find", json={"name": "test"})
        assert resp.status_code == 401


class TestFindNoMatches:
    """Tests for when no persons match the query."""

    @pytest.mark.anyio
    async def test_no_match_returns_404(self, client, valid_api_key, tmp_db):
        """A name with no matches should return 404 with empty results."""
        resp = await client.post(
            "/v1/find",
            json={"name": "Nonexistent Person"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["query"]["original"] == "Nonexistent Person"
        assert body["results"] == []
        assert body["message"] == "No matching persons found"

    @pytest.mark.anyio
    async def test_no_match_includes_normalized_query(self, client, valid_api_key, tmp_db):
        """The 404 response should include the normalized query."""
        resp = await client.post(
            "/v1/find",
            json={"name": "  Bob  Smith  Jr. "},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        body = resp.json()
        assert body["query"]["normalized"] == "bob smith jr"


class TestFindExactMatch:
    """Tests for exact-match scenarios."""

    @pytest.mark.anyio
    async def test_exact_primary_match_returns_200(self, client, valid_api_key, tmp_db):
        """Exact match on primary full_name should return 200 with certainty 1.0."""
        pid = _insert_person(tmp_db, name="Robert Smith", given_name="Robert", surname="Smith")
        _insert_person_name(
            tmp_db,
            pid,
            "Robert Smith",
            name_type="primary",
            given_name="Robert",
            surname="Smith",
            is_primary=True,
        )
        resp = await client.post(
            "/v1/find",
            json={"name": "Robert Smith"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["results"]) >= 1
        top = body["results"][0]
        assert top["id"] == pid
        assert top["certainty"] == 1.0
        assert top["matched_name"]["full_name"] == "Robert Smith"
        assert top["matched_name"]["name_type"] == "primary"

    @pytest.mark.anyio
    async def test_case_insensitive_match(self, client, valid_api_key, tmp_db):
        """Matching should be case-insensitive."""
        pid = _insert_person(tmp_db, name="Robert Smith", given_name="Robert", surname="Smith")
        _insert_person_name(
            tmp_db,
            pid,
            "Robert Smith",
            name_type="primary",
            given_name="Robert",
            surname="Smith",
            is_primary=True,
        )
        resp = await client.post(
            "/v1/find",
            json={"name": "robert smith"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 200
        assert resp.json()["results"][0]["id"] == pid


class TestFindAliasMatch:
    """Tests for non-primary name type matches."""

    @pytest.mark.anyio
    async def test_alias_match_certainty_below_1(self, client, valid_api_key, tmp_db):
        """Match on alias should return certainty < 1.0."""
        pid = _insert_person(tmp_db, name="Robert Smith", given_name="Robert", surname="Smith")
        _insert_person_name(
            tmp_db,
            pid,
            "Robert Smith",
            name_type="primary",
            given_name="Robert",
            surname="Smith",
            is_primary=True,
        )
        _insert_person_name(
            tmp_db,
            pid,
            "Bobby Smith",
            name_type="nickname",
            given_name="Bobby",
            surname="Smith",
        )
        resp = await client.post(
            "/v1/find",
            json={"name": "Bobby Smith"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["results"]) >= 1
        top = body["results"][0]
        assert top["id"] == pid
        assert top["certainty"] == 0.9
        assert top["matched_name"]["name_type"] == "nickname"


class TestFindPartialMatch:
    """Tests for partial name matching (given_name + surname)."""

    @pytest.mark.anyio
    async def test_given_plus_surname_match(self, client, valid_api_key, tmp_db):
        """Query matching given_name + surname should return a result."""
        pid = _insert_person(
            tmp_db,
            name="Robert James Smith Jr.",
            given_name="Robert",
            surname="Smith",
        )
        _insert_person_name(
            tmp_db,
            pid,
            "Robert James Smith Jr.",
            name_type="primary",
            given_name="Robert",
            surname="Smith",
            is_primary=True,
        )
        resp = await client.post(
            "/v1/find",
            json={"name": "Robert Smith"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["results"]) >= 1
        top = body["results"][0]
        assert top["id"] == pid
        # Partial match should be below 1.0
        assert 0.0 < top["certainty"] < 1.0


class TestFindResponseSchema:
    """Tests for response structure conformance."""

    @pytest.mark.anyio
    async def test_response_has_query_block(self, client, valid_api_key, tmp_db):
        """Response should always include a query block."""
        resp = await client.post(
            "/v1/find",
            json={"name": "Nobody"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        body = resp.json()
        assert "query" in body
        assert "original" in body["query"]
        assert "normalized" in body["query"]
        assert "variants" in body["query"]

    @pytest.mark.anyio
    async def test_results_sorted_by_certainty_descending(self, client, valid_api_key, tmp_db):
        """Results should be sorted by certainty, highest first."""
        pid1 = _insert_person(tmp_db, name="Alice Johnson", given_name="Alice", surname="Johnson")
        _insert_person_name(
            tmp_db,
            pid1,
            "Alice Johnson",
            name_type="primary",
            given_name="Alice",
            surname="Johnson",
            is_primary=True,
        )

        pid2 = _insert_person(
            tmp_db,
            name="Alice Marie Johnson",
            given_name="Alice",
            surname="Johnson",
        )
        _insert_person_name(
            tmp_db,
            pid2,
            "Alice Marie Johnson",
            name_type="primary",
            given_name="Alice",
            surname="Johnson",
            is_primary=True,
        )
        _insert_person_name(
            tmp_db,
            pid2,
            "Alice Johnson",
            name_type="nickname",
            given_name="Alice",
            surname="Johnson",
        )

        resp = await client.post(
            "/v1/find",
            json={"name": "Alice Johnson"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        results = body["results"]
        assert len(results) >= 2
        certainties = [r["certainty"] for r in results]
        assert certainties == sorted(certainties, reverse=True)
