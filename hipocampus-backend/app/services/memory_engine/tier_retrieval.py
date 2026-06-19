"""
app/services/memory_engine/tier_retrieval.py

The core retrieval pipeline. Given a user message, this module:
  1. Expands the query into multiple semantic variants (via Qwen-Max).
  2. Embeds all variants and runs parallel cosine similarity searches
     across all three persistent memory tiers (episodic, semantic, procedural).
  3. Deduplicates, ranks, and confidence-filters the results.
  4. Folds everything into a single [MEMORY_CONTEXT] block that fits inside
     the LLM's context window.
  5. Detects contradictions between the current message and stored facts
     and raises MemoryConflictError when resolution is required.

This is the most complex file in the memory engine. Every function has a
single responsibility so the pipeline steps stay independently testable.

Used by: app/services/chat_service.py → process_turn()
"""

import asyncio
import logging
from dataclasses import dataclass, field

from sqlalchemy import select, text # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore

from app.core.exceptions import MemoryConflictError
from app.services.memory_engine.qwen_router import embed_text, expand_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retrieval thresholds — tune these without touching query logic
# ---------------------------------------------------------------------------

# Maximum cosine distance (0 = identical, 2 = opposite) accepted per tier.
# Lower value = stricter match. Procedural uses the tightest threshold
# because action patterns must be highly relevant to be safe to inject.
EPISODIC_DISTANCE_THRESHOLD = 0.70
SEMANTIC_DISTANCE_THRESHOLD = 0.65
PROCEDURAL_DISTANCE_THRESHOLD = 0.60

# Maximum results fetched per tier before ranking.
RESULTS_PER_TIER = 4

# Minimum confidence for a semantic fact to be injected into context.
SEMANTIC_CONFIDENCE_MIN = 0.60

# Minimum success rate for a procedural pattern to be injected.
PROCEDURAL_SUCCESS_RATE_MIN = 0.40

# Hard token budget for the entire [MEMORY_CONTEXT] block.
# ~4 chars per token is a safe approximation for English/code text.
MAX_CONTEXT_TOKENS = 1_500
CHARS_PER_TOKEN = 4

# Cosine similarity threshold above which two facts are considered
# contradictory (semantically close but textually divergent).
CONFLICT_SIMILARITY_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Internal data containers
# ---------------------------------------------------------------------------


@dataclass
class RetrievedFact:
    """
    Normalised container for a single result from any memory tier.
    Holding tier results in one type lets rank_and_fold() treat them uniformly.

    Fields:
        tier       (str)   — "episodic" | "semantic" | "procedural"
        content    (str)   — the human-readable text to inject into context
        score      (float) — normalised relevance score (higher = more relevant)
        confidence (float) — the stored confidence / success_rate value
        source_id  (str)   — UUID of the source row, used for deduplication
    """
    tier: str
    content: str
    score: float
    confidence: float
    source_id: str
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Step 1: Query expansion
# ---------------------------------------------------------------------------


async def _expand_query(user_message: str) -> list[str]:
    """
    Wraps qwen_router.expand_query() and always returns at least the
    original message. Expansion failures are non-fatal — the search
    continues with the original query.

    Parameters:
        user_message (str) — the raw message from the current turn.

    Returns:
        list[str] — 1–3 query strings for vector search. Always non-empty.

    Used by: retrieve_all_tiers()
    """
    try:
        variants = await expand_query(user_message)
        # Deduplicate while preserving order.
        seen: set[str] = set()
        result: list[str] = []
        for v in [user_message, *variants]:
            if v not in seen:
                seen.add(v)
                result.append(v)
        return result
    except Exception as exc:
        logger.warning("Query expansion failed, using raw message: %s", exc)
        return [user_message]


# ---------------------------------------------------------------------------
# Step 2: Parallel vector search across all three tiers
# ---------------------------------------------------------------------------


