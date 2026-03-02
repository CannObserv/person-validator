"""Health check endpoints."""

from fastapi import APIRouter

from src.api.schemas import HealthResponse

health_router = APIRouter(tags=["health"])


@health_router.get("/health", response_model=HealthResponse)
def health() -> dict:
    """Unauthenticated health check."""
    return {"status": "ok"}
