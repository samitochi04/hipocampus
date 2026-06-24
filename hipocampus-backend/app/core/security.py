"""
app/core/security.py

All cryptographic operations live here and nowhere else.
Two responsibilities:
  1. Login key — the one-time-shown secret the user saves to log back in.
     We store only its Argon2 hash, never the plaintext.
  2. JWT access token — short-lived, cookie-bound token used for every
     authenticated request.

No database calls happen here. This is pure crypto logic so it stays
unit-testable without a DB.

Used by: app/services/auth_service.py (the only caller that should
touch these functions directly).
"""

import secrets
import re
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from app.config import get_settings
from app.core.exceptions import InvalidLoginKeyError, TokenExpiredError, TokenInvalidError

settings = get_settings()

# ---------------------------------------------------------------------------
# Argon2 hasher
# ---------------------------------------------------------------------------
# Argon2id is the current OWASP-recommended algorithm for password/key hashing.
# Default parameters (time_cost=3, memory_cost=65536, parallelism=4) are
# deliberately conservative — login happens rarely so the latency is fine.
_hasher = PasswordHasher()


# ---------------------------------------------------------------------------
# Login key helpers
# ---------------------------------------------------------------------------


def generate_login_key(name: str) -> str:
    """
    Builds a human-readable but cryptographically random login key that
    the user must copy and store after registration. It is shown exactly
    once and never retrievable again.

    Format: <slugified-name>-<32-char-urlsafe-token>
    Example: "alice-3Kx9mNpQ..."

    Parameters:
        name (str) — the display name the user registered with.
                     Used as a readable prefix so users can identify
                     which key belongs to which account.

    Returns:
        str — the plaintext login key. Caller must pass this to
              hash_login_key() before storing and return the plaintext
              only once to the client.

    Used by: app/services/auth_service.py → create_user_with_key().
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "user"
    # token_hex produces only 0-9a-f characters — no hyphens — so the key
    # format is unambiguously "{slug}-{48hexchars}". Using rsplit("-", maxsplit=1)
    # in auth_service.py then reliably extracts the slug regardless of how many
    # hyphens the slug itself has (e.g. "alex-chen-{hex}").
    # token_urlsafe was the previous choice but can produce "-" in its output,
    # causing rsplit to split inside the token instead of at the slug boundary.
    token = secrets.token_hex(24)    # 24 bytes → 48 lowercase hex chars, no hyphens
    return f"{slug}-{token}"


def hash_login_key(plaintext_key: str) -> str:
    """
    Hashes the plaintext login key with Argon2id.
    The resulting hash is what gets stored in the users table.

    Parameters:
        plaintext_key (str) — the key returned by generate_login_key().

    Returns:
        str — Argon2 hash string safe to persist in the database.

    Used by: app/services/auth_service.py → create_user_with_key().
    """
    return _hasher.hash(plaintext_key)


def verify_login_key(plaintext_key: str, stored_hash: str) -> bool:
    """
    Constant-time comparison of a submitted login key against the stored
    Argon2 hash. Returns True on match, raises InvalidLoginKeyError on
    mismatch or invalid hash so the caller never has to inspect low-level
    argon2 exceptions.

    Parameters:
        plaintext_key (str) — what the user typed / pasted into the login form.
        stored_hash   (str) — the value from users.login_key_hash in the DB.

    Returns:
        bool — always True when the key matches (raises on failure).

    Raises:
        app.core.exceptions.InvalidLoginKeyError — on any mismatch or bad hash.

    Used by: app/services/auth_service.py → authenticate_with_key().
    """
    try:
        _hasher.verify(stored_hash, plaintext_key)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        raise InvalidLoginKeyError("Login key is incorrect.")


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_access_token(user_id: str) -> str:
    """
    Encodes a signed JWT containing the user's UUID and an expiry claim.
    The token is later set as an httpOnly cookie by auth_service — it
    never touches the client's JavaScript environment.

    Parameters:
        user_id (str) — UUID of the authenticated user (users.id).

    Returns:
        str — signed JWT string.

    Used by: app/services/auth_service.py → issue_session_cookie().
    """
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,        # subject — the user's UUID
        "iat": now,            # issued-at
        "exp": expire,         # expiry — validated automatically by PyJWT
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """
    Decodes and validates a JWT, returning the embedded user_id (sub claim).
    Raises typed exceptions so the get_current_user dependency in
    dependencies.py can return clean 401 responses without leaking
    internal error details to the client.

    Parameters:
        token (str) — the raw JWT string read from the request cookie.

    Returns:
        str — the user UUID stored in the "sub" claim.

    Raises:
        app.core.exceptions.TokenExpiredError  — when the exp claim is in the past.
        app.core.exceptions.TokenInvalidError  — on any other decode failure
                                                 (bad signature, malformed token, etc.)

    Used by: app/dependencies.py → get_current_user().
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise TokenInvalidError("Token payload is missing 'sub' claim.")
        return user_id
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Access token has expired.")
    except jwt.PyJWTError:
        raise TokenInvalidError("Access token is invalid or has been tampered with.")