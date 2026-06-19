"""
app/api/v1/router.py

Single top-level APIRouter for the entire v1 API surface.
main.py mounts this one router under /api/v1, so adding a new feature
means adding one include_router() call here — nothing else changes.

Sub-router prefix layout after mounting at /api/v1:
    /api/v1/auth/register
    /api/v1/auth/login
    /api/v1/auth/logout
    /api/v1/auth/me
    /api/v1/chat
    /api/v1/chat/history
    /api/v1/memory/conflicts
    /api/v1/memory/facts/{id}
    /api/v1/memory/export
    /api/v1/health

Used by: app/main.py exclusively.
"""

from fastapi import APIRouter # type: ignore

from app.api.v1 import auth, chat, health, memory

# The prefix here is intentionally empty — each sub-router carries its own
# prefix (/auth, /chat, /memory). The /health router has no prefix because
# the endpoint is /health, not /health/something.
v1_router = APIRouter()

v1_router.include_router(auth.router)
v1_router.include_router(chat.router)
v1_router.include_router(memory.router)
v1_router.include_router(health.router)