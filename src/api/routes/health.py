"""Health check and version discovery endpoints."""

from fastapi import APIRouter

from src.api.schemas import HealthResponse, VersionEntry, VersionsResponse

health_router = APIRouter(tags=["health"])

# Registry of API versions served by this application.
# When a version is deprecated, set status="deprecated" and add sunset_date.
_API_VERSIONS: list[VersionEntry] = [
    VersionEntry(version="v1", status="stable", prefix="/v1"),
]


@health_router.get("/health", response_model=HealthResponse)
def health() -> dict:
    """Unauthenticated health check."""
    return {"status": "ok"}


@health_router.get("/versions", response_model=VersionsResponse, response_model_exclude_none=True)
def versions() -> VersionsResponse:
    """Return the list of supported API versions and their deprecation status.

    Each entry includes:
    - ``version``: the version identifier (e.g. ``"v1"``)
    - ``status``: ``"stable"`` or ``"deprecated"``
    - ``prefix``: the URL prefix for this version (e.g. ``"/v1"``)
    - ``sunset_date``: ISO 8601 date on which the version will be removed
      (only present for deprecated versions)
    """
    return VersionsResponse(versions=_API_VERSIONS)
