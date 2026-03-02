"""Shared API key validation logic.

Single-sourced validation used by both the Django ORM layer and the
FastAPI raw-SQL layer.  Operates on a raw ``sqlite3.Connection`` for
speed — no ORM overhead on the hot path.
"""

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class KeyValidationResult:
    """Outcome of an API key validation attempt."""

    key_id: str
    is_valid: bool
    rejection_reason: str | None = None


def validate_api_key(
    raw_key: str, conn: sqlite3.Connection, *, commit: bool = True
) -> KeyValidationResult:
    """Validate *raw_key* against the ``keys_apikey`` table.

    On success the ``last_used_at`` and ``updated_at`` columns are bumped
    and the transaction is committed.

    Parameters
    ----------
    raw_key:
        The plaintext API key sent by the client.
    conn:
        An open ``sqlite3.Connection`` with ``row_factory = sqlite3.Row``.
    commit:
        Whether to call ``conn.commit()`` after updating ``last_used_at``.
        Set to ``False`` when the caller manages transactions (e.g. Django
        ORM test wrappers).

    Returns
    -------
    KeyValidationResult
        Always returned — callers inspect ``.is_valid`` and
        ``.rejection_reason`` rather than catching exceptions.
    """
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    row = conn.execute(
        "SELECT id, is_active, expires_at FROM keys_apikey WHERE key_hash = ?",
        (key_hash,),
    ).fetchone()

    if row is None:
        return KeyValidationResult(key_id="", is_valid=False, rejection_reason="invalid")

    if not row["is_active"]:
        return KeyValidationResult(key_id=row["id"], is_valid=False, rejection_reason="revoked")

    if row["expires_at"] is not None:
        raw_expires = row["expires_at"]
        if isinstance(raw_expires, str):
            expires = datetime.fromisoformat(raw_expires)
        else:
            expires = raw_expires
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires <= datetime.now(UTC):
            return KeyValidationResult(key_id=row["id"], is_valid=False, rejection_reason="expired")

    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE keys_apikey SET last_used_at = ?, updated_at = ? WHERE id = ?",
        (now, now, row["id"]),
    )
    if commit:
        conn.commit()

    return KeyValidationResult(key_id=row["id"], is_valid=True)
