"""Root-level test fixtures."""

import shutil
import sqlite3

import pytest

from tests.helpers import run_django_migrations


@pytest.fixture(scope="session")
def _migrated_db_template(tmp_path_factory):
    """Run Django migrations once per session and return the DB path.

    Other fixtures copy this file to avoid paying the subprocess cost
    per test.
    """
    db_path = tmp_path_factory.mktemp("db_template") / "db.sqlite3"
    run_django_migrations(db_path)

    # Insert a dummy auth_user row so foreign keys to user_id resolve.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT OR IGNORE INTO auth_user"
        " (id, username, password, is_superuser, is_staff, is_active,"
        "  first_name, last_name, email, date_joined)"
        " VALUES (1, 'testuser', '', 0, 0, 1, '', '', 'test@example.com',"
        "  datetime('now'))"
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def migrated_db(tmp_path, _migrated_db_template):
    """Return a per-test copy of the migrated database template.

    Each test gets its own file so writes are isolated.
    """
    db_path = tmp_path / "db.sqlite3"
    shutil.copy2(_migrated_db_template, db_path)
    return db_path
