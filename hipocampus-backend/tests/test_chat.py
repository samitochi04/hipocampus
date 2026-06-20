"""
tests/test_chat.py

Endpoint tests for the chat routes:
    POST /api/v1/chat
    GET  /api/v1/chat/history

All Qwen API calls are mocked via the mock_qwen fixture from conftest.py.
Tests verify the full turn pipeline output without making live API calls.
"""

import pytest # type: ignore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_and_login(client, name: str = "Tester") -> dict:
    """
    Registers a user and returns the registration response body.
    The session cookie is automatically stored in the client after registration.
    """
    response = await client.post("/api/v1/auth/register", json={"name": name})
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_requires_auth(client):
    """
    /chat must return 401 when called without a session cookie.
    """
    client.cookies.clear()
    response = await client.post("/api/v1/chat", json={"message": "Hello"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_success(client, mock_qwen):
    """
    Happy path: authenticated user sends a message.
    Response must include session_id, response text, context_tokens_used,
    and importance_score.
    The mocked LLM response must be returned verbatim.
    """
    await _register_and_login(client, "Frank")

    response = await client.post(
        "/api/v1/chat",
        json={"message": "Initialize a FastAPI backend with async SQLAlchemy."},
    )
    assert response.status_code == 200

    body = response.json()
    assert "session_id" in body
    assert body["response"] == "This is a mocked LLM response for testing."
    assert isinstance(body["context_tokens_used"], int)
    assert 0.0 <= body["importance_score"] <= 1.0


@pytest.mark.asyncio
async def test_chat_empty_message_rejected(client, mock_qwen):
    """
    An empty message string must be rejected with 422 (Pydantic validation).
    """
    await _register_and_login(client, "Grace")

    response = await client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_message_too_long_rejected(client, mock_qwen):
    """
    A message exceeding 8000 characters must be rejected with 422.
    """
    await _register_and_login(client, "Heidi")

    response = await client.post(
        "/api/v1/chat",
        json={"message": "x" * 8001},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_pushes_messages_to_buffer(client, mock_qwen, fake_redis):
    """
    After a successful turn, both the user message and the assistant reply
    must be present in the Redis buffer.
    """
    await _register_and_login(client, "Ivan")

    user_message = "What is the capital of France?"
    await client.post("/api/v1/chat", json={"message": user_message})

    # Inspect the Redis buffer directly.
    import json
    keys = await fake_redis.keys("session:*:buffer")
    assert len(keys) >= 1

    raw_messages = await fake_redis.lrange(keys[0], 0, -1)
    messages = [json.loads(m) for m in raw_messages]
    roles = [m["role"] for m in messages]

    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_chat_high_importance_saves_episode(client, mock_qwen, db_session):
    """
    Messages containing explicit keywords (e.g. "always") should push the
    importance score above the 0.45 threshold, resulting in an Episode row
    being created in the DB.
    """
    from sqlalchemy import select # type: ignore
    from app.models.episode import Episode

    await _register_and_login(client, "Judy")

    # "always" triggers the explicit_flag boost in score_importance().
    await client.post(
        "/api/v1/chat",
        json={"message": "Always use Pydantic v2 for all schema validation."},
    )

    result = await db_session.execute(select(Episode))
    episodes = result.scalars().all()
    assert len(episodes) >= 1


@pytest.mark.asyncio
async def test_chat_conflict_returns_409(client, mock_qwen, db_session):
    """
    If the user message contradicts a high-confidence stored fact using
    override language, the endpoint must return 409 with type=memory_conflict.
    """
    from sqlalchemy import text # type: ignore
    from app.models.user import User
    from sqlalchemy import select # type: ignore

    reg = await _register_and_login(client, "Karl")
    user_id = reg["user_id"]

    # Manually insert a high-confidence semantic fact for this user so
    # the conflict detector has something to find.
    fake_embedding = str([0.5] * 1536)
    await db_session.execute(
        text(
            """
            INSERT INTO semantic_facts (user_id, fact_text, confidence, is_conflicted, embedding)
            VALUES (:uid, :fact, 0.95, FALSE, CAST(:emb AS vector))
            """
        ),
        {
            "uid": user_id,
            "fact": "User strictly prefers PostgreSQL for all time-series data.",
            "emb": fake_embedding,
        },
    )
    await db_session.flush()

    # Override embed_text to return the same embedding so cosine distance ≈ 0
    # (maximum similarity), ensuring the conflict threshold is crossed.
    mock_qwen["embed_text"].return_value = [0.5] * 1536

    response = await client.post(
        "/api/v1/chat",
        json={"message": "Switch to TimescaleDB instead of PostgreSQL."},
    )
    assert response.status_code == 409
    assert response.json()["type"] == "memory_conflict"


# ---------------------------------------------------------------------------
# GET /chat/history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_empty_on_cold_start(client):
    """
    A freshly registered user with no prior messages must get an empty
    messages list from /chat/history.
    """
    await _register_and_login(client, "Laura")

    response = await client.get("/api/v1/chat/history")
    assert response.status_code == 200

    body = response.json()
    assert "session_id" in body
    assert body["messages"] == []


@pytest.mark.asyncio
async def test_history_returns_buffer_after_turn(client, mock_qwen):
    """
    After one full chat turn, /chat/history must return the user message
    and assistant reply in the correct order (oldest first).
    """
    await _register_and_login(client, "Mike")

    user_msg = "Tell me about async Python."
    await client.post("/api/v1/chat", json={"message": user_msg})

    response = await client.get("/api/v1/chat/history")
    assert response.status_code == 200

    messages = response.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == user_msg
    assert messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_history_requires_auth(client):
    """
    /chat/history must return 401 when called without a session cookie.
    """
    client.cookies.clear()
    response = await client.get("/api/v1/chat/history")
    assert response.status_code == 401# Endpoint tests for /chat and /chat/history