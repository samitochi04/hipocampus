"""
app/schemas/auth.py

Pydantic v2 request and response models for authentication.
These are the shapes FastAPI validates on the wire — they are completely
separate from the SQLAlchemy ORM models in app/models/.

Rules enforced here:
  - name must be 1–64 non-whitespace-only characters.
  - login_key is treated as an opaque string; no format assumption is made
    on the client side (the server generates it, the user pastes it back).

Used by: app/api/v1/auth.py route handlers.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    """
    Body the client sends to POST /api/v1/auth/register.

    Parameters:
        name (str) — the display name the user types on the registration screen.
                     Must be 1–64 chars and cannot be blank whitespace.

    Used by: app/api/v1/auth.py → register()
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Display name shown in the UI and used as the key prefix.",
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        """
        Rejects names that are only whitespace (e.g. "   ").
        Pydantic min_length counts characters, not printable content,
        so this validator is the second line of defence.
        """
        if not v.strip():
            raise ValueError("Name cannot be blank or whitespace only.")
        return v.strip()


class RegisterResponse(BaseModel):
    """
    Body returned by POST /api/v1/auth/register on success.
    The login_key is shown exactly once — the client must display it with a
    copy button and require the user to confirm they saved it before proceeding.

    Parameters (all set by auth_service, never by the client):
        login_key (str)  — plaintext key the user must save; never stored server-side.
        user_id   (str)  — UUID of the newly created user row.
        message   (str)  — human-readable instruction shown alongside the key.

    Used by: app/api/v1/auth.py → register()
    """

    login_key: str = Field(..., description="Save this — it cannot be recovered later.")
    user_id: str = Field(..., description="UUID of the newly created account.")
    message: str = Field(
        default="Registration successful. Copy your login key — it will not be shown again."
    )


class LoginRequest(BaseModel):
    """
    Body the client sends to POST /api/v1/auth/login.

    Parameters:
        login_key (str) — the plaintext key the user saved at registration.
                          The server verifies it against the Argon2 hash in the DB.

    Used by: app/api/v1/auth.py → login()
    """

    login_key: str = Field(
        ...,
        min_length=8,
        description="The login key that was shown once at registration.",
    )


class UserOut(BaseModel):
    """
    Safe public representation of a user, returned by GET /api/v1/auth/me.
    Never includes login_key_hash or any other internal field.

    Parameters (all sourced from the User ORM row):
        id            (uuid.UUID)       — user UUID
        name          (str)             — display name
        created_at    (datetime)        — account creation timestamp
        last_login_at (datetime | None) — most recent successful login, or None

    Used by:
        app/api/v1/auth.py → me()
        app/dependencies.py — returned as the current-user object in protected routes
    """

    model_config = {"from_attributes": True}  # Lets Pydantic read SQLAlchemy model attrs directly

    id: uuid.UUID
    name: str
    created_at: datetime
    last_login_at: datetime | None = None