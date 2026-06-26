"""
app/services/chat_service.py

The central orchestrator for every chat turn.
This is where every memory engine component is called in sequence.

process_turn() is the only public function. It is called by the /chat
route handler and returns the final response payload.

Turn sequence:
  1.  Resolve or create the Chat row (session_id).
  2.  Push the user message to the Redis working-memory buffer.
  3.  Retrieve multi-tier memory context via tier_retrieval.
  4.  Assemble the final prompt (system prompt + memory context + buffer history).
  5.  Call Qwen-Max and get the response.
  6.  Push the assistant reply to the Redis buffer.
  7.  Save both turns to the messages table (permanent archive).
  8.  Embed the episode (async background task).
  9.  Score importance and conditionally write the episode to PostgreSQL.
  10. If first turn in this chat: generate and save a title (async background task).
  11. Return the ChatResponse payload.

Used by: app/api/v1/chat.py exclusively.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, Message
from app.models.episode import Episode
from app.schemas.auth import UserOut
from app.schemas.chat import ChatResponse
from app.services.memory_engine.importance import score_importance
from app.services.memory_engine.qwen_router import embed_text, generate, generate_with_search
from app.services.memory_engine.redis_buffer import get_buffer, push_message
from app.services.memory_engine.tier_retrieval import retrieve_all_tiers

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

def _build_system_prompt_template() -> str:
    """
    Builds the system prompt with today's date injected at construction time.
    The date is critical: Qwen's training cutoff predates events happening
    in 2025-2026, so without it the model assumes recent events are "future"
    and skips the web search tool entirely.
    """
    from datetime import UTC, datetime
    today = datetime.now(UTC).strftime("%B %d, %Y")   # e.g. "June 26, 2026"
    return f"""You are Hipocampus, a highly capable AI assistant with persistent memory \
and real-time web search capability. Today's date is {today}.

{{memory_context}}

CRITICAL — Web search rules (follow these before every response):
- You have a web_search tool. Use it proactively, especially for:
  * ANY sports result, score, or statistic (football, basketball, F1, etc.)
  * Current prices, market data, exchange rates
  * News or events from 2025 or 2026
  * Anything the user says happened "recently" or provides a URL for
- NEVER say an event "has not yet occurred" or "is in the future" without
  searching first. Your training data has a cutoff — events you don't know
  about may have already happened by {today}.
- If a search returns a rate-limit error, wait and try a different query.
  Do NOT fall back to "I don't have access to real-time data."

