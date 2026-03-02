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


def search(conn: sqlite3.Connection, variants: list[str]) -> list[MatchResult]:
    """Search PersonName records for matches against one or more normalized variants.

    Accepts a list of normalized name strings and executes two batch queries:
    1. Exact full_name match (IN clause) → certainty 1.0 primary / 0.9 other
    2. given_name + surname combination (OR-expanded) → 0.8 primary / 0.7 other

    Returns results sorted by certainty descending, one entry per person
    (highest certainty across all variants wins).
    """
    if not variants:
        return []

    best: dict[str, MatchResult] = {}

    # 1. Batch exact full_name match
    placeholders = ",".join("?" * len(variants))
    rows = conn.execute(
        f"SELECT pn.full_name, pn.name_type, pn.is_primary, p.id AS person_id"
        f" FROM persons_personname pn"
        f" JOIN persons_person p ON p.id = pn.person_id"
        f" WHERE LOWER(pn.full_name) IN ({placeholders})",
        variants,
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

    # 2. Batch given_name + surname match
    # Build unique (given, surname) pairs from all multi-word variants.
    pairs: list[tuple[str, str]] = list(
        dict.fromkeys((parts[0], parts[-1]) for v in variants if len(parts := v.split()) >= 2)
    )

    if pairs:
        # Expand to: (LOWER(given)=? AND LOWER(surname)=?) OR ...
        pair_clauses = " OR ".join(
            "(LOWER(pn.given_name) = ? AND LOWER(pn.surname) = ?)" for _ in pairs
        )
        params = [val for pair in pairs for val in pair]
        rows = conn.execute(
            f"SELECT pn.full_name, pn.name_type, pn.is_primary, p.id AS person_id"
            f" FROM persons_personname pn"
            f" JOIN persons_person p ON p.id = pn.person_id"
            f" WHERE {pair_clauses}",
            params,
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
