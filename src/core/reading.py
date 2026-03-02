"""Person read queries (raw SQL against shared SQLite DB)."""

import sqlite3
from dataclasses import dataclass


@dataclass
class PersonRecord:
    """Full person record from the database."""

    id: str
    name: str
    given_name: str | None
    middle_name: str | None
    surname: str | None
    created_at: str
    updated_at: str


@dataclass
class NameRecord:
    """A person name variant record."""

    id: str
    name_type: str
    full_name: str
    given_name: str | None
    middle_name: str | None
    surname: str | None
    prefix: str | None
    suffix: str | None
    is_primary: bool
    source: str
    effective_date: str | None
    end_date: str | None


@dataclass
class AttributeRecord:
    """A person enrichment attribute record."""

    id: str
    source: str
    key: str
    value: str
    confidence: float
    created_at: str


@dataclass
class PersonDetail:
    """Aggregated person detail with names and attributes."""

    person: PersonRecord
    names: list[NameRecord]
    attributes: list[AttributeRecord]


def read_person(conn: sqlite3.Connection, person_id: str) -> PersonDetail | None:
    """Look up a person by ID with all names and attributes.

    Returns ``None`` if the person does not exist.
    """
    row = conn.execute(
        "SELECT id, name, given_name, middle_name, surname, created_at, updated_at"
        " FROM persons_person WHERE id = ?",
        (person_id,),
    ).fetchone()
    if row is None:
        return None

    person = PersonRecord(
        id=row["id"],
        name=row["name"],
        given_name=row["given_name"],
        middle_name=row["middle_name"],
        surname=row["surname"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

    name_rows = conn.execute(
        "SELECT id, name_type, full_name, given_name, middle_name, surname,"
        "  prefix, suffix, is_primary, source, effective_date, end_date"
        " FROM persons_personname WHERE person_id = ?"
        " ORDER BY is_primary DESC, created_at DESC",
        (person_id,),
    ).fetchall()

    names = [
        NameRecord(
            id=r["id"],
            name_type=r["name_type"],
            full_name=r["full_name"],
            given_name=r["given_name"],
            middle_name=r["middle_name"],
            surname=r["surname"],
            prefix=r["prefix"],
            suffix=r["suffix"],
            is_primary=bool(r["is_primary"]),
            source=r["source"],
            effective_date=r["effective_date"],
            end_date=r["end_date"],
        )
        for r in name_rows
    ]

    attr_rows = conn.execute(
        "SELECT id, source, key, value, confidence, created_at"
        " FROM persons_personattribute WHERE person_id = ?"
        " ORDER BY created_at DESC",
        (person_id,),
    ).fetchall()

    attributes = [
        AttributeRecord(
            id=r["id"],
            source=r["source"],
            key=r["key"],
            value=r["value"],
            confidence=r["confidence"],
            created_at=r["created_at"],
        )
        for r in attr_rows
    ]

    return PersonDetail(person=person, names=names, attributes=attributes)
