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

settings = get_settings()

# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

celery_app = Celery(
    "hipocampus",
    # Broker: where Celery workers listen for new tasks.
    # Using Redis DB index 1 to avoid colliding with session buffers (index 0).
    broker=settings.REDIS_URL.rstrip("/") + "/1"
    if not settings.REDIS_URL.endswith("/1")
    else settings.REDIS_URL,
    # Result backend: where task return values and states are stored.
    # Same DB index as the broker — results are short-lived anyway.
    backend=settings.REDIS_URL.rstrip("/") + "/1"
    if not settings.REDIS_URL.endswith("/1")
    else settings.REDIS_URL,
    # Tell Celery where to find the task functions.
    include=["app.tasks.scheduled_tasks"],
)

# ---------------------------------------------------------------------------
# Serialisation config
# ---------------------------------------------------------------------------

celery_app.conf.update(
    # JSON is safer than the default pickle — no arbitrary code execution risk.
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # All datetimes in UTC to match the rest of the application.
    timezone="UTC",
    enable_utc=True,
    # Prevent a hung task from blocking a worker forever.
    # Consolidation tasks are given 10 minutes; decay tasks 5 minutes.
    task_soft_time_limit=600,   # SIGTERM sent after 10 min
    task_time_limit=660,         # SIGKILL sent after 11 min (hard ceiling)
    # Retry configuration for transient failures (e.g. Qwen rate limits).
    task_max_retries=3,
    task_default_retry_delay=60,  # Wait 60 seconds between retries
    # Keep task results for 1 hour — long enough to inspect after a run
    # but short enough not to bloat Redis.
    result_expires=3600,
    # Workers ack tasks only after completion, not on receipt.
    # This means a worker crash reruns the task rather than silently dropping it.
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