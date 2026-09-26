"""How DATABASE_URL is interpreted, and why the pool is small.

These exist because the Aiven cutover broke on both points: the provider hands
out a URL scheme SQLAlchemy 2 rejects, and its free plan has far fewer spare
connections than SQLAlchemy's default pool will open.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import settings

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def reload_database():
    """Reload app.database under a patched URL, then put it back.

    Without the restore, the module keeps an engine built from the fake URL and
    whichever test runs next inherits it - a failure that depends on test order
    and would be thoroughly confusing to debug."""
    import importlib

    from app import database

    def _reload():
        importlib.reload(database)
        return database

    yield _reload
    importlib.reload(database)


def test_the_legacy_postgres_scheme_is_accepted(monkeypatch, reload_database):
    """Several providers still hand out `postgres://`; SQLAlchemy 2 only takes
    `postgresql://`. Pasting the old form into DATABASE_URL used to take the API
    down with an error naming neither the setting nor the provider."""
    monkeypatch.setattr(settings, "database_url", "postgres://u:p@host:5432/db?sslmode=require")
    database = reload_database()

    assert database.DATABASE_URL.startswith("postgresql://")
    assert database.DATABASE_URL.endswith("@host:5432/db?sslmode=require")


def test_postgres_gets_a_pool_small_enough_for_the_plan(monkeypatch, reload_database):
    """Aiven's free plan allows 20 connections and its own agents hold most of
    them. SQLAlchemy's default pool (5 + 10 overflow) would exhaust what's left."""
    monkeypatch.setattr(settings, "database_url", "postgresql://u:p@host:5432/db")
    database = reload_database()

    assert database.engine.pool.size() + database.engine.pool._max_overflow <= 7
    assert database.engine.pool._pre_ping is True


def test_sqlite_keeps_its_own_connect_args(monkeypatch, reload_database):
    """Dev and the test suite run on SQLite, which takes none of the pool
    settings and does need check_same_thread."""
    monkeypatch.setattr(settings, "database_url", "sqlite:///./signal.db")
    database = reload_database()

    assert database.engine.dialect.name == "sqlite"


def test_alembic_accepts_the_legacy_postgres_scheme():
    """The bug this file exists for.

    app/database.py rewrote `postgres://` for the app, but alembic/env.py built
    its own engine from the raw setting - so the API tolerated the URL and every
    deploy still died on `alembic upgrade head` with "Can't load plugin:
    sqlalchemy.dialects:postgres". Offline mode reaches the dialect without
    needing a database; it fails later, on a data-dependent migration, which is
    not what this test is about.
    """
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=BACKEND,
        env={"PATH": "/usr/bin:/bin", "DATABASE_URL": "postgres://u:p@localhost:5432/db"},
        capture_output=True,
        text=True,
    )

    assert "NoSuchModuleError" not in result.stderr
    assert "sqlalchemy.dialects:postgres" not in result.stderr
