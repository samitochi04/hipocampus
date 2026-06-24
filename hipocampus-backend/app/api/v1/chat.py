"""
app/api/v1/chats.py

Chat management route handlers. Four endpoints:

  POST  /chats                  — create a new chat, return ChatOut with a
                                  fresh session_id the client uses for all
                                  subsequent turns in that conversation.
  GET   /chats                  — list the current user's chats newest-first,
                                  with message counts for the sidebar.
  GET   /chats/{id}/messages    — permanent full-history archive for one chat.
                                  This is what lets a user retrieve code from
                                  two days ago without asking the AI again.
  PATCH /chats/{id}             — rename a chat title manually.

Design notes:
  - session_id is generated here (POST /chats) and owned by the client
    from that point on. The client sends it with every POST /api/v1/chat
    turn so the service knows which Chat row to write messages to.
  - All four endpoints are ownership-gated: a user can only see and modify
    their own chats. 404 (not 403) is returned for cross-user access to
    avoid leaking whether a chat_id exists.
  - No business logic lives here — handlers are thin wrappers over DB queries.

Used by: app/api/v1/router.py (mounted under /chats).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.dependencies import get_current_user
from app.models.chat import Chat, Message
from app.schemas.auth import UserOut
from app.schemas.chat import ChatListItem, ChatMessagesResponse, ChatOut, MessageOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["chats"])


# ---------------------------------------------------------------------------
# Request body for PATCH /chats/{id}
# ---------------------------------------------------------------------------


class RenameChatRequest(BaseModel):
    """
    Body for PATCH /chats/{id}.

    Parameters:
        title (str) — new title, 1–256 characters.

    Used by: rename_chat()
    """

    title: str = Field(..., min_length=1, max_length=256)


# ---------------------------------------------------------------------------
# POST /chats
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ChatOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat",
)
async def create_chat(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatOut:
    """
    Creates a new Chat row with a server-generated session_id and returns it.

    The client must store the returned session_id and send it with every
    POST /api/v1/chat turn that belongs to this conversation. Omitting
    session_id in a chat turn automatically creates a new chat, so this
    endpoint only needs to be called explicitly when the user clicks
    "New Chat" before sending any messages.

    Parameters:
        current_user (UserOut)      — resolved by Depends(get_current_user).
        db           (AsyncSession) — async DB session from Depends(get_db).

    Returns:
        ChatOut — {id, session_id, title (None), created_at}

    Used by: src/api/chats.js → createChat()
             "New Chat" button in ChatSidebar
    """
    # Generate a short, human-readable session_id.
    # Format: chat-{8 hex chars} — unique enough for any single user's chats
    # and short enough to fit in the Redis key without clutter.
    raw = uuid.uuid4().hex
    session_id = f"chat-{raw[:8]}-{raw[8:12]}"

    new_chat = Chat(
        user_id=current_user.id,
        session_id=session_id,
        title=None,  # Populated by the background title-generation task after first turn.
    )
    db.add(new_chat)
    await db.flush()   # Get the DB-generated id before commit.
    await db.commit()
    await db.refresh(new_chat)

    logger.info(
        "Created chat %s (session=%s) for user %s",
        new_chat.id, session_id, current_user.id,
    )
    return ChatOut.model_validate(new_chat)


# ---------------------------------------------------------------------------
# GET /chats
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[ChatListItem],
    status_code=status.HTTP_200_OK,
    summary="List the current user's chats",
)
async def list_chats(
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChatListItem]:
    """
    Returns all chats owned by the current user, ordered by most-recently-
    messaged first. Includes a message_count and last_message_at for each
    chat so the sidebar can show "3 messages · 2 days ago" without a
    separate request.

    Empty chats (created but no messages sent yet) appear with
    message_count=0 and last_message_at=None, ordered by created_at.

    Parameters:
        current_user (UserOut)      — resolved by Depends(get_current_user).
        db           (AsyncSession) — async DB session from Depends(get_db).

    Returns:
        list[ChatListItem] — sorted newest-first.

    Used by: src/api/chats.js → listChats()
             ChatSidebar on mount and after a new chat is created.
    """
    # Subquery: per-chat message count and last message timestamp.
    # LEFT JOIN so chats with no messages are still returned.
    msg_stats = (
        select(
            Message.chat_id.label("chat_id"),
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at"),
        )
        .group_by(Message.chat_id)
        .subquery()
    )

    result = await db.execute(
        select(
            Chat,
            func.coalesce(msg_stats.c.message_count, 0).label("message_count"),
            msg_stats.c.last_message_at.label("last_message_at"),
        )
        .outerjoin(msg_stats, Chat.id == msg_stats.c.chat_id)
        .where(Chat.user_id == current_user.id)
        # Most recently active chats first; fall back to created_at for empty chats.
        .order_by(
            func.coalesce(msg_stats.c.last_message_at, Chat.created_at).desc()
        )
    )

    rows = result.all()

    return [
        ChatListItem(
            id=row.Chat.id,
            session_id=row.Chat.session_id,
            title=row.Chat.title,
            created_at=row.Chat.created_at,
            message_count=row.message_count,
            last_message_at=row.last_message_at,
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# GET /chats/{id}/messages
# ---------------------------------------------------------------------------


@router.get(
    "/{chat_id}/messages",
    response_model=ChatMessagesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the full message archive for a chat",
)
async def get_chat_messages(
    chat_id: uuid.UUID,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatMessagesResponse:
    """
    Returns every message ever sent in this chat, oldest first.

    This is the permanent archive that lets a user read back a conversation
    from two days ago, copy code from an old response, or review a decision
    — without asking the AI again (saving tokens and staying in context).

    Unlike GET /api/v1/chat/history (which only returns the Redis buffer,
    max 10 messages, 1-hour TTL), this endpoint queries PostgreSQL and
    has no TTL — it returns the complete history.

    Parameters:
        chat_id      (UUID)         — path parameter identifying the chat.
        current_user (UserOut)      — resolved by Depends(get_current_user).
        db           (AsyncSession) — async DB session from Depends(get_db).

    Returns:
        ChatMessagesResponse — {chat_id, session_id, title, messages[]}

    Raises:
        HTTPException 404 — chat not found or belongs to another user.
                            Returns 404 (not 403) to avoid leaking whether
                            the chat_id exists.

    Used by: src/api/chats.js → getChatMessages()
             ChatPage when loading an old conversation.
    """
    # Verify ownership before returning any data.
    chat_result = await db.execute(
        select(Chat).where(Chat.id == chat_id).where(Chat.user_id == current_user.id)
    )
    chat = chat_result.scalars().first()
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found.",
        )

    # Fetch all messages ordered oldest → newest.
    msgs_result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
    )
    messages = msgs_result.scalars().all()

    return ChatMessagesResponse(
        chat_id=chat.id,
        session_id=chat.session_id,
        title=chat.title,
        messages=[MessageOut.model_validate(m) for m in messages],
    )


# ---------------------------------------------------------------------------
# PATCH /chats/{id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{chat_id}",
    response_model=ChatOut,
    status_code=status.HTTP_200_OK,
    summary="Rename a chat",
)
async def rename_chat(
    chat_id: uuid.UUID,
    body: RenameChatRequest,
    current_user: UserOut = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatOut:
    """
    Updates the title of a chat owned by the current user.
    Called when the user edits a chat name in the sidebar, or to override
    a Qwen-generated title they don't like.

    Parameters:
        chat_id      (UUID)              — path parameter identifying the chat.
        body         (RenameChatRequest) — {title: str}
        current_user (UserOut)           — resolved by Depends(get_current_user).
        db           (AsyncSession)      — async DB session from Depends(get_db).

    Returns:
        ChatOut — the updated chat with the new title.

    Raises:
        HTTPException 404 — chat not found or belongs to another user.

    Used by: src/api/chats.js → renameChat()
             ChatSidebar double-click to rename.
    """
    chat_result = await db.execute(
        select(Chat).where(Chat.id == chat_id).where(Chat.user_id == current_user.id)
    )
    chat = chat_result.scalars().first()
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found.",
        )

    chat.title = body.title
    await db.commit()
    await db.refresh(chat)

    logger.info("Renamed chat %s → %r (user %s)", chat_id, body.title, current_user.id)
    return ChatOut.model_validate(chat)