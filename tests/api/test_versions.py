"""Tests for GET /versions endpoint."""

import pytest

import src.api.routes.health as health_module
from src.api.schemas import VersionEntry


@pytest.mark.anyio
class TestVersionsEndpoint:
    """Tests for the public GET /versions endpoint."""

    async def test_versions_returns_200(self, client):
        """GET /versions should return 200."""
        response = await client.get("/versions")
        assert response.status_code == 200

    async def test_versions_requires_no_api_key(self, client):
        """GET /versions must return 200 even with no X-API-Key header."""
        response = await client.get("/versions", headers={})
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

    async def test_deprecated_entry_includes_sunset_date(self, client, monkeypatch):
        """A deprecated version entry must include a sunset_date field."""
        deprecated = (
            VersionEntry(
                version="v0",
                status="deprecated",
                prefix="/v0",
                sunset_date="2026-04-01",
            ),
        )
        monkeypatch.setattr(health_module, "_API_VERSIONS", deprecated)
        response = await client.get("/versions")
        versions = response.json()["versions"]
        v0 = next(v for v in versions if v["version"] == "v0")
        assert v0["status"] == "deprecated"
        assert v0["sunset_date"] == "2026-04-01"

    async def test_deprecated_entry_has_correct_prefix(self, client, monkeypatch):
        """A deprecated version entry must include the correct prefix."""
        deprecated = (
            VersionEntry(
                version="v0",
                status="deprecated",
                prefix="/v0",
                sunset_date="2026-04-01",
            ),
        )
        monkeypatch.setattr(health_module, "_API_VERSIONS", deprecated)
        response = await client.get("/versions")
        versions = response.json()["versions"]
        v0 = next(v for v in versions if v["version"] == "v0")
        assert v0["prefix"] == "/v0"
