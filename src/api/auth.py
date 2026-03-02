"""API key authentication dependency for FastAPI.

Reads the X-API-Key header and delegates validation to the shared
``src.core.key_validation`` module.
"""

import sqlite3

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from src.api.db import get_db
from src.core.key_validation import validate_api_key

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    api_key: str | None = Security(_api_key_header),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """FastAPI dependency that validates an API key.

    Returns a dict with key metadata on success.
    Raises HTTPException 401 (missing/invalid) or 403 (revoked/expired).
    """
    if api_key is None:
        raise HTTPException(status_code=401, detail="API key required")

    result = validate_api_key(api_key, conn)

    if not result.is_valid:
        status = 401 if result.rejection_reason == "invalid" else 403
        detail_map = {
            "invalid": "Invalid API key",
            "revoked": "API key revoked",
            "expired": "API key expired",
        }
        raise HTTPException(status_code=status, detail=detail_map[result.rejection_reason])

    return {"key_id": result.key_id}
