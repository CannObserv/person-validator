"""Shared Pydantic models for the FastAPI service."""

from typing import Literal

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


class PersonNameSchema(BaseModel):
    """Schema for a person's name variant."""

    id: str
    name_type: str
    full_name: str
    given_name: str | None = None
    middle_name: str | None = None
    surname: str | None = None
    prefix: str | None = None
    suffix: str | None = None
    is_primary: bool
    source: str
    effective_date: str | None = None
    end_date: str | None = None


class PersonAttributeSchema(BaseModel):
    """Schema for a person enrichment attribute."""

    id: str
    source: str
    key: str
    value: str
    confidence: float
    created_at: str


class VersionEntry(BaseModel):
    """A single API version entry in the /versions response."""

    version: str
    status: Literal["stable", "deprecated"]
    prefix: str
    sunset_date: str | None = None


class VersionsResponse(BaseModel):
    """Response body for GET /versions."""

    versions: list[VersionEntry]


class PersonReadResponse(BaseModel):
    """Response body for GET /v1/read/{id}."""

    id: str
    name: str
    given_name: str | None = None
    middle_name: str | None = None
    surname: str | None = None
    created_at: str
    updated_at: str
    names: list[PersonNameSchema]
    attributes: list[PersonAttributeSchema]
