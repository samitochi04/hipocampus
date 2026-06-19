"""
app/models/__init__.py

Imports every ORM model so that when alembic/env.py imports Base.metadata,
all tables are already registered on it. Without this file, Alembic's
--autogenerate would see an empty schema and generate DROP TABLE migrations.

No application code should import from this file directly — import from
the individual model modules instead (e.g. from app.models.user import User).

Used by: alembic/env.py (via `from app.models import *` or `import app.models`)
"""

from app.models.user import User  # noqa: F401
from app.models.episode import Episode  # noqa: F401
from app.models.semantic_fact import SemanticFact  # noqa: F401
from app.models.procedural_pattern import ProceduralPattern  # noqa: F401

__all__ = ["User", "Episode", "SemanticFact", "ProceduralPattern"]