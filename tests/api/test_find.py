"""Tests for POST /v1/find endpoint."""

import pytest


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
        assert "No matching persons found" in body["messages"]

    @pytest.mark.anyio
    async def test_no_match_includes_normalized_query(self, client, valid_api_key, tmp_db):
        """The 404 response should include the normalized query."""
        resp = await client.post(
            "/v1/find",
            json={"name": "  Bob  Smith  Jr. "},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 404
        body = resp.json()
        # NameParsing strips generational suffixes — "Jr." is removed
        assert body["query"]["normalized"] == "bob smith"


class TestFindInputClassification422:
    """Inputs classified as non-person-names return 422."""

    @pytest.mark.anyio
    async def test_org_suffix_returns_422(self, client, valid_api_key, tmp_db):
        resp = await client.post(
            "/v1/find",
            json={"name": "Acme Corporation"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_llc_suffix_returns_422(self, client, valid_api_key, tmp_db):
        resp = await client.post(
            "/v1/find",
            json={"name": "Some Business LLC"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 422


class TestFindExactMatch:
    """Tests for exact-match scenarios."""

    @pytest.mark.anyio
    async def test_exact_primary_match_returns_200(
        self, client, valid_api_key, tmp_db, insert_person, insert_person_name
    ):
        """Exact match on primary full_name should return 200 with certainty 1.0."""
        pid = insert_person(name="Robert Smith", given_name="Robert", surname="Smith")
        insert_person_name(
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
    async def test_case_insensitive_match(
        self, client, valid_api_key, tmp_db, insert_person, insert_person_name
    ):
        """Matching should be case-insensitive."""
        pid = insert_person(name="Robert Smith", given_name="Robert", surname="Smith")
        insert_person_name(
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
    async def test_alias_match_certainty_below_1(
        self, client, valid_api_key, tmp_db, insert_person, insert_person_name
    ):
        """Match on alias should return certainty < 1.0."""
        pid = insert_person(name="Robert Smith", given_name="Robert", surname="Smith")
        insert_person_name(
            pid,
            "Robert Smith",
            name_type="primary",
            given_name="Robert",
            surname="Smith",
            is_primary=True,
        )
        insert_person_name(
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
    async def test_given_plus_surname_match(
        self, client, valid_api_key, tmp_db, insert_person, insert_person_name
    ):
        """Query matching given_name + surname should return a result."""
        pid = insert_person(
            name="Robert James Smith Jr.",
            given_name="Robert",
            surname="Smith",
        )
        insert_person_name(
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
    async def test_response_has_messages_list(self, client, valid_api_key, tmp_db):
        """Response should always include messages as a list."""
        resp = await client.post(
            "/v1/find",
            json={"name": "Nobody"},
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        body = resp.json()
        assert "messages" in body
        assert isinstance(body["messages"], list)

    @pytest.mark.anyio
    async def test_results_sorted_by_certainty_descending(
        self, client, valid_api_key, tmp_db, insert_person, insert_person_name
    ):
        """Results should be sorted by certainty, highest first."""
        pid1 = insert_person(
            name="Alice Johnson",
            given_name="Alice",
            surname="Johnson",
        )
        insert_person_name(
            pid1,
            "Alice Johnson",
            name_type="primary",
            given_name="Alice",
            surname="Johnson",
            is_primary=True,
        )

        pid2 = insert_person(
            name="Alice Marie Johnson",
            given_name="Alice",
            surname="Johnson",
        )
        insert_person_name(
            pid2,
            "Alice Marie Johnson",
            name_type="primary",
            given_name="Alice",
            surname="Johnson",
            is_primary=True,
        )
        insert_person_name(
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
