"""
tests/conftest.py

Shared pytest fixtures available to every test module automatically.
No imports needed in test files — pytest discovers and injects these by name.

Three fixture layers:
  1. DB — a real async Postgres session wrapped in a rollback-on-teardown
     transaction so each test starts with a clean slate without truncating tables.
  2. Redis — a fakeredis instance that behaves like the real client but lives
     in memory, so tests never need a running Redis server.
  3. Qwen — a monkeypatched QwenClient that returns canned responses, so
     tests never make live API calls and are fully deterministic.
  4. HTTP client — an AsyncClient pointed at the test app with all
     dependency overrides wired in.

pytest.ini must contain:
    [pytest]
    asyncio_mode = auto
This replaces the deprecated session-scoped event_loop fixture.
"""

# ── Environment overrides ──────────────────────────────────────────────────
# These MUST be set before any app module is imported so that get_settings()
# caches the correct values when it is first called during the imports below.
#
# COOKIE_SECURE=false: httpx won't store or send a Secure cookie over plain
#   http://test (the base URL used by ASGITransport). Without this, every
#   register/login response sets a cookie the client silently ignores, and
#   every subsequent authenticated request returns 401.
#
# AUTO_CREATE_TABLES=false: the lifespan startup event is skipped for table
#   creation; the test_engine fixture handles schema setup instead.
import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ── Cookie patch ───────────────────────────────────────────────────────────
# Must happen before any app module is imported.
#
# httpx follows RFC 6265: cookies with the Secure attribute received over
# http:// are silently discarded. The test base URL is "http://test"
# (ASGITransport doesn't use TLS), so any cookie set with secure=True is
# never stored and subsequent authenticated requests return 401.
#
# We patch Starlette's Response.set_cookie at the class level to always
# force secure=False. This runs before any app import, so every set_cookie
# call for the entire test session — including the register and login routes
# — uses secure=False, and httpx stores the cookie correctly.
from starlette.responses import Response as _StarletteResponse

_orig_set_cookie = _StarletteResponse.set_cookie


def _insecure_set_cookie(self, key, value="", **kwargs):
    """Wrapper that forces secure=False so httpx stores cookies over http://."""
    kwargs["secure"] = False
    return _orig_set_cookie(self, key, value, **kwargs)


_StarletteResponse.set_cookie = _insecure_set_cookie
# ──────────────────────────────────────────────────────────────────────────

from app.core.db import Base, get_db
from app.core.redis_client import get_redis_client
from app.main import create_app

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

# Use the same Postgres instance as docker-compose but a separate database.
# The docker-compose service name resolves to localhost when running tests
# locally with `docker compose up postgres -d`.
# Override with: export TEST_DB_URL=postgresql+asyncpg://...
TEST_DB_URL = os.getenv(
    "TEST_DB_URL",
    "postgresql+asyncpg://hipocampus:hipocampus@localhost:5432/hipocampus_test",
)


@pytest_asyncio.fixture
async def test_engine():
    """
    Creates an async engine using NullPool for each test function.

    NullPool is the key: instead of maintaining a pool of reusable asyncpg
    connections, every DB call opens a fresh connection and closes it
    immediately. This means connections are always created on the current
    test's event loop — there is no pooled connection from a previous loop
    to cause 'Future attached to a different loop' errors.

    The trade-off is slightly slower tests (no connection reuse), but it is
    the only approach that works reliably when pytest-asyncio gives each test
    its own event loop (which is the default in 0.21+).

    Creates the pgvector extension and all tables on setup.
    Drops all tables on teardown so the next test starts clean.

    Used by: db_session fixture.
    """
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Provides a fresh AsyncSession per test.

    Deliberately avoids binding the session to a specific connection or
    manually calling conn.begin() — both patterns cause asyncpg to raise
    'cannot perform operation: another operation is in progress' because
    asyncpg does not allow two concurrent operations on the same connection.

    Cleanup strategy: override_get_db (in the client fixture) never calls
    commit(), so every write the route handlers make is uncommitted at the
    end of the test. Rolling back here discards those writes, giving each
    test a clean slate without needing TRUNCATE or SAVEPOINTs.

    Parameters:
        test_engine — session-scoped engine from the test_engine fixture.

    Yields:
        AsyncSession — independent session with autoflush=False so explicit
                       flush() calls in service code work as expected.

    Used by: client fixture (injected into override_get_db).
    """
    factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,   # Service code calls flush() explicitly; don't double-flush
        autocommit=False,
    )
    async with factory() as session:
        yield session
        # Roll back any uncommitted writes so the next test starts clean.
        await session.rollback()


# ---------------------------------------------------------------------------
# Redis fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def fake_redis() -> AsyncGenerator[FakeRedis, None]:
    """
    Provides a FakeRedis instance that implements the full redis.asyncio API
    in memory. Tests can call push_message(), get_buffer(), etc. without
    a running Redis server.

    Yields:
        FakeRedis — in-memory Redis compatible client, reset between tests
                    because each fixture call creates a new instance.

    Used by: client fixture (wired into get_redis_client override).
    """
    redis = FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


# ---------------------------------------------------------------------------
# Qwen mock fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_qwen():
    """
    Monkeypatches the three Qwen API functions used during a chat turn so
    tests never make live HTTP calls. Returns canned, deterministic responses.

    Patched functions:
        qwen_router.generate()       → returns a fixed assistant reply string
        qwen_router.expand_query()   → returns 3 fixed query expansion strings
        qwen_router.embed_text()     → returns a 1536-element list of 0.1 floats

    Yields:
        dict — the three AsyncMock objects keyed by function name, so individual
               tests can override return values or assert call counts.

    Used by: test_chat.py, test_memory.py (any test that triggers process_turn).
    """
    fake_embedding = [0.1] * 1536

    with (
        patch(
            "app.services.memory_engine.qwen_router.generate",
            new_callable=AsyncMock,
            return_value="This is a mocked LLM response for testing.",
        ) as mock_generate,
        patch(
            "app.services.memory_engine.qwen_router.expand_query",
            new_callable=AsyncMock,
            return_value=["query variant one", "query variant two", "query variant three"],
        ) as mock_expand,
        patch(
            "app.services.memory_engine.qwen_router.embed_text",
            new_callable=AsyncMock,
            return_value=fake_embedding,
        ) as mock_embed,
    ):
        yield {
            "generate": mock_generate,
            "expand_query": mock_expand,
            "embed_text": mock_embed,
        }


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session, fake_redis) -> AsyncGenerator[AsyncClient, None]:
    """
    Provides a fully wired AsyncClient pointing at the test FastAPI app.
    Dependency overrides replace the real DB session and Redis client with
    the test fixtures so no live infrastructure is needed.

    Parameters:
        db_session  — injected rollback-wrapped DB session.
        fake_redis  — injected in-memory FakeRedis instance.

    Yields:
        AsyncClient — httpx async client with base_url set to the test app.
                      Use it exactly like a real HTTP client:
                          response = await client.post("/api/v1/auth/register", json={...})

    Used by: every test file.
    """
    app = create_app()

    # Override get_db() to use the test session.
    # Deliberately does NOT commit — all writes stay uncommitted so the
    # db_session fixture can roll them back after the test ends.
    async def override_get_db():
        try:
            yield db_session
        except Exception:
            await db_session.rollback()
            raise

    # Override get_redis_client() to use FakeRedis.
    def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        yield ac