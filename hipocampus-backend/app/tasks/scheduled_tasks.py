"""
app/tasks/scheduled_tasks.py

Celery task functions triggered by the Beat schedule defined in celery_app.py.

Two tasks are defined:
  1. consolidate_all_users() — iterates over every user that has unpromoted
     episodes and calls sleep_consolidator.consolidate_user_memory() for each.

  2. refresh_all_decay() — iterates over every user that has promoted episodes
     and calls sleep_consolidator.decay_refresh() for each.

Both tasks are async under the hood but Celery workers are synchronous by default.
We use asyncio.run() to bridge the two worlds cleanly without needing a third-party
library like celery-pool-asyncio. This pattern is safe because each task runs in
its own Celery worker process with its own event loop.

The tasks query the DB for the full user list themselves rather than accepting
user IDs as arguments. This avoids the Beat schedule needing to know about users
and keeps the task idempotent — re-running it processes whoever has pending work.

Used by: app/tasks/celery_app.py beat_schedule (triggered automatically).
         Can also be called manually: celery -A app.tasks.celery_app call
             app.tasks.scheduled_tasks.consolidate_all_users
"""

import asyncio
import logging

from sqlalchemy import select # type: ignore

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared DB helper
# ---------------------------------------------------------------------------


async def _get_all_user_ids() -> list[str]:
    """
    Returns the UUID strings of every user in the database.
    Opens its own DB session so it is independent of the FastAPI request lifecycle.
    Used by both tasks to get the full user list before iterating.

    Returns:
        list[str] — UUID strings of all users. Empty list if no users exist.

    Raises:
        Does not raise — failures are caught and logged by the calling task.

    Used by: consolidate_all_users(), refresh_all_decay()
    """
    from app.core.db import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User.id))
        return [str(row[0]) for row in result.all()]


# ---------------------------------------------------------------------------
# Task 1: Nightly consolidation
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.scheduled_tasks.consolidate_all_users",
    bind=True,           # `self` gives access to retry() and request metadata
    max_retries=3,
    default_retry_delay=120,  # 2 minutes between retries on transient failure
)
def consolidate_all_users(self) -> dict:
    """
    Celery task: runs the full sleep consolidation pipeline for every user.
    Triggered nightly at 3:00 AM UTC by Celery Beat.

    For each user:
      - Fetches unpromoted episodes above the importance threshold.
      - Sends them to Qwen-Max in 32-episode chunks.
      - Resolves contradictions against stored semantic facts.
      - Writes new semantic facts and procedural patterns.
      - Marks processed episodes as promoted.

    Individual user failures are caught and logged without aborting the
    entire batch — one user's Qwen error doesn't affect other users.

    Parameters:
        self — Celery task instance (injected by bind=True); used for retry().

    Returns:
        dict — summary of the full run:
               {
                 "users_processed": int,
                 "users_failed":    int,
                 "per_user":        [list of per-user summary dicts]
               }

    Raises (Celery retry):
        Any exception from _get_all_user_ids() triggers a retry up to max_retries.

    Used by: celery_app.py beat_schedule → "consolidate-all-users"
    """
    logger.info("consolidate_all_users: starting nightly consolidation run")

    async def _run() -> dict:
        from app.services.memory_engine.sleep_consolidator import consolidate_user_memory

        try:
            user_ids = await _get_all_user_ids()
        except Exception as exc:
            logger.error("consolidate_all_users: failed to fetch user list: %s", exc)
            raise  # Will trigger Celery retry

        results = []
        failed = 0

        for user_id in user_ids:
            try:
                summary = await consolidate_user_memory(user_id)
                results.append(summary)
                logger.info(
                    "consolidate_all_users: user=%s episodes=%d facts=%d patterns=%d",
                    user_id,
                    summary.get("episodes_processed", 0),
                    summary.get("facts_written", 0),
                    summary.get("patterns_written", 0),
                )
            except Exception as exc:
                failed += 1
                logger.error(
                    "consolidate_all_users: failed for user %s: %s", user_id, exc
                )

        return {
            "users_processed": len(user_ids) - failed,
            "users_failed": failed,
            "per_user": results,
        }

    try:
        result = asyncio.run(_run())
        logger.info(
            "consolidate_all_users: complete — processed=%d failed=%d",
            result["users_processed"],
            result["users_failed"],
        )
        return result
    except Exception as exc:
        logger.error("consolidate_all_users: unrecoverable error: %s", exc)
        # Trigger Celery retry with exponential back-off.
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Task 2: Daily decay refresh
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.scheduled_tasks.refresh_all_decay",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def refresh_all_decay(self) -> dict:
    """
    Celery task: applies the biological forgetting curve to every user's
    promoted episodes and hard-deletes those below the pruning threshold.
    Triggered daily at 3:30 AM UTC by Celery Beat (30 minutes after consolidation).

    For each user:
      - Multiplies decay_weight by DEFAULT_DECAY_RATE (0.96) on every promoted episode.
      - Deletes promoted episodes where decay_weight < 0.30 AND age > 90 days.

    Individual user failures are caught and logged without aborting the batch.

    Parameters:
        self — Celery task instance (injected by bind=True); used for retry().

    Returns:
        dict — summary of the full run:
               {
                 "users_processed": int,
                 "users_failed":    int,
                 "total_decayed":   int,
                 "total_pruned":    int,
               }

    Raises (Celery retry):
        Any exception from _get_all_user_ids() triggers a retry up to max_retries.

    Used by: celery_app.py beat_schedule → "decay-refresh-all-users"
    """
    logger.info("refresh_all_decay: starting daily decay refresh run")

    async def _run() -> dict:
        from app.services.memory_engine.sleep_consolidator import decay_refresh

        try:
            user_ids = await _get_all_user_ids()
        except Exception as exc:
            logger.error("refresh_all_decay: failed to fetch user list: %s", exc)
            raise

        total_decayed = 0
        total_pruned = 0
        failed = 0

        for user_id in user_ids:
            try:
                summary = await decay_refresh(user_id)
                total_decayed += summary.get("decayed", 0)
                total_pruned += summary.get("pruned", 0)
                logger.info(
                    "refresh_all_decay: user=%s decayed=%d pruned=%d",
                    user_id,
                    summary.get("decayed", 0),
                    summary.get("pruned", 0),
                )
            except Exception as exc:
                failed += 1
                logger.error(
                    "refresh_all_decay: failed for user %s: %s", user_id, exc
                )

        return {
            "users_processed": len(user_ids) - failed,
            "users_failed": failed,
            "total_decayed": total_decayed,
            "total_pruned": total_pruned,
        }

    try:
        result = asyncio.run(_run())
        logger.info(
            "refresh_all_decay: complete — decayed=%d pruned=%d failed=%d",
            result["total_decayed"],
            result["total_pruned"],
            result["users_failed"],
        )
        return result
    except Exception as exc:
        logger.error("refresh_all_decay: unrecoverable error: %s", exc)
        raise self.retry(exc=exc)