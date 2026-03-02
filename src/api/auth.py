"""API key authentication dependency for FastAPI.

Reads the X-API-Key header, hashes it (SHA-256), and validates against
the keys_apikey table in the shared SQLite database.
"""

import hashlib
from datetime import UTC, datetime

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from src.api.db import get_connection

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Security(_api_key_header)) -> dict:
    """FastAPI dependency that validates an API key.

    Returns a dict with key metadata on success.
    Raises HTTPException 401 (missing/invalid) or 403 (revoked/expired).
    """
    if api_key is None:
        raise HTTPException(status_code=401, detail="API key required")

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, is_active, expires_at FROM keys_apikey WHERE key_hash = ?",
            (key_hash,),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=401, detail="Invalid API key")

        if not row["is_active"]:
            raise HTTPException(status_code=403, detail="API key revoked")

        if row["expires_at"] is not None:
            expires = datetime.fromisoformat(row["expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            if expires <= datetime.now(UTC):
                raise HTTPException(status_code=403, detail="API key expired")

        # Update last_used_at
        now = datetime.now(UTC).isoformat()
        conn.execute(
            "UPDATE keys_apikey SET last_used_at = ?, updated_at = ? WHERE id = ?",
            (now, now, row["id"]),
        )
        conn.commit()

        return {"key_id": row["id"]}
    finally:
        conn.close()
