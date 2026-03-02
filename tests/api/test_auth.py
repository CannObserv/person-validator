"""Tests for API key authentication dependency."""

import sqlite3
from datetime import UTC, datetime

import pytest


@pytest.mark.anyio
class TestAPIKeyAuth:
    """Tests for the X-API-Key header authentication."""

    async def test_missing_key_returns_401(self, client):
        """Request without X-API-Key header should return 401."""
        response = await client.get("/v1/health")
        assert response.status_code == 401
        assert "API key required" in response.json()["detail"]

    async def test_invalid_key_returns_401(self, client):
        """Request with an unknown API key should return 401."""
        response = await client.get("/v1/health", headers={"X-API-Key": "bogus-key"})
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    async def test_revoked_key_returns_403(self, client, tmp_db, revoked_api_key):
        """Request with a revoked (is_active=False) key should return 403."""
        response = await client.get("/v1/health", headers={"X-API-Key": revoked_api_key})
        assert response.status_code == 403
        assert "revoked" in response.json()["detail"].lower()

    async def test_expired_key_returns_403(self, client, tmp_db, expired_api_key):
        """Request with an expired key should return 403."""
        response = await client.get("/v1/health", headers={"X-API-Key": expired_api_key})
        assert response.status_code == 403
        assert "expired" in response.json()["detail"].lower()

    async def test_valid_key_passes(self, client, tmp_db, valid_api_key):
        """Request with a valid API key should pass authentication."""
        response = await client.get("/v1/health", headers={"X-API-Key": valid_api_key})
        assert response.status_code == 200

    async def test_valid_key_updates_last_used_at(self, client, tmp_db, valid_api_key):
        """Successful auth should update last_used_at."""
        before = datetime.now(UTC)
        await client.get("/v1/health", headers={"X-API-Key": valid_api_key})

        conn = sqlite3.connect(str(tmp_db))
        row = conn.execute(
            "SELECT last_used_at FROM keys_apikey WHERE id = ?",
            ("01TESTKEY000000000000000001",),
        ).fetchone()
        conn.close()
        assert row[0] is not None
        last_used = datetime.fromisoformat(row[0])
        assert last_used >= before


@pytest.mark.anyio
class TestV1HealthWithAuth:
    """Tests for the authenticated /v1/health endpoint."""

    async def test_v1_health_returns_ok(self, client, tmp_db, valid_api_key):
        """GET /v1/health with valid key should return {"status": "ok"}."""
        response = await client.get("/v1/health", headers={"X-API-Key": valid_api_key})
        assert response.json() == {"status": "ok"}
