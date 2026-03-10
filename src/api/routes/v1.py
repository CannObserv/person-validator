"""Versioned v1 API routes (authenticated)."""

import sqlite3
from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.api.auth import require_api_key
from src.api.db import get_db
from src.api.schemas import (
    FindRequest,
    FindResponse,
    FindResult,
    HealthResponse,
    MatchedName,
    PersonAttributeSchema,
    PersonNameSchema,
    PersonReadResponse,
    QueryInfo,
)
from src.core.matching import search
from src.core.pipeline import BasicNormalization, StageRegistry, WeightedVariant
from src.core.reading import read_person

# Assemble the default pipeline via the registry so stage order is
# configuration-driven and new stages require zero endpoint changes.
_registry = StageRegistry()
_registry.register("basic_normalization", BasicNormalization)
_default_pipeline = _registry.build_pipeline(["basic_normalization"])

v1_router = APIRouter(
    prefix="/v1",
    tags=["v1"],
    dependencies=[Depends(require_api_key)],
)


@v1_router.get("/health", response_model=HealthResponse, tags=["health"])
def v1_health() -> dict:
    """Authenticated health check for the v1 API."""
    return {"status": "ok"}


@v1_router.post("/find", response_model=FindResponse)
def find(
    body: FindRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    """Find persons matching a name query."""
    pipeline_result = _default_pipeline.run(body.name)
    normalized = pipeline_result.resolved
    # resolved is always searched first at full weight; stage-produced variants follow.
    # Build a deduplicated list of WeightedVariants keyed by name; the first
    # occurrence (resolved at weight 1.0) wins for any duplicated name.
    resolved_variant = WeightedVariant(name=normalized, weight=1.0)
    seen: dict[str, WeightedVariant] = {resolved_variant.name: resolved_variant}
    for v in pipeline_result.variants:
        if v.name not in seen:
            seen[v.name] = v
    weighted_variants: list[WeightedVariant] = list(seen.values())

    query_info = QueryInfo(
        original=body.name,
        normalized=normalized,
        variants=[v.name for v in weighted_variants],
    )

    matches = search(conn, weighted_variants)
    results = [
        FindResult(
            id=m.person_id,
            certainty=m.certainty,
            matched_name=MatchedName(
                full_name=m.full_name,
                name_type=m.name_type,
            ),
        )
        for m in matches
    ]

    response = FindResponse(
        query=query_info,
        results=results,
        message="No matching persons found" if not results else None,
    )

    status_code = 200 if results else 404
    return JSONResponse(content=response.model_dump(), status_code=status_code)


@v1_router.get("/read/{person_id}", response_model=PersonReadResponse)
def get_person(
    person_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    """Return a full person record by ID."""
    detail = read_person(conn, person_id)
    if detail is None:
        return JSONResponse(
            content={"message": "Person not found"},
            status_code=404,
        )

    names = [PersonNameSchema(**asdict(n)) for n in detail.names]
    attributes = [PersonAttributeSchema(**asdict(a)) for a in detail.attributes]
    response = PersonReadResponse(**asdict(detail.person), names=names, attributes=attributes)

    return JSONResponse(content=response.model_dump(), status_code=200)
