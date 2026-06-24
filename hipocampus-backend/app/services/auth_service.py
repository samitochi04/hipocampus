"""
app/services/auth_service.py

All authentication business logic lives here.
The route handlers in app/api/v1/auth.py are thin wrappers that delegate
to these functions — no DB queries or crypto operations belong in the router.

Three responsibilities:
  1. create_user_with_key()  — registration: generate key, hash it, insert user row
  2. authenticate_with_key() — login: look up user by name prefix, verify key hash
  3. issue_session_cookie()  — cookie issuance: sign JWT, set httpOnly cookie on response

Used by: app/api/v1/auth.py exclusively.
"""

from datetime import UTC, datetime

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import InvalidLoginKeyError
from app.core.security import (
    create_access_token,
    generate_login_key,
    hash_login_key,
    verify_login_key,
)
from app.models.user import User
from app.schemas.auth import RegisterResponse, UserOut

settings = get_settings()


async def create_user_with_key(name: str, db: AsyncSession) -> RegisterResponse:
    """
    Handles the full registration flow in one transaction:
      1. Generates a plaintext login key from the user's name.
      2. Hashes it with Argon2 — the plaintext is never stored.
      3. Inserts the new User row with the hash.
      4. Returns the plaintext key inside RegisterResponse so the route
         can hand it to the client exactly once.

    Parameters:
        name (str)           — display name from RegisterRequest.name;
                               already stripped and validated by Pydantic.
        db   (AsyncSession)  — injected async DB session from Depends(get_db).

    Returns:
        RegisterResponse — contains the one-time plaintext login_key and the
                           new user's UUID. The route must NOT call this function
                           twice — each call generates a different key.

    Raises:
        sqlalchemy.exc.SQLAlchemyError — on any DB write failure; the session
                                         rolls back automatically via get_db().

    Used by: app/api/v1/auth.py → register()
    """
    plaintext_key = generate_login_key(name)
    key_hash = hash_login_key(plaintext_key)

    new_user = User(
        name=name,
        login_key_hash=key_hash,
    )
    db.add(new_user)
    await db.flush()   # Flush to get the DB-generated UUID without committing yet
    await db.refresh(new_user)  # Reload so new_user.id is populated from the DB

    return RegisterResponse(
        login_key=plaintext_key,
        user_id=str(new_user.id),
    )


async def authenticate_with_key(login_key: str, db: AsyncSession) -> User:
    """
    Verifies a submitted login key against all stored Argon2 hashes for
    users whose key prefix matches the name slug embedded in the key.

    Strategy:
      - Extract the name slug (everything before the last '-') from the key.
      - Query all users whose name slug matches (usually 1, rarely a few).
      - Run Argon2 verify on each candidate — the correct one returns True.
      - On success, update last_login_at and return the User row.
      - On failure, raise InvalidLoginKeyError (caught by the exception handler).

    Why not query by a stored slug? Storing the slug separately would leak
    part of the key structure. Querying by the name prefix is safe because
    the slug is derived from a public value (the display name) and the
    token suffix is the actual secret.

    Parameters:
        login_key (str)      — plaintext key pasted by the user into the login form.
        db        (AsyncSession) — injected async DB session from Depends(get_db).

    Returns:
        User — the authenticated ORM user object (not yet committed; the route
               calls issue_session_cookie which triggers the commit via get_db).

    Raises:
        app.core.exceptions.InvalidLoginKeyError — if no user matches or the
                                                   key is wrong for every candidate.

    Used by: app/api/v1/auth.py → login()
    """
    # Extract the name slug: "alice-3kx9mn..." → "alice"
    # Key format: "{slug}-{48hexchars}" — token is hex-only (no hyphens), so
    # rsplit on the last "-" always lands at the slug/token boundary.

    parts = login_key.rsplit("-", maxsplit=1)
    if len(parts) < 2:  # Malformed key — fail fast
        raise InvalidLoginKeyError("Login key format is invalid.")

    name_slug = parts[0]  # e.g. "alice" or "john-doe"

    # Reconstruct the likely display name to narrow the DB query.
    # Slug uses hyphens for spaces/special chars, so "john-doe" → "john doe".
    # This is a best-effort filter, not security-critical — Argon2 verify
    # is the actual gate.
    name_hint = name_slug.replace("-", " ")

    result = await db.execute(
        select(User).where(User.name.ilike(f"%{name_hint}%"))
    )
    candidates: list[User] = list(result.scalars().all())

    if not candidates:
        raise InvalidLoginKeyError("Login key is incorrect.")

    for user in candidates:
        try:
            verify_login_key(login_key, user.login_key_hash)
            # If verify_login_key didn't raise, this is the right user.
            user.last_login_at = datetime.now(UTC)
            return user
        except InvalidLoginKeyError:
            continue  # Try the next candidate

    # No candidate passed verification.
    raise InvalidLoginKeyError("Login key is incorrect.")


def issue_session_cookie(user: User | UserOut, response: Response) -> str:
    """
    Signs a JWT containing the user's UUID and attaches it to the response
    as an httpOnly cookie. Returns the raw token string so the route can
    include metadata in the response body if needed.

    httpOnly=True  — JavaScript cannot read the cookie; protects against XSS.
    samesite="lax" — Cookie is sent on top-level navigations from other sites
                     but not on cross-site sub-requests; balances UX and security.
    secure         — Set from settings.COOKIE_SECURE; should be True in prod (HTTPS only).

    Parameters:
        user     (User | UserOut) — the authenticated user; only .id is used.
        response (Response)       — the FastAPI Response object the route receives
                                    as a parameter; the cookie is set on this object
                                    and FastAPI attaches it to the outgoing HTTP response.

    Returns:
        str — the signed JWT string (useful for debugging; not needed by the client).

    Used by: app/api/v1/auth.py → register(), login()
    """
    token = create_access_token(user_id=str(user.id))

    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,           # Never readable by JavaScript
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        domain=settings.COOKIE_DOMAIN,  # None = current host only
        max_age=settings.JWT_EXPIRE_MINUTES * 60,  # Browser clears cookie after this
    )

    return token