# Async SQLAlchemy engine (asyncpg driver) built from settings.DB_URL, async sessionmaker, 
# exposes Base = declarative_base() for all models to inherit

"""
app/core/db.py

Bootstraps the async SQLAlchemy engine and session factory.
All ORM models inherit Base from here.
This module is imported by:
  - app/models/* (to inherit Base)
  - app/dependencies.py (to expose get_db() as a FastAPI Depends)
  - alembic/env.py (to read Base.metadata for autogenerate)
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import ( # type: ignore
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase # type: ignore

from app.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_async_engine(
    settings.DB_URL,
    # Pool configuration — tuned for a single FastAPI worker.
    # Scale pool_size up if you add Gunicorn workers.
    pool_size=10,
    max_overflow=20,
    # Drop idle connections after 30 min so the DB doesn't hit its
    # max_connections limit when the app is quiet.
    pool_recycle=1800,
    # Eagerly validate that a pooled connection is still alive before
    # handing it to a request. Adds a tiny round-trip but prevents
    # "connection was closed" errors after a DB restart.
    pool_pre_ping=True,
    echo=True,  # Set True locally to log every SQL statement
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    # Don't auto-commit or auto-flush — callers decide when to commit,
    # keeping transaction control explicit and predictable.
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Keeps ORM objects usable after session.commit()
)

# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """
    Shared declarative base that every ORM model inherits.
    Importing this class in alembic/env.py lets Alembic's autogenerate
    diff all tables defined anywhere in app/models/ automatically.
    Takes no parameters — SQLAlchemy uses it as a metaclass registry.
    Used by: every file under app/models/*.
    """
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async generator that yields one SQLAlchemy session per request and
    guarantees it is closed when the request is done, even on exceptions.
    Takes no parameters — FastAPI calls it through Depends().
    Used by: app/dependencies.py, which re-exports it so route handlers
    never import core/db.py directly.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_all_tables() -> None:
    """
    Creates every table registered on Base.metadata if it does not already
    exist. Called once in main.py's startup event during local development.
    In production, Alembic migrations are used instead — this function is
    a convenience shortcut only.
    Takes no parameters.
    Used by: app/main.py startup event (dev mode only).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """
    Gracefully closes every connection in the pool.
    Called in main.py's shutdown event so the process exits cleanly
    without leaving open connections on the DB side.
    Takes no parameters.
    Used by: app/main.py shutdown event.
    """
    await engine.dispose()