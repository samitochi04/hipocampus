"""
app/models/procedural_pattern.py

ORM model for the `procedural_patterns` table — the action-pattern tier
of the memory system.

Where semantic facts store *what* the user knows or prefers, procedural
patterns store *how* the user wants things done. They encode repeatable
action templates that the model should follow when a matching context is
detected during retrieval.

Examples:
    pattern_name:       "chunk_historical_data_fetch"
    trigger_conditions: {"contains": ["fetch", "historical data", "ohlcv"]}
    successful_actions: {"chunk_size": "7d", "cache_key": "ohlcv:{pair}:{date}", "ttl": 600}
    success_rate:       0.92

    pattern_name:       "async_db_writes"
    trigger_conditions: {"contains": ["write", "insert", "database"]}
    successful_actions: {"pattern": "asyncpg", "pool_size": 10, "retry": "tenacity"}
    success_rate:       0.87

Patterns are created and updated by the sleep consolidator. Their
success_rate is incremented when the user's next turn confirms the
pattern worked, and decremented when an explicit override is detected.

Columns:
    id                  — UUID PK (UUIDMixin)
    user_id             — owner of this pattern
    pattern_name        — short human-readable label (e.g. "jwt_middleware_setup")
    trigger_conditions  — JSONB: keywords or embedding criteria that activate this pattern
    successful_actions  — JSONB: the action template to inject into [MEMORY_CONTEXT]
    success_rate        — 0.0–1.0 hit-rate; patterns below 0.4 are deprecated
    last_used_at        — timestamp of the most recent successful trigger
    context_signature   — 1024-dim vector computed from trigger_conditions
                          for fuzzy matching during retrieval
    created_at          — TimestampMixin
    updated_at          — TimestampMixin

Used by:
    app/models/__init__.py                          — Alembic visibility
    app/services/memory_engine/tier_retrieval.py    — trigger matching + vector search
    app/services/memory_engine/sleep_consolidator.py — insert / update / deprecate
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector # type: ignore
from sqlalchemy import DateTime, Float, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin


class ProceduralPattern(UUIDMixin, TimestampMixin, Base):
    """
    Maps to the `procedural_patterns` table.
    Inherits id, created_at, updated_at from the mixins.
    Created by: app/services/memory_engine/sleep_consolidator.py
    Read by:    app/services/memory_engine/tier_retrieval.py
    """

    __tablename__ = "procedural_patterns"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    pattern_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        # Short label used in logs and the [MEMORY_CONTEXT] block header.
        # Not required to be unique per user — different patterns can share
        # a family name if they cover related actions.
    )

    trigger_conditions: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        # Keyword-based trigger checked before the vector search.
        # Example: {"contains": ["fetch", "historical data"]}
        # If the user prompt matches ALL listed keywords, this pattern
        # is a candidate; the context_signature embedding breaks ties.
    )

    successful_actions: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        # The action template injected into [MEMORY_CONTEXT] when this
        # pattern fires.
        # Example: {"tool": "write_file", "template": "clean_state_hook"}
        # The LLM reads this block and follows the specified approach.
    )

    success_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
        # Starts neutral. Updated by the consolidator after each session
        # that references this pattern.
        # < 0.4  → pattern is deprecated (excluded from retrieval)
        # >= 0.7 → pattern is injected with high priority in the context block
        index=True,
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        # Null until the pattern is first triggered during retrieval.
        # Used by the decay worker to down-rank stale patterns.
    )

    context_signature: Mapped[list | None] = mapped_column(
        Vector(1024),
        nullable=True,
        # Embedding computed from the concatenation of trigger_conditions
        # values. Used for fuzzy matching when keyword matching alone is
        # insufficient (e.g. paraphrased user prompts).
    )

    def __repr__(self) -> str:
        """
        Developer-friendly string.
        Used by: logging, debugger, test output.
        """
        return (
            f"<ProceduralPattern id={self.id} "
            f"name={self.pattern_name!r} "
            f"success_rate={self.success_rate}>"
        )