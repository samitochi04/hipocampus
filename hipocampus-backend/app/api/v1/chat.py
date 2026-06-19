"""
app/api/v1/chat.py

Chat route handlers. Two endpoints:
  POST /chat         — the main turn endpoint, delegates to chat_service.process_turn()
  GET  /chat/history — returns the current Redis working-memory buffer for the session

Both routes require authentication via Depends(get_current_user).
No business logic lives here — the handlers validate input, delegate,
and format the response.

Used by: app/api/v1/router.py, which mounts this router under /chat.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore

from app.core.db import get_db
from app.core.exceptions import MemoryConflictError
from app.dependencies import get_current_user, get_redis
from app.schemas.auth import UserOut
from app.schemas.chat import (
    ChatHistoryMessage,
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
)
from app.services.chat_service import process_turn
from app.services.memory_engine.qwen_router import QwenAPIError
from app.services.memory_engine.redis_buffer import get_buffer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message",
    description=(
        "Processes one chat turn through the full memory pipeline: "
        "retrieves multi-tier context, assembles the prompt, calls Qwen-Max, "
        "scores and stores the episode, and returns the model's response. "
        "Returns 409 if the message contradicts a stored high-confidence preference."
    ),
)
async def chat(
    body: ChatRequest,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Main chat turn endpoint. Delegates entirely to chat_service.process_turn().

    Parameters:
        body         (ChatRequest) — validated request body containing the user message.
        current_user (UserOut)     — injected by Depends(get_current_user); raises 401
                                     automatically if the cookie is missing or expired.
        db           (AsyncSession)— async DB session from Depends(get_db).

    Returns:
        ChatResponse — {session_id, response, context_tokens_used, importance_score}

    Raises (mapped to HTTP responses):
        MemoryConflictError → 409 (handled by the exception handler in main.py,
                                   the React client shows the conflict resolution UI)
        QwenAPIError        → 503 (Qwen API unreachable or rate-limited)
        SessionBufferError  → 503 (handled by the exception handler in main.py)

    Used by: React ChatInput component → api/chat.js → sendMessage()
    """
    try:
        return await process_turn(
            user_message=body.message,
            current_user=current_user,
            db=db,
        )
    except MemoryConflictError:
        # Re-raise so the registered exception handler in main.py formats
        # the 409 response with the conflict detail and "type" field.
        raise
    except QwenAPIError as exc:
        logger.error("Qwen API error during chat turn for user %s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI service is temporarily unavailable. Please try again in a moment.",
        )
    except Exception as exc:
        logger.error("Unexpected error in chat turn for user %s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )


@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current session history",
    description=(
        "Returns the contents of the Redis working-memory buffer for the "
        "user's current session — up to the last 10 messages (5 full turns). "
        "Returns an empty message list if the session has expired or no messages "
        "have been sent yet."
    ),
)
async def get_history(
    current_user: UserOut = Depends(get_current_user),
) -> ChatHistoryResponse:
    """
    Session history endpoint. Reads directly from the Redis buffer without
    touching PostgreSQL, so it is always fast regardless of episode count.

    Parameters:
        current_user (UserOut) — injected by Depends(get_current_user).

    Returns:
        ChatHistoryResponse — {session_id, messages: [{role, content}, ...]}
                              Messages are ordered oldest → newest.

    Used by: React ChatWindow component on mount to restore visible history
             after a page refresh (the buffer survives within its 1h TTL).
    """
    from app.services.chat_service import _get_or_create_session_id

    user_id = str(current_user.id)
    session_id = _get_or_create_session_id(user_id)
    redis = get_redis()

    raw_messages = await get_buffer(
        redis=redis,
        user_id=user_id,
        session_id=session_id,
    )

    messages = [
        ChatHistoryMessage(role=m["role"], content=m["content"])
        for m in raw_messages
        if "role" in m and "content" in m
    ]

    return ChatHistoryResponse(session_id=session_id, messages=messages)