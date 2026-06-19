"""
app/api/v1/auth.py

Authentication route handlers. Every handler is intentionally thin:
it validates the request body (Pydantic does this automatically),
delegates to auth_service, and formats the response.
No crypto, no DB queries, no business logic lives here.

Routes:
    POST /register  — create account, receive one-time login key
    POST /login     — submit login key, receive session cookie
    POST /logout    — clear the session cookie
    GET  /me        — return the current authenticated user's public info

Used by: app/api/v1/router.py, which mounts this router under /auth.
"""

from fastapi import APIRouter, Depends, Response, status # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore

from app.core.db import get_db
from app.dependencies import get_current_user
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    UserOut,
)
from app.services.auth_service import (
    authenticate_with_key,
    create_user_with_key,
    issue_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
    description=(
        "Creates a new user with the given display name. "
        "Returns a login key that is shown exactly once — the client must "
        "display it with a copy button and require the user to confirm they "
        "saved it before proceeding. A session cookie is set immediately so "
        "the user is logged in right after registering."
    ),
)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """
    Registration endpoint. Delegates entirely to auth_service.

    Parameters:
        body     (RegisterRequest) — validated request body containing `name`.
        response (Response)        — FastAPI injects this so we can set the
                                     session cookie on the outgoing response.
        db       (AsyncSession)    — async DB session from Depends(get_db).

    Returns:
        RegisterResponse — {login_key, user_id, message}
                           login_key is the plaintext key shown once to the user.

    Side effects:
        - Inserts one row into the `users` table.
        - Sets an httpOnly session cookie on the response.

    Used by: React RegisterForm component → api/auth.js → register()
    """
    result = await create_user_with_key(name=body.name, db=db)

    # Log the user in immediately after registration — no second trip needed.
    # We need a minimal user-like object with an `id` field for issue_session_cookie.
    class _MinimalUser:
        id = result.user_id

    issue_session_cookie(user=_MinimalUser(), response=response)

    return result


@router.post(
    "/login",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    summary="Log in with a login key",
    description=(
        "Verifies the submitted login key against the stored Argon2 hash. "
        "On success, issues a fresh session cookie and returns the user's "
        "public info. On failure, returns 401 with a generic message."
    ),
)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """
    Login endpoint. Verifies the key and issues a fresh session cookie.

    Parameters:
        body     (LoginRequest) — validated request body containing `login_key`.
        response (Response)     — FastAPI injects this for cookie issuance.
        db       (AsyncSession) — async DB session from Depends(get_db).

    Returns:
        UserOut — {id, name, created_at, last_login_at}
                  The client can use this to populate the UI without an
                  extra /me call after login.

    Side effects:
        - Updates users.last_login_at for the authenticated user.
        - Sets a fresh httpOnly session cookie on the response.

    Raises (handled by exception handlers in main.py):
        InvalidLoginKeyError → 401

    Used by: React LoginForm component → api/auth.js → login()
    """
    user = await authenticate_with_key(login_key=body.login_key, db=db)
    issue_session_cookie(user=user, response=response)
    return UserOut.model_validate(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out",
    description="Clears the session cookie. No request body needed.",
)
async def logout(response: Response) -> None:
    """
    Logout endpoint. Deletes the session cookie by setting it to an empty
    value with max_age=0 so the browser removes it immediately.
    No DB interaction needed — JWTs are stateless.

    Parameters:
        response (Response) — FastAPI injects this for cookie deletion.

    Returns:
        204 No Content — nothing to return after a logout.

    Used by: React Header component → api/auth.js → logout()
    """
    from app.config import get_settings
    s = get_settings()
    response.delete_cookie(
        key=s.COOKIE_NAME,
        httponly=True,
        secure=s.COOKIE_SECURE,
        samesite="lax",
        domain=s.COOKIE_DOMAIN,
    )


@router.get(
    "/me",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    summary="Get the current authenticated user",
    description=(
        "Returns the public profile of the user whose session cookie is "
        "attached to the request. Used by the React AuthContext on mount "
        "to restore the session without requiring a login."
    ),
)
async def me(
    current_user: UserOut = Depends(get_current_user),
) -> UserOut:
    """
    Session check endpoint. Validates the cookie and returns the user.
    The heavy lifting (cookie reading, JWT decoding, DB lookup) is done
    entirely by the get_current_user dependency — this handler is one line.

    Parameters:
        current_user (UserOut) — injected by Depends(get_current_user);
                                 raises 401 automatically if the cookie is
                                 missing, expired, or invalid.

    Returns:
        UserOut — {id, name, created_at, last_login_at}

    Used by: React AuthContext → api/auth.js → me()  (called on every app load)
    """
    return current_user