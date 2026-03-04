"""Tests for FastAPI app factory and basic configuration."""

import logging
import os

import pytest
from fastapi import FastAPI

from src.api.main import create_app


class TestAppFactory:
    """Tests for the create_app factory function."""

    def test_create_app_returns_fastapi_instance(self, tmp_db):
        """create_app() should return a FastAPI instance."""
        os.environ["DATABASE_PATH"] = str(tmp_db)
        try:
            app = create_app()
            assert isinstance(app, FastAPI)
        finally:
            del os.environ["DATABASE_PATH"]

    def test_app_has_v1_routes(self, tmp_db):
        """App should have routes under the /v1/ prefix."""
        os.environ["DATABASE_PATH"] = str(tmp_db)
        try:
            app = create_app()
            paths = [route.path for route in app.routes]
            assert any(p.startswith("/v1") for p in paths)
        finally:
            del os.environ["DATABASE_PATH"]

    def test_app_has_health_endpoint(self, tmp_db):
        """App should have a /health endpoint."""
        os.environ["DATABASE_PATH"] = str(tmp_db)
        try:
            app = create_app()
            paths = [route.path for route in app.routes]
            assert "/health" in paths
        finally:
            del os.environ["DATABASE_PATH"]


class TestLoggingConfiguration:
    """Verify that create_app() installs JSON logging."""

    def test_create_app_configures_root_handler(self, tmp_db):
        """create_app() must attach at least one handler to the root logger."""
        # Clear handlers first to make the assertion meaningful.
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        root.handlers = []
        os.environ["DATABASE_PATH"] = str(tmp_db)
        try:
            create_app()
            assert len(root.handlers) >= 1
        finally:
            del os.environ["DATABASE_PATH"]
            root.handlers = original_handlers

    def test_create_app_handler_is_stream_handler(self, tmp_db):
        """The handler installed by create_app() must be a StreamHandler."""
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        root.handlers = []
        os.environ["DATABASE_PATH"] = str(tmp_db)
        try:
            create_app()
            assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
        finally:
            del os.environ["DATABASE_PATH"]
            root.handlers = original_handlers


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
