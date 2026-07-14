"""
XIOPATH — Alembic Environment Configuration
==============================================
Configures Alembic to use the same database URL resolution logic as
core.database.DatabaseManager. Supports SQLite (default) and PostgreSQL
via the DATABASE_URL environment variable.
"""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool, create_engine
from alembic import context

# Ensure the project root is on the path so we can import core modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Alembic Config object — provides access to alembic.ini values
config = context.config

# Set up Python logging from the config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the SQLAlchemy metadata for autogenerate support (future use)
# For now we use raw SQL migrations, but this enables `alembic revision --autogenerate`
# from core.models import Base
# target_metadata = Base.metadata
target_metadata = None


def get_database_url() -> str:
    """
    Resolve the database URL using the same logic as DatabaseManager.
    Priority: DATABASE_URL env var > default SQLite path.
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        db_path = Path("data/xiopath.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{db_path}"
    return db_url


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — generates SQL scripts without
    connecting to the database. Useful for review before applying.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite needs batch mode for ALTER TABLE support
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode — connects to the database and
    applies migrations directly.
    """
    db_url = get_database_url()

    # Use the same pool strategy as DatabaseManager
    if "postgresql" in db_url:
        engine_kwargs = {
            "pool_size": 5,
            "max_overflow": 10,
            "pool_timeout": 30,
        }
    else:
        engine_kwargs = {"poolclass": pool.NullPool}

    connectable = create_engine(db_url, **engine_kwargs)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite needs batch mode for ALTER TABLE support
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
