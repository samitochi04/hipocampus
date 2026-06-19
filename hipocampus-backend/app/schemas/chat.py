"""
app/schemas/chat.py

Pydantic v2 request and response models for the chat endpoint.
The session_id is generated server-side, not supplied by the client,
so it only appears in responses.

Used by: app/api/v1/chat.py route handlers.
"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """
    Body the client sends to POST /api/v1/chat.
    The user_id is read from the JWT cookie via get_current_user(),
    so it is NOT included here — the client never sends its own identity.

    Parameters:
        message (str) — the raw user message, 1–8000 characters.
                        8000 is a safe ceiling below the Qwen-Max context limit
                        while still allowing long technical prompts.

    Used by: app/api/v1/chat.py → chat()
    """

    message: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="The user's message for this turn.",
    )


class ChatResponse(BaseModel):
    """
    Body returned by POST /api/v1/chat on success.

    Parameters:
        session_id          (str)  — the session key used for the Redis buffer,
                                     so the client can track which session it's in.
        response            (str)  — the LLM's response for this turn.
        context_tokens_used (int)  — how many tokens the [MEMORY_CONTEXT] block
                                     consumed; useful for debugging retrieval depth.
        importance_score    (float)— the score computed by score_importance(); exposed
                                     so the frontend can show memory indicators if desired.

    Used by: app/api/v1/chat.py → chat()
    """

    session_id: str
    response: str
    context_tokens_used: int
    importance_score: float


class ChatHistoryMessage(BaseModel):
    """
    A single message object from the Redis working-memory buffer,
    returned as part of the GET /api/v1/chat/history response.

    Parameters:
        role    (str) — "user" or "assistant"
        content (str) — the raw message text

    Used by: app/api/v1/chat.py → get_history()
    """

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatHistoryResponse(BaseModel):
    """
    Full response body for GET /api/v1/chat/history.

    Parameters:
        session_id (str)                    — the session the buffer belongs to.
        messages   (list[ChatHistoryMessage])— ordered oldest-to-newest slice of
                                              the Redis sliding window (up to 10 msgs).

    Used by: app/api/v1/chat.py → get_history()
    """

    session_id: str
    messages: list[ChatHistoryMessage]