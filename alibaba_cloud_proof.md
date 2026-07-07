# Alibaba Cloud Deployment Proof

**Project:** Hipocampus — Persistent Memory Infrastructure for AI Assistants  
**Hackathon:** Qwen Cloud Hackathon 2026 — Track 1: MemoryAgent  
**Submission date:** July 2026

---

## Deployment Images

<img width="1918" height="862" alt="SWAS-Server" src="https://github.com/user-attachments/assets/23482b99-5e0a-48df-aefb-dbfe682d6dd9" />

---

<img width="1918" height="867" alt="SWAS-Server-Instance" src="https://github.com/user-attachments/assets/d1f81c39-28a9-4cc4-ba7c-b71376f8fc45" />

---

<img width="1918" height="868" alt="SWAS-Server-Usage" src="https://github.com/user-attachments/assets/4b3d4435-fca0-4961-ae7b-f6daa30cab07" />

---

## 1. Alibaba Cloud Services Used

### 1.1 Simple Application Server (SWAS)

The Hipocampus backend is deployed on an **Alibaba Cloud Simple Application Server** instance running in the `singapore` region.

| Property       | Value                               |
| :------------- | :---------------------------------- |
| Instance type  | Simple Application Server           |
| OS             | Ubuntu 24.04 LTS                    |
| Public IP      | `47.236.190.20`                     |
| Region         | `singapore`                         |
| Firewall rules | TCP 3000 (frontend), TCP 8000 (API) |

**Notes: Screenshots of Alibaba Cloud Server and Qwen Cloud APIs use are in alibaba-cloud/ folder**

**Live endpoints:**

```
Frontend:  http://47.236.190.20:3000
           https://disk-studying-imagination-concern.trycloudflare.com

API:       http://47.236.190.20:8000
Health:    http://47.236.190.20:8000/api/v1/health
Analytics: http://47.236.190.20:3000/analyse  (public, no auth)
```

### 1.2 Qwen Cloud (DashScope International)

All AI inference is powered exclusively by **Alibaba Cloud's Qwen Cloud** via the DashScope international API endpoint (`home.qwencloud.com`). No other AI provider is used anywhere in the stack.

| Model              | API String           | Purpose                                                    |
| :----------------- | :------------------- | :--------------------------------------------------------- |
| Qwen-Max           | `qwen-max`           | Chat generation, memory consolidation, document generation |
| Text Embedding v3  | `text-embedding-v3`  | 1024-dim semantic vectors for memory storage and retrieval |
| Qwen3.5-Omni-Flash | `qwen3.5-omni-flash` | Speech-to-text (voice mode)                                |
| Qwen-Omni-Turbo    | `qwen-omni-turbo`    | Text-to-speech (voice mode audio output)                   |

---

## 2. Backend Running on Alibaba Cloud — Evidence

### 2.1 Health Check Response

The following endpoint is live on the Alibaba Cloud SWAS instance. It confirms PostgreSQL, Redis, and Qwen API connectivity:

**Request:**

```bash
curl https://disk-studying-imagination-concern.trycloudflare.com/api/v1/health
```

**Response:**

```json
{
  "status": "healthy",
  "timestamp": "2026-07-05T20:00:00.000000+00:00",
  "checks": {
    "postgres": { "status": "ok", "latency_ms": 24.63 },
    "redis": { "status": "ok", "latency_ms": 17.18 },
    "qwen": { "status": "ok", "latency_ms": 41.3 }
  }
}
```

The `qwen` check makes a live call to `dashscope-intl.aliyuncs.com` — confirming the backend is actively communicating with Alibaba Cloud's Qwen API from the server.

### 2.2 Live API Logs — Qwen Cloud Calls

The following log lines are from the running backend on the Alibaba Cloud server, captured during a live voice session. They confirm real API calls to DashScope:

```
2026-07-05T19:11:55 | INFO | app.api.v1.voice  | Voice turn: 130345 bytes mime=audio/webm;codecs=opus
2026-07-05T19:11:59 | INFO | app.api.v1.voice  | STT OK: 138 chars
                                                   ↑ qwen3.5-omni-flash (DashScope)

2026-07-05T19:12:05 | INFO | app.services.memory_engine.qwen_router | Search OK (html/6): 'current temperature in Évry, France'
                                                   ↑ qwen-max with web_search tool (DashScope)

2026-07-05T19:12:09 | INFO | app.services.chat_service | Saved episode b43dd7e8 (score=0.800)
                                                   ↑ text-embedding-v3 vector stored in pgvector (DashScope)

2026-07-05T20:04:28 | INFO | app.api.v1.voice  | TTS OK (omni-turbo stream/134): 2069760 bytes
                                                   ↑ qwen-omni-turbo audio streaming (DashScope)
```

### 2.3 Docker Containers Running on Alibaba Cloud Server

Output of `docker compose ps` on the Alibaba Cloud SWAS instance:

```
NAME                        STATUS          PORTS
hipocampus-api-1            Up (healthy)    0.0.0.0:8000->8000/tcp
hipocampus-client-1         Up              0.0.0.0:3000->80/tcp
hipocampus-worker-1         Up              (Celery worker)
hipocampus-beat-1           Up              (Celery Beat scheduler)
hipocampus-postgres-1       Up (healthy)    5432/tcp
hipocampus-redis-1          Up (healthy)    6379/tcp
```

