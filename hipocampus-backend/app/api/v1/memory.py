"""
app/api/v1/memory.py

Memory management route handlers. Three endpoints:
  GET   /memory/conflicts      — list semantic facts flagged is_conflicted=True
  GET   /memory/export         — dump all three memory tiers as a JSON payload
  PATCH /memory/facts/{id}     — let the user manually edit or resolve a fact

All routes require authentication. No business logic beyond DB queries
lives here — each handler is intentionally thin.

Used by: app/api/v1/router.py, mounted under /memory.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status # type: ignore
from sqlalchemy import select, update # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore
import asyncio

from app.core.db import get_db
from app.dependencies import get_current_user
from app.models.episode import Episode
from app.models.procedural_pattern import ProceduralPattern
from app.models.semantic_fact import SemanticFact
from app.schemas.auth import UserOut
from app.schemas.memory import (
    ConflictOut,
    MemoryExportOut,
    SemanticFactOut,
    UpdateFactRequest,
    UpdateFactResponse,
    EpisodeOut,
    ProceduralPatternOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get(
    "/conflicts",
    response_model=list[ConflictOut],
    status_code=status.HTTP_200_OK,
    summary="List unresolved memory conflicts",
    description=(
        "Returns all semantic facts currently flagged as is_conflicted=True "
        "for the authenticated user. Each result includes the conflicted fact "
        "and the raw prompt from the episode that triggered the contradiction, "
        "so the UI can show the user exactly what caused the conflict."
    ),
)
async def get_conflicts(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConflictOut]:
    """
    Conflict listing endpoint.
    Queries semantic_facts for is_conflicted=True rows belonging to this user,
    then attempts to join with the episodes table to surface the triggering prompt.

    Parameters:
        current_user (UserOut)      — injected by Depends(get_current_user).
        db           (AsyncSession) — async DB session from Depends(get_db).

    Returns:
        list[ConflictOut] — may be empty if no conflicts exist.
                            Each item contains the full SemanticFactOut plus
                            the conflicting_prompt string (or None if the
                            source episode was already pruned).

    Used by: React ConflictList component → api/memory.js → getConflicts()
    """
    user_id = str(current_user.id)

    result = await db.execute(
        select(SemanticFact)
        .where(SemanticFact.user_id == user_id)
        .where(SemanticFact.is_conflicted == True)  # noqa: E712
        .order_by(SemanticFact.updated_at.desc())
    )
    conflicted_facts: list[SemanticFact] = list(result.scalars().all())

    conflicts: list[ConflictOut] = []
    for fact in conflicted_facts:
        conflicting_prompt: str | None = None

        # Try to find the most recent source episode to surface its prompt.
        if fact.source_episode_ids:
            # source_episode_ids is a list; check the last UUID (most recent).
            latest_source_id = fact.source_episode_ids[-1]
            ep_result = await db.execute(
                select(Episode.raw_prompt)
                .where(Episode.id == latest_source_id)
            )
            row = ep_result.first()
            if row:
                conflicting_prompt = row.raw_prompt[:400]  # Truncate for UI display

        conflicts.append(
            ConflictOut(
                fact=SemanticFactOut.model_validate(fact),
                conflicting_prompt=conflicting_prompt,
            )
        )

    return conflicts


@router.patch(
    "/facts/{fact_id}",
    response_model=UpdateFactResponse,
    status_code=status.HTTP_200_OK,
    summary="Edit or resolve a semantic fact",
    description=(
        "Allows the authenticated user to manually update a semantic fact's text, "
        "confidence, or conflict status. Passing is_conflicted=false marks the "
        "conflict as resolved. All fields are optional — only provided fields are updated."
    ),
)
async def update_fact(
    fact_id: uuid.UUID,
    body: UpdateFactRequest,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UpdateFactResponse:
    """
    Fact edit / conflict resolution endpoint.

    Parameters:
        fact_id      (uuid.UUID)        — UUID of the SemanticFact row to update,
                                          taken from the URL path.
        body         (UpdateFactRequest)— partial update: fact_text, confidence,
                                          and/or is_conflicted.
        current_user (UserOut)          — injected by Depends(get_current_user);
                                          enforces ownership (user can only edit
                                          their own facts).
        db           (AsyncSession)     — async DB session from Depends(get_db).

    Returns:
        UpdateFactResponse — {updated: SemanticFactOut, message: str}

    Raises:
        HTTPException 404 — if the fact doesn't exist or belongs to another user.

    Used by: React FactCard and ConflictList components → api/memory.js → updateFact()
    """
    user_id = str(current_user.id)

    result = await db.execute(
        select(SemanticFact)
        .where(SemanticFact.id == fact_id)
        .where(SemanticFact.user_id == user_id)  # Ownership gate
    )
    fact: SemanticFact | None = result.scalars().first()

    if fact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fact not found or does not belong to your account.",
        )

    # Apply only the fields the client explicitly sent.
    update_values: dict = {"updated_at": datetime.now(UTC)}

    if body.fact_text is not None:
        update_values["fact_text"] = body.fact_text.strip()

    if body.confidence is not None:
        update_values["confidence"] = body.confidence

    if body.is_conflicted is not None:
        update_values["is_conflicted"] = body.is_conflicted

    await db.execute(
        update(SemanticFact)
        .where(SemanticFact.id == fact_id)
        .values(**update_values)
    )
    await db.refresh(fact)

    logger.info(
        "User %s updated fact %s: %s",
        user_id, fact_id, list(update_values.keys())
    )

    return UpdateFactResponse(updated=SemanticFactOut.model_validate(fact))


@router.get(
    "/export",
    response_model=MemoryExportOut,
    status_code=status.HTTP_200_OK,
    summary="Export all memory tiers",
    description=(
        "Returns all three persistent memory tiers (episodes, semantic facts, "
        "procedural patterns) for the authenticated user as a single JSON payload. "
        "Embeddings are omitted from the export — they are binary and not useful "
        "outside the DB. The client can offer this as a downloadable JSON file."
    ),
)
async def export_memory(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryExportOut:
    """
    Full memory export endpoint.
    Queries all three persistent tables and serialises them into the
    MemoryExportOut schema. No pagination — if volume becomes a concern
    in a future version, add limit/offset parameters.

    Parameters:
        current_user (UserOut)      — injected by Depends(get_current_user).
        db           (AsyncSession) — async DB session from Depends(get_db).

    Returns:
        MemoryExportOut — {user_id, episodes, semantic_facts,
                           procedural_patterns, exported_at}

    Used by: React MemoryPage export button → api/memory.js → exportMemory()
    """
    user_id = str(current_user.id)

    # Fetch all three tiers concurrently.
    episodes_result, facts_result, patterns_result = await asyncio.gather(
        db.execute(
            select(Episode)
            .where(Episode.user_id == user_id)
            .order_by(Episode.created_at.desc())
        ),
        db.execute(
            select(SemanticFact)
            .where(SemanticFact.user_id == user_id)
            .order_by(SemanticFact.updated_at.desc())
        ),
        db.execute(
            select(ProceduralPattern)
            .where(ProceduralPattern.user_id == user_id)
            .order_by(ProceduralPattern.success_rate.desc())
        ),
    )

    episodes = [EpisodeOut.model_validate(r) for r in episodes_result.scalars().all()]
    facts = [SemanticFactOut.model_validate(r) for r in facts_result.scalars().all()]
    patterns = [ProceduralPatternOut.model_validate(r) for r in patterns_result.scalars().all()]

    return MemoryExportOut(
        user_id=user_id,
        episodes=episodes,
        semantic_facts=facts,
        procedural_patterns=patterns,
        exported_at=datetime.now(UTC),
    )