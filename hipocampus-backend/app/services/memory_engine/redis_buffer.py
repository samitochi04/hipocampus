"""
app/services/memory_engine/redis_buffer.py

Manages the Redis-backed working-memory buffer for each user session.
This is the "working memory" tier — the sliding context window that keeps
the last N messages in fast storage so every turn can read recent history
without touching PostgreSQL.

Key design decisions:
  - One Redis LIST per session: session:{user_id}:{session_id}:buffer
  - Messages are stored as JSON strings and always returned as dicts.
  - The buffer is a sliding window (LTRIM keeps exactly MAX_BUFFER_SIZE items).
  - TTL is reset on every write — idle sessions expire automatically.
  - A separate Redis SET tracks active session IDs per user for enumeration.

All functions are async and accept an explicit `redis` client parameter
so they are easy to unit-test with a fake Redis instance.

Used by:
    app/services/chat_service.py  — push/get on every turn
    app/api/v1/chat.py            — get_buffer() for the /history endpoint
"""

import json

from redis.asyncio import Redis # type: ignore

from app.core.exceptions import SessionBufferError

# Maximum number of messages kept in the sliding window.
# 10 = 5 full user↔assistant turns, which comfortably fits within Qwen-Max's
# context limit while giving the model enough conversational history.
MAX_BUFFER_SIZE = 10

# Redis TTL for session buffers — 1 hour of inactivity triggers eviction.
BUFFER_TTL_SECONDS = 3_600


def _buffer_key(user_id: str, session_id: str) -> str:
    """
    Builds the Redis LIST key for a session buffer.
    Centralising the key format here means any key-shape change is a
    one-line edit, not a grep across the codebase.

    Parameters:
        user_id    (str) — UUID string of the authenticated user.
        session_id (str) — opaque session identifier generated per conversation.

    Returns:
        str — e.g. "session:usr_8a3f2c:sess_eng_01:buffer"

    Used by: every function in this module.
    """
    return f"session:{user_id}:{session_id}:buffer"


def _sessions_key(user_id: str) -> str:
    """
    Builds the Redis SET key that tracks all active session IDs for a user.
    Used to enumerate sessions without scanning all keys.

    Parameters:
        user_id (str) — UUID string of the authenticated user.

    Returns:
        str — e.g. "session:usr_8a3f2c:active_sessions"

    Used by: push_message(), get_active_sessions()
    """
    return f"session:{user_id}:active_sessions"


async def push_message(
    redis: Redis,
    user_id: str,
    session_id: str,
    role: str,
    content: str,
) -> None:
    """
    Appends one message to the session buffer and trims the list to the
    sliding window size. Also resets the TTL so active sessions don't expire
    mid-conversation.

    The write is done as a Redis pipeline (atomic batch) so the push,
    trim, and TTL reset either all succeed or all fail — no partial state.

    Parameters:
        redis      (Redis) — the shared async Redis client from get_redis_client().
        user_id    (str)   — UUID string of the message author's account.
        session_id (str)   — identifies the conversation this message belongs to.
        role       (str)   — "user" or "assistant". No other values are valid.
        content    (str)   — the raw message text.

    Returns:
        None

    Raises:
        app.core.exceptions.SessionBufferError — wraps any Redis exception so
            the caller never has to handle raw redis errors.

    Used by: app/services/chat_service.py → process_turn() (twice per turn:
             once for the user message, once for the assistant reply).
    """
    if role not in ("user", "assistant"):
        raise ValueError(f"Invalid role '{role}'. Must be 'user' or 'assistant'.")

    key = _buffer_key(user_id, session_id)
    message = json.dumps({"role": role, "content": content})

    try:
        async with redis.pipeline(transaction=True) as pipe:
            # RPUSH appends to the tail so the list reads oldest→newest.
            pipe.rpush(key, message)
            # LTRIM keeps only the last MAX_BUFFER_SIZE items (sliding window).
            pipe.ltrim(key, -MAX_BUFFER_SIZE, -1)
            # Reset TTL on every write — idle sessions expire, active ones don't.
            pipe.expire(key, BUFFER_TTL_SECONDS)
            # Track this session in the user's active sessions SET.
            pipe.sadd(_sessions_key(user_id), session_id)
            await pipe.execute()
    except Exception as exc:
        raise SessionBufferError(
            f"Failed to push message to buffer for session {session_id}."
        ) from exc


async def get_buffer(
    redis: Redis,
    user_id: str,
    session_id: str,
) -> list[dict]:
    """
    Returns the full contents of the session buffer as a list of message
    dicts, ordered oldest to newest.

    Parameters:
        redis      (Redis) — the shared async Redis client.
        user_id    (str)   — UUID string of the session owner.
        session_id (str)   — identifies the conversation to retrieve.

    Returns:
        list[dict] — up to MAX_BUFFER_SIZE dicts, each with "role" and "content".
                     Returns an empty list if the session key doesn't exist or
                     has expired — the caller treats this as a cold start.

    Raises:
        app.core.exceptions.SessionBufferError — on Redis read failure.

    Used by:
        app/services/chat_service.py → process_turn() (assembles the prompt context)
        app/api/v1/chat.py           → get_history() (the /history endpoint)
    """
    key = _buffer_key(user_id, session_id)
    try:
        raw_messages: list[str] = await redis.lrange(key, 0, -1)
        return [json.loads(m) for m in raw_messages]
    except Exception as exc:
        raise SessionBufferError(
            f"Failed to read buffer for session {session_id}."
        ) from exc


async def clear_buffer(
    redis: Redis,
    user_id: str,
    session_id: str,
) -> None:
    """
    Deletes the session buffer and removes the session from the active
    sessions SET. Called when a session is explicitly ended or when tests
    need a clean slate.

    Parameters:
        redis      (Redis) — the shared async Redis client.
        user_id    (str)   — UUID string of the session owner.
        session_id (str)   — the session to wipe.

    Returns:
        None

    Raises:
        app.core.exceptions.SessionBufferError — on Redis delete failure.

    Used by: future session-management routes, test fixtures (conftest.py).
    """
    key = _buffer_key(user_id, session_id)
    sessions_key = _sessions_key(user_id)
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            pipe.srem(sessions_key, session_id)
            await pipe.execute()
    except Exception as exc:
        raise SessionBufferError(
            f"Failed to clear buffer for session {session_id}."
        ) from exc


async def get_active_sessions(
    redis: Redis,
    user_id: str,
) -> list[str]:
    """
    Returns all session IDs currently tracked for a user.
    Used by the sleep consolidator to know which sessions are active
    and should not have their buffers pruned during consolidation.

    Parameters:
        redis   (Redis) — the shared async Redis client.
        user_id (str)   — UUID string of the user.

    Returns:
        list[str] — list of session_id strings. May be empty if the user
                    has no active sessions or all buffers have expired.

    Raises:
        app.core.exceptions.SessionBufferError — on Redis read failure.

    Used by: app/services/memory_engine/sleep_consolidator.py
    """
    try:
        members: set[str] = await redis.smembers(_sessions_key(user_id))
        return list(members)
    except Exception as exc:
        raise SessionBufferError(
            f"Failed to retrieve active sessions for user {user_id}."
        ) from exc