---

## 3. Qwen Cloud API Integration — Code References

The following source files contain all Qwen Cloud API calls. Every AI operation in Hipocampus routes through these files to `dashscope-intl.aliyuncs.com`.

### Primary integration file

**[`hipocampus-backend/app/services/memory_engine/qwen_router.py`](hipocampus-backend/app/services/memory_engine/qwen_router.py)**

This single file handles all four Qwen Cloud API integrations:

```python
# Base endpoint — Alibaba Cloud DashScope International
_QWEN_ENDPOINT = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# 1. Text generation + web search tool calling (qwen-max)
async def generate_with_search(system_prompt, messages, ...) -> tuple[str, bool]:
    payload = {
        "model": "qwen-max",
        "tools": [WEB_SEARCH_TOOL],     # OpenAI-compatible tool calling
        "tool_choice": "auto",
        ...
    }
    # If finish_reason == "tool_calls": execute search, return results to Qwen

# 2. Text embeddings (text-embedding-v3, 1024 dimensions)
async def embed_text(text: str) -> list[float]:
    payload = {
        "model": "text-embedding-v3",
        "input": text,
        "dimension": 1024,
    }
    # Returns 1024-float vector stored in PostgreSQL + pgvector
```

### Voice API integration

**[`hipocampus-backend/app/api/v1/voice.py`](hipocampus-backend/app/api/v1/voice.py)**

```python
# Speech-to-Text: qwen3.5-omni-flash
_NATIVE_URL = "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

async def _transcribe(audio_bytes: bytes, mime_type: str) -> str:
    payload = {
        "model": "qwen3.5-omni-flash",
        "input": {
            "messages": [{
                "role": "user",
                "content": [
                    {"audio": f"data:{mime_type};base64,{b64}"},
                    {"text": "Transcribe exactly what was said."}
                ]
            }]
        },
        "parameters": {"result_format": "message"},
    }

# Text-to-Speech: qwen-omni-turbo (streaming PCM16 → WAV)
async def _synthesise(text: str) -> bytes:
    payload = {
        "model": "qwen-omni-turbo",
        "modalities": ["text", "audio"],
        "audio": {"format": "mp3"},
        "stream": True,     # Audio requires streaming
        ...
    }
    # Chunks arrive as delta.audio.data (PCM16)
    # Wrapped in WAV header via _pcm_to_wav()
```

### Sleep Consolidation (Qwen-Max)

**[`hipocampus-backend/app/services/memory_engine/qwen_router.py`](hipocampus-backend/app/services/memory_engine/qwen_router.py)**

```python
# Nightly memory consolidation — extracts semantic facts from episodes
async def consolidate_episodes(episodes: list[dict]) -> dict:
    # Calls qwen-max with structured extraction prompt
    # Returns: {facts: [...], patterns: [...], conflicts: [...]}
```

---

## 4. Public Analytics Dashboard

The `/analyse` endpoint is publicly accessible with no authentication required. It provides live statistics from the running backend on Alibaba Cloud:

```
https://disk-studying-imagination-concern.trycloudflare.com/analyse
```

This dashboard shows:

- Total episodes stored (PostgreSQL + pgvector on Alibaba Cloud SWAS)
- Semantic facts extracted by Qwen-Max
- 24-hour API activity (live DashScope call counts)
- Memory tier distribution
- Importance score histogram

---

## 5. Deployment Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│         Alibaba Cloud Simple Application Server          │
│                   singapore region                     │
│                  IP: 47.236.190.20                       │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Docker Compose (6 containers)                  │    │
│  │  ├── FastAPI (uvicorn, port 8000)               │    │
│  │  ├── React/Nginx (port 3000)                    │    │
│  │  ├── Celery Worker                              │    │
│  │  ├── Celery Beat (3AM consolidation)            │    │
│  │  ├── PostgreSQL 16 + pgvector                   │    │
│  │  └── Redis 7                                    │    │
│  └─────────────────────────────────────────────────┘    │
│                          │                               │
│                          │ HTTPS calls to                │
│                          ▼ dashscope-intl.aliyuncs.com   │
└─────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┴─────────────────┐
          │    Qwen Cloud (DashScope Intl)    │
          │  qwen-max · text-embedding-v3     │
          │  qwen3.5-omni-flash · omni-turbo  │
          └───────────────────────────────────┘
```

---

## 6. Short Proof Recording

A separate 60-second screen recording accompanies this submission demonstrating:

1. SSH connection to the Alibaba Cloud SWAS instance (`ssh admin@47.236.190.20`)
2. `docker compose ps` — all 6 containers healthy
3. `curl localhost:8000/api/v1/health` — Postgres, Redis, and Qwen all returning `ok`
4. Live backend logs showing DashScope API calls (`STT OK`, `TTS OK`, `Search OK`)
5. The Alibaba Cloud console showing the running SWAS instance

---

_This file serves as the required proof of Alibaba Cloud deployment for the Qwen Cloud Hackathon 2026 submission._
