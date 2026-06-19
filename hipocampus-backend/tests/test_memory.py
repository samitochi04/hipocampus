"""
tests/test_memory.py

Endpoint tests for the memory management routes:
    GET   /api/v1/memory/conflicts
    PATCH /api/v1/memory/facts/{id}
    GET   /api/v1/memory/export

Tests seed the DB directly via db_session rather than going through
the chat pipeline, so they are independent of Qwen mock behaviour
and run faster.
"""

import uuid

import pytest # type: ignore
from sqlalchemy import text # type: ignore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register(client, name: str = "MemTester") -> dict:
    """Registers a user and returns the response body (includes user_id)."""
    response = await client.post("/api/v1/auth/register", json={"name": name})
    assert response.status_code == 201
    return response.json()


async def _seed_semantic_fact(
    db_session,
    user_id: str,
    fact_text: str = "User prefers async SQLAlchemy.",
    confidence: float = 0.85,
    is_conflicted: bool = False,
) -> str:
    """
    Inserts a SemanticFact row directly into the DB and returns its UUID string.
    Used to set up test state without going through the full chat pipeline.
    """
    fact_id = str(uuid.uuid4())
    fake_embedding = str([0.1] * 1536)
    await db_session.execute(
        text(
            """
            INSERT INTO semantic_facts
                (id, user_id, fact_text, confidence, is_conflicted, embedding)
            VALUES
                (CAST(:id AS uuid), CAST(:uid AS uuid), :fact, :conf, :conflict,
                 CAST(:emb AS vector))
            """
        ),
        {
            "id": fact_id,
            "uid": user_id,
            "fact": fact_text,
            "conf": confidence,
            "conflict": is_conflicted,
            "emb": fake_embedding,
        },
    )
    await db_session.flush()
    return fact_id


async def _seed_episode(db_session, user_id: str, session_id: str = "sess-test") -> str:
    """
    Inserts an Episode row directly into the DB and returns its UUID string.
    """
    ep_id = str(uuid.uuid4())
    await db_session.execute(
        text(
            """
            INSERT INTO episodes
                (id, user_id, session_id, raw_prompt, llm_response,
                 importance_score, promoted, decay_weight)
            VALUES
                (CAST(:id AS uuid), CAST(:uid AS uuid), :sid,
                 'Test prompt', 'Test response', 0.75, FALSE, 1.0)
            """
        ),
        {"id": ep_id, "uid": user_id, "sid": session_id},
    )
    await db_session.flush()
    return ep_id


# ---------------------------------------------------------------------------
# GET /memory/conflicts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflicts_empty_when_none_exist(client):
    """
    A user with no conflicted facts must receive an empty list.
    """
    await _register(client, "Nancy")

    response = await client.get("/api/v1/memory/conflicts")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_conflicts_requires_auth(client):
    """
    /memory/conflicts must return 401 when called without a session cookie.
    """
    client.cookies.clear()
    response = await client.get("/api/v1/memory/conflicts")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_conflicts_returns_conflicted_facts(client, db_session):
    """
    A user with is_conflicted=True facts must see them in the conflicts list.
    Non-conflicted facts for the same user must not appear.
    """
    reg = await _register(client, "Oscar")
    user_id = reg["user_id"]

    # Seed one conflicted and one clean fact.
    await _seed_semantic_fact(
        db_session, user_id,
        fact_text="User prefers PostgreSQL.",
        is_conflicted=True,
    )
    await _seed_semantic_fact(
        db_session, user_id,
        fact_text="User uses Pydantic v2.",
        is_conflicted=False,
    )

    response = await client.get("/api/v1/memory/conflicts")
    assert response.status_code == 200

    conflicts = response.json()
    assert len(conflicts) == 1
    assert conflicts[0]["fact"]["is_conflicted"] is True
    assert "PostgreSQL" in conflicts[0]["fact"]["fact_text"]


@pytest.mark.asyncio
async def test_conflicts_includes_conflicting_prompt_when_episode_exists(
    client, db_session
):
    """
    If a source episode exists for a conflicted fact, its raw_prompt must
    appear in the conflicting_prompt field of the conflict response.
    """
    reg = await _register(client, "Paula")
    user_id = reg["user_id"]

    ep_id = await _seed_episode(db_session, user_id)

    # Seed a conflicted fact that references the episode.
    fact_id = str(uuid.uuid4())
    fake_embedding = str([0.1] * 1536)
    await db_session.execute(
        text(
            """
            INSERT INTO semantic_facts
                (id, user_id, fact_text, confidence, is_conflicted,
                 source_episode_ids, embedding)
            VALUES
                (CAST(:id AS uuid), CAST(:uid AS uuid),
                 'User prefers Redis for caching.',
                 0.9, TRUE,
                 ARRAY[CAST(:ep_id AS uuid)],
                 CAST(:emb AS vector))
            """
        ),
        {
            "id": fact_id,
            "uid": user_id,
            "ep_id": ep_id,
            "emb": fake_embedding,
        },
    )
    await db_session.flush()

    response = await client.get("/api/v1/memory/conflicts")
    assert response.status_code == 200

    conflicts = response.json()
    assert len(conflicts) == 1
    assert conflicts[0]["conflicting_prompt"] == "Test prompt"


