"""Integration-test fixtures — scratch database per doc 06 §10.

Every integration test runs against a freshly created, empty PostgreSQL
database (INV-TEST-SCHEMA-1) reached only via ``DATABASE_URL`` (D-016: Neon
Postgres in-sandbox, ``postgres:17`` service containers in CI). The fixture:

1. connects to the database named in ``DATABASE_URL`` as an admin channel,
2. ``CREATE DATABASE`` a uniquely named scratch database,
3. yields a URL pointing at that scratch database, and
4. drops it afterwards (``WITH (FORCE)`` to evict stray connections).

The ``CREATE DATABASE`` here is test *infrastructure* (a blank container for
the real Alembic chain), not schema fabrication: INV-TEST-SCHEMA-1 bans
fabricated **tables**; the schema itself may only ever come from
``persistence/migrations/`` (INV-SCHEMA-1).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from xiosync.persistence.database import validated_psycopg_url


def _admin_url() -> str:
    """The operator-supplied PostgreSQL URL, or skip if none is configured."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        pytest.skip(
            "DATABASE_URL is not set — integration tests require a real "
            "PostgreSQL database (doc 06 §10; D-016). CI MUST set it: a "
            "skip here is only acceptable for local unit-only runs."
        )
    return validated_psycopg_url(url)


@pytest.fixture()
def scratch_database_url() -> Iterator[str]:
    """Yield a URL to a freshly created, empty scratch database, then drop it."""
    admin_url = make_url(_admin_url())
    scratch_name = f"xiosync_test_{uuid.uuid4().hex}"

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            # scratch_name is generated from uuid4 hex above — not user input.
            connection.execute(text(f'CREATE DATABASE "{scratch_name}"'))
        try:
            yield admin_url.set(database=scratch_name).render_as_string(hide_password=False)
        finally:
            with admin_engine.connect() as connection:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)'))
    finally:
        admin_engine.dispose()
