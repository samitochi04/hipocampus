"""
app/services/memory_engine/sleep_consolidator.py

Implements the "sleep" phase of the hippocampal memory model.
Runs offline via Celery Beat (3 AM daily) — never during a live request.

Two top-level entry points:
  1. consolidate_user_memory(user_id) — extracts semantic facts and procedural
     patterns from recent unpromoted episodes, resolves contradictions, and
     writes the distilled knowledge back to the persistent memory tables.
  2. decay_refresh(user_id) — applies the biological forgetting curve to
     all promoted episodes and hard-deletes those below the pruning threshold.

Pipeline inside consolidate_user_memory():
  A. Fetch pending episodes      — unpromoted, importance >= 0.45, newest 64
  B. Recalculate importance      — re-score with updated recency/frequency data
  C. Chunk and send to Qwen-Long — 32 episodes per chunk, returns structured JSON
  D. Resolve contradictions      — compare new facts against stored ones via
                                   cosine similarity + LLM arbitration
  E. Write back                  — insert new semantic facts and procedural patterns
  F. Mark episodes promoted      — set promoted=True on all processed rows

Used by: app/tasks/scheduled_tasks.py (Celery tasks call these functions directly)
"""

import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal
from app.models.episode import Episode
from app.models.procedural_pattern import ProceduralPattern
from app.models.semantic_fact import SemanticFact
from app.services.memory_engine.qwen_router import (
    consolidate_episodes,
    embed_text,
    resolve_conflict,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Episodes with importance below this are skipped by the consolidator
# (they stay in the table but are never promoted or consolidated).
MIN_IMPORTANCE_FOR_CONSOLIDATION = 0.45

# Maximum episodes fetched per consolidation run per user.
MAX_EPISODES_PER_RUN = 64

# Episodes are sent to Qwen-Long in chunks to stay within its context window.
CHUNK_SIZE = 32

# Cosine distance threshold below which two semantic facts are considered
# similar enough to check for contradiction.
CONTRADICTION_DISTANCE = 0.30   # i.e. similarity > 0.70

# Combined confidence above which the consolidator invokes LLM arbitration
# instead of simple overwrite.
ARBITRATION_CONFIDENCE_THRESHOLD = 1.5

# Decay multiplier applied to promoted episodes each day.
# Domain-specific overrides can be added when multi-domain routing lands.
DEFAULT_DECAY_RATE = 0.96

# Episodes below this decay weight AND older than PRUNE_AGE_DAYS are hard-deleted.
PRUNE_DECAY_THRESHOLD = 0.30
PRUNE_AGE_DAYS = 90


# ---------------------------------------------------------------------------
# Phase A: Fetch pending episodes
# ---------------------------------------------------------------------------


async def _fetch_pending_episodes(user_id: str, db: AsyncSession) -> list[Episode]:
    """
    Queries the episodes table for unpromoted rows above the importance
    threshold, ordered newest-first so the most recent knowledge is
    prioritised when the batch is larger than MAX_EPISODES_PER_RUN.

    Parameters:
        user_id (str)         — UUID string of the user being consolidated.
        db      (AsyncSession)— open async DB session.

    Returns:
        list[Episode] — up to MAX_EPISODES_PER_RUN Episode ORM objects.

    Used by: consolidate_user_memory()
    """
    result = await db.execute(
        select(Episode)
        .where(Episode.user_id == user_id)
        .where(Episode.promoted == False)  # noqa: E712
        .where(Episode.importance_score >= MIN_IMPORTANCE_FOR_CONSOLIDATION)
        # NOTE: embedding may be NULL if the background embed task failed
        # (e.g. API error during the turn). We still consolidate these episodes —
        # the consolidation pipeline re-embeds the extracted *facts*, not the
        # episode rows themselves, so a NULL episode embedding is harmless here.
        .order_by(Episode.created_at.desc())
        .limit(MAX_EPISODES_PER_RUN)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Phase B: Recalculate importance with fresh signals
# ---------------------------------------------------------------------------


def _recalculate_importance(episode: Episode, total_episodes: int) -> float:
    """
    Re-scores a single episode using updated recency and frequency signals.
    This is a lightweight version of the live score_importance() function —
    it doesn't call the embedding API again (embedding already exists) and
    doesn't query the DB per-episode. It uses the batch-level total_episodes
    count as a proxy for frequency.

    Formula:
        recency_weight = 1.0 / (1.0 + days_since_creation * 0.2)
        frequency_bonus = min(1.5, log1p(total_episodes) * 0.3)
        score = clip(original_score * recency_weight * frequency_bonus, 0.0, 1.0)

    Parameters:
        episode        (Episode) — the ORM episode to re-score.
        total_episodes (int)     — total episode count for this user in the batch;
                                   used as a frequency proxy.

    Returns:
        float — updated importance score in [0.0, 1.0].

    Used by: consolidate_user_memory()
    """
    now = datetime.now(UTC)
    age_days = (now - episode.created_at).days if episode.created_at else 0
    recency_weight = 1.0 / (1.0 + age_days * 0.2)
    frequency_bonus = min(1.5, math.log1p(total_episodes) * 0.3)

    raw = episode.importance_score * recency_weight * frequency_bonus
    return round(max(0.0, min(1.0, raw)), 3)


# ---------------------------------------------------------------------------
# Phase D: Contradiction resolution
# ---------------------------------------------------------------------------


async def _resolve_contradictions(
    new_facts: list[dict],
    user_id: str,
    db: AsyncSession,
) -> list[dict]:
    """
    For each candidate new fact, checks whether a semantically similar fact
    already exists in semantic_facts. If so:
      - If both have high confidence (combined > ARBITRATION_CONFIDENCE_THRESHOLD)
        and the cosine distance suggests they diverge in meaning → invoke Qwen-Max
        arbitration to produce a unified fact.
      - Otherwise → flag the existing fact as is_conflicted=True so the user
        can resolve it manually via the /memory/conflicts endpoint.

    Facts with no near-neighbour in the DB are returned unchanged.

    Parameters:
        new_facts (list[dict]) — dicts with "fact_text" and "confidence" keys,
                                 as returned by qwen_router.consolidate_episodes().
        user_id   (str)        — filters DB lookups to this user.
        db        (AsyncSession)— open async DB session.

    Returns:
        list[dict] — processed facts ready for write-back. Each dict has
                     "fact_text", "confidence", and optionally "resolved" (bool).

    Used by: consolidate_user_memory()
    """
    resolved_facts: list[dict] = []

    for candidate in new_facts:
        fact_text: str = candidate.get("fact_text", "")
        confidence: float = float(candidate.get("confidence", 0.5))

        if not fact_text.strip():
            continue

        # Embed the candidate fact for similarity search.
        try:
            candidate_embedding = await embed_text(fact_text)
        except Exception as exc:
            logger.warning("Skipping fact embedding failure: %s", exc)
            resolved_facts.append(candidate)
            continue

        embedding_literal = str(candidate_embedding)

        # Find the closest existing fact for this user.
        result = await db.execute(
            text(
                """
                SELECT id, fact_text, confidence,
                       embedding <=> CAST(:embedding AS vector) AS distance
                FROM semantic_facts
                WHERE user_id = :user_id
                  AND embedding IS NOT NULL
                  AND embedding <=> CAST(:embedding AS vector) < :threshold
                ORDER BY distance ASC
                LIMIT 1
                """
            ),
            {
                "embedding": embedding_literal,
                "user_id": user_id,
                "threshold": CONTRADICTION_DISTANCE,
            },
        )
        existing_row = result.mappings().first()

        if existing_row is None:
            # No near-neighbour — this is genuinely new knowledge.
            candidate["embedding"] = candidate_embedding
            resolved_facts.append(candidate)
            continue

        existing_confidence = float(existing_row["confidence"])
        combined_confidence = confidence + existing_confidence

        if combined_confidence > ARBITRATION_CONFIDENCE_THRESHOLD:
            # Both facts are high-confidence and cover the same topic —
            # invoke LLM arbitration to merge them into a unified statement.
            try:
                resolution = await resolve_conflict(
                    existing_fact=existing_row["fact_text"],
                    new_fact=fact_text,
                )
                await db.execute(
                    update(SemanticFact)
                    .where(SemanticFact.id == existing_row["id"])
                    .values(
                        fact_text=resolution["unified_text"],
                        confidence=float(resolution.get("confidence", 0.75)),
                        is_conflicted=False,
                        updated_at=datetime.now(UTC),
                    )
                )
                logger.info(
                    "Resolved contradiction for user %s: merged into '%s'",
                    user_id,
                    resolution["unified_text"][:80],
                )
            except Exception as exc:
                # Arbitration failed — flag the existing fact for manual review.
                logger.warning("LLM arbitration failed, flagging conflict: %s", exc)
                await db.execute(
                    update(SemanticFact)
                    .where(SemanticFact.id == existing_row["id"])
                    .values(is_conflicted=True, updated_at=datetime.now(UTC))
                )
        else:
            # Low-confidence contradiction — flag for user review rather than
            # auto-resolving, since we're not confident enough to merge.
            await db.execute(
                update(SemanticFact)
                .where(SemanticFact.id == existing_row["id"])
                .values(is_conflicted=True, updated_at=datetime.now(UTC))
            )
            logger.info(
                "Flagged low-confidence conflict for user %s on fact: '%s'",
                user_id,
                existing_row["fact_text"][:80],
            )
        # Don't add the candidate — the existing fact was updated instead.

    return resolved_facts


# ---------------------------------------------------------------------------
# Phase E: Write-back
# ---------------------------------------------------------------------------


async def _write_semantic_facts(
    facts: list[dict],
    user_id: str,
    source_episode_ids: list[str],
    db: AsyncSession,
) -> None:
    """
    Inserts new semantic facts into the semantic_facts table.
    Each fact gets an embedding (already computed in _resolve_contradictions)
    and the source_episode_ids for auditability.

    Parameters:
        facts              (list[dict])  — processed facts from _resolve_contradictions().
        user_id            (str)         — owner of these facts.
        source_episode_ids (list[str])   — UUID strings of the episodes this batch came from.
        db                 (AsyncSession)— open async DB session.

    Returns:
        None

    Used by: consolidate_user_memory()
    """
    for fact in facts:
        fact_text = fact.get("fact_text", "").strip()
        confidence = float(fact.get("confidence", 0.5))
        embedding = fact.get("embedding")

        if not fact_text:
            continue

        new_fact = SemanticFact(
            user_id=user_id,
            fact_text=fact_text,
            confidence=confidence,
            source_episode_ids=source_episode_ids,
            is_conflicted=False,
            embedding=embedding,
        )
        db.add(new_fact)

    await db.flush()


async def _write_procedural_patterns(
    patterns: list[dict],
    user_id: str,
    db: AsyncSession,
) -> None:
    """
    Inserts new procedural patterns into the procedural_patterns table.
    Each pattern gets a context_signature embedding computed from its
    trigger_conditions values for fuzzy matching during retrieval.

    Parameters:
        patterns (list[dict])  — pattern dicts from consolidate_episodes():
                                 {pattern_name, trigger_conditions, successful_actions}
        user_id  (str)         — owner of these patterns.
        db       (AsyncSession)— open async DB session.

    Returns:
        None

    Used by: consolidate_user_memory()
    """
    for pattern in patterns:
        name = pattern.get("pattern_name", "").strip()
        trigger = pattern.get("trigger_conditions", {})
        actions = pattern.get("successful_actions", {})

        if not name or not trigger or not actions:
            continue

        # Embed the trigger conditions as a text blob for context_signature.
        trigger_text = " ".join(
            str(v) for v in trigger.values() if isinstance(v, (str, list))
        )
        try:
            signature = await embed_text(trigger_text) if trigger_text else None
        except Exception as exc:
            logger.warning("Procedural pattern embedding failed: %s", exc)
            signature = None

        new_pattern = ProceduralPattern(
            user_id=user_id,
            pattern_name=name,
            trigger_conditions=trigger,
            successful_actions=actions,
            success_rate=0.5,  # Starts neutral; updated as the pattern proves itself
            context_signature=signature,
        )
        db.add(new_pattern)

    await db.flush()


# ---------------------------------------------------------------------------
# Phase F: Mark episodes promoted
# ---------------------------------------------------------------------------


async def _mark_promoted(episode_ids: list[str], db: AsyncSession) -> None:
    """
    Sets promoted=True on all processed episodes so they are not picked up
    by the next consolidation run. Promoted episodes remain in the table
    and are subject to the decay curve.

    Parameters:
        episode_ids (list[str])  — UUID strings of the episodes to mark.
        db          (AsyncSession)— open async DB session.

    Returns:
        None

    Used by: consolidate_user_memory()
    """
    if not episode_ids:
        return

    await db.execute(
        update(Episode)
        .where(Episode.id.in_(episode_ids))
        .values(promoted=True, updated_at=datetime.now(UTC))
    )


# ---------------------------------------------------------------------------
# Public entry point 1: consolidate_user_memory
# ---------------------------------------------------------------------------


async def consolidate_user_memory(user_id: str) -> dict:
    """
    Full consolidation pipeline for one user. Called by the Celery task
    at 3 AM daily. Opens its own DB session so it is independent of the
    FastAPI request lifecycle.

    Phases: A (fetch) → B (re-score) → C (chunk + Qwen-Long) →
            D (contradiction resolution) → E (write-back) → F (promote)

    Parameters:
        user_id (str) — UUID string of the user to consolidate.

    Returns:
        dict — summary of the run:
               {
                 "user_id":          str,
                 "episodes_processed": int,
                 "facts_written":    int,
                 "patterns_written": int,
                 "episodes_to_forget": int,
               }
               Used by the Celery task for logging.

    Raises:
        Does not raise — all inner failures are caught and logged so one
        user's consolidation failure doesn't abort the batch job.

    Used by: app/tasks/scheduled_tasks.py → consolidate_all_users()
    """
    summary = {
        "user_id": user_id,
        "episodes_processed": 0,
        "facts_written": 0,
        "patterns_written": 0,
        "episodes_to_forget": 0,
    }

    try:
        async with AsyncSessionLocal() as db:
            # ── Phase A ────────────────────────────────────────────────────
            pending = await _fetch_pending_episodes(user_id, db)
            if not pending:
                logger.info("consolidate_user_memory: no pending episodes for %s", user_id)
                return summary

            summary["episodes_processed"] = len(pending)
            episode_ids = [str(ep.id) for ep in pending]

            # ── Phase B ────────────────────────────────────────────────────
            total = len(pending)
            for ep in pending:
                ep.importance_score = _recalculate_importance(ep, total)

            # ── Phase C ────────────────────────────────────────────────────
            # Serialise episodes to plain dicts for the Qwen-Long prompt.
            episode_dicts = [
                {
                    "id": str(ep.id),
                    "raw_prompt": ep.raw_prompt,
                    "llm_response": ep.llm_response[:500],  # Truncate to keep prompt size manageable
                    "importance_score": ep.importance_score,
                }
                for ep in pending
            ]

            all_semantic_facts: list[dict] = []
            all_procedural_patterns: list[dict] = []
            all_to_forget: list[str] = []
            # Only promote episodes from chunks that succeeded — if Qwen
            # fails for a chunk, those episodes stay unpromoted so they are
            # retried on the next consolidation run rather than being silently
            # dropped forever.
            successfully_processed_ids: list[str] = []

            chunks = [
                episode_dicts[i : i + CHUNK_SIZE]
                for i in range(0, len(episode_dicts), CHUNK_SIZE)
            ]

            for chunk in chunks:
                try:
                    result = await consolidate_episodes(chunk)
                    all_semantic_facts.extend(result.get("semantic_facts", []))
                    all_procedural_patterns.extend(result.get("procedural_patterns", []))
                    all_to_forget.extend(result.get("to_forget", []))
                    # Mark only this chunk's episodes for promotion.
                    successfully_processed_ids.extend(ep["id"] for ep in chunk)
                except Exception as exc:
                    logger.error(
                        "Chunk consolidation failed for user %s: %s", user_id, exc
                    )
                    continue  # Skip the failed chunk, process the rest

            summary["episodes_to_forget"] = len(all_to_forget)

            # ── Phase D ────────────────────────────────────────────────────
            resolved_facts = await _resolve_contradictions(
                all_semantic_facts, user_id, db
            )

            # ── Phase E ────────────────────────────────────────────────────
            await _write_semantic_facts(resolved_facts, user_id, episode_ids, db)
            await _write_procedural_patterns(all_procedural_patterns, user_id, db)

            summary["facts_written"] = len(resolved_facts)
            summary["patterns_written"] = len(all_procedural_patterns)

            # ── Phase F ────────────────────────────────────────────────────
            # Only promote episodes whose chunk completed without error.
            if successfully_processed_ids:
                await _mark_promoted(successfully_processed_ids, db)

            await db.commit()
            logger.info("consolidate_user_memory complete: %s", summary)

    except Exception as exc:
        logger.error(
            "consolidate_user_memory failed for user %s: %s", user_id, exc
        )

    return summary


# ---------------------------------------------------------------------------
# Public entry point 2: decay_refresh
# ---------------------------------------------------------------------------


async def decay_refresh(user_id: str) -> dict:
    """
    Applies the biological forgetting curve to all promoted episodes for
    a user and hard-deletes those that have decayed below the pruning
    threshold and are older than PRUNE_AGE_DAYS.

    Decay formula per run:
        new_decay_weight = current_decay_weight * DEFAULT_DECAY_RATE (0.96)

    Pruning condition (both must be true):
        decay_weight < PRUNE_DECAY_THRESHOLD (0.30)
        created_at   < now() - PRUNE_AGE_DAYS (90 days)

    Parameters:
        user_id (str) — UUID string of the user whose episodes should decay.

    Returns:
        dict — {"user_id": str, "decayed": int, "pruned": int}

    Raises:
        Does not raise — failures are caught and logged.

    Used by: app/tasks/scheduled_tasks.py → refresh_all_decay()
    """
    summary = {"user_id": user_id, "decayed": 0, "pruned": 0}

    try:
        async with AsyncSessionLocal() as db:
            # Apply decay multiplier to all promoted episodes for this user.
            decay_result = await db.execute(
                update(Episode)
                .where(Episode.user_id == user_id)
                .where(Episode.promoted == True)  # noqa: E712
                .values(
                    decay_weight=Episode.decay_weight * DEFAULT_DECAY_RATE,
                    updated_at=datetime.now(UTC),
                )
            )
            summary["decayed"] = decay_result.rowcount

            # Hard-delete episodes below the pruning threshold that are old enough.
            prune_cutoff = datetime.now(UTC) - timedelta(days=PRUNE_AGE_DAYS)
            prune_result = await db.execute(
                delete(Episode)
                .where(Episode.user_id == user_id)
                .where(Episode.promoted == True)  # noqa: E712
                .where(Episode.decay_weight < PRUNE_DECAY_THRESHOLD)
                .where(Episode.created_at < prune_cutoff)
            )
            summary["pruned"] = prune_result.rowcount

            await db.commit()
            logger.info("decay_refresh complete: %s", summary)

    except Exception as exc:
        logger.error("decay_refresh failed for user %s: %s", user_id, exc)

    return summary