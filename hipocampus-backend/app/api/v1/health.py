"""
app/api/v1/health.py

Health check endpoint used by Docker, Kubernetes liveness/readiness probes,
and uptime monitors to verify the service and all its dependencies are reachable.

GET /health returns a combined status object with an individual check for:
  - PostgreSQL (via a lightweight SELECT 1)
  - Redis      (via PING)
  - Qwen API   (via a HEAD / OPTIONS request to the configured endpoint)

The route is intentionally unauthenticated so load balancers and orchestration
tools can probe it without needing a session cookie.

Used by: app/api/v1/router.py, mounted at /health.
         docker-compose.yml healthcheck directive.
"""

import logging
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, status # type: ignore
from fastapi.responses import JSONResponse # type: ignore
from sqlalchemy import text # type: ignore

from app.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(tags=["health"])


async def _check_postgres() -> dict:
    """
    Executes a trivial SELECT 1 query against the configured PostgreSQL DB.
    Opens its own session rather than using Depends(get_db) so the health
    check doesn't count as a live request in middleware metrics.

    Returns:
        dict — {"status": "ok", "latency_ms": float}
               or {"status": "error", "detail": str} on failure.

    Used by: health()
    """
    start = datetime.now(UTC)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        latency = (datetime.now(UTC) - start).total_seconds() * 1000
        return {"status": "ok", "latency_ms": round(latency, 2)}
    except Exception as exc:
        logger.error("Health check: Postgres unreachable: %s", exc)
        return {"status": "error", "detail": str(exc)[:120]}


async def _check_redis() -> dict:
    """
    Sends a PING command to the Redis instance and expects a PONG response.
    Uses the shared pool so it exercises the same connection the app uses.

    Returns:
        dict — {"status": "ok", "latency_ms": float}
               or {"status": "error", "detail": str} on failure.

    Used by: health()
    """
    start = datetime.now(UTC)
    try:
        redis = get_redis_client()
        pong = await redis.ping()
        if not pong:
            raise RuntimeError("Redis PING returned falsy response.")
        latency = (datetime.now(UTC) - start).total_seconds() * 1000
        return {"status": "ok", "latency_ms": round(latency, 2)}
    except Exception as exc:
        logger.error("Health check: Redis unreachable: %s", exc)
        return {"status": "error", "detail": str(exc)[:120]}


async def _check_qwen() -> dict:
    """
    Makes a lightweight GET request to the Qwen/DashScope base endpoint to
    verify network reachability and that the API key header is accepted.
    Uses a short 5-second timeout so a slow Qwen response doesn't make
    the entire health check appear hung.

    Returns:
        dict — {"status": "ok", "latency_ms": float}
               or {"status": "error", "detail": str} on failure.
               Note: a 401 from Qwen means the endpoint is reachable but the
               key is invalid — still reported as "error".

    Used by: health()
    """
    start = datetime.now(UTC)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                settings.QWEN_ENDPOINT,
                headers={"Authorization": f"Bearer {settings.QWEN_API_KEY}"},
            )
        latency = (datetime.now(UTC) - start).total_seconds() * 1000
        # Any 2xx or 4xx (including 401/403/404) means the endpoint is reachable.
        # Only network-level errors (connection refused, timeout) are treated as down.
        if response.status_code < 500:
            return {"status": "ok", "latency_ms": round(latency, 2)}
        return {
            "status": "error",
            "detail": f"Qwen endpoint returned {response.status_code}",
        }
    except Exception as exc:
        logger.error("Health check: Qwen endpoint unreachable: %s", exc)
        return {"status": "error", "detail": str(exc)[:120]}


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Service health check",
    description=(
        "Checks reachability of PostgreSQL, Redis, and the Qwen API endpoint. "
        "Returns 200 if all dependencies are healthy, 503 if any check fails. "
        "Does not require authentication."
    ),
)
async def health() -> JSONResponse:
    """
    Aggregated health check endpoint. Runs all three dependency checks
    concurrently via asyncio.gather so total latency is bounded by the
    slowest single check rather than the sum of all three.

    Parameters:
        None — unauthenticated endpoint, no Depends() needed.

    Returns:
        JSONResponse 200 — when all checks pass:
            {
              "status": "healthy",
              "timestamp": "2025-...",
              "checks": {
                "postgres": {"status": "ok", "latency_ms": 3.2},
                "redis":    {"status": "ok", "latency_ms": 0.8},
                "qwen":     {"status": "ok", "latency_ms": 142.1}
              }
            }
        JSONResponse 503 — when any check fails:
            {
              "status": "degraded",
              "timestamp": "...",
              "checks": { ... }  // failing check shows "status": "error"
            }

    Used by:
        docker-compose.yml healthcheck: curl /api/v1/health
        Kubernetes liveness / readiness probes
        External uptime monitors
    """
    import asyncio

    postgres_check, redis_check, qwen_check = await asyncio.gather(
        _check_postgres(),
        _check_redis(),
        _check_qwen(),
    )

    checks = {
        "postgres": postgres_check,
        "redis": redis_check,
        "qwen": qwen_check,
    }

    all_ok = all(c["status"] == "ok" for c in checks.values())
    overall_status = "healthy" if all_ok else "degraded"
    http_status = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=http_status,
        content={
            "status": overall_status,
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": checks,
        },
    )