"""Tests for GET /versions endpoint."""

import pytest


@pytest.mark.anyio
class TestVersionsEndpoint:
    """Tests for the public GET /versions endpoint."""

    async def test_versions_returns_200(self, client):
        """GET /versions should return 200."""
        response = await client.get("/versions")
        assert response.status_code == 200

    async def test_versions_does_not_require_auth(self, client):
        """GET /versions should be publicly accessible without an API key."""
        response = await client.get("/versions")
        assert response.status_code == 200

    async def test_versions_response_has_versions_key(self, client):
        """Response body should contain a 'versions' list."""
        response = await client.get("/versions")
        body = response.json()
        assert "versions" in body
        assert isinstance(body["versions"], list)

    async def test_versions_contains_v1_entry(self, client):
        """v1 should appear in the versions list."""
        response = await client.get("/versions")
        versions = response.json()["versions"]
        assert any(v["version"] == "v1" for v in versions)

    async def test_v1_entry_shape(self, client):
        """Each version entry must include version, status, and prefix fields."""
        response = await client.get("/versions")
        versions = response.json()["versions"]
        v1 = next(v for v in versions if v["version"] == "v1")
        assert v1["prefix"] == "/v1"
        assert v1["status"] in ("stable", "deprecated")

    async def test_v1_is_stable(self, client):
        """v1 should currently report status 'stable'."""
        response = await client.get("/versions")
        versions = response.json()["versions"]
        v1 = next(v for v in versions if v["version"] == "v1")
        assert v1["status"] == "stable"

    async def test_stable_entry_has_no_sunset_date(self, client):
        """A stable version entry must not include a sunset_date field."""
        response = await client.get("/versions")
        versions = response.json()["versions"]
        v1 = next(v for v in versions if v["version"] == "v1")
        assert "sunset_date" not in v1