Memory instructions:
- Always follow stored preferences exactly.
- When writing code, match the exact libraries and patterns the user has used.
- Be direct and technically precise. Avoid padding or filler sentences.
"""

SYSTEM_PROMPT_TEMPLATE = _build_system_prompt_template()

# Importance thresholds — must stay in sync with importance.py comments.
IMPORTANCE_THRESHOLD_SAVE = 0.45
IMPORTANCE_THRESHOLD_CANDIDATE = 0.60


# ---------------------------------------------------------------------------
# Chat resolution
# ---------------------------------------------------------------------------


async def _get_or_create_chat(
    session_id: str | None,
    user_id: str,
    db: AsyncSession,
) -> tuple[Chat, bool]:
    """
    Resolves which Chat row this turn belongs to, creating one if needed.

    Parameters:
        session_id (str | None) — from ChatRequest.session_id.
            • Provided → look up the Chat row, verify the user owns it.
            • None     → create a new Chat row with a fresh session_id.
        user_id    (str)        — UUID string of the authenticated user.
        db         (AsyncSession) — open async DB session.

    Returns:
        (Chat, is_first_turn: bool)
        is_first_turn is True when the messages table has 0 rows for this
        chat before this turn — used to decide whether to queue title generation.

    Raises:
        HTTPException 404 — session_id provided but not found or owned by
                            another user. 404 (not 403) avoids leaking existence.

    Used by: process_turn()
    """
    if session_id:
        result = await db.execute(
            select(Chat)
            .where(Chat.session_id == session_id)
            .where(Chat.user_id == uuid.UUID(user_id))
        )
        chat = result.scalars().first()
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found. Create a new chat first.",
            )
        # Check message count BEFORE this turn to detect the first turn.
        count_result = await db.execute(
            select(func.count(Message.id)).where(Message.chat_id == chat.id)
        )
        is_first_turn = (count_result.scalar() or 0) == 0
        return chat, is_first_turn

    # No session_id supplied → create a new chat.
    raw = uuid.uuid4().hex
    new_session_id = f"chat-{raw[:8]}-{raw[8:12]}"
    chat = Chat(
        user_id=uuid.UUID(user_id),
        session_id=new_session_id,
        title=None,
    )
    db.add(chat)
    await db.flush()
    await db.refresh(chat)
    logger.info(
        "Auto-created chat %s (session=%s) for user %s",
        chat.id, new_session_id, user_id,
    )
    return chat, True  # Always first turn for a brand-new chat.


# ---------------------------------------------------------------------------
# Message persistence
# ---------------------------------------------------------------------------


async def _save_messages(
    chat_id: uuid.UUID,
    session_id: str,
    user_message: str,
    assistant_message: str,
    db: AsyncSession,
) -> None:
    """
    Writes both turns of a conversation round to the messages table.
    Called after the LLM response is received so both rows are written
    together in the same transaction — the archive is always consistent.

    Parameters:
        chat_id           (UUID)         — parent Chat row.
        session_id        (str)          — redundant copy for fast session queries.
        user_message      (str)          — the raw user message.
        assistant_message (str)          — the LLM's response.
        db                (AsyncSession) — open async DB session.

    Returns: None (writes to DB as side-effect).
    Used by: process_turn()
    """
    db.add(Message(
        chat_id=chat_id,
        session_id=session_id,
        role="user",
        content=user_message,
    ))
    db.add(Message(
        chat_id=chat_id,
        session_id=session_id,
        role="assistant",
        content=assistant_message,
    ))
    await db.flush()
    logger.debug("Saved 2 messages to archive for chat %s", chat_id)


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------


async def _embed_and_update_episode(
    episode_id: str,
    text: str,
    db: AsyncSession,
) -> None:
    """
    Computes and stores the embedding for a newly created episode.
    Runs as a fire-and-forget task — failures are logged, never raised.

    Parameters:
        episode_id (str)          — UUID string of the Episode row.
        text       (str)          — user_message + llm_response concatenated.
        db         (AsyncSession) — async DB session.

    Used by: process_turn() via asyncio.create_task()
    """
    try:
        embedding = await embed_text(text)
        await db.execute(
            sa_update(Episode)
            .where(Episode.id == episode_id)
            .values(embedding=embedding)
        )
        await db.commit()
        logger.debug("Embedded episode %s", episode_id)
    except Exception as exc:
        logger.error("Failed to embed episode %s: %s", episode_id, exc)


async def _generate_title(chat_id: uuid.UUID, user_message: str) -> None:
    """
    Generates a 4–6 word title for a new chat from its first user message
    and writes it back to the chats table.

    Uses a dedicated DB session (separate from the request session) because
    this runs after the response is already returned to the client.

    Parameters:
        chat_id      (uuid.UUID) — the Chat row to update.
        user_message (str)       — the first message the user sent, used
                                   as context for title generation.

    Used by: process_turn() via asyncio.create_task() on first turn only.
    """
    from app.core.db import AsyncSessionLocal

    try:
        raw_title = await generate(
            system_prompt=(
                "You generate ultra-short chat titles. "
                "Reply with ONLY the title: 4-6 words, title case, "
                "no punctuation, no quotes, no explanation."
            ),
            messages=[{"role": "user", "content": user_message[:500]}],
            temperature=0.3,
            max_tokens=20,
        )
        title = raw_title.strip().strip("\"'").strip()[:200]
        async with AsyncSessionLocal() as db:
            await db.execute(
                sa_update(Chat)
                .where(Chat.id == chat_id)
                .values(title=title)
            )
            await db.commit()
        logger.info("Generated title for chat %s: %r", chat_id, title)
    except Exception as exc:
        logger.error("Title generation failed for chat %s: %s", chat_id, exc)


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def _assemble_prompt(memory_context: str) -> str:
    """
    Injects the retrieved memory context block into the system prompt.
    Re-evaluates the template each call so the embedded date is always today.
    """
    # Rebuild with today's date on every turn (cheap string op).
    template = _build_system_prompt_template()
    context_section = (
        memory_context.strip()
        or "(No prior memory found for this user. Treat this as a fresh session.)"
    )
    return template.format(memory_context=context_section)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def process_turn(
    user_message: str,
    session_id: str | None,
    current_user: UserOut,
    db: AsyncSession,
) -> ChatResponse:
    """
    Orchestrates a complete chat turn from raw user message to final response.

    Parameters:
        user_message (str)        — validated user message (1–8000 chars).
        session_id   (str | None) — from ChatRequest.session_id.
                                    None = start a new chat automatically.
        current_user (UserOut)    — the authenticated user.
        db           (AsyncSession) — async DB session.

    Returns:
        ChatResponse — {session_id, chat_id, response,
                        context_tokens_used, importance_score}

    Raises:
        MemoryConflictError — propagates to the 409 handler in main.py.
        QwenAPIError        — propagates to the 503 handler in chat.py.

    Used by: app/api/v1/chat.py → chat()
    """
    user_id = str(current_user.id)

    # ── Step 1: Resolve or create the Chat row ───────────────────────────────
    chat, is_first_turn = await _get_or_create_chat(session_id, user_id, db)
    active_session_id = chat.session_id
    chat_id = chat.id

    # ── Step 2: Push user message to Redis buffer ────────────────────────────
    from app.core.redis_client import get_redis_client
    redis = get_redis_client()

    await push_message(
        redis=redis,
        user_id=user_id,
        session_id=active_session_id,
        role="user",
        content=user_message,
    )
    logger.debug("Pushed user message to buffer session=%s", active_session_id)

    # ── Step 3: Retrieve multi-tier memory context ───────────────────────────
    memory_context, context_tokens_used = await retrieve_all_tiers(
        user_message=user_message,
        user_id=user_id,
        db=db,
    )

    # ── Step 4: Assemble final prompt ────────────────────────────────────────
    system_prompt = _assemble_prompt(memory_context)
    buffer_messages = await get_buffer(
        redis=redis,
        user_id=user_id,
        session_id=active_session_id,
    )

    # ── Step 5: Call Qwen-Max with web search MCP tool ──────────────────────
    # generate_with_search() passes enable_search=True to DashScope so Qwen
    # can autonomously invoke real-time web search when the query needs current
    # information. Returns (text, was_search_used).
    llm_response, web_searched = await generate_with_search(
        system_prompt=system_prompt,
        messages=buffer_messages,
        temperature=0.1,
        max_tokens=2048,
    )
    logger.debug(
        "LLM response for session=%s: %d chars web_searched=%s",
        active_session_id, len(llm_response), web_searched,
    )

    # ── Step 6: Push assistant reply to Redis buffer ─────────────────────────
    await push_message(
        redis=redis,
        user_id=user_id,
        session_id=active_session_id,
        role="assistant",
        content=llm_response,
    )

    # ── Step 7: Save both turns to the permanent messages archive ────────────
    await _save_messages(
        chat_id=chat_id,
        session_id=active_session_id,
        user_message=user_message,
        assistant_message=llm_response,
        db=db,
    )

    # ── Step 8: Score importance and conditionally save episode ──────────────
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
            session_id=active_session_id,
            raw_prompt=user_message,
            llm_response=llm_response,
            importance_score=importance,
            promoted=False,
            decay_weight=1.0,
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

    await db.commit()

    # ── Step 8b (async): embed episode in background ─────────────────────────
    if episode_id:
        combined_text = f"{user_message}\n\n{llm_response}"
        asyncio.create_task(
            _embed_and_update_episode(episode_id, combined_text, db)
        )

    # ── Step 10: Generate chat title on first turn (async background) ────────
    if is_first_turn:
        asyncio.create_task(_generate_title(chat_id, user_message))

    # ── Step 11: Return response ─────────────────────────────────────────────
    return ChatResponse(
        session_id=active_session_id,
        chat_id=str(chat_id),
        response=llm_response,
        context_tokens_used=context_tokens_used,
        importance_score=importance,
        web_searched=web_searched,
    )


# ---------------------------------------------------------------------------
# Compatibility shim — used by GET /chat/history
# ---------------------------------------------------------------------------


def _get_or_create_session_id(user_id: str) -> str:
    """
    Legacy session ID generation kept for the GET /chat/history endpoint
    while the frontend is being migrated to multi-chat.
    Returns the same daily-based session ID as before so the Redis buffer
    key is still valid for clients that haven't adopted session_id yet.

    Parameters:
        user_id (str) — UUID string of the authenticated user.

    Returns:
        str — daily session ID in the format 'sess-{uid8}-{YYYYMMDD}'.

    Used by: app/api/v1/chat.py → get_history() (legacy path only)
    """
    today = datetime.now(UTC).strftime("%Y%m%d")
    short_uid = user_id.replace("-", "")[:8]
    return f"sess-{short_uid}-{today}"