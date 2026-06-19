"""
app/services/chat_service.py

The central orchestrator for every chat turn.
This is where every memory engine component is called in sequence.

process_turn() is the only public function. It is called by the /chat
route handler and returns the final response payload. The route handler
does nothing except call this function and return its output.

Turn sequence (mirrors the blueprint exactly):
  1.  Push the user message to the Redis working-memory buffer.
  2.  Retrieve multi-tier memory context via tier_retrieval.
  3.  Assemble the final prompt (system prompt + memory context + buffer history).
  4.  Call Qwen-Max and get the response.
  5.  Push the assistant reply to the Redis buffer.
  6.  Embed the episode (async, non-blocking to caller).
  7.  Score importance and conditionally write the episode to PostgreSQL.
  8.  Return the ChatResponse payload.

Used by: app/api/v1/chat.py exclusively.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession # type: ignore

from app.models.episode import Episode
from app.schemas.auth import UserOut
from app.schemas.chat import ChatResponse
from app.services.memory_engine.importance import score_importance
from app.services.memory_engine.qwen_router import embed_text, generate
from app.services.memory_engine.redis_buffer import get_buffer, push_message
from app.services.memory_engine.tier_retrieval import retrieve_all_tiers

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

# The [MEMORY_CONTEXT] placeholder is replaced at runtime with the block
# returned by retrieve_all_tiers(). On cold start (no stored memory) it is
# replaced with an empty string so the system prompt stays clean.

SYSTEM_PROMPT_TEMPLATE = """You are Hipocampus, a highly capable technical assistant \
with persistent memory. You remember the user's preferences, past decisions, and \
recurring patterns across sessions.

{memory_context}

