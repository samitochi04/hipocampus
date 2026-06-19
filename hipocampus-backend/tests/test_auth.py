"""
tests/test_auth.py

Endpoint tests for the authentication routes:
    POST /api/v1/auth/register
    POST /api/v1/auth/login
    POST /api/v1/auth/logout
    GET  /api/v1/auth/me

All tests use the AsyncClient fixture from conftest.py.
No live DB, Redis, or Qwen calls are made.
"""

import pytest # type: ignore


# ---------------------------------------------------------------------------
# /register
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_success(client):
    """
    Happy path: valid name returns 201 with a login_key, user_id, and message.
    A session cookie must be set on the response so the user is immediately
    logged in after registration.
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "Alice"},
    )
    assert response.status_code == 201

    body = response.json()
    assert "login_key" in body
    assert "user_id" in body
    assert body["login_key"].startswith("alice-")  # Key uses slugified name as prefix

    # Session cookie must be present after registration.
    assert "hipocampus_session" in response.cookies


@pytest.mark.asyncio
async def test_register_blank_name_rejected(client):
    """
    A name consisting of only whitespace must be rejected with 422 (Pydantic validation).
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "   "},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_empty_name_rejected(client):
    """
    An empty name string must be rejected with 422.
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": ""},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_name_too_long_rejected(client):
    """
    A name exceeding 64 characters must be rejected with 422.
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "A" * 65},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_stores_hashed_key_not_plaintext(client, db_session):
    """
    After registration, the DB row must store a hash, not the plaintext key.
    We verify by checking that login_key_hash does not equal the returned login_key.
    """
    from sqlalchemy import select # type: ignore
    from app.models.user import User

    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "Bob"},
    )
    assert response.status_code == 201
    plaintext_key = response.json()["login_key"]

    result = await db_session.execute(select(User).where(User.name == "Bob"))
    user = result.scalars().first()

    assert user is not None
    assert user.login_key_hash != plaintext_key
    assert user.login_key_hash.startswith("$argon2")  # Argon2 hash prefix


# ---------------------------------------------------------------------------
# /login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success(client):
    """
    Happy path: register first, then log in with the returned key.
    Response must be 200 with user info and a fresh session cookie.
    """
    reg = await client.post("/api/v1/auth/register", json={"name": "Carol"})
    assert reg.status_code == 201
    login_key = reg.json()["login_key"]

    # Clear cookies to simulate a fresh session.
    client.cookies.clear()

    response = await client.post(
        "/api/v1/auth/login",
        json={"login_key": login_key},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["name"] == "Carol"
    assert "id" in body
    assert "hipocampus_session" in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_key_returns_401(client):
    """
    Submitting a completely fabricated key must return 401 with a generic message.
    The message must not hint whether the name or key portion was wrong.
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={"login_key": "nobody-thiskeyiscompletelywrong1234567890ab"},
    )
    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_short_key_rejected(client):
    """
    A key shorter than 8 characters must be rejected by Pydantic validation (422).
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={"login_key": "short"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_clears_cookie(client):
    """
    After logout the session cookie must be deleted (max_age=0 or absent).
    The endpoint must return 204 with no body.
    """
    # Register and confirm the cookie is set.
    await client.post("/api/v1/auth/register", json={"name": "Dave"})
    assert "hipocampus_session" in client.cookies

    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 204

    # Cookie should be cleared after logout.
    assert "hipocampus_session" not in client.cookies


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_returns_current_user(client):
    """
    /me must return the authenticated user's public info when a valid
    session cookie is attached.
    """
    await client.post("/api/v1/auth/register", json={"name": "Eve"})

    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200

    body = response.json()
    assert body["name"] == "Eve"
    assert "id" in body
    assert "login_key_hash" not in body  # Must never be exposed


@pytest.mark.asyncio
async def test_me_unauthenticated_returns_401(client):
    """
    /me without a session cookie must return 401.
    """
    client.cookies.clear()
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401