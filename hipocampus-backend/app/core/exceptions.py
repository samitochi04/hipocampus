"""
app/core/exceptions.py

Defines every custom exception the backend raises, plus the FastAPI
exception handlers that turn them into clean JSON responses.

Convention:
  - Raise a typed exception deep in service/core code.
  - The handler here catches it at the app boundary and formats the
    HTTP response, so route handlers stay free of HTTPException boilerplate.

Handlers are registered in app/main.py via:
    app.add_exception_handler(ExcClass, handler_fn)

Used by:
    app/core/security.py       — raises InvalidLoginKeyError, TokenExpiredError, TokenInvalidError
    app/services/auth_service.py — raises InvalidLoginKeyError
    app/dependencies.py         — catches Token* errors to return 401
    app/main.py                 — registers the handlers
"""

from fastapi import Request # type: ignore
from fastapi.responses import JSONResponse # type: ignore


# ---------------------------------------------------------------------------
# Auth exceptions
# ---------------------------------------------------------------------------


class InvalidLoginKeyError(Exception):
    """
    Raised when a submitted login key does not match the stored Argon2 hash.
    Maps to HTTP 401.
    Raised by: app/core/security.py → verify_login_key()
    Caught by:  invalid_login_key_handler() below, registered in main.py
    """


class TokenExpiredError(Exception):
    """
    Raised when the JWT exp claim is in the past.
    Maps to HTTP 401 with a specific message so the client knows to prompt
    the user to log in again rather than treating it as a generic error.
    Raised by: app/core/security.py → decode_access_token()
    Caught by:  token_expired_handler() below, registered in main.py
    """


class TokenInvalidError(Exception):
    """
    Raised when the JWT is malformed, has a bad signature, or is missing
    the required sub claim. Maps to HTTP 401.
    Raised by: app/core/security.py → decode_access_token()
    Caught by:  token_invalid_handler() below, registered in main.py
    """


# ---------------------------------------------------------------------------
# Memory exceptions
# ---------------------------------------------------------------------------


class MemoryConflictError(Exception):
    """
    Raised when the memory engine detects that an incoming user preference
    directly contradicts a stored semantic fact that hasn't been resolved yet.
    Maps to HTTP 409 so the client can surface the conflict UI.
    Raised by: app/services/memory_engine/tier_retrieval.py → detect_conflict()
    Caught by:  memory_conflict_handler() below, registered in main.py
    """


class SessionBufferError(Exception):
    """
    Raised when the Redis session buffer cannot be read or written —
    typically because the Redis pool isn't ready or the key has been
    evicted mid-request.
    Maps to HTTP 503 (Service Unavailable).
    Raised by: app/services/memory_engine/redis_buffer.py
    Caught by:  session_buffer_handler() below, registered in main.py
    """


# ---------------------------------------------------------------------------
# Exception handlers
# — Each handler follows the FastAPI signature: (request, exc) → Response
# ---------------------------------------------------------------------------


async def invalid_login_key_handler(request: Request, exc: InvalidLoginKeyError) -> JSONResponse:
    """
    Returns a 401 with a generic message that does not hint whether the
    name or the key itself was wrong — prevents user enumeration.

    Parameters:
        request (Request) — the incoming FastAPI request (required by the handler protocol)
        exc (InvalidLoginKeyError) — the raised exception instance

    Used by: registered in app/main.py via app.add_exception_handler()
    """
    return JSONResponse(
        status_code=401,
        content={"detail": "Login key is incorrect. Please check your saved key and try again."},
    )


async def token_expired_handler(request: Request, exc: TokenExpiredError) -> JSONResponse:
    """
    Returns a 401 with a message telling the client the session has expired,
    prompting a re-login rather than a generic error page.

    Parameters:
        request (Request) — the incoming FastAPI request
        exc (TokenExpiredError) — the raised exception instance

    Used by: registered in app/main.py via app.add_exception_handler()
    """
    return JSONResponse(
        status_code=401,
        content={"detail": "Your session has expired. Please log in again."},
    )


async def token_invalid_handler(request: Request, exc: TokenInvalidError) -> JSONResponse:
    """
    Returns a 401 for any JWT that is malformed or tampered with.

    Parameters:
        request (Request) — the incoming FastAPI request
        exc (TokenInvalidError) — the raised exception instance

    Used by: registered in app/main.py via app.add_exception_handler()
    """
    return JSONResponse(
        status_code=401,
        content={"detail": "Invalid session token. Please log in again."},
    )


async def memory_conflict_handler(request: Request, exc: MemoryConflictError) -> JSONResponse:
    """
    Returns a 409 Conflict so the React client knows to show the conflict
    resolution UI instead of treating the response as a normal chat reply.

    Parameters:
        request (Request) — the incoming FastAPI request
        exc (MemoryConflictError) — carries the conflict detail in str(exc)

    Used by: registered in app/main.py via app.add_exception_handler()
    """
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc), "type": "memory_conflict"},
    )


async def session_buffer_handler(request: Request, exc: SessionBufferError) -> JSONResponse:
    """
    Returns a 503 when the Redis working-memory buffer is unavailable.

    Parameters:
        request (Request) — the incoming FastAPI request
        exc (SessionBufferError) — the raised exception instance

    Used by: registered in app/main.py via app.add_exception_handler()
    """
    return JSONResponse(
        status_code=503,
        content={"detail": "Memory buffer is temporarily unavailable. Please try again."},
    )