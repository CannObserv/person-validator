"""Versioned v1 API routes (authenticated)."""

import sqlite3

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
    QueryInfo,
)
from src.core.matching import normalize, search

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
    normalized = normalize(body.name)
    variants = [normalized]

    query_info = QueryInfo(
        original=body.name,
        normalized=normalized,
        variants=variants,
    )

    matches = search(conn, normalized)
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
