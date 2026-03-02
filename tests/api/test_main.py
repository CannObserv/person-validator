"""Tests for FastAPI app factory and basic configuration."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI


class TestAppFactory:
    """Tests for the create_app factory function."""

    def test_create_app_returns_fastapi_instance(self, tmp_db):
        """create_app() should return a FastAPI instance."""
        with patch("src.api.db.get_db_path", return_value=tmp_db):
            from src.api.main import create_app

            app = create_app()
            assert isinstance(app, FastAPI)

    def test_app_has_v1_routes(self, tmp_db):
        """App should have routes under the /v1/ prefix."""
        with patch("src.api.db.get_db_path", return_value=tmp_db):
            from src.api.main import create_app

            app = create_app()
            paths = [route.path for route in app.routes]
            assert any(p.startswith("/v1") for p in paths)

    def test_app_has_health_endpoint(self, tmp_db):
        """App should have a /health endpoint."""
        with patch("src.api.db.get_db_path", return_value=tmp_db):
            from src.api.main import create_app

            app = create_app()
            paths = [route.path for route in app.routes]
            assert "/health" in paths


@pytest.mark.anyio
class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    async def test_health_returns_200(self, client):
        """GET /health should return 200."""
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_returns_ok_status(self, client):
        """GET /health should return {"status": "ok"}."""
        response = await client.get("/health")
        assert response.json() == {"status": "ok"}

    async def test_health_does_not_require_auth(self, client):
        """GET /health should not require an API key."""
        response = await client.get("/health")
        assert response.status_code == 200
