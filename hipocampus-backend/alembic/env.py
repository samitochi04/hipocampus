"""
alembic/env.py

Alembic migration runtime configuration.
This file is executed by Alembic on every `alembic` CLI command.

Key responsibilities:
  1. Loads the DB URL from app settings (never hardcoded).
  2. Imports Base.metadata via app.models so autogenerate can diff
     every table defined in the project automatically.
  3. Supports both offline mode (generates SQL without a live DB connection)
     and online mode (runs migrations against a live DB via asyncpg).

Async note: Alembic's autogenerate and migration execution require a
synchronous connection. We use run_sync() inside an async context to
bridge asyncpg (async driver) with Alembic's sync migration API.
This is the officially recommended pattern for asyncpg + Alembic.

Used by: every `alembic` CLI command (upgrade, downgrade, revision, etc.)
"""

import asyncio
from logging.config import fileConfig

from alembic import context # type: ignore
from sqlalchemy import pool # type: ignore
from sqlalchemy.engine import Connection # type: ignore
from sqlalchemy.ext.asyncio import create_async_engine # type: ignore

# ---------------------------------------------------------------------------
# Alembic Config object — provides access to alembic.ini values.
# ---------------------------------------------------------------------------
config = context.config

# ---------------------------------------------------------------------------
# Logging — use the INI file's [loggers] section if present.
# ---------------------------------------------------------------------------
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import our declarative Base so Alembic sees every table in metadata.
# app/models/__init__.py imports all model classes, which registers them
# on Base.metadata. Importing Base here is enough.
# ---------------------------------------------------------------------------
from app.core.db import Base  # noqa: E402
import app.models  # noqa: E402, F401 — side-effect import to register all tables

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# DB URL — read from app settings, not from alembic.ini, so we have a
# single source of truth for the connection string.
# ---------------------------------------------------------------------------
from app.config import get_settings  # noqa: E402

settings = get_settings()
DB_URL = settings.DB_URL


# ---------------------------------------------------------------------------
# Offline mode — generates SQL migration scripts without a live DB.
# Useful for reviewing migrations or running them via DBA tooling.
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """
    Runs Alembic in offline mode: emits SQL statements to stdout or a file
    rather than executing them against a live database.
    Triggered by: `alembic upgrade head --sql > migration.sql`

    Parameters: none — reads all config from the module-level variables above.
    Returns:    none
    Used by:    Alembic CLI (offline mode).
    """
    context.configure(
        url=DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Include schema in generated SQL so it works against non-default schemas.
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — runs migrations directly against the live database.
# ---------------------------------------------------------------------------


def do_run_migrations(connection: Connection) -> None:
    """
    Executes the pending migrations using an already-open synchronous
    connection. Called by run_migrations_online() via run_sync().

    Parameters:
        connection (Connection) — a synchronous SQLAlchemy connection
                                  obtained from the async engine via run_sync().
    Returns:    none
    Used by:    run_migrations_online()
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detect column type changes (e.g. VARCHAR length changes) during autogenerate.
        compare_type=True,
        # Detect server default changes.
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Creates an async engine, connects, and runs migrations synchronously
    via run_sync(). This is the recommended pattern for asyncpg + Alembic.

    NullPool is used instead of the regular connection pool because Alembic
    creates a single connection, runs migrations, and exits — pooling adds
    no benefit and can leave connections open after the CLI exits.

    Parameters: none
    Returns:    none
    Used by:    the module-level if/else block below (online migration path).
    """
    connectable = create_async_engine(
        DB_URL,
        poolclass=pool.NullPool,  # No connection pooling for migration runs
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# ---------------------------------------------------------------------------
# Entry point — Alembic calls this file as a script.
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())