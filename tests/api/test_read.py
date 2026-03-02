"""Tests for GET /v1/read/{id} endpoint."""

import sqlite3

import pytest
from ulid import ULID


class TestReadNotFound:
    """Tests for 404 responses."""

    @pytest.mark.anyio
    async def test_nonexistent_id_returns_404(self, client, valid_api_key):
        """A ULID that doesn't exist should return 404."""
        fake_id = str(ULID())
        resp = await client.get(
            f"/v1/read/{fake_id}",
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 404
        assert resp.json() == {"message": "Person not found"}

    @pytest.mark.anyio
    async def test_invalid_id_returns_404(self, client, valid_api_key):
        """A malformed ID should return 404."""
        resp = await client.get(
            "/v1/read/not-a-valid-id",
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 404
        assert resp.json() == {"message": "Person not found"}

    @pytest.mark.anyio
    async def test_no_api_key_returns_401(self, client):
        """Missing API key should return 401."""
        fake_id = str(ULID())
        resp = await client.get(f"/v1/read/{fake_id}")
        assert resp.status_code == 401


class TestReadSuccess:
    """Tests for successful 200 responses."""

    @pytest.mark.anyio
    async def test_valid_id_returns_person(
        self, client, valid_api_key, insert_person, insert_person_name
    ):
        """A valid person ID should return full person record."""
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

        resp = await client.get(
            f"/v1/read/{pid}",
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == pid
        assert body["name"] == "Robert James Smith Jr."
        assert body["given_name"] == "Robert"
        assert body["surname"] == "Smith"
        assert "created_at" in body
        assert "updated_at" in body

    @pytest.mark.anyio
    async def test_person_with_no_attributes(
        self, client, valid_api_key, insert_person, insert_person_name
    ):
        """A person with no attributes should return empty attributes list."""
        pid = insert_person(name="Alice Smith", given_name="Alice", surname="Smith")
        insert_person_name(
            pid,
            "Alice Smith",
            name_type="primary",
            is_primary=True,
            given_name="Alice",
            surname="Smith",
        )

        resp = await client.get(
            f"/v1/read/{pid}",
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["attributes"] == []

    @pytest.mark.anyio
    async def test_person_with_multiple_names(
        self, client, valid_api_key, insert_person, insert_person_name
    ):
        """A person with multiple name variants should include all."""
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
            "Bob Smith",
            name_type="nickname",
            given_name="Bob",
            surname="Smith",
        )
        insert_person_name(
            pid,
            "Bobby Smith",
            name_type="alias",
            given_name="Bobby",
            surname="Smith",
        )

        resp = await client.get(
            f"/v1/read/{pid}",
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["names"]) == 3
        full_names = {n["full_name"] for n in body["names"]}
        assert full_names == {"Robert Smith", "Bob Smith", "Bobby Smith"}

    @pytest.mark.anyio
    async def test_person_with_attributes(
        self, client, valid_api_key, tmp_db, insert_person, insert_person_name
    ):
        """A person with enrichment attributes should include them."""
        pid = insert_person(name="Alice Smith", given_name="Alice", surname="Smith")
        insert_person_name(
            pid,
            "Alice Smith",
            name_type="primary",
            is_primary=True,
            given_name="Alice",
            surname="Smith",
        )
        # Insert an attribute directly
        attr_id = str(ULID())
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "INSERT INTO persons_personattribute"
            " (id, person_id, source, key, value, confidence, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (attr_id, pid, "test_provider", "employer", "Acme Corp", 0.85),
        )
        conn.commit()
        conn.close()

        resp = await client.get(
            f"/v1/read/{pid}",
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["attributes"]) == 1
        attr = body["attributes"][0]
        assert attr["id"] == attr_id
        assert attr["source"] == "test_provider"
        assert attr["key"] == "employer"
        assert attr["value"] == "Acme Corp"
        assert attr["confidence"] == 0.85
        assert "created_at" in attr


class TestReadResponseSchema:
    """Tests for response structure conformance."""

    @pytest.mark.anyio
    async def test_name_schema_fields(
        self, client, valid_api_key, insert_person, insert_person_name
    ):
        """Each name record should have all expected fields."""
        pid = insert_person(name="Jane Doe", given_name="Jane", surname="Doe")
        insert_person_name(
            pid,
            "Jane Doe",
            name_type="primary",
            is_primary=True,
            given_name="Jane",
            surname="Doe",
            source="manual",
        )

        resp = await client.get(
            f"/v1/read/{pid}",
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 200
        name = resp.json()["names"][0]
        expected_fields = {
            "id",
            "name_type",
            "full_name",
            "given_name",
            "middle_name",
            "surname",
            "prefix",
            "suffix",
            "is_primary",
            "source",
            "effective_date",
            "end_date",
        }
        assert expected_fields.issubset(name.keys())

    @pytest.mark.anyio
    async def test_top_level_fields(self, client, valid_api_key, insert_person, insert_person_name):
        """Response should have all top-level person fields."""
        pid = insert_person(name="Jane Doe", given_name="Jane", surname="Doe")
        insert_person_name(
            pid,
            "Jane Doe",
            name_type="primary",
            is_primary=True,
            given_name="Jane",
            surname="Doe",
        )

        resp = await client.get(
            f"/v1/read/{pid}",
            headers={"X-API-Key": valid_api_key.raw_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        expected_fields = {
            "id",
            "name",
            "given_name",
            "middle_name",
            "surname",
            "created_at",
            "updated_at",
            "names",
            "attributes",
        }
        assert expected_fields.issubset(body.keys())