Instructions:
- Always follow stored preferences exactly. Never contradict them unless the user \
explicitly asks you to override.
- When writing code, match the exact libraries, versions, and patterns the user \
has used before.
- Be direct and technically precise. Avoid padding or filler sentences.
- If you are uncertain about a stored preference, state the uncertainty clearly \
rather than guessing.
"""

# Importance thresholds — must stay in sync with importance.py comments.
IMPORTANCE_THRESHOLD_SAVE = 0.45      # Minimum score to write to episodes table
IMPORTANCE_THRESHOLD_CANDIDATE = 0.60  # Score above which row is a consolidation candidate


# ---------------------------------------------------------------------------
# Session ID management
# ---------------------------------------------------------------------------


def _get_or_create_session_id(user_id: str) -> str:
    """
    Generates a stable session ID for a user's current conversation.
    In the current implementation each server restart begins a new session.
    A production upgrade would store the active session_id in Redis so it
    persists across restarts and API pod restarts.

    Parameters:
        user_id (str) — UUID string of the authenticated user.
                        Included in the session ID for human-readable Redis keys.

    Returns:
        str — e.g. "sess-usr_8a3f2c-4f3a1b2c"

    Used by: process_turn()
    """
    # In a future iteration, fetch from Redis: GET session:{user_id}:current_session
    # For now, generate a reproducible ID from user_id + today's date so the
    # same session persists within a calendar day.
    today = datetime.now(UTC).strftime("%Y%m%d")
    short_uid = user_id.replace("-", "")[:8]
    return f"sess-{short_uid}-{today}"


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def _assemble_prompt(memory_context: str) -> str:
    """
    Injects the retrieved memory context block into the system prompt template.
    If memory_context is empty (cold start), the {memory_context} placeholder
    is replaced with a minimal "no prior memory" note so the LLM doesn't
    hallucinate stored preferences.

    Parameters:
        memory_context (str) — the [MEMORY_CONTEXT]...[/MEMORY_CONTEXT] block
                               returned by tier_retrieval.retrieve_all_tiers(),
                               or an empty string on cold start.

    Returns:
        str — the fully assembled system prompt ready to send to Qwen-Max.

    Used by: process_turn()
    """
    if not memory_context.strip():
        context_section = "(No prior memory found for this user. Treat this as a fresh session.)"
    else:
        context_section = memory_context

    return SYSTEM_PROMPT_TEMPLATE.format(memory_context=context_section)


# ---------------------------------------------------------------------------
# Background embedding task
# ---------------------------------------------------------------------------


async def _embed_and_update_episode(episode_id: str, text: str, db: AsyncSession) -> None:
    """
    Computes the embedding for a newly created episode and writes it back
    to the DB. Called as a fire-and-forget background task after process_turn()
    returns its response to the client, so embedding latency never adds to
    the user-perceived response time.

    Parameters:
        episode_id (str)         — UUID string of the Episode row to update.
        text       (str)         — concatenated user_message + llm_response to embed.
        db         (AsyncSession)— async DB session (kept open by the background task).

    Returns:
        None

    Raises:
        Does not raise — failures are logged but never surface to the client
        because this runs after the response is already sent.

    Used by: process_turn() via asyncio.create_task()
    """
    try:
        embedding = await embed_text(text)
        from sqlalchemy import update as sa_update # type: ignore
        await db.execute(
            sa_update(Episode)
            .where(Episode.id == episode_id)
            .values(embedding=embedding)
        )
        await db.commit()
        logger.debug("Embedded episode %s", episode_id)
    except Exception as exc:
        logger.error("Failed to embed episode %s: %s", episode_id, exc)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def process_turn(
    user_message: str,
    current_user: UserOut,
    db: AsyncSession,
) -> ChatResponse:
    """
    Orchestrates a complete chat turn from raw user message to final response.

    This function is the single entry point from the /chat route handler.
    It sequences every memory engine component in the correct order and
    returns a fully populated ChatResponse.

    Parameters:
        user_message  (str)          — the raw message the user typed, already
                                       validated by ChatRequest (1–8000 chars).
        current_user  (UserOut)      — the authenticated user injected by
                                       Depends(get_current_user) in the route.
        db            (AsyncSession) — async DB session from Depends(get_db).

    Returns:
        ChatResponse — {session_id, response, context_tokens_used, importance_score}

    Raises:
        app.core.exceptions.MemoryConflictError — propagated from tier_retrieval
            when the user message contradicts a high-confidence stored fact.
            The /chat route lets this bubble up to the 409 handler in main.py.
        app.services.memory_engine.qwen_router.QwenAPIError — propagated if the
            Qwen API call fails. The /chat route catches this and returns 503.

    Used by: app/api/v1/chat.py → chat()
    """
    user_id = str(current_user.id)
    session_id = _get_or_create_session_id(user_id)

    # ── Step 1: Push user message to Redis buffer ────────────────────────────
    from app.core.redis_client import get_redis_client
    redis = get_redis_client()

    await push_message(
        redis=redis,
        user_id=user_id,
        session_id=session_id,
        role="user",
        content=user_message,
    )
    logger.debug("Pushed user message to buffer session=%s", session_id)

    # ── Step 2: Retrieve multi-tier memory context ───────────────────────────
    # Raises MemoryConflictError if the message overrides a stored fact —
    # the exception propagates to the route handler unchanged.
    memory_context, context_tokens_used = await retrieve_all_tiers(
        user_message=user_message,
        user_id=user_id,
        db=db,
    )

    # ── Step 3: Assemble final prompt ────────────────────────────────────────
    system_prompt = _assemble_prompt(memory_context)

    # Read the current buffer to pass as conversation history to Qwen-Max.
    # This gives the model short-term continuity within the session.
    buffer_messages = await get_buffer(
        redis=redis,
        user_id=user_id,
        session_id=session_id,
    )

    # ── Step 4: Call Qwen-Max ────────────────────────────────────────────────
    llm_response = await generate(
        system_prompt=system_prompt,
        messages=buffer_messages,
        temperature=0.1,
        max_tokens=2048,
    )
    logger.debug("Received LLM response for session=%s (%d chars)", session_id, len(llm_response))

    # ── Step 5: Push assistant reply to Redis buffer ─────────────────────────
    await push_message(
        redis=redis,
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content=llm_response,
    )

    # ── Step 6 + 7: Score importance and conditionally save episode ──────────
    importance = await score_importance(
        user_message=user_message,
        llm_response=llm_response,
        user_id=user_id,
        db=db,
    )

    episode_id: str | None = None

    if importance >= IMPORTANCE_THRESHOLD_SAVE:
        new_episode = Episode(
            user_id=user_id,
            session_id=session_id,
            raw_prompt=user_message,
            llm_response=llm_response,
            importance_score=importance,
            promoted=False,
            decay_weight=1.0,
            # embedding is None on insert; populated by the background task below
        )
        db.add(new_episode)
        await db.flush()
        await db.refresh(new_episode)
        episode_id = str(new_episode.id)
        logger.info(
            "Saved episode %s for user %s (score=%.3f candidate=%s)",
            episode_id, user_id, importance,
            importance >= IMPORTANCE_THRESHOLD_CANDIDATE,
        )

    # ── Step 6 (async): Embed the episode in the background ─────────────────
    # Fire-and-forget: the response is returned to the client immediately;
    # embedding runs concurrently and writes back when ready.
    if episode_id:
        combined_text = f"{user_message}\n\n{llm_response}"
        asyncio.create_task(
            _embed_and_update_episode(episode_id, combined_text, db)
        )

    # ── Step 8: Return response payload ─────────────────────────────────────
    return ChatResponse(
        session_id=session_id,
        response=llm_response,
        context_tokens_used=context_tokens_used,
        importance_score=importance,
    )