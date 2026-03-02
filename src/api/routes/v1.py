"""Versioned v1 API routes (authenticated)."""

import re
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

v1_router = APIRouter(
    prefix="/v1",
    tags=["v1"],
    dependencies=[Depends(require_api_key)],
)


def _normalize(name: str) -> str:
    """Lowercase, strip punctuation, and collapse whitespace."""
    text = name.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _search(conn: sqlite3.Connection, normalized: str) -> list[FindResult]:
    """Search PersonName records for matches against the normalized query.

    Matching strategy:
    1. Exact match on full_name (case-insensitive) → 1.0 for primary, 0.9 for others
    2. Match on given_name + surname combination → 0.8 for primary, 0.7 for others

    Returns results sorted by certainty descending.
    """
    results: list[FindResult] = []
    seen_person_ids: dict[str, float] = {}

    # 1. Exact full_name match (case-insensitive)
    rows = conn.execute(
        "SELECT pn.full_name, pn.name_type, pn.is_primary, p.id AS person_id"
        " FROM persons_personname pn"
        " JOIN persons_person p ON p.id = pn.person_id"
        " WHERE LOWER(pn.full_name) = ?",
        (normalized,),
    ).fetchall()

    for row in rows:
        certainty = 1.0 if row["is_primary"] else 0.9
        pid = row["person_id"]
        if pid not in seen_person_ids or certainty > seen_person_ids[pid]:
            seen_person_ids[pid] = certainty
            # Remove any existing lower-certainty entry for this person
            results = [r for r in results if r.id != pid]
            results.append(
                FindResult(
                    id=pid,
                    certainty=certainty,
                    matched_name=MatchedName(
                        full_name=row["full_name"],
                        name_type=row["name_type"],
                    ),
                )
            )

    # 2. given_name + surname combination match
    # Split query into parts and try matching
    parts = normalized.split()
    if len(parts) >= 2:
        given = parts[0]
        surname = parts[-1]
        rows = conn.execute(
            "SELECT pn.full_name, pn.name_type, pn.is_primary, p.id AS person_id"
            " FROM persons_personname pn"
            " JOIN persons_person p ON p.id = pn.person_id"
            " WHERE LOWER(pn.given_name) = ? AND LOWER(pn.surname) = ?",
            (given, surname),
        ).fetchall()

        for row in rows:
            pid = row["person_id"]
            if pid in seen_person_ids:
                continue  # Already matched with higher certainty
            certainty = 0.8 if row["is_primary"] else 0.7
            seen_person_ids[pid] = certainty
            results.append(
                FindResult(
                    id=pid,
                    certainty=certainty,
                    matched_name=MatchedName(
                        full_name=row["full_name"],
                        name_type=row["name_type"],
                    ),
                )
            )

    results.sort(key=lambda r: r.certainty, reverse=True)
    return results


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
    normalized = _normalize(body.name)
    variants = [normalized]

    query_info = QueryInfo(
        original=body.name,
        normalized=normalized,
        variants=variants,
    )

    results = _search(conn, normalized)

    response = FindResponse(
        query=query_info,
        results=results,
        message="No matching persons found" if not results else None,
    )

    status_code = 200 if results else 404
    return JSONResponse(content=response.model_dump(), status_code=status_code)