async def _search_episodic(
    query_embedding: list[float],
    user_id: str,
    db: AsyncSession,
) -> list[RetrievedFact]:
    """
    Searches the episodes table for unpromoted episodes similar to the
    current query. Unpromoted episodes are recent raw exchanges not yet
    distilled into semantic facts — useful for short-term continuity.

    Parameters:
        query_embedding (list[float]) — 1536-dim embedding of the query string.
        user_id         (str)         — filters results to this user only.
        db              (AsyncSession)— async DB session.

    Returns:
        list[RetrievedFact] — up to RESULTS_PER_TIER results above the
                              distance threshold, ordered by similarity.

    Used by: _parallel_vector_search()
    """
    # pgvector <=> operator computes cosine distance (0=identical, 2=opposite).
    # Cast the Python list to a pgvector literal so SQLAlchemy passes it correctly.
    embedding_literal = str(query_embedding)

    result = await db.execute(
        text(
            """
            SELECT id, raw_prompt, llm_response, importance_score,
                   embedding <=> CAST(:embedding AS vector) AS distance
            FROM episodes
            WHERE user_id = :user_id
              AND promoted = FALSE
              AND embedding IS NOT NULL
              AND embedding <=> CAST(:embedding AS vector) < :threshold
            ORDER BY distance ASC
            LIMIT :limit
            """
        ),
        {
            "embedding": embedding_literal,
            "user_id": user_id,
            "threshold": EPISODIC_DISTANCE_THRESHOLD,
            "limit": RESULTS_PER_TIER,
        },
    )
    rows = result.mappings().all()

    facts: list[RetrievedFact] = []
    for row in rows:
        distance = float(row["distance"])
        score = 1.0 - (distance / 2.0)  # Normalise distance [0,2] → score [0,1]
        content = f"[Past exchange] User asked: {row['raw_prompt'][:200]}"
        facts.append(
            RetrievedFact(
                tier="episodic",
                content=content,
                score=score,
                confidence=float(row["importance_score"]),
                source_id=str(row["id"]),
            )
        )
    return facts


async def _search_semantic(
    query_embedding: list[float],
    user_id: str,
    db: AsyncSession,
) -> list[RetrievedFact]:
    """
    Searches semantic_facts for distilled user preferences and knowledge
    that match the current query. Only non-conflicted facts above the
    confidence minimum are returned — conflicted facts need resolution first.

    Parameters:
        query_embedding (list[float]) — 1536-dim embedding of the query string.
        user_id         (str)         — filters results to this user only.
        db              (AsyncSession)— async DB session.

    Returns:
        list[RetrievedFact] — up to RESULTS_PER_TIER results.

    Used by: _parallel_vector_search()
    """
    embedding_literal = str(query_embedding)

    result = await db.execute(
        text(
            """
            SELECT id, fact_text, confidence,
                   embedding <=> CAST(:embedding AS vector) AS distance
            FROM semantic_facts
            WHERE user_id = :user_id
              AND is_conflicted = FALSE
              AND confidence >= :min_confidence
              AND embedding IS NOT NULL
              AND embedding <=> CAST(:embedding AS vector) < :threshold
            ORDER BY distance ASC
            LIMIT :limit
            """
        ),
        {
            "embedding": embedding_literal,
            "user_id": user_id,
            "min_confidence": SEMANTIC_CONFIDENCE_MIN,
            "threshold": SEMANTIC_DISTANCE_THRESHOLD,
            "limit": RESULTS_PER_TIER,
        },
    )
    rows = result.mappings().all()

    facts: list[RetrievedFact] = []
    for row in rows:
        distance = float(row["distance"])
        score = 1.0 - (distance / 2.0)
        facts.append(
            RetrievedFact(
                tier="semantic",
                content=row["fact_text"],
                score=score,
                confidence=float(row["confidence"]),
                source_id=str(row["id"]),
            )
        )
    return facts


async def _search_procedural(
    query_embedding: list[float],
    user_message: str,
    user_id: str,
    db: AsyncSession,
) -> list[RetrievedFact]:
    """
    Searches procedural_patterns using two signals:
      1. Keyword trigger matching (JSONB @> check on trigger_conditions.contains).
      2. Vector similarity on context_signature for fuzzy topic matching.

    Only patterns above PROCEDURAL_SUCCESS_RATE_MIN are considered —
    low-performing patterns are excluded before they can pollute context.

    Parameters:
        query_embedding (list[float]) — 1536-dim embedding of the query string.
        user_message    (str)         — raw user message for keyword trigger matching.
        user_id         (str)         — filters results to this user only.
        db              (AsyncSession)— async DB session.

    Returns:
        list[RetrievedFact] — up to RESULTS_PER_TIER results.

    Used by: _parallel_vector_search()
    """
    embedding_literal = str(query_embedding)
    lowered_message = user_message.lower()

    result = await db.execute(
        text(
            """
            SELECT id, pattern_name, trigger_conditions, successful_actions,
                   success_rate,
                   context_signature <=> CAST(:embedding AS vector) AS distance
            FROM procedural_patterns
            WHERE user_id = :user_id
              AND success_rate >= :min_rate
              AND context_signature IS NOT NULL
              AND context_signature <=> CAST(:embedding AS vector) < :threshold
            ORDER BY distance ASC
            LIMIT :limit
            """
        ),
        {
            "embedding": embedding_literal,
            "user_id": user_id,
            "min_rate": PROCEDURAL_SUCCESS_RATE_MIN,
            "threshold": PROCEDURAL_DISTANCE_THRESHOLD,
            "limit": RESULTS_PER_TIER,
        },
    )
    rows = result.mappings().all()

    facts: list[RetrievedFact] = []
    for row in rows:
        # Secondary keyword gate: if trigger_conditions specifies keywords,
        # all of them must appear in the user message for the pattern to fire.
        trigger = row["trigger_conditions"] or {}
        required_keywords: list[str] = trigger.get("contains", [])
        if required_keywords and not all(kw in lowered_message for kw in required_keywords):
            continue  # Keyword gate failed — skip this pattern

        distance = float(row["distance"])
        score = 1.0 - (distance / 2.0)
        content = (
            f"[Procedural] {row['pattern_name']}: "
            f"use approach → {row['successful_actions']}"
        )
        facts.append(
            RetrievedFact(
                tier="procedural",
                content=content,
                score=score,
                confidence=float(row["success_rate"]),
                source_id=str(row["id"]),
                metadata={"successful_actions": row["successful_actions"]},
            )
        )
    return facts


