"""
app/models/user.py

ORM model for the `users` table.
This is the only identity record we store. There is no email or password —
authentication is entirely key-based (see app/core/security.py).

Columns:
    id               — UUID primary key (from UUIDMixin)
    name             — display name entered at registration, not required to be unique
    login_key_hash   — Argon2 hash of the one-time login key shown at registration
    last_login_at    — updated every time the user authenticates successfully
    created_at       — set once on insert (from TimestampMixin)
    updated_at       — auto-refreshed on every update (from TimestampMixin)

Used by:
    app/models/__init__.py      — so Alembic sees this table in metadata
    app/services/auth_service.py — creates and queries user rows
    app/dependencies.py          — loads the user row from the JWT sub claim
"""

from datetime import datetime

from sqlalchemy import DateTime, String # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore

from app.core.db import Base # type: ignore
from app.models.base import TimestampMixin, UUIDMixin # type: ignore


class User(UUIDMixin, TimestampMixin, Base):
    """
    Maps to the `users` table in PostgreSQL.
    Inherits id (UUID PK), created_at, and updated_at from the mixins.

    Takes no parameters at class definition — SQLAlchemy reads the
    column declarations automatically.
    Instantiated by: app/services/auth_service.py → create_user_with_key().
    """

    __tablename__ = "users"

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        # Not declared UNIQUE — two people can register with the name "Alex".
        # Identity is the login key, not the name.
        index=True,  # Indexed so we can look up users by name if needed in future
    )

    login_key_hash: Mapped[str] = mapped_column(
        String(256),  # Argon2 hashes are ~95 chars; 256 gives comfortable headroom
        nullable=False,
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,  # NULL until the user logs in for the first time after registration
    )

    def __repr__(self) -> str:
        """
        Developer-friendly string representation of the User instance.
        Never exposes login_key_hash — only id and name.
        Used by: logging, debugger, test output.
        """
        return f"<User id={self.id} name={self.name!r}>"