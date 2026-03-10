"""Name normalization and matching logic.

Pure domain functions for normalizing name queries and searching
PersonName records in the shared SQLite database. No API-layer
dependencies — returns plain dicts suitable for any caller.
"""

import re
import sqlite3
from dataclasses import dataclass

from src.core.pipeline.base import WeightedVariant

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


def search(conn: sqlite3.Connection, variants: list[WeightedVariant]) -> list[MatchResult]:
    """Search PersonName records for matches against weighted name variants.

    Executes two batch queries across all variants:
    1. Exact full_name match → base certainty 1.0 primary / 0.9 other
    2. given_name + surname pair match → base certainty 0.8 primary / 0.7 other

    Final certainty = base_certainty × variant.weight.

    Returns results sorted by certainty descending, one entry per person
    (highest certainty across all variants wins).
    """
    if not variants:
        return []

    weight_map = {v.name: v.weight for v in variants}
    variant_names = [v.name for v in variants]

    best: dict[str, MatchResult] = {}

    # 1. Batch exact full_name match
    placeholders = ",".join("?" * len(variant_names))
    rows = conn.execute(
        f"SELECT pn.full_name, pn.name_type, pn.is_primary, p.id AS person_id"
        f" FROM persons_personname pn"
        f" JOIN persons_person p ON p.id = pn.person_id"
        f" WHERE LOWER(pn.full_name) IN ({placeholders})",
        variant_names,
    ).fetchall()

    for row in rows:
        base = 1.0 if row["is_primary"] else 0.9
        weight = weight_map.get(row["full_name"].lower(), 1.0)
        certainty = base * weight
        pid = row["person_id"]
        if pid not in best or certainty > best[pid].certainty:
            best[pid] = MatchResult(
                person_id=pid,
                certainty=certainty,
                full_name=row["full_name"],
                name_type=row["name_type"],
            )

    # 2. Batch given_name + surname pair match.
    # For each pair, track the maximum weight across all variants that produce it.
    pair_weights: dict[tuple[str, str], float] = {}
    for v in variants:
        parts = v.name.split()
        if len(parts) >= 2:
            pair = (parts[0], parts[-1])
            pair_weights[pair] = max(pair_weights.get(pair, 0.0), v.weight)

    pairs = list(pair_weights.keys())

    if pairs:
        pair_clauses = " OR ".join(
            "(LOWER(pn.given_name) = ? AND LOWER(pn.surname) = ?)" for _ in pairs
        )
        params = [val for pair in pairs for val in pair]
        rows = conn.execute(
            f"SELECT pn.full_name, pn.name_type, pn.is_primary, p.id AS person_id,"
            f" pn.given_name, pn.surname"
            f" FROM persons_personname pn"
            f" JOIN persons_person p ON p.id = pn.person_id"
            f" WHERE {pair_clauses}",
            params,
        ).fetchall()

        for row in rows:
            pid = row["person_id"]
            if pid in best:
                continue
            base = 0.8 if row["is_primary"] else 0.7
            given = (row["given_name"] or "").lower()
            surname = (row["surname"] or "").lower()
            weight = pair_weights.get((given, surname), 0.0)
            certainty = base * weight
            best[pid] = MatchResult(
                person_id=pid,
                certainty=certainty,
                full_name=row["full_name"],
                name_type=row["name_type"],
            )

    return sorted(best.values(), key=lambda r: r.certainty, reverse=True)
