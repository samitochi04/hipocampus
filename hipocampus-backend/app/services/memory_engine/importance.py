"""
app/services/memory_engine/importance.py

Computes a 0.0–1.0 importance score for each user↔AI exchange.
The score gates episodic storage and drives consolidation priority:

    >= 0.6  → saved as consolidation_candidate, processed next sleep cycle
    >= 0.45 → saved to episodes but lower priority for consolidation
    < 0.45  → skipped (kept only in the Redis buffer, never hits Postgres)

The formula combines four independent signals:
    1. recency_weight    — how active this user has been lately
    2. frequency_bonus   — how often similar topics appear in their history
    3. surprise_delta    — how novel this exchange is vs their baseline
    4. explicit_flag     — did the user use high-commitment language?

Each signal is bounded to prevent any single factor from dominating.
The final score is clipped to [0.0, 1.0].

Used by: app/services/chat_service.py → process_turn()
"""

import logging
import math

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.episode import Episode
from app.services.memory_engine.qwen_router import embed_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signal bounds (tweak here, not inside the formula functions)
# ---------------------------------------------------------------------------

RECENCY_MAX = 1.0
RECENCY_MIN = 0.3
FREQUENCY_MAX = 1.5
FREQUENCY_MIN = 1.0
SURPRISE_MAX = 1.2
SURPRISE_MIN = 0.8
EXPLICIT_BOOST = 2.0   # Multiplier when high-commitment language is detected
EXPLICIT_NONE = 1.0

# Words that signal the user is expressing a strong, lasting preference.
# Presence of ANY of these in the user message triggers the explicit boost.
EXPLICIT_KEYWORDS = frozenset([
    "always", "never", "strictly", "require", "must", "only",
    "every time", "without exception", "mandatory", "enforce",
])


# ---------------------------------------------------------------------------
# Individual signal functions
# ---------------------------------------------------------------------------


def _recency_weight(active_session_count: int) -> float:
    """
    Scores how recently / frequently the user has been active.
    More active users get higher recency weights because their exchanges
    are more likely to represent evolving, relevant preferences.

    Formula: clamp(0.5 + active_sessions / 10, RECENCY_MIN, RECENCY_MAX)
    A user with 5 active sessions in the last 30 days → 0.5 + 0.5 = 1.0 (max).
    A brand-new user with 0 sessions → 0.5 (neutral).

    Parameters:
        active_session_count (int) — number of sessions this user has started
                                     in the last 30 days, queried by score_importance().

    Returns:
        float — in range [RECENCY_MIN, RECENCY_MAX].

    Used by: score_importance()
    """
    raw = 0.5 + (active_session_count / 10.0)
    return max(RECENCY_MIN, min(RECENCY_MAX, raw))


def _frequency_bonus(similar_episode_count: int) -> float:
    """
    Boosts importance when the same topic has appeared multiple times —
    repetition signals genuine long-term relevance.

    Formula: clamp(1.0 + log1p(similar_count) * 0.2, FREQUENCY_MIN, FREQUENCY_MAX)
    0 similar episodes  → 1.0 (no boost)
    10 similar episodes → ~1.0 + log(11)*0.2 ≈ 1.48 (near max)

    Parameters:
        similar_episode_count (int) — number of existing episodes whose
                                      raw_prompt contains the same leading
                                      30-char token as the current message.

    Returns:
        float — in range [FREQUENCY_MIN, FREQUENCY_MAX].

    Used by: score_importance()
    """
    raw = 1.0 + math.log1p(similar_episode_count) * 0.2
    return max(FREQUENCY_MIN, min(FREQUENCY_MAX, raw))


def _surprise_delta(
    current_embedding: list[float],
    centroid_embedding: list[float] | None,
) -> float:
    """
    Measures how novel this exchange is relative to the user's existing
    semantic memory baseline (the centroid of all their stored embeddings).
    Novel exchanges score higher because they represent new knowledge worth retaining.

    Formula: clamp(1.0 / (1.0 + cosine_similarity), SURPRISE_MIN, SURPRISE_MAX)
    High similarity (familiar topic) → low surprise → score closer to SURPRISE_MIN.
    Low similarity (novel topic)     → high surprise → score closer to SURPRISE_MAX.

    Parameters:
        current_embedding  (list[float])       — 1536-dim embedding of the current
                                                  user message + LLM response.
        centroid_embedding (list[float] | None) — average embedding across all the user's
                                                  stored episodes. None if the user has no
                                                  episodes yet (cold start) → returns neutral 1.0.

    Returns:
        float — in range [SURPRISE_MIN, SURPRISE_MAX].

    Used by: score_importance()
    """
    if centroid_embedding is None:
        return 1.0  # Cold start: no baseline to compare against, treat as neutral

    # Cosine similarity via dot product of normalised vectors.
    dot = sum(a * b for a, b in zip(current_embedding, centroid_embedding))
    norm_a = math.sqrt(sum(a * a for a in current_embedding)) or 1e-9
    norm_b = math.sqrt(sum(b * b for b in centroid_embedding)) or 1e-9
    cosine_sim = dot / (norm_a * norm_b)

    raw = 1.0 / (1.0 + cosine_sim)
    return max(SURPRISE_MIN, min(SURPRISE_MAX, raw))


