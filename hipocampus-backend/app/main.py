"""
app/main.py

FastAPI application factory and entry point.
This file is the only place that:
  - Creates the FastAPI() instance.
  - Registers CORS middleware (credentials=True for cookie auth).
  - Registers custom exception handlers from core/exceptions.py.
  - Mounts the v1 router under /api/v1.
  - Defines the startup event (opens DB engine, Redis pool, logs ready).
  - Defines the shutdown event (drains DB pool, closes Redis pool).

uvicorn entry point (local dev):
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Docker entry point (production):
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

Used by: uvicorn (directly), Docker CMD, and tests via TestClient/AsyncClient.
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import v1_router
from app.config import get_settings
from app.core.exceptions import (
    InvalidLoginKeyError,
    MemoryConflictError,
    SessionBufferError,
    TokenExpiredError,
    TokenInvalidError,
    invalid_login_key_handler,
    memory_conflict_handler,
    session_buffer_handler,
    token_expired_handler,
    token_invalid_handler,
)
from app.utils.logger import setup_logging

settings = get_settings()

# ---------------------------------------------------------------------------
# Logging — must be configured before anything else logs.
# ---------------------------------------------------------------------------

setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — replaces deprecated @app.on_event("startup"/"shutdown")
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages all resources that must be opened before the first request
    and closed after the last. FastAPI calls the code before `yield` on
    startup and the code after `yield` on shutdown.

    Startup actions:
      - Initialise the async Redis connection pool.
      - Log a ready message so ops teams can see the exact moment the
        server became available.

    Shutdown actions:
      - Drain the DB connection pool (lets Postgres close connections cleanly).
      - Close the Redis pool (avoids TIME_WAIT sockets piling up).

    Parameters:
        app (FastAPI) — the application instance (unused here but required
                        by the lifespan protocol).

    Used by: FastAPI() constructor via lifespan= argument below.
    """
    # ── Startup ─────────────────────────────────────────────────────────────
    logger.info("Hipocampus API starting up…")

    from app.core.redis_client import init_redis_pool
    await init_redis_pool()
    logger.info("Redis pool initialised.")

    # In local dev, create tables automatically so you don't need to run
    # Alembic before the first request. In production this line is a no-op
    # because Alembic migrations already created the tables.
    if settings.AUTO_CREATE_TABLES:
        from app.core.db import create_all_tables
        await create_all_tables()
        logger.info("Database tables verified / created (AUTO_CREATE_TABLES=true).")

    logger.info("Hipocampus API is ready. Listening on /api/v1")

    yield  # ← Application handles requests while suspended here

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Hipocampus API shutting down…")

    from app.core.db import dispose_engine
    from app.core.redis_client import close_redis_pool

    await close_redis_pool()
    logger.info("Redis pool closed.")

    await dispose_engine()
    logger.info("Database engine disposed. Goodbye.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """
    Builds and returns the configured FastAPI application instance.
    Separating creation into a factory function makes it easy for tests
    to call create_app() and get a fresh instance with overridden dependencies.

    Parameters: none
    Returns:    FastAPI — the fully configured application instance.
    Used by:    module level (app = create_app() below), tests/conftest.py.
    """
    application = FastAPI(
        title="Hipocampus API",
        description=(
            "Persistent memory system for AI assistants. "
            "Implements a four-tier hippocampal memory model: "
            "working (Redis), episodic, semantic, and procedural (PostgreSQL + pgvector)."
        ),
        version="1.0.0",
        # Disable the default /docs and /redoc in production by reading an env var.
        # Set DISABLE_DOCS=true in the production docker-compose.
        docs_url=None if os.getenv("DISABLE_DOCS", "false").lower() == "true" else "/docs",
        redoc_url=None if os.getenv("DISABLE_DOCS", "false").lower() == "true" else "/redoc",
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    # allow_credentials=True is required for the browser to send and receive
    # httpOnly cookies cross-origin. It MUST be paired with explicit origins —
    # allow_origins=["*"] is forbidden when credentials=True.
    # settings.CORS_ORIGINS is a comma-separated str; split it here so the
    # field stays a plain string in config.py (avoids pydantic-settings
    # trying to json.loads() a list field from the .env source).
    cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,         # Enables cookie transport
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Set-Cookie"],  # Lets the browser read the cookie header
    )

    # ── Exception handlers ───────────────────────────────────────────────────
    # Each handler maps one custom exception class to a clean JSON response.
    # Adding a new exception type means: define it in core/exceptions.py,
    # write its handler there, and register it here.
    application.add_exception_handler(InvalidLoginKeyError, invalid_login_key_handler)
    application.add_exception_handler(TokenExpiredError, token_expired_handler)
    application.add_exception_handler(TokenInvalidError, token_invalid_handler)
    application.add_exception_handler(MemoryConflictError, memory_conflict_handler)
    application.add_exception_handler(SessionBufferError, session_buffer_handler)

    # ── Routers ──────────────────────────────────────────────────────────────
    # All routes are under /api/v1 so future /api/v2 can coexist without conflict.
    application.include_router(v1_router, prefix="/api/v1")

    return application


# ---------------------------------------------------------------------------
# Module-level app instance — what uvicorn imports.
# ---------------------------------------------------------------------------

app = create_app()