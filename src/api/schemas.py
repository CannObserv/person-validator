"""Shared Pydantic models for the FastAPI service."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response body for health check endpoints."""

    status: str
