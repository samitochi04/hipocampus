"""
app/models/base.py

Provides two reusable SQLAlchemy mixins that every model in this project
inherits, keeping the boilerplate columns DRY:

  - UUIDMixin     → id column (UUID primary key, server-generated)
  - TimestampMixin → created_at / updated_at columns (auto-managed)

Import pattern in model files:
    from app.core.db import Base
    from app.models.base import UUIDMixin, TimestampMixin

    class MyModel(UUIDMixin, TimestampMixin, Base):
        __tablename__ = "my_table"
        ...

Used by: every file under app/models/*.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, func # type: ignore
from sqlalchemy.dialects.postgresql import UUID # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore


class UUIDMixin:
    """
    Adds an `id` column (PostgreSQL UUID, primary key) auto-generated
    server-side by gen_random_uuid(). Using a UUID instead of a serial
    integer makes IDs safe to expose in API responses and avoids
    enumeration attacks.

    Takes no parameters — SQLAlchemy reads this as a mixin at class
    definition time.

    Used by: all models in app/models/*.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,             # Python-side default (used in tests / inserts)
        server_default=func.gen_random_uuid(),  # DB-side default (used in raw SQL)
        index=True,
    )


class TimestampMixin:
    """
    Adds `created_at` and `updated_at` columns that are managed
    automatically by the database:
      - created_at is set once on INSERT via now().
      - updated_at is set on INSERT and refreshed on every UPDATE
        via the onupdate hook.

    Both are timezone-aware (TIMESTAMPTZ in Postgres).

    Takes no parameters — SQLAlchemy reads this as a mixin.

    Used by: all models in app/models/* that need audit timestamps.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),  # Refreshed on every ORM update
        nullable=False,
    )