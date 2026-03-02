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
    PersonAttributeSchema,
    PersonNameSchema,
    PersonReadResponse,
    QueryInfo,
)
from src.core.matching import normalize, search
from src.core.reading import read_person

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


@v1_router.get("/read/{person_id}", response_model=PersonReadResponse)
def read(
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

    names = [
        PersonNameSchema(
            id=n.id,
            name_type=n.name_type,
            full_name=n.full_name,
            given_name=n.given_name,
            middle_name=n.middle_name,
            surname=n.surname,
            prefix=n.prefix,
            suffix=n.suffix,
            is_primary=n.is_primary,
            source=n.source,
            effective_date=n.effective_date,
            end_date=n.end_date,
        )
        for n in detail.names
    ]

    attributes = [
        PersonAttributeSchema(
            id=a.id,
            source=a.source,
            key=a.key,
            value=a.value,
            confidence=a.confidence,
            created_at=a.created_at,
        )
        for a in detail.attributes
    ]

    response = PersonReadResponse(
        id=detail.person.id,
        name=detail.person.name,
        given_name=detail.person.given_name,
        middle_name=detail.person.middle_name,
        surname=detail.person.surname,
        created_at=detail.person.created_at,
        updated_at=detail.person.updated_at,
        names=names,
        attributes=attributes,
    )

    return JSONResponse(content=response.model_dump(), status_code=200)
