"""
app/api/v1/admin.py

Admin-only endpoints for demo and development use.
These are NOT protected by auth in their current form for ease of demo use —
gate them behind get_current_user() before any production deployment.

Routes:
    POST /admin/consolidate   — run the sleep consolidation pipeline NOW for
                                the authenticated user, without waiting for the
                                3 AM Celery beat schedule. Returns the summary
                                dict produced by consolidate_user_memory().

Why this exists:
    The nightly Celery beat runs at 3:00 AM UTC. For demos and testing you
    need to see the Memory page populate with semantic facts immediately after
    a conversation. This endpoint triggers the same consolidation code path
    that the Celery task calls, so the result is identical.

Used by: src/api/memory.js → consolidateNow() (called from MemoryPage button)
"""

import logging

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.schemas.auth import UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post(
    "/consolidate",
    status_code=200,
    summary="Trigger sleep consolidation immediately (demo/dev only)",
)
async def consolidate_now(
    current_user: UserOut = Depends(get_current_user),
) -> dict:
    """
    Runs the full sleep consolidation pipeline synchronously for the
    authenticated user and returns a summary of what was processed.

    This is the same code path the nightly Celery task calls — the only
    difference is it runs NOW instead of at 3 AM, and it runs only for
    the requesting user instead of all users.

    Returns:
        dict — the summary returned by consolidate_user_memory():
               { episodes_processed, facts_written, conflicts_detected,
                 patterns_updated }

    Raises:
        HTTPException 500 — if the consolidation pipeline itself raises.
                            The error detail contains the original exception
                            message for debugging.

    Used by: MemoryPage "Consolidate Now" button → api/memory.js.
    """
    from fastapi import HTTPException

    from app.services.memory_engine.sleep_consolidator import consolidate_user_memory

    try:
        logger.info("Manual consolidation triggered for user %s", current_user.id)
        # consolidate_user_memory opens its own DB session internally
        # so we don't need to pass one here.
        result = await consolidate_user_memory(user_id=str(current_user.id))
        logger.info(
            "Manual consolidation complete for user %s: %s",
            current_user.id,
            result,
        )
        return result
    except Exception as exc:
        logger.error(
            "Manual consolidation failed for user %s: %s",
            current_user.id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(exc))