async def _parallel_vector_search(
    queries: list[str],
    user_message: str,
    user_id: str,
    db: AsyncSession,
) -> list[RetrievedFact]:
    """
    Embeds all expanded query strings concurrently, then runs all three
    tier searches concurrently using asyncio.gather. The results are
    merged and deduplicated by source_id.

    Parallelism here is safe because each search is a read-only DB query
    with its own sub-result — no shared mutable state.

    Parameters:
        queries      (list[str])    — 1–3 query strings from _expand_query().
        user_message (str)          — raw user message (passed to procedural search
                                      for keyword trigger matching).
        user_id      (str)          — filters all searches to this user.
        db           (AsyncSession) — async DB session.

    Returns:
        list[RetrievedFact] — merged, deduplicated results from all tiers.

    Used by: retrieve_all_tiers()
    """
    # Embed all query variants concurrently.
    embeddings: list[list[float]] = await asyncio.gather(
        *[embed_text(q) for q in queries]
    )

    # For each embedding, search all three tiers concurrently.
    all_search_tasks = []
    for emb in embeddings:
        all_search_tasks.extend([
            _search_episodic(emb, user_id, db),
            _search_semantic(emb, user_id, db),
            _search_procedural(emb, user_message, user_id, db),
        ])

    tier_results: list[list[RetrievedFact]] = await asyncio.gather(*all_search_tasks)

    # Flatten and deduplicate by source_id (keep highest score per source).
    seen_ids: dict[str, RetrievedFact] = {}
    for result_list in tier_results:
        for fact in result_list:
            if fact.source_id not in seen_ids or fact.score > seen_ids[fact.source_id].score:
                seen_ids[fact.source_id] = fact

    return list(seen_ids.values())


# ---------------------------------------------------------------------------
# Step 3: Rank, filter, and fold into context block
# ---------------------------------------------------------------------------


def _rank_and_fold(facts: list[RetrievedFact]) -> tuple[str, int]:
    """
    Sorts the retrieved facts by a combined relevance×confidence score,
    then folds them into a structured [MEMORY_CONTEXT] block string.
    The block is token-budgeted: items are dropped from the bottom of the
    ranked list until the block fits within MAX_CONTEXT_TOKENS.

    The output format is deterministic so the LLM always sees memory in
    the same structure regardless of which tier items came from.

    Parameters:
        facts (list[RetrievedFact]) — deduplicated results from all tiers.

    Returns:
        tuple[str, int]:
            str — the complete [MEMORY_CONTEXT]...[/MEMORY_CONTEXT] block,
                  or an empty string if there are no relevant facts.
            int — estimated token count of the block (for ChatResponse metadata).

    Used by: retrieve_all_tiers()
    """
    if not facts:
        return "", 0

    # Rank by score × confidence — both signals must be high to surface.
    ranked = sorted(facts, key=lambda f: f.score * f.confidence, reverse=True)

    # Segregate by tier for a structured output block.
    preferences: list[str] = []
    procedural: list[str] = []
    episodes: list[str] = []

    for fact in ranked:
        if fact.tier == "semantic":
            preferences.append(fact.content)
        elif fact.tier == "procedural":
            procedural.append(fact.content)
        elif fact.tier == "episodic":
            episodes.append(fact.content)

    lines: list[str] = ["[MEMORY_CONTEXT]"]
    if preferences:
        lines.append("# USER PREFERENCES & FACTS:")
        lines.extend(f"  - {p}" for p in preferences)
    if procedural:
        lines.append("# PROCEDURAL PATTERNS:")
        lines.extend(f"  - {p}" for p in procedural)
    if episodes:
        lines.append("# RELEVANT PAST EXCHANGES:")
        lines.extend(f"  - {e}" for e in episodes)
    lines.append("[/MEMORY_CONTEXT]")

    block = "\n".join(lines)

    # Token-budget enforcement: trim from the bottom until it fits.
    while len(block) > MAX_CONTEXT_TOKENS * CHARS_PER_TOKEN and len(lines) > 2:
        # Remove the last content line before the closing tag.
        lines.pop(-2)
        block = "\n".join(lines)

    estimated_tokens = len(block) // CHARS_PER_TOKEN
    return block, estimated_tokens


