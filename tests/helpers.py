"""Shared test utilities."""

import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_django_migrations(db_path: Path) -> None:
    """Run Django migrations in a subprocess against *db_path*.

    Uses a subprocess to avoid pytest-django's DB access guard while
    guaranteeing schema parity with the real database.  The database
    path is passed via the ``DATABASE_PATH`` environment variable
    rather than string interpolation.
    """
    env = {**os.environ, "DATABASE_PATH": str(db_path)}
    # settings.py resolves the DB path from DATABASES, not DATABASE_PATH,
    # so we override DATABASES after setup using the env var.
    script = (
        "import django, os; "
        "os.environ['DJANGO_SETTINGS_MODULE'] = 'src.web.config.settings'; "
        "django.setup(); "
        "from django.conf import settings; "
        "settings.DATABASES['default']['NAME'] = os.environ['DATABASE_PATH']; "
        "from django.core.management import call_command; "
        "call_command('migrate', '--run-syncdb', verbosity=0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Django migrations failed:\n{result.stderr}")
