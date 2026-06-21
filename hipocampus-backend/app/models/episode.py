"""
app/models/episode.py

ORM model for the `episodes` table — the raw episodic memory tier.
Every user ↔ AI exchange that scores above the importance threshold is
written here immediately after the turn completes.

During the nightly sleep consolidation pass, high-scoring episodes are
distilled into semantic_facts and procedural_patterns, then marked
promoted=True. Low-scoring promoted episodes eventually fall below the
decay threshold and are hard-deleted by the decay worker.

Columns:
    id               — UUID primary key (UUIDMixin)
    user_id          — FK reference to users.id (not a SQLAlchemy FK to keep
                       the model self-contained; integrity enforced in service layer)
    session_id       — the session this turn belonged to (matches the Redis key)
    raw_prompt       — the verbatim user message
    llm_response     — the verbatim model response
    importance_score — 0.0–1.0, computed by importance.score_importance()
    promoted         — True once the sleep consolidator has processed this row
    decay_weight     — starts at 1.0, multiplied by 0.96 on each daily decay pass
    conflict_metadata — JSONB blob storing override details when this episode
                        triggered a contradiction (nullable)
    embedding        — 1024-dim pgvector column for cosine similarity search
    created_at       — set once on insert (TimestampMixin)
    updated_at       — refreshed on update (TimestampMixin)

Used by:
    app/models/__init__.py                         — so Alembic sees the table
    app/services/chat_service.py                   — inserts a row after each turn
    app/services/memory_engine/tier_retrieval.py   — reads rows for vector search
    app/services/memory_engine/sleep_consolidator.py — promotes and prunes rows
"""

import uuid

from pgvector.sqlalchemy import Vector # type: ignore
from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin


class Episode(UUIDMixin, TimestampMixin, Base):
    """
    Maps to the `episodes` table.
    Inherits id, created_at, updated_at from the mixins.
    Instantiated by: app/services/chat_service.py after each scored turn.
    """

    __tablename__ = "episodes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,  # Almost every query filters by user_id first
    )

    session_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,  # Needed for history queries scoped to one session
    )

    raw_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        # Full text is stored so the sleep consolidator can re-read it
        # verbatim when building semantic facts.
    )

    llm_response: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    importance_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        # 0.0–1.0. Rows below 0.4 are skipped by the sleep consolidator.
        # Rows below 0.45 are not consolidated but kept for decay.
        index=True,
    )

    promoted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        # True once the sleep consolidator has extracted semantic/procedural
        # knowledge from this row. Promoted rows are still subject to decay.
        index=True,
    )

    decay_weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        # Multiplied by the domain-specific decay rate each day.
        # Rows below 0.3 are hard-deleted if also older than 90 days.
    )

    conflict_metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        # Example: {"old": "PostgreSQL", "new": "TimescaleDB", "resolution": "user_override"}
        # Null for episodes that triggered no contradiction.
    )

    embedding: Mapped[list | None] = mapped_column(
        Vector(1024),
        nullable=True,
        # Null on insert; populated asynchronously after the turn completes
        # to avoid blocking the response. The sleep consolidator skips rows
        # with no embedding.
    )

    def __repr__(self) -> str:
        """
        Developer-friendly string. Truncates raw_prompt to 60 chars to keep
        log lines readable.
        Used by: logging, debugger, test output.
        """
        preview = (self.raw_prompt or "")[:60].replace("\n", " ")
        return f"<Episode id={self.id} score={self.importance_score} promoted={self.promoted} prompt={preview!r}>"