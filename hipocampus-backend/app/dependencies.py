"""
app/dependencies.py

Defines FastAPI Depends() callables shared across route handlers.
Keeping them here (rather than inline in route files) means they can be
imported by any router without creating circular imports.

Three dependencies are defined:
  1. get_db()          — yields an async SQLAlchemy session per request
  2. get_redis()       — returns the shared Redis client
  3. get_current_user()— reads the JWT cookie, validates it, and returns the
                         authenticated User ORM object (or raises 401)

Used by: every protected route handler across app/api/v1/*.
"""

from fastapi import Cookie, Depends # type: ignore
from sqlalchemy import select # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore

from app.config import get_settings
from app.core.db import get_db  # re-exported so routes only need to import from here
from app.core.exceptions import TokenInvalidError
from app.core.redis_client import get_redis_client
from app.core.security import decode_access_token
from app.models.user import User
from app.schemas.auth import UserOut

settings = get_settings()

# ---------------------------------------------------------------------------
# Re-export get_db so route files have a single import source
# ---------------------------------------------------------------------------

# `get_db` is already an async generator defined in core/db.py.
# Re-exporting it here keeps route files from importing directly from core/.

# ---------------------------------------------------------------------------
# Redis dependency
# ---------------------------------------------------------------------------


def get_redis():
    """
    Returns the shared async Redis client backed by the connection pool
    opened at startup. No parameters needed — the pool is module-level state
    in core/redis_client.py.

    Returns:
        redis.asyncio.Redis — the shared client instance.

    Raises:
        RuntimeError — if called before init_redis_pool() ran (startup bug).

    Used by: any route or service that needs direct Redis access.
             Currently: app/api/v1/chat.py → get_history()
    """
    return get_redis_client()


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=settings.COOKIE_NAME),
) -> UserOut:
    """
    Reads the JWT from the httpOnly cookie, decodes it, and loads the
    corresponding User row from the database.

    This is the primary auth guard — add it as a Depends() argument to any
    route that must be authenticated:
        @router.get("/protected")
        async def protected(current_user: UserOut = Depends(get_current_user)):
            ...

    Parameters:
        db            (AsyncSession) — injected by Depends(get_db); used to
                                       query the users table.
        session_token (str | None)   — JWT string read automatically from the
                                       cookie named settings.COOKIE_NAME.
                                       FastAPI reads it from the request; the
                                       route handler never touches it directly.

    Returns:
        UserOut — the validated, authenticated user as a Pydantic schema object.
                  Does NOT return the raw ORM model so the hash is never
                  accidentally serialised.

    Raises:
        fastapi.HTTPException 401 — if the cookie is missing, the token is
                                    expired, the signature is invalid, or the
                                    user_id in the token no longer exists in DB.
                                    The specific error message is handled by the
                                    exception handlers in core/exceptions.py, so
                                    this function just raises TokenInvalidError
                                    for anything that isn't a clean decode.

    Used by: every protected route in app/api/v1/ via Depends(get_current_user).
    """
    from fastapi import HTTPException  # local import to avoid circular at module level

    if session_token is None:
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")

    # decode_access_token raises TokenExpiredError or TokenInvalidError on failure;
    # those are caught by the handlers registered in main.py.
    user_id = decode_access_token(session_token)

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalars().first()

    if user is None:
        # Token was valid but the account was deleted — treat as invalid.
        raise TokenInvalidError("User account not found.")

    return UserOut.model_validate(user)