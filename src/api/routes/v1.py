"""Versioned v1 API routes (authenticated)."""

from fastapi import APIRouter, Depends

from src.api.auth import require_api_key
from src.api.schemas import HealthResponse

v1_router = APIRouter(
    prefix="/v1",
    tags=["v1"],
    dependencies=[Depends(require_api_key)],
)


@v1_router.get("/health", response_model=HealthResponse, tags=["health"])
def v1_health() -> dict:
    """Authenticated health check for the v1 API."""
    return {"status": "ok"}
