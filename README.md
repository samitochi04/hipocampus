# 🧠 Hipocampus

> **Persistent memory infrastructure for AI assistants.**
> Hipocampus gives any AI agent a hippocampal memory model: it accumulates
> experience across sessions, extracts lasting preferences, and retrieves the
> right context at the right moment — all within a limited context window.

---

## What it does

Most AI assistants forget everything the moment a conversation ends. Hipocampus
fixes that with a biologically-inspired four-tier memory architecture:

| Tier | Storage | What lives here |
|---|---|---|
| **Working** | Redis | Last 10 messages in the active session (sliding buffer) |
| **Episodic** | PostgreSQL + pgvector | Every significant exchange, scored by importance |
| **Semantic** | PostgreSQL + pgvector | Extracted long-term preferences and facts |
| **Procedural** | PostgreSQL + pgvector | Learned behavioural patterns across sessions |

On every chat turn, Hipocampus retrieves context from all four tiers, assembles
a ranked memory block, and injects it into the model prompt — without exceeding
the context window. Every night (or on demand), the sleep consolidation cycle
extracts semantic facts from recent episodes, resolves contradictions, and
applies a biological forgetting curve to stale memories.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        React Client                          │
│  RegisterPage → LoginKeyDisplay → ChatPage → MemoryPage     │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP (Bearer token)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI (Uvicorn)                        │
│                                                             │
│  POST /api/v1/chat ──► process_turn()                       │
│                              │                              │
│                    ┌─────────▼─────────┐                   │
│                    │  tier_retrieval   │                   │
│                    │  ┌─────────────┐  │                   │
│                    │  │ Redis buf   │  │  ← working memory │
│                    │  │ Episodes    │  │  ← episodic       │
│                    │  │ Sem. facts  │  │  ← semantic       │
│                    │  │ Proc. patt. │  │  ← procedural     │
│                    │  └─────────────┘  │                   │
│                    └─────────┬─────────┘                   │
│                              │ ranked context block         │
│                              ▼                              │
│                    Qwen-Max API call                        │
│                              │                              │
│                    score_importance() ──► Episode saved     │
└─────────────────────────────────────────────────────────────┘
                            │
                  ┌─────────┴──────────┐
                  ▼                    ▼
          PostgreSQL + pgvector     Redis 7
          (episodes, semantic       (working memory
           facts, procedural        buffer + Celery
           patterns, users)         broker)
                  │
                  ▼
         Celery Beat (3 AM UTC)
         sleep_consolidator.py
         ┌──────────────────────┐
         │ A. Fetch episodes    │
         │ B. Re-score decay    │
         │ C. Chunk by topic    │
         │ D. Qwen extraction   │
         │ E. Conflict resolve  │
         │ F. Write facts       │
         │ G. Mark promoted     │
         └──────────────────────┘
