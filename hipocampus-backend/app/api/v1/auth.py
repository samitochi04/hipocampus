"""
app/api/v1/auth.py

Authentication route handlers — thin wrappers over auth_service.

Change: register and login now return `access_token` in the response body
in addition to setting the httpOnly cookie. The React client stores the
token in memory and sends it as Authorization: Bearer on every request,
bypassing browser cookie restrictions over plain HTTP / nginx proxy.

Routes:
    POST /register  — create account, receive one-time login key + token
    POST /login     — submit login key, receive user profile + token
    POST /logout    — clear session cookie
    GET  /me        — return current authenticated user's public info
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.dependencies import get_current_user
from app.schemas.auth import LoginRequest, RegisterRequest, RegisterResponse, UserOut
from app.services.auth_service import (
    authenticate_with_key,
    create_user_with_key,
    issue_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Registration endpoint.
    Returns the one-time login key, user_id, and a signed JWT access_token.
    The token lets the client authenticate immediately via Authorization: Bearer
    without relying on the cookie being stored.

    Parameters:
        body     (RegisterRequest) — validated request body containing `name`.
        response (Response)        — FastAPI injects this for cookie issuance.
        db       (AsyncSession)    — async DB session from Depends(get_db).

    Returns:
        dict — {login_key, user_id, message, access_token}

    Used by: React RegisterForm → api/auth.js → register()
    """
    result = await create_user_with_key(name=body.name, db=db)

    class _MinimalUser:
        id = result.user_id

    # issue_session_cookie sets the httpOnly cookie AND returns the raw JWT.
    token = issue_session_cookie(user=_MinimalUser(), response=response)

    # Return all RegisterResponse fields plus the token so the client can
    # store it and use Authorization: Bearer on subsequent requests.
    return {
        "login_key": result.login_key,
        "user_id": result.user_id,
        "message": result.message,
        "access_token": token,
    }


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    summary="Log in with a login key",
)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Login endpoint. Returns user profile + access_token in the response body.

    Parameters:
        body     (LoginRequest) — validated request body containing `login_key`.
        response (Response)     — FastAPI injects this for cookie issuance.
        db       (AsyncSession) — async DB session from Depends(get_db).

    Returns:
        dict — {id, name, created_at, last_login_at, access_token}

    Used by: React LoginForm → api/auth.js → login()
    """
    user = await authenticate_with_key(login_key=body.login_key, db=db)
    token = issue_session_cookie(user=user, response=response)
    user_out = UserOut.model_validate(user)

    return {**user_out.model_dump(), "access_token": token}


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out",
)
async def logout(response: Response) -> None:
    """
    Logout endpoint. Clears the session cookie.
    The client also discards its in-memory Bearer token.

    Parameters:
        response (Response) — FastAPI injects this for cookie deletion.

    Returns: 204 No Content.
    Used by: React Header → api/auth.js → logout()
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
)
async def me(
    current_user: UserOut = Depends(get_current_user),
) -> UserOut:
    """
    Session check. Accepts token from Authorization: Bearer header OR cookie.
    Used by AuthContext on mount to restore session after page load.

    Parameters:
        current_user (UserOut) — resolved by Depends(get_current_user).

    Returns: UserOut — {id, name, created_at, last_login_at}
    Used by: React AuthContext → api/auth.js → me()
    """
    return current_user