# ---------------------------------------------------------------------------
# PATCH /memory/facts/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_fact_resolves_conflict(client, db_session):
    """
    PATCH /memory/facts/{id} with is_conflicted=false must clear the
    conflict flag and return the updated fact.
    """
    reg = await _register(client, "Quinn")
    user_id = reg["user_id"]

    fact_id = await _seed_semantic_fact(
        db_session, user_id,
        fact_text="User prefers sync over async.",
        is_conflicted=True,
    )

    response = await client.patch(
        f"/api/v1/memory/facts/{fact_id}",
        json={"is_conflicted": False},
    )
    assert response.status_code == 200

    updated = response.json()["updated"]
    assert updated["is_conflicted"] is False


@pytest.mark.asyncio
async def test_update_fact_changes_text(client, db_session):
    """
    PATCH /memory/facts/{id} with new fact_text must update the stored text
    and return it in the response.
    """
    reg = await _register(client, "Rita")
    user_id = reg["user_id"]

    fact_id = await _seed_semantic_fact(
        db_session, user_id,
        fact_text="User uses Flask.",
    )

    response = await client.patch(
        f"/api/v1/memory/facts/{fact_id}",
        json={"fact_text": "User uses FastAPI."},
    )
    assert response.status_code == 200
    assert response.json()["updated"]["fact_text"] == "User uses FastAPI."


@pytest.mark.asyncio
async def test_update_fact_not_found_returns_404(client, db_session):
    """
    PATCH on a non-existent fact UUID must return 404.
    """
    await _register(client, "Steve")
    fake_id = str(uuid.uuid4())

    response = await client.patch(
        f"/api/v1/memory/facts/{fake_id}",
        json={"is_conflicted": False},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_fact_ownership_enforced(client, db_session):
    """
    A user must not be able to edit another user's semantic fact.
    The endpoint must return 404 (not 403) to avoid leaking fact existence.
    """
    # Register user A, seed their fact.
    reg_a = await _register(client, "Tara")
    fact_id = await _seed_semantic_fact(
        db_session, reg_a["user_id"], fact_text="Tara's private fact."
    )

    # Register user B and try to edit user A's fact.
    client.cookies.clear()
    await _register(client, "Uma")

    response = await client.patch(
        f"/api/v1/memory/facts/{fact_id}",
        json={"fact_text": "Overwritten by Uma."},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_fact_requires_auth(client):
    """
    PATCH without a session cookie must return 401.
    """
    client.cookies.clear()
    response = await client.patch(
        f"/api/v1/memory/facts/{uuid.uuid4()}",
        json={"is_conflicted": False},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /memory/export
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_requires_auth(client):
    """
    /memory/export must return 401 without a session cookie.
    """
    client.cookies.clear()
    response = await client.get("/api/v1/memory/export")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_export_empty_for_new_user(client):
    """
    A brand-new user with no memory data must receive empty lists for
    all three tiers.
    """
    await _register(client, "Victor")

    response = await client.get("/api/v1/memory/export")
    assert response.status_code == 200

    body = response.json()
    assert body["episodes"] == []
    assert body["semantic_facts"] == []
    assert body["procedural_patterns"] == []
    assert "exported_at" in body


@pytest.mark.asyncio
async def test_export_includes_seeded_data(client, db_session):
    """
    After seeding one episode and one semantic fact, the export must
    include both under their respective keys.
    """
    reg = await _register(client, "Wendy")
    user_id = reg["user_id"]

    await _seed_episode(db_session, user_id)
    await _seed_semantic_fact(db_session, user_id)

    response = await client.get("/api/v1/memory/export")
    assert response.status_code == 200

    body = response.json()
    assert len(body["episodes"]) == 1
    assert len(body["semantic_facts"]) == 1
    assert body["episodes"][0]["raw_prompt"] == "Test prompt"
    assert "async SQLAlchemy" in body["semantic_facts"][0]["fact_text"]


@pytest.mark.asyncio
async def test_export_does_not_include_other_users_data(client, db_session):
    """
    User A's export must never contain User B's episodes or facts.
    Data isolation is enforced by the user_id filter on every query.
    """
    # Register user A and seed their data.
    reg_a = await _register(client, "Xander")
    await _seed_episode(db_session, reg_a["user_id"])

    # Register user B (cookie switches to B automatically).
    client.cookies.clear()
    await _register(client, "Yara")

    # User B's export must be empty.
    response = await client.get("/api/v1/memory/export")
    assert response.status_code == 200

    body = response.json()
    assert body["episodes"] == []
    assert body["semantic_facts"] == []