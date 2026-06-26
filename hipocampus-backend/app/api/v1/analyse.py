"""
app/api/v1/analyse.py

Public read-only analytics endpoint for the Hipocampus demo.
No authentication required — intended for hackathon judges to inspect live
system stats without needing to register an account.

GET /analyse   — aggregate statistics across all memory tiers.
                 Returns counts, health metrics, and activity data.
                 Never returns raw prompts, responses, or user identifiers.

Used by: app/api/v1/router.py, src/pages/AnalysePage.jsx (public route).
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.chat import Chat, Message
from app.models.episode import Episode
from app.models.procedural_pattern import ProceduralPattern
from app.models.semantic_fact import SemanticFact
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyse", tags=["analyse"])


@router.get(
    "",
    status_code=200,
    summary="Live memory system statistics (public, read-only)",
)
async def get_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Returns aggregate statistics across all four memory tiers.

    All queries are SELECT-only. No data is created, modified, or deleted.
    Raw prompts, responses, and user identifiers are never included.

    Returns a flat JSON dict with five sections:
      overview            — total row counts per table
      episode_health      — promotion rate, avg importance, pending count
      importance_dist     — episodes bucketed by importance score
      semantic_health     — confidence distribution + conflict count
      activity_24h        — rows created in the last 24 hours
      generated_at        — UTC timestamp this response was built

    Used by: src/pages/AnalysePage.jsx
    """
    now     = datetime.now(UTC)
    cutoff  = now - timedelta(hours=24)

    # ── Overview counts ───────────────────────────────────────────────────
    users_total     = await db.scalar(select(func.count(User.id)))              or 0
    episodes_total  = await db.scalar(select(func.count(Episode.id)))           or 0
    semantic_total  = await db.scalar(select(func.count(SemanticFact.id)))      or 0
    procedural_total= await db.scalar(select(func.count(ProceduralPattern.id))) or 0
    chats_total     = await db.scalar(select(func.count(Chat.id)))              or 0
    messages_total  = await db.scalar(select(func.count(Message.id)))           or 0

    # ── Episode health ────────────────────────────────────────────────────
    ep_promoted = await db.scalar(
        select(func.count(Episode.id)).where(Episode.promoted == True)  # noqa: E712
    ) or 0
    ep_avg_importance = await db.scalar(
        select(func.round(func.avg(Episode.importance_score).cast(
            __import__("sqlalchemy").Numeric
        ), 3))
    )
    ep_with_embedding = await db.scalar(
        select(func.count(Episode.id)).where(Episode.embedding.isnot(None))
    ) or 0

    # ── Importance distribution (all saved episodes have score >= 0.45) ───
    ep_saved = await db.scalar(
        select(func.count(Episode.id))
        .where(Episode.importance_score >= 0.45)
        .where(Episode.importance_score < 0.60)
    ) or 0
    ep_candidate = await db.scalar(
        select(func.count(Episode.id))
        .where(Episode.importance_score >= 0.60)
        .where(Episode.importance_score < 0.80)
    ) or 0
    ep_high = await db.scalar(
        select(func.count(Episode.id))
        .where(Episode.importance_score >= 0.80)
    ) or 0

    # ── Semantic health ───────────────────────────────────────────────────
    sf_avg_confidence = await db.scalar(
        select(func.round(func.avg(SemanticFact.confidence).cast(
            __import__("sqlalchemy").Numeric
        ), 3))
    )
    sf_conflicted = await db.scalar(
        select(func.count(SemanticFact.id))
        .where(SemanticFact.is_conflicted == True)  # noqa: E712
    ) or 0
    sf_high = await db.scalar(
        select(func.count(SemanticFact.id))
        .where(SemanticFact.confidence >= 0.80)
    ) or 0
    sf_medium = await db.scalar(
        select(func.count(SemanticFact.id))
        .where(SemanticFact.confidence >= 0.50)
        .where(SemanticFact.confidence < 0.80)
    ) or 0
    sf_low = await db.scalar(
        select(func.count(SemanticFact.id))
        .where(SemanticFact.confidence < 0.50)
    ) or 0

    # ── Procedural health ─────────────────────────────────────────────────
    pp_avg_success = await db.scalar(
        select(func.round(func.avg(ProceduralPattern.success_rate).cast(
            __import__("sqlalchemy").Numeric
        ), 3))
    )

    # ── Activity last 24 h ────────────────────────────────────────────────
    new_episodes = await db.scalar(
        select(func.count(Episode.id)).where(Episode.created_at > cutoff)
    ) or 0
    new_facts = await db.scalar(
        select(func.count(SemanticFact.id)).where(SemanticFact.created_at > cutoff)
    ) or 0
    new_messages = await db.scalar(
        select(func.count(Message.id)).where(Message.created_at > cutoff)
    ) or 0
    new_chats = await db.scalar(
        select(func.count(Chat.id)).where(Chat.created_at > cutoff)
    ) or 0

    return {
        "overview": {
            "users":               users_total,
            "chats":               chats_total,
            "messages":            messages_total,
            "episodes":            episodes_total,
            "semantic_facts":      semantic_total,
            "procedural_patterns": procedural_total,
        },
        "episode_health": {
            "total":              episodes_total,
            "promoted":           ep_promoted,
            "pending":            episodes_total - ep_promoted,
            "with_embedding":     ep_with_embedding,
            "promoted_pct":       round(ep_promoted / episodes_total * 100, 1)
                                  if episodes_total else 0,
            "avg_importance":     float(ep_avg_importance) if ep_avg_importance else 0,
        },
        "importance_distribution": {
            "saved":      ep_saved,       # 0.45 – 0.60
            "candidate":  ep_candidate,   # 0.60 – 0.80
            "high":       ep_high,        # 0.80 – 1.00
        },
        "semantic_health": {
            "total":          semantic_total,
            "avg_confidence": float(sf_avg_confidence) if sf_avg_confidence else 0,
            "conflicted":     sf_conflicted,
            "high":           sf_high,    # confidence >= 0.80
            "medium":         sf_medium,  # 0.50 – 0.80
            "low":            sf_low,     # < 0.50
        },
        "procedural_health": {
            "total":           procedural_total,
            "avg_success_rate": float(pp_avg_success) if pp_avg_success else 0,
        },
        "activity_24h": {
            "new_episodes": new_episodes,
            "new_facts":    new_facts,
            "new_messages": new_messages,
            "new_chats":    new_chats,
        },
        "generated_at": now.isoformat(),
    }