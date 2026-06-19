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
"""

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest # type: ignore
import pytest_asyncio # type: ignore
from fakeredis.aioredis import FakeRedis # type: ignore
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine # type: ignore

from app.core.db import Base, get_db
from app.core.redis_client import get_redis_client
from app.main import create_app

# ---------------------------------------------------------------------------
# Event loop — one loop per test session (required for async fixtures).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """
    Provides a single asyncio event loop for the entire test session.
    Using scope="session" avoids the overhead of creating and destroying
    a loop for every test function.

    Used by: every async fixture and test via pytest-asyncio.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

# Use an in-memory-style Postgres URL for tests.
# Set TEST_DB_URL in your environment or .env.test to override.
# Defaults to a local test database that should be separate from dev.
import os
TEST_DB_URL = os.getenv(
    "TEST_DB_URL",
    "postgresql+asyncpg://user:pass@localhost:5432/hipocampus_test",
)


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """
    Creates the async SQLAlchemy engine pointing at the test database and
    creates all tables before any test runs. Drops all tables after the
    session ends to leave the test DB clean.

    Scope: session — the engine is shared across all tests for performance.

    Used by: db_session fixture.
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Yields an async DB session that is rolled back after each test.
    This means every test sees a clean database without needing to
    truncate tables between runs.

    Strategy: open a connection, begin a SAVEPOINT, run the test,
    roll back to the SAVEPOINT, then close the connection.

    Parameters:
        test_engine — injected by pytest from the session-scoped fixture above.

    Yields:
        AsyncSession — a transactional session isolated from other tests.

    Used by: all test files via Depends override in the client fixture.
    """
    async_session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with test_engine.connect() as conn:
        await conn.begin()
        async with async_session(bind=conn) as session:
            yield session
        await conn.rollback()


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

    # Override get_db() to use the test session (with rollback isolation).
    async def override_get_db():
        yield db_session

    # Override get_redis_client() to use FakeRedis.
    def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = override_get_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as ac:
        yield ac