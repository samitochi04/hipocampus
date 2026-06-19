# Shared declarative Base, plus TimestampMixin (created_at, updated_at) and UUIDMixin (uuid primary key default) 
# reused by every table

from pydantic import BaseModel, Field
from datetime import datetime

class Episode(BaseModel):
    episode_id: str = ""
    user_id: str
    session_id: str
    content: str
    importance: float = 0.0
    tags: list[str] = []
    promoted: bool = False

class SemanticFact(BaseModel):
    fact_id: str = ""
    user_id: str
    statement: str
    confidence: float = 0.5
    source_ids: list[str] = []

class Procedure(BaseModel):
    proc_id: str = ""
    user_id: str
    trigger_text: str
    action_text: str
    success_rate: float = 0.5
    use_count: int = 0