# ---------------------------------------------------------------------------
# Step 4: Conflict detection
# ---------------------------------------------------------------------------


async def _detect_conflict(
    user_message: str,
    user_id: str,
    db: AsyncSession,
) -> None:
    """
    Checks whether the current user message contradicts any high-confidence
    stored semantic fact. A contradiction is detected when the message's
    embedding is semantically close to a stored fact (similar topic) but
    the message content appears to override it (checked by keyword heuristic).

    This is a lightweight pre-flight check — full contradiction resolution
    happens in the sleep consolidator. Here we only raise a flag when the
    contradiction is obvious enough to warrant stopping the turn and asking
    the user to confirm.

    Parameters:
        user_message (str)         — the raw user message for this turn.
        user_id      (str)         — filters facts to this user.
        db           (AsyncSession)— async DB session.

    Returns:
        None — raises MemoryConflictError if a contradiction is found,
               returns silently otherwise.

    Raises:
        app.core.exceptions.MemoryConflictError — when the user's message
            contradicts a stored semantic fact with confidence >= 0.8.
            The chat route catches this and returns a 409 so the React
            client shows the conflict resolution UI.

    Used by: retrieve_all_tiers()
    """
    override_signals = [
        "switch to", "change to", "use instead", "replace with",
        "no longer", "stop using", "don't use", "switch from",
        "migrate to", "move to", "now use",
    ]
    lowered = user_message.lower()
    if not any(sig in lowered for sig in override_signals):
        return  # No override language detected — skip the conflict check

    # Embed the message and find semantically close high-confidence facts.
    query_embedding = await embed_text(user_message)
    embedding_literal = str(query_embedding)

    result = await db.execute(
        text(
            """
            SELECT id, fact_text, confidence
            FROM semantic_facts
            WHERE user_id = :user_id
              AND confidence >= 0.8
              AND is_conflicted = FALSE
              AND embedding IS NOT NULL
              AND embedding <=> CAST(:embedding AS vector) < :threshold
            ORDER BY embedding <=> CAST(:embedding AS vector) ASC
            LIMIT 1
            """
        ),
        {
            "embedding": embedding_literal,
            "user_id": user_id,
            "threshold": CONFLICT_SIMILARITY_THRESHOLD,
        },
    )
    row = result.mappings().first()

    if row:
        raise MemoryConflictError(
            f"Your message appears to override a stored preference: "
            f"\"{row['fact_text']}\" (confidence {row['confidence']:.0%}). "
            f"Confirm override to proceed."
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def retrieve_all_tiers(
    user_message: str,
    user_id: str,
    db: AsyncSession,
) -> tuple[str, int]:
    """
    Full retrieval pipeline. Orchestrates all steps in order:
      1. Expand the user message into semantic query variants.
      2. Check for contradictions against stored high-confidence facts.
      3. Run parallel vector search across all three memory tiers.
      4. Rank, deduplicate, and fold results into a context block.

    This is the only function chat_service.py needs to call — it returns
    a ready-to-inject string and a token count.

    Parameters:
        user_message (str)         — the raw message from the current turn.
        user_id      (str)         — the authenticated user's UUID string.
        db           (AsyncSession)— async DB session from Depends(get_db).

    Returns:
        tuple[str, int]:
            str — the [MEMORY_CONTEXT] block (empty string on cold start).
            int — estimated token count of the block.

    Raises:
        app.core.exceptions.MemoryConflictError — if the message overrides a
            stored fact; propagated up to the chat route which returns 409.

    Used by: app/services/chat_service.py → process_turn()
    """
    # Step 1: expand query
    queries = await _expand_query(user_message)

    # Step 2: conflict detection (raises MemoryConflictError if needed)
    await _detect_conflict(user_message, user_id, db)

    # Step 3: parallel vector search
    facts = await _parallel_vector_search(queries, user_message, user_id, db)

    # Step 4: rank and fold
    context_block, token_count = _rank_and_fold(facts)

    logger.debug(
        "retrieve_all_tiers user=%s queries=%d facts=%d tokens=%d",
        user_id, len(queries), len(facts), token_count,
    )

    return context_block, token_count