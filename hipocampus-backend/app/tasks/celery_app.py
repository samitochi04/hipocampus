"""
app/tasks/celery_app.py

Creates and configures the shared Celery application instance.
Both the Celery worker and Celery Beat import `celery_app` from here.

Two scheduled jobs are configured via beat_schedule:
  1. consolidate-all-users — runs at 3:00 AM UTC daily.
     Triggers consolidate_user_memory() for every user that has unpromoted
     episodes, extracting semantic facts and procedural patterns.

  2. decay-refresh-all-users — runs every 24 hours offset by 30 minutes
     (3:30 AM UTC) so it always runs after consolidation is complete.
     Applies the biological forgetting curve and prunes stale episodes.

Broker and result backend both point at the same Redis instance used by
the API (database index 1 to keep task data separate from session buffers
which live on index 0).

Used by:
    app/tasks/scheduled_tasks.py — registers task functions on this app
    docker-compose.yml           — celery-worker and celery-beat services
                                   both reference `hipocampus.tasks.celery_app`
"""

from celery import Celery # type: ignore
from celery.schedules import crontab # type: ignore

from app.config import get_settings

import re

settings = get_settings()

_celery_redis_url = re.sub(r"/\d+$", "", settings.REDIS_URL) + "/1"

# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

celery_app = Celery(
    "hipocampus",
    broker=_celery_redis_url,
    backend=_celery_redis_url,
    include=["app.tasks.scheduled_tasks"],
)

# ---------------------------------------------------------------------------
# Serialisation config
# ---------------------------------------------------------------------------

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_soft_time_limit=600,   # SIGTERM sent after 10 min
    task_time_limit=660,         # SIGKILL sent after 11 min (hard ceiling)
    task_max_retries=3,
    task_default_retry_delay=60,  # Wait 60 seconds between retries
    result_expires=3600,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker — memory tasks are heavy
)

# ---------------------------------------------------------------------------
# Beat schedule
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    # ── Job 1: nightly memory consolidation ─────────────────────────────────
    "consolidate-all-users": {
        "task": "app.tasks.scheduled_tasks.consolidate_all_users",
        # 3:00 AM UTC daily. Adjust hour to suit your user timezone if needed.
        "schedule": crontab(hour=3, minute=0),
        # No args — the task queries the DB for the full user list itself.
        "args": (),
        "options": {
            # Route to a dedicated queue so heavy consolidation tasks
            # don't starve the decay tasks or any future real-time tasks.
            "queue": "consolidation",
        },
    },
    # ── Job 2: biological forgetting curve + pruning ─────────────────────────
    "decay-refresh-all-users": {
        "task": "app.tasks.scheduled_tasks.refresh_all_decay",
        # 3:30 AM UTC daily — always after consolidation finishes.
        "schedule": crontab(hour=3, minute=30),
        "args": (),
        "options": {
            "queue": "consolidation",
        },
    },
}

# Default queue for any task not explicitly routed.
celery_app.conf.task_default_queue = "default"