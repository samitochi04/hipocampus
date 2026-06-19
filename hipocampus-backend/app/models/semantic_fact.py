"""
app/models/semantic_fact.py

ORM model for the `semantic_facts` table — the distilled, long-term
knowledge tier extracted from episodes during sleep consolidation.

A semantic fact is a single declarative statement about the user:
a preference, a constraint, a domain choice, or a known fact about
their project. Examples:
    "User strictly prefers Pydantic v2 for all schema validation."
    "User's primary database is PostgreSQL with the pgvector extension."

Facts are created by the sleep consolidator and can be updated in two ways:
    1. Sleep consolidator detects a more confident version → updates in place.
    2. User explicitly overrides a fact via PATCH /api/v1/memory/facts/{id}.

When an incoming episode contradicts an existing fact, is_conflicted is set
to True and the fact is surfaced at GET /api/v1/memory/conflicts until the
user resolves it.

Columns:
    id                — UUID PK (UUIDMixin)
    user_id           — owner of this fact
    fact_text         — the declarative statement in plain English
    confidence        — 0.0–1.0, updated by the consolidator as more evidence
                        accumulates or the user explicitly confirms/overrides
    source_episode_ids — UUIDs of the episodes this fact was derived from
    is_conflicted     — True when a newer episode contradicts this fact and
                        the conflict hasn't been resolved yet
    embedding         — 1536-dim vector for cosine similarity retrieval
    created_at        — TimestampMixin
    updated_at        — TimestampMixin (refreshed on every consolidator update)

Used by:
    app/models/__init__.py                          — Alembic visibility
    app/services/memory_engine/tier_retrieval.py    — vector search
    app/services/memory_engine/sleep_consolidator.py — insert / update / conflict flag
    app/api/v1/memory.py                            — GET /conflicts, PATCH /facts/{id}
"""

import uuid

from pgvector.sqlalchemy import Vector # type: ignore
from sqlalchemy import Boolean, Float, String, Text # type: ignore
from sqlalchemy.dialects.postgresql import ARRAY, UUID # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDMixin


class SemanticFact(UUIDMixin, TimestampMixin, Base):
    """
    Maps to the `semantic_facts` table.
    Inherits id, created_at, updated_at from the mixins.
    Created by: app/services/memory_engine/sleep_consolidator.py
    Read by:    app/services/memory_engine/tier_retrieval.py,
                app/api/v1/memory.py
    """

    __tablename__ = "semantic_facts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    fact_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        # Plain-English declarative statement — what the consolidator
        # extracted from one or more episodes. Updated in place when
        # a higher-confidence version is found or when the user overrides.
    )

    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
        # 0.0–1.0. Starts at 0.5 for new facts, rises as corroborating
        # episodes accumulate. Falls during contradiction arbitration.
        # Only facts >= 0.6 are injected into the [MEMORY_CONTEXT] block.
        index=True,
    )

    source_episode_ids: Mapped[list | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        # Audit trail: which episodes contributed to this fact.
        # Null for facts created from manual user overrides.
    )

    is_conflicted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        # Set to True by the consolidator when a new episode contradicts
        # this fact. Cleared to False when the user resolves the conflict
        # via PATCH /api/v1/memory/facts/{id}.
        index=True,
    )

    embedding: Mapped[list | None] = mapped_column(
        Vector(1536),
        nullable=True,
        # Populated by the consolidator after fact_text is written.
        # Used for cosine similarity search in tier_retrieval.py.
    )

    def __repr__(self) -> str:
        """
        Developer-friendly string. Truncates fact_text to 80 chars.
        Used by: logging, debugger, test output.
        """
        preview = (self.fact_text or "")[:80].replace("\n", " ")
        return f"<SemanticFact id={self.id} confidence={self.confidence} conflicted={self.is_conflicted} text={preview!r}>"