```

---

## Key technical design decisions

### Importance scoring
Every exchange is scored 0–1 before being written to PostgreSQL. The formula
combines four independent signals:

```
score = recency_weight × frequency_bonus × surprise_delta × explicit_flag
```

- **recency_weight** — how active the user has been in the last 30 days
- **frequency_bonus** — how often this topic has appeared before (repetition = importance)
- **surprise_delta** — cosine distance from the user's embedding centroid (novelty = importance)
- **explicit_flag** — 2× boost when the user uses commitment language ("always", "require", "never")

Episodes scoring ≥ 0.45 are saved to PostgreSQL. Episodes scoring ≥ 0.6 are
marked as consolidation candidates for the next sleep cycle.

### Sleep consolidation (hippocampal replay)
Inspired by the role of sleep in human memory consolidation, a Celery Beat job
runs nightly (or on demand via the Memory page) to:
1. Fetch unpromoted episodes above the importance threshold
2. Chunk them semantically and send to Qwen-Max for fact extraction
3. Embed each extracted fact and run pgvector cosine search against existing facts
4. Resolve contradictions — conflicted facts are flagged for user review
5. Write new semantic facts to PostgreSQL
6. Apply a 0.96/day decay multiplier to promoted episodes; prune those below 0.30 after 90 days

### Context window management
On every turn, `tier_retrieval.py`:
1. Expands the query using Qwen (query expansion for better semantic recall)
2. Runs parallel cosine similarity searches across episodes, semantic facts, and procedural patterns
3. Ranks results by a combined score (similarity × importance × recency)
4. Folds results into a `[MEMORY CONTEXT]` block sized to fit the token budget
5. Detects conflicts between the user's message and high-confidence stored facts → 409

### Auth
Passwordless — login key only. Registration generates a random key with the
user's slugified name as a prefix (`alice-x7k2m9p4...`). The key is shown
exactly once and cannot be recovered. JWTs are issued on login and sent as
`Authorization: Bearer` headers from the client (stored in `sessionStorage`).
`httpOnly` cookies are also set as a backup layer.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite 5, React Router v6, plain CSS custom properties |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Uvicorn |
| AI | Qwen-Max (chat + consolidation), text-embedding-v3 (1024-dim vectors) |
| Vector search | pgvector (cosine similarity, `<=>` operator) |
| Primary DB | PostgreSQL 16 |
| Cache / buffer | Redis 7 |
| Background tasks | Celery 5 (worker + beat scheduler) |
| Container | Docker + Docker Compose |
| Reverse proxy | nginx (in Docker; Vite proxy in local dev) |

---

## Quickstart

### Prerequisites
- Docker Desktop (Windows/Mac) or Docker Engine + Compose (Linux)
- A [Qwen/DashScope API key](https://dashscope.aliyuncs.com/) with access to
  `qwen-max` and `text-embedding-v3`

### 1 — Clone and configure

```bash
git clone https://github.com/your-org/hipocampus.git
cd hipocampus
```

Create `hipocampus-backend/.env`:

```env
DB_URL=postgresql+asyncpg://hipocampus:hipocampus@postgres:5432/hipocampus
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=your-secret-key-min-32-chars
QWEN_API_KEY=sk-...
COOKIE_SECURE=false
AUTO_CREATE_TABLES=true
CORS_ORIGINS=http://localhost:3000
```

### 2 — Build and run

```bash
docker compose up --build
```

Open **http://localhost:3000**

### 3 — Register

Go to `/register`, enter a display name, and **save the login key** that appears.
It is shown exactly once and cannot be recovered.

---

## Local development (without Docker for client + API)

Run Postgres, Redis, Celery worker and beat in Docker; run the API and client
natively for hot reload.

```bash
# Start infrastructure only
docker compose up postgres redis worker beat

# API (in hipocampus-backend/)
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Create `hipocampus-backend/.env.local` (overrides `.env` for local hostnames):

```env
DB_URL=postgresql+asyncpg://hipocampus:hipocampus@localhost:5432/hipocampus
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
COOKIE_SECURE=false
```

```bash
# Client (in hipocampus-client/)
npm install
npm run dev        # → http://localhost:5173
```

---

## Project structure

```
hipocampus/
├── docker-compose.yml
├── hipocampus-backend/
│   ├── app/
│   │   ├── api/v1/          # Route handlers (auth, chat, memory, admin, health)
│   │   ├── core/            # DB engine, Redis pool, security (JWT + Argon2)
│   │   ├── models/          # SQLAlchemy ORM models (User, Episode, SemanticFact, ProceduralPattern)
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   ├── chat_service.py
│   │   │   └── memory_engine/
│   │   │       ├── importance.py       # 4-signal importance scoring
│   │   │       ├── qwen_router.py      # All Qwen API calls (generate, embed, consolidate)
│   │   │       ├── redis_buffer.py     # Working memory (sliding window, TTL)
│   │   │       ├── sleep_consolidator.py  # Nightly memory consolidation pipeline
│   │   │       └── tier_retrieval.py   # Multi-tier context assembly
│   │   ├── tasks/           # Celery app + scheduled tasks
│   │   ├── config.py        # Pydantic-settings (reads .env + .env.local)
│   │   └── main.py          # FastAPI factory + lifespan
│   ├── tests/               # Async pytest suite (34 tests)
│   └── Dockerfile
└── hipocampus-client/
    ├── src/
    │   ├── api/             # Fetch wrappers (auth, chat, memory) + Bearer token management
    │   ├── components/      # Layout, auth, chat, memory components
    │   ├── context/         # AuthContext (register, login, logout, refreshUser)
    │   ├── hooks/           # useAuth, useChat
    │   └── pages/           # RegisterPage, LoginPage, ChatPage, MemoryPage
    ├── nginx.conf           # SPA fallback + /api proxy
    └── Dockerfile           # Multi-stage: Vite build → nginx:alpine
```

