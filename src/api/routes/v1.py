"""Versioned v1 API routes (authenticated)."""

import sqlite3
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
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
from src.core.pipeline.input_classification import InputClassification
from src.core.pipeline.name_parsing import NameParsing
from src.core.pipeline.nickname_expansion import NicknameExpansion
from src.core.pipeline.title_extraction import TitleExtraction
from src.core.reading import read_person

_registry = StageRegistry()
_registry.register("input_classification", InputClassification)
_registry.register("basic_normalization", BasicNormalization)
_registry.register("name_parsing", NameParsing)
_registry.register("nickname_expansion", NicknameExpansion)
_registry.register("title_extraction", TitleExtraction)
_default_pipeline = _registry.build_pipeline(
    [
        "input_classification",
        "basic_normalization",
        "name_parsing",
        "nickname_expansion",
        "title_extraction",
    ]
)

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

    if pipeline_result.is_valid_name is False:
        raise HTTPException(
            status_code=422,
            detail=[
                {"type": "invalid_input", "loc": ["body", "name"], "msg": msg}
                for msg in pipeline_result.messages
            ],
        )

    normalized = pipeline_result.resolved

    # Deduplicate variants by name, keeping the highest weight.
    # resolved always leads with weight 1.0.
    seen: dict[str, float] = {normalized: 1.0}
    for v in pipeline_result.variants:
        if v.name not in seen or v.weight > seen[v.name]:
            seen[v.name] = v.weight
    unique_variants = [WeightedVariant(name=name, weight=weight) for name, weight in seen.items()]

    query_info = QueryInfo(
        original=body.name,
        normalized=normalized,
        variants=[v.name for v in unique_variants],
    )

    matches = search(conn, unique_variants)
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

    messages = list(pipeline_result.messages)
    if not results:
        messages.append("No matching persons found")

    response = FindResponse(
        query=query_info,
        results=results,
        messages=messages,
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
