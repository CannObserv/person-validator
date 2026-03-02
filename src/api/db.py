"""SQLite connection management for the FastAPI service.

Direct SQLite access via the stdlib sqlite3 module. Django owns the schema;
the API service reads/writes the same database file.
"""

import os
import sqlite3
from collections.abc import Generator
from pathlib import Path

_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "db.sqlite3"


def get_db_path() -> Path:
    """Return the path to the shared SQLite database.

    Reads from the ``DATABASE_PATH`` environment variable. Falls back to
    ``<project_root>/db.sqlite3`` when the variable is not set.
    """
    return Path(os.environ.get("DATABASE_PATH", str(_DEFAULT_DB_PATH)))


def get_connection() -> sqlite3.Connection:
    """Open a new SQLite connection with WAL mode and Row factory.

    Callers are responsible for closing the connection.
    """
    conn = sqlite3.connect(str(get_db_path()))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency that yields a request-scoped SQLite connection.

    Usage::

        @router.get("/example")
        def example(conn: sqlite3.Connection = Depends(get_db)):
            ...
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
