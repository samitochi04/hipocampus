"""
app/utils/logger.py

Configures a single structured logger for the entire application.
Both FastAPI request handlers and Celery worker tasks import from here
so all logs share the same format and level, making them trivially
greppable in production log aggregators (Datadog, CloudWatch, etc.).

Call setup_logging() once at process startup (in main.py for the API,
and at the top of celery_app.py for workers). After that, every module
uses the standard pattern:
    import logging
    logger = logging.getLogger(__name__)

The log level is controlled by the LOG_LEVEL environment variable
(default: INFO). Set LOG_LEVEL=DEBUG locally to see every SQL query,
Redis op, and retrieval step.

Used by: app/main.py (API startup), app/tasks/celery_app.py (worker startup).
"""

import logging
import sys
from typing import Literal

# Valid log level strings accepted by the LOG_LEVEL env var.
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Log format includes timestamp, level, logger name (module path), and message.
# The logger name is the __name__ of the calling module, so log lines are
# immediately traceable to the file that produced them.
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def setup_logging(level: LogLevel = "INFO") -> None:
    """
    Configures the root logger with a consistent format and directs all
    output to stdout (so Docker / Kubernetes log collectors capture it).
    Safe to call multiple times — subsequent calls are no-ops because
    basicConfig() checks if handlers are already attached.

    Parameters:
        level (LogLevel) — the minimum severity to emit. Accepts the standard
                           Python log level strings: DEBUG, INFO, WARNING,
                           ERROR, CRITICAL. Default is INFO.
                           In practice, read this from an env var at the call site:
                               setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))

    Returns:
        None

    Side effects:
        - Attaches a StreamHandler(sys.stdout) to the root logger.
        - Sets the root logger level so all child loggers (every module
          that calls getLogger(__name__)) inherit it automatically.
        - Suppresses noisy third-party loggers (sqlalchemy.engine,
          httpx, celery.utils.functional) down to WARNING so they don't
          flood the output during normal operation.

    Used by: app/main.py startup, app/tasks/celery_app.py module level.
    """
    logging.basicConfig(
        level=logging.getLevelName(level),
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        stream=sys.stdout,
        # force=False: won't replace existing handlers if called again.
    )

    # Suppress verbose third-party loggers that add noise without value.
    _quiet = [
        "sqlalchemy.engine",        # Logs every SQL statement at INFO — too noisy
        "sqlalchemy.pool",          # Connection pool events — only useful when debugging pool exhaustion
        "httpx",                    # Logs every HTTP request/response — use DEBUG locally if needed
        "httpcore",                 # Underlying transport layer for httpx
        "celery.utils.functional",  # Internal Celery tracing — not actionable
        "celery.app.trace",         # Per-task lifecycle logs — enable at DEBUG if debugging task routing
        "asyncio",                  # Event loop internals — only useful for debugging concurrency bugs
    ]
    for name in _quiet:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Keep our own app logs at the requested level regardless of root config.
    logging.getLogger("app").setLevel(logging.getLevelName(level))