"""
app/schemas/memory.py

Pydantic v2 request and response models for the /memory/* routes.
These cover three surfaces:
  - Conflict listing  (GET  /memory/conflicts)
  - Fact editing      (PATCH /memory/facts/{id})
  - Full data export  (GET  /memory/export)

Used by: app/api/v1/memory.py route handlers.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Semantic fact schemas
# ---------------------------------------------------------------------------


class SemanticFactOut(BaseModel):
    """
    Public representation of a single semantic fact row.
    Returned inside ConflictOut and MemoryExportOut.

    Parameters (sourced from SemanticFact ORM row):
        id                 (uuid.UUID)       — fact UUID
        fact_text          (str)             — the declarative statement
        confidence         (float)           — 0.0–1.0 confidence score
        is_conflicted      (bool)            — True if awaiting user resolution
        source_episode_ids (list[uuid.UUID]) — which episodes produced this fact
        created_at         (datetime)        — when the fact was first extracted
        updated_at         (datetime)        — when it was last modified

    Used by:
        app/api/v1/memory.py → get_conflicts(), export_memory()
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    fact_text: str
    confidence: float
    is_conflicted: bool
    source_episode_ids: list[uuid.UUID] | None = None
    created_at: datetime
    updated_at: datetime


class ConflictOut(BaseModel):
    """
    Response body item for GET /api/v1/memory/conflicts.
    Wraps a SemanticFactOut and adds the conflicting episode's prompt
    so the client can show the user what triggered the contradiction.

    Parameters:
        fact              (SemanticFactOut) — the conflicted semantic fact
        conflicting_prompt (str | None)     — the raw_prompt from the episode
                                             that set is_conflicted=True;
                                             None if the episode was already pruned

    Used by: app/api/v1/memory.py → get_conflicts()
    """

    fact: SemanticFactOut
    conflicting_prompt: str | None = None


class UpdateFactRequest(BaseModel):
    """
    Body the client sends to PATCH /api/v1/memory/facts/{id}.
    Allows the user to manually correct a fact's text or reset
    its conflict flag after reviewing it.
    All fields are optional — only provided fields are updated.

    Parameters:
        fact_text     (str | None)   — replacement text for the fact.
        confidence    (float | None) — new confidence override (0.0–1.0).
        is_conflicted (bool | None)  — pass False to mark the conflict resolved.

    Used by: app/api/v1/memory.py → update_fact()
    """

    fact_text: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
        description="Replacement declarative statement for this fact.",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Manual confidence override.",
    )
    is_conflicted: bool | None = Field(
        default=None,
        description="Set to false to mark a conflict as resolved.",
    )


class UpdateFactResponse(BaseModel):
    """
    Body returned by PATCH /api/v1/memory/facts/{id} on success.

    Parameters:
        updated (SemanticFactOut) — the fact row after applying the patch.
        message (str)             — human-readable confirmation.

    Used by: app/api/v1/memory.py → update_fact()
    """

    updated: SemanticFactOut
    message: str = "Fact updated successfully."


# ---------------------------------------------------------------------------
# Export schema
# ---------------------------------------------------------------------------


class EpisodeOut(BaseModel):
    """
    Lightweight episode representation used inside MemoryExportOut.
    Omits the embedding vector (binary, not useful in a JSON export).

    Parameters (sourced from Episode ORM row):
        id               (uuid.UUID) — episode UUID
        session_id       (str)       — session the turn belonged to
        raw_prompt       (str)       — the user's message
        llm_response     (str)       — the model's response
        importance_score (float)     — 0.0–1.0 score at the time of storage
        promoted         (bool)      — whether sleep consolidation processed this
        created_at       (datetime)  — when the turn happened

    Used by: app/api/v1/memory.py → export_memory()
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    session_id: str
    raw_prompt: str
    llm_response: str
    importance_score: float
    promoted: bool
    created_at: datetime


class ProceduralPatternOut(BaseModel):
    """
    Lightweight procedural pattern representation for the export endpoint.

    Parameters (sourced from ProceduralPattern ORM row):
        id                 (uuid.UUID) — pattern UUID
        pattern_name       (str)       — short label
        trigger_conditions (dict)      — JSONB trigger spec
        successful_actions (dict)      — JSONB action template
        success_rate       (float)     — current hit-rate
        last_used_at       (datetime | None) — most recent trigger timestamp

    Used by: app/api/v1/memory.py → export_memory()
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    pattern_name: str
    trigger_conditions: dict
    successful_actions: dict
    success_rate: float
    last_used_at: datetime | None = None


class MemoryExportOut(BaseModel):
    """
    Full response body for GET /api/v1/memory/export.
    Bundles all three persistent memory tiers into one payload the user
    can download as a JSON file from the client.

    Parameters:
        user_id             (str)                    — whose memory this is
        episodes            (list[EpisodeOut])        — raw episodic rows
        semantic_facts      (list[SemanticFactOut])   — distilled facts
        procedural_patterns (list[ProceduralPatternOut]) — action patterns
        exported_at         (datetime)               — timestamp of the export

    Used by: app/api/v1/memory.py → export_memory()
    """

    user_id: str
    episodes: list[EpisodeOut]
    semantic_facts: list[SemanticFactOut]
    procedural_patterns: list[ProceduralPatternOut]
    exported_at: datetime