---

## Memory page

The `/memory` route gives users full visibility and control over what Hipocampus
knows about them:

- **Conflicts** — facts contradicted by recent messages, pending user resolution
- **Stored preferences** — all extracted semantic facts with confidence scores and edit/correct controls
- **⚡ Consolidate Now** — triggers the sleep consolidation pipeline immediately (dev/demo)
- **↓ Export JSON** — downloads the complete memory export (all three persistent tiers)

---

## API reference

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | — | Create account, get one-time login key |
| `POST` | `/api/v1/auth/login` | — | Authenticate with login key |
| `POST` | `/api/v1/auth/logout` | ✓ | Clear session |
| `GET` | `/api/v1/auth/me` | ✓ | Get current user |
| `POST` | `/api/v1/chat` | ✓ | Send message, get AI response with memory context |
| `GET` | `/api/v1/chat/history` | ✓ | Get Redis session buffer |
| `GET` | `/api/v1/memory/conflicts` | ✓ | List conflicted semantic facts |
| `PATCH` | `/api/v1/memory/facts/{id}` | ✓ | Edit or resolve a semantic fact |
| `GET` | `/api/v1/memory/export` | ✓ | Export all memory tiers as JSON |
| `POST` | `/api/v1/admin/consolidate` | ✓ | Trigger sleep consolidation immediately |
| `GET` | `/api/v1/health` | — | Health check (Postgres + Redis + Qwen) |

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_URL` | ✓ | — | `postgresql+asyncpg://...` |
| `REDIS_URL` | ✓ | — | `redis://...` |
| `JWT_SECRET_KEY` | ✓ | — | Signing secret (min 32 chars) |
| `QWEN_API_KEY` | ✓ | — | DashScope API key |
| `QWEN_ENDPOINT` | | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | Qwen base URL |
| `COOKIE_SECURE` | | `true` | Set `false` for local HTTP dev |
| `COOKIE_NAME` | | `hipocampus_session` | Session cookie name |
| `AUTO_CREATE_TABLES` | | `false` | Create DB tables on startup (dev only) |
| `CORS_ORIGINS` | | `http://localhost:5173` | Comma-separated allowed origins |
| `JWT_EXPIRE_MINUTES` | | `10080` | Token lifetime (default 7 days) |
| `LOG_LEVEL` | | `INFO` | Uvicorn / application log level |

---

## Running tests

```bash
# Requires a running Postgres instance
docker compose up postgres -d

docker exec hipocampus-postgres-1 \
  psql -U hipocampus -c "CREATE DATABASE hipocampus_test;"

cd hipocampus-backend
export TEST_DB_URL="postgresql+asyncpg://hipocampus:hipocampus@localhost:5432/hipocampus_test"
pytest tests/ -v
```

34 tests covering auth, chat, and memory endpoints.

---

## Deployment notes

- **Cookie security:** Set `COOKIE_SECURE=true` (default) in production. Requires HTTPS.
- **Secrets:** Rotate `JWT_SECRET_KEY` to invalidate all active sessions.
- **Scale:** Celery workers and beat can be scaled independently of the API.
  The beat scheduler must run as a single instance.
- **Migrations:** `AUTO_CREATE_TABLES=true` is for development only. Use
  `alembic upgrade head` in production.
- **Vector dimensions:** All embedding columns are `VECTOR(1024)` matching
  Qwen `text-embedding-v3`. Changing dimensions requires a schema migration.

---

## Track 1 — MemoryAgent (Qwen Cloud Hackathon)

Hipocampus was built for the **Track 1: MemoryAgent** challenge:

> *Build an Agent with persistent memory that autonomously accumulates
> experience, remembers user preferences, and makes increasingly accurate
> decisions across multi-turn, cross-session interactions.*

It directly addresses all three judging focus areas:

- **Efficient memory storage and retrieval** — pgvector cosine search across
  three persistent tiers with Qwen-powered query expansion
- **Timely forgetting of outdated information** — biological decay curve
  (0.96×/day multiplier, 90-day prune threshold)
- **Recalling critical memories within limited context windows** — ranked fold
  algorithm that fits retrieved context within the token budget

---

## License

MIT