def _explicit_flag(user_message: str) -> float:
    """
    Detects high-commitment language that signals the user is expressing
    a strong, lasting preference rather than a one-off request.
    These exchanges should almost always be remembered.

    Parameters:
        user_message (str) — the raw message the user sent this turn.

    Returns:
        float — EXPLICIT_BOOST (2.0) if any keyword found, EXPLICIT_NONE (1.0) otherwise.

    Used by: score_importance()
    """
    lowered = user_message.lower()
    if any(kw in lowered for kw in EXPLICIT_KEYWORDS):
        return EXPLICIT_BOOST
    return EXPLICIT_NONE


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------


async def score_importance(
    user_message: str,
    llm_response: str,
    user_id: str,
    db: AsyncSession,
) -> float:
    """
    Computes the final 0.0–1.0 importance score for the current turn by
    combining all four signals and clipping the product to [0.0, 1.0].

    Final formula:
        raw = recency_weight × frequency_bonus × surprise_delta × explicit_flag
        score = clip(raw, 0.0, 1.0)

    This function performs two async DB queries and one embedding API call:
      1. Count of active sessions in the last 30 days (recency).
      2. Count of similar prior episodes by prompt prefix (frequency).
      3. Centroid embedding of all user episodes (surprise baseline).
      4. Embedding of the current message + response (surprise delta).

    Parameters:
        user_message  (str)          — the raw user message for this turn.
        llm_response  (str)          — the model's reply for this turn.
        user_id       (str)          — UUID string of the authenticated user.
        db            (AsyncSession) — async DB session for the history queries.

    Returns:
        float — importance score in [0.0, 1.0], rounded to 3 decimal places.
                Caller compares this against the 0.45 and 0.6 thresholds to
                decide whether and how urgently to store the episode.

    Raises:
        Does not raise — all sub-calls are wrapped in try/except so a scoring
        failure degrades to a neutral score (0.5) rather than breaking the turn.

    Used by: app/services/chat_service.py → process_turn()
    """
    try:
        # ── Signal 1: recency ───────────────────────────────────────────────
        active_count_result = await db.execute(
            select(func.count(Episode.id).label("cnt"))
            .where(Episode.user_id == user_id)
            .where(text("created_at > now() - interval '30 days'"))
        )
        active_session_count: int = active_count_result.scalar() or 0
        recency = _recency_weight(active_session_count)

        # ── Signal 2: frequency ─────────────────────────────────────────────
        # Use the first 40 chars of the prompt as a rough topic fingerprint.
        prompt_prefix = user_message[:40].replace("%", "")  # sanitise LIKE wildcard
        similar_count_result = await db.execute(
            select(func.count(Episode.id).label("cnt"))
            .where(Episode.user_id == user_id)
            .where(Episode.raw_prompt.ilike(f"%{prompt_prefix}%"))
        )
        similar_count: int = similar_count_result.scalar() or 0
        frequency = _frequency_bonus(similar_count)

        # ── Signal 3: surprise ──────────────────────────────────────────────
        # Embed the current exchange.
        combined_text = f"{user_message}\n\n{llm_response}"
        current_embedding = await embed_text(combined_text)

        # Fetch the average (centroid) embedding across all stored user episodes.
        # avg() on a pgvector column returns the element-wise mean vector.
        centroid_result = await db.execute(
            select(func.avg(Episode.embedding).label("centroid"))
            .where(Episode.user_id == user_id)
            .where(Episode.embedding.isnot(None))
        )
        centroid_row = centroid_result.first()

        # pgvector's avg() aggregate may return the vector as a string
        # '[-0.12, 0.34, ...]' rather than a list[float], depending on the
        # SQLAlchemy driver version. list(string) iterates over characters
        # which causes "can't multiply sequence by non-int of type 'float'"
        # inside _surprise_delta. We detect and handle both return types.
        centroid_embedding: list[float] | None = None
        if centroid_row and centroid_row.centroid is not None:
            raw = centroid_row.centroid
            if isinstance(raw, str):
                # String form: '[0.1, 0.2, ...]' — parse as JSON list.
                import json as _json
                try:
                    centroid_embedding = _json.loads(raw)
                except (_json.JSONDecodeError, ValueError):
                    # Fallback: strip brackets and split on commas.
                    centroid_embedding = [
                        float(x) for x in raw.strip("[] \n").split(",") if x.strip()
                    ]
            else:
                # Already iterable (pgvector Python type or list).
                centroid_embedding = list(raw)
        surprise = _surprise_delta(current_embedding, centroid_embedding)

        # ── Signal 4: explicit flag ─────────────────────────────────────────
        explicit = _explicit_flag(user_message)

        # ── Combine ─────────────────────────────────────────────────────────
        raw_score = recency * frequency * surprise * explicit
        final_score = round(max(0.0, min(1.0, raw_score)), 3)

        logger.debug(
            "score_importance user=%s recency=%.2f freq=%.2f surprise=%.2f "
            "explicit=%.1f → %.3f",
            user_id, recency, frequency, surprise, explicit, final_score,
        )
        return final_score

    except Exception as exc:
        # Scoring is non-critical — a failure must never break the chat turn.
        # Log the error and return a neutral score so the episode is still saved.
        logger.error("score_importance failed for user %s: %s", user_id, exc)
        return 0.5