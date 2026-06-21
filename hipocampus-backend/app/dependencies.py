"""
app/dependencies.py

FastAPI Depends() callables shared across route handlers.

Auth flow change (Bearer token primary):
  Previously read the JWT exclusively from the httpOnly cookie. Browsers
  in some environments silently drop cookies set through an nginx proxy over
  plain HTTP, so authenticated requests would return 401 even after a
  successful login.

  The dependency now checks BOTH locations in order:
    1. Authorization: Bearer <token>  ← set by the React client after login
    2. Cookie: hipocampus_session     ← fallback / future HTTPS production

  The backend issues both on every login/register response, so older clients
  that only use cookies still work, and new clients that use the header work
  regardless of cookie handling.

Used by: every protected route handler across app/api/v1/*.
"""

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_db  # re-exported so routes only need to import from here
from app.core.exceptions import TokenInvalidError
from app.core.redis_client import get_redis_client
from app.core.security import decode_access_token
from app.models.user import User
from app.schemas.auth import UserOut

settings = get_settings()

# ---------------------------------------------------------------------------
# Re-export get_db
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Redis dependency
# ---------------------------------------------------------------------------


def get_redis():
    """
    Returns the shared async Redis client.

    Returns: redis.asyncio.Redis
    Used by: any route or service that needs direct Redis access.
    """
    return get_redis_client()


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """
    Resolves the authenticated user from the incoming request.

    Token extraction order:
      1. Authorization: Bearer <token> — used by the React frontend. The
         token is returned in the login/register response body and stored
         in the client's memory, then sent as a header on every request.
         This bypasses any browser cookie restrictions (Secure attribute,
         SameSite, proxy stripping, etc.).
      2. Cookie: hipocampus_session — legacy / backup path. Used by any
         client that stores the httpOnly cookie (e.g. curl, future native
         app, or a browser that actually forwards it correctly).

    Parameters:
        request (Request)      — raw FastAPI request; gives access to both
                                 headers and cookies without a Depends binding
                                 that might conflict with the two-source strategy.
        db      (AsyncSession) — injected by Depends(get_db).

    Returns:
        UserOut — validated, authenticated user (never the raw ORM model).

    Raises:
        HTTPException 401 — token missing from both sources, expired, invalid
                            signature, or user_id no longer in the database.

    Used by: every protected route in app/api/v1/ via Depends(get_current_user).
    """
    from fastapi import HTTPException  # local import avoids circular at module level

    # ── 1. Try Authorization: Bearer header ──────────────────────────────
    token: str | None = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    # ── 2. Fall back to httpOnly cookie ──────────────────────────────────
    if not token:
        token = request.cookies.get(settings.COOKIE_NAME)

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    # decode_access_token raises TokenExpiredError / TokenInvalidError on failure;
    # those are caught by the handlers registered in main.py.
    user_id = decode_access_token(token)

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalars().first()

    if user is None:
        raise TokenInvalidError("User account not found.")

    return UserOut.model_validate(user)