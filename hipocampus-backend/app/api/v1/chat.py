"""
app/api/v1/chat.py

Chat route handlers. Two endpoints:
  POST /chat         — main turn endpoint, delegates to chat_service.process_turn()
  GET  /chat/history — returns the Redis working-memory buffer for a session

Both routes require authentication via Depends(get_current_user).

Changes from original:
  - POST /chat now passes body.session_id to process_turn() so the service
    knows which Chat row to write messages to (or creates a new one).
  - GET /chat/history accepts an optional ?session_id= query parameter so
    the multi-chat frontend can load the buffer for any specific session.
    Falls back to the legacy daily session if no session_id is supplied
    (backward-compatible with the old single-chat UI).

Used by: app/api/v1/router.py, mounted under /chat.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.chat_service import _get_or_create_session_id, process_turn
from app.services.memory_engine.qwen_router import QwenAPIError
from app.services.memory_engine.redis_buffer import get_buffer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message",
)
async def chat(
    body: ChatRequest,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """
    Main chat turn endpoint.

    Passes body.session_id to process_turn() which resolves (or creates) the
    Chat row, saves both turns to the messages archive, and returns the LLM
    response with the active session_id and chat_id included so the client
    can track which conversation it's in.

    Parameters:
        body         (ChatRequest) — {message, session_id?}
        current_user (UserOut)     — resolved by Depends(get_current_user).
        db           (AsyncSession)— async DB session from Depends(get_db).

    Returns:
        ChatResponse — {session_id, chat_id, response,
                        context_tokens_used, importance_score}

    Raises:
        MemoryConflictError → 409
        QwenAPIError        → 503
    """
    try:
        return await process_turn(
            user_message=body.message,
            session_id=body.session_id,
            current_user=current_user,
            db=db,
        )
    except MemoryConflictError:
        raise
    except QwenAPIError as exc:
        logger.error(
            "Qwen API error during chat turn for user %s: %s",
            current_user.id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI service is temporarily unavailable. Please try again.",
        )
    except HTTPException:
        # Re-raise FastAPI exceptions (e.g. 404 for unknown session_id) unchanged.
        raise
    except Exception as exc:
        logger.error(
            "Unexpected error in chat turn for user %s: %s",
            current_user.id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )


@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get working-memory buffer for a session",
)
async def get_history(
    session_id: str | None = Query(
        default=None,
        description=(
            "The session_id of the chat whose Redis buffer to return. "
            "Omit to use the legacy daily session (backward-compatible)."
        ),
    ),
    current_user: UserOut = Depends(get_current_user),
) -> ChatHistoryResponse:
    """
    Returns the Redis working-memory buffer (last 10 messages, 1h TTL).

    With multi-chat, the client passes ?session_id=<chat.session_id> to
    load the buffer for a specific conversation. Without it, the endpoint
    falls back to the legacy daily session so the existing frontend keeps
    working until Batch 5 updates it.

    For full permanent history (no TTL) use GET /api/v1/chats/{id}/messages.

    Parameters:
        session_id   (str | None) — query param, optional.
        current_user (UserOut)    — resolved by Depends(get_current_user).

    Returns:
        ChatHistoryResponse — {session_id, messages: [{role, content}]}
    """
    user_id = str(current_user.id)
    active_session = session_id or _get_or_create_session_id(user_id)
    redis = get_redis()

    raw_messages = await get_buffer(
        redis=redis,
        user_id=user_id,
        session_id=active_session,
    )

    messages = [
        ChatHistoryMessage(role=m["role"], content=m["content"])
        for m in raw_messages
        if "role" in m and "content" in m
    ]

    return ChatHistoryResponse(session_id=active_session, messages=messages)