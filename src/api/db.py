"""SQLite connection management for the FastAPI service.

Direct SQLite access via the stdlib sqlite3 module. Django owns the schema;
the API service reads/writes the same database file.
"""

import sqlite3
from pathlib import Path


def get_db_path() -> Path:
    """Return the path to the shared SQLite database.

    Derives the path from the Django settings BASE_DIR convention:
    the database lives at ``<project_root>/db.sqlite3``.
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / "db.sqlite3"


def get_connection() -> sqlite3.Connection:
    """Open a new SQLite connection with WAL mode and Row factory.

    Callers are responsible for closing the connection.
    """
    conn = sqlite3.connect(str(get_db_path()))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn
