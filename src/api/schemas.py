"""Shared Pydantic models for the FastAPI service."""

from pydantic import BaseModel, field_validator


class HealthResponse(BaseModel):
    """Response body for health check endpoints."""

    status: str


class FindRequest(BaseModel):
    """Request body for POST /v1/find."""

    name: str

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        """Reject empty or whitespace-only name strings."""
        if not v.strip():
            raise ValueError("name must not be empty or whitespace-only")
        return v


class MatchedName(BaseModel):
    """A matched name record from the database."""

    full_name: str
    name_type: str


class FindResult(BaseModel):
    """A single match result with certainty score."""

    id: str
    certainty: float
    matched_name: MatchedName


class QueryInfo(BaseModel):
    """Metadata about the query that was executed."""

    original: str
    normalized: str
    variants: list[str]


class FindResponse(BaseModel):
    """Response body for POST /v1/find."""

    query: QueryInfo
    results: list[FindResult]
    message: str | None = None
