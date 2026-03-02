"""Name normalization and matching logic.

Pure domain functions for normalizing name queries and searching
PersonName records in the shared SQLite database. No API-layer
dependencies — returns plain dicts suitable for any caller.
"""

import re
import sqlite3
from dataclasses import dataclass

_NON_ALPHA_RE = re.compile(r"[^a-zA-Z\s]")
_MULTI_SPACE_RE = re.compile(r"\s+")


def normalize(name: str) -> str:
    """Lowercase, strip non-letter characters, and collapse whitespace."""
    text = name.lower()
    text = _NON_ALPHA_RE.sub("", text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip()
    return text


@dataclass(frozen=True)
class MatchResult:
    """A single person match from the database."""

    person_id: str
    certainty: float
    full_name: str
    name_type: str


def search_variants(conn: sqlite3.Connection, variants: list[str]) -> list[MatchResult]:
    """Search across multiple normalized variants, returning deduplicated results.

    Each variant is searched independently; the best certainty per person
    across all variants is kept.
    """
    best: dict[str, MatchResult] = {}
    for variant in variants:
        for match in search(conn, variant):
            pid = match.person_id
            if pid not in best or match.certainty > best[pid].certainty:
                best[pid] = match
    return sorted(best.values(), key=lambda r: r.certainty, reverse=True)


def search(conn: sqlite3.Connection, normalized: str) -> list[MatchResult]:
    """Search PersonName records for matches against the normalized query.

    Matching strategy:
    1. Exact match on full_name (case-insensitive) → 1.0 for primary, 0.9 for others
    2. Match on given_name + surname combination → 0.8 for primary, 0.7 for others

    Returns results sorted by certainty descending, one entry per person
    (highest certainty wins).
    """
    best: dict[str, MatchResult] = {}

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
        if pid not in best or certainty > best[pid].certainty:
            best[pid] = MatchResult(
                person_id=pid,
                certainty=certainty,
                full_name=row["full_name"],
                name_type=row["name_type"],
            )

    # 2. given_name + surname combination match
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
            if pid in best:
                continue  # Already matched with higher certainty
            certainty = 0.8 if row["is_primary"] else 0.7
            best[pid] = MatchResult(
                person_id=pid,
                certainty=certainty,
                full_name=row["full_name"],
                name_type=row["name_type"],
            )

    return sorted(best.values(), key=lambda r: r.certainty, reverse=True)
