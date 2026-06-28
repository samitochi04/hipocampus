"""
app/api/v1/voice.py

Voice-mode endpoint: speech-to-text → memory pipeline → text-to-speech.

Two additional Qwen Cloud APIs used here:
  • qwen3.5-omni-flash  — multimodal STT (audio → transcription text)
  • qwen3-tts-flash     — TTS (response text → MP3 audio)

Combined with qwen-max (chat + consolidation) and text-embedding-v3 (vectors),
Hipocampus now uses four distinct Qwen Cloud APIs.

Flow for POST /voice/chat:
  1. Receive audio blob (WebM/WAV) + optional pre-extracted document content.
  2. Send audio to qwen3.5-omni-flash → get transcription.
  3. Feed transcription (+ doc content) into the existing process_turn() pipeline
     so the conversation is embedded, scored, and stored in memory exactly like
     a text turn. No special-casing — voice is a first-class memory citizen.
  4. Send AI response text to qwen3-tts-flash → get MP3 bytes.
  5. Return JSON: { transcription, response, audio_base64, session_id, chat_id }.

The frontend plays the audio, while the chat window still shows both the
transcription and the AI response as regular chat bubbles (with a mic indicator).

Used by: app/api/v1/router.py, src/api/voice.js.
"""

import base64
import json
import logging

import httpx
from app.core.db import get_db
from app.dependencies import get_current_user
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

settings = get_settings()
from app.schemas.auth import UserOut
from app.services.chat_service import process_turn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

# ---------------------------------------------------------------------------
# Qwen API endpoints (international)
# ---------------------------------------------------------------------------

_QWEN_BASE   = "https://dashscope-intl.aliyuncs.com"
_CHAT_URL    = f"{_QWEN_BASE}/compatible-mode/v1/chat/completions"
_TTS_URL     = f"{_QWEN_BASE}/compatible-mode/v1/audio/speech"
# Native DashScope multimodal endpoint — the compatible-mode endpoint does NOT
# support audio content type (only text/image_url/video_url/video).
_NATIVE_URL      = f"{_QWEN_BASE}/api/v1/services/aigc/multimodal-generation/generation"
# Native TTS endpoint — the compatible-mode /audio/speech endpoint returns
# empty bodies on the international DashScope instance.
_NATIVE_TTS_URL  = f"{_QWEN_BASE}/api/v1/services/aigc/text2audio/generation"

_HEADERS = {
    "Authorization": f"Bearer {settings.QWEN_API_KEY}",
    "Content-Type":  "application/json",
}

# Default TTS voice — professional, clear English.
# Options: Cherry, Ethan, Serena, Adrian, etc. (qwen3-tts-flash has 17 voices).
_TTS_VOICE  = "Cherry"
_TTS_MODEL  = "qwen3-tts-flash"
_STT_MODEL  = "qwen3.5-omni-flash"

# Maximum characters sent to TTS in one call.  Very long responses are
# truncated so the endpoint stays within the 180 RPM / char-limit window.
_TTS_MAX_CHARS = 3000

# ---------------------------------------------------------------------------
# Internal: speech-to-text via Qwen3.5-Omni-Flash
# ---------------------------------------------------------------------------


async def _transcribe(audio_bytes: bytes, mime_type: str) -> str:
    """
    Sends audio to qwen3.5-omni-flash for transcription.

    Uses the OpenAI-compatible chat completions endpoint with an ``audio_url``
    content block (data URI, base64-encoded).  The model returns plain text —
    we strip any surrounding quotes/labels the model might add.

    Parameters:
        audio_bytes (bytes) — raw audio from the browser (WebM/Opus or WAV).
        mime_type   (str)   — MIME type from the upload, e.g. "audio/webm".

    Returns:
        str — transcription text.

    Raises:
        HTTPException 422 — if the model returns an empty or error response.
    """
    audio_b64 = base64.b64encode(audio_bytes).decode()
    data_uri  = f"data:{mime_type};base64,{audio_b64}"

    # Native DashScope multimodal API format.
    # The compatible-mode endpoint only accepts text/image_url/video_url/video.
    # Audio requires the native /multimodal-generation/generation endpoint with
    # content items keyed as {"audio": "data:..."} and {"text": "..."}.
    payload = {
        "model": _STT_MODEL,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"audio": data_uri},
                        {"text": (
                            "Transcribe exactly what was said in this audio. "
                            "Return only the spoken words — no labels, no explanation."
                        )},
                    ],
                }
            ]
        },
        "parameters": {"result_format": "message"},
    }

    resp = None
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.post(_NATIVE_URL, json=payload, headers=_HEADERS)

        data = resp.json()

        # Native API response: output.choices[0].message.content is a list of dicts.
        content = data["output"]["choices"][0]["message"]["content"]
        # Content can be a string or a list like [{"text": "..."}]
        if isinstance(content, str):
            text = content.strip()
        else:
            text = " ".join(
                item.get("text", "") for item in content if item.get("text")
            ).strip()

        if not text:
            raise ValueError("Empty transcription")
        logger.info("STT OK: %d chars", len(text))
        return text

    except (KeyError, IndexError, ValueError) as exc:
        logger.error("STT error: %s | raw: %.300s",
                     exc, resp.text if resp is not None else "no response")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not transcribe audio. Please speak more clearly and try again.",
        )
    except httpx.RequestError as exc:
        logger.error("STT network error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speech recognition service unavailable.",
        )


# ---------------------------------------------------------------------------
# Internal: text-to-speech via Qwen3-TTS-Flash
# ---------------------------------------------------------------------------


def _synthesise_blocking(text: str) -> bytes:
    """
    Blocking TTS call using the official DashScope Python SDK.
    Runs in a thread pool via _synthesise() to avoid blocking the event loop.

    Uses qwen3-tts-flash via the SDK's SpeechSynthesizer which handles the
    WebSocket/streaming protocol internally — no need to manage SSE chunks or
    base64 reassembly manually.

    The SDK is pointed at the international DashScope endpoint so all
    billing goes through the same account as the other API calls.

    Parameters:
        text (str) — AI response text (already capped at _TTS_MAX_CHARS).

    Returns:
        bytes — raw MP3 audio data.

    Raises:
        ValueError — if the SDK returns no audio (model error or rate limit).
        ImportError — if dashscope is not installed (pip install dashscope).
    """
    import dashscope
    from dashscope.audio.tts_v3 import SpeechSynthesizer

    # Point the SDK at the international endpoint.
    dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"
    dashscope.api_key = settings.QWEN_API_KEY

    result = SpeechSynthesizer.call(
        model="qwen3-tts-flash",
        text=text,
        sample_rate=22050,
        format="mp3",
    )

    audio = result.get_audio_data()
    if not audio:
        resp = result.get_response()
        raise ValueError(f"TTS SDK returned no audio. Response: {resp}")

    logger.info("TTS OK (dashscope SDK): %d bytes", len(audio))
    return audio


async def _synthesise(text: str) -> bytes:
    """
    Async wrapper around _synthesise_blocking().
    Runs the blocking DashScope SDK call in a thread pool executor so the
    FastAPI event loop is not blocked during the TTS WebSocket connection.

    Parameters:
        text (str) — AI response text (capped at _TTS_MAX_CHARS).

    Returns:
        bytes — raw MP3 audio.

    Raises:
        ValueError / ImportError — propagated from _synthesise_blocking.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _synthesise_blocking, text[:_TTS_MAX_CHARS])


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/chat",
    status_code=200,
    summary="Voice turn: audio in → AI text + audio out",
)
async def voice_chat(
    audio:       UploadFile              = ...,
    session_id:  str | None              = Form(default=None),
    doc_content: str | None              = Form(default=None),
    doc_name:    str | None              = Form(default=None),
    current_user: UserOut                = Depends(get_current_user),
    db:          AsyncSession            = Depends(get_db),
) -> dict:
    """
    Processes one voice turn end-to-end.

    Steps:
      1. Read uploaded audio (WebM from browser MediaRecorder).
      2. Transcribe via qwen3.5-omni-flash.
      3. Optionally prepend document content (same format as text upload).
      4. Run through process_turn() — memory retrieval, qwen-max generation,
         importance scoring, episode storage.  Identical to a text turn.
      5. Synthesise AI response via qwen3-tts-flash → MP3.
      6. Return { transcription, response, audio_base64, session_id, chat_id }.

    The frontend displays the transcription as a user bubble (with a mic icon)
    and the response as an AI bubble, then plays the MP3 through the Audio API.
    Memory is stored for both — voice turns are first-class citizens.

    Parameters:
        audio       (UploadFile)   — audio blob from MediaRecorder (WebM/Opus).
        session_id  (str | None)   — session to continue, or None for new chat.
        doc_content (str | None)   — pre-extracted document text (from upload).
        doc_name    (str | None)   — document filename for the [DOCUMENT:] prefix.
        current_user, db, redis    — standard FastAPI dependencies.

    Returns:
        dict — { transcription, response, audio_base64, session_id, chat_id,
                 web_searched }.
    """
    # ── 1. Read audio ──────────────────────────────────────────────────────
    audio_bytes = await audio.read(20 * 1024 * 1024)   # 20 MB cap
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio upload.")

    mime = audio.content_type or "audio/webm"
    logger.info(
        "Voice turn: %d bytes mime=%s user=%s", len(audio_bytes), mime, current_user.id
    )

    # ── 2. Transcribe ──────────────────────────────────────────────────────
    transcription = await _transcribe(audio_bytes, mime)

    # ── 2b. Reject noise / too-short transcriptions ────────────────────────
    # VAD auto-mode can pick up ambient noise (keyboard, fan, etc.) that the
    # STT model transcribes as 1-3 Chinese characters. Reject anything < 5 chars
    # to prevent spurious API calls and Chinese-language AI responses.
    if len(transcription.strip()) < 5:
        logger.warning(
            "Transcription too short (%d chars) — likely noise, skipped: %r",
            len(transcription.strip()), transcription,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Transcription too short — please speak more clearly and hold the button longer.",
        )

    # ── 3. Build user message (with optional doc context) ─────────────────
    # Cap document content at 5,000 chars so the combined user_message
    # stays within the embedding model's hard limit of 8,192 chars.
    # The AI gets enough context for the voice turn; full content is in
    # the upload endpoint for any follow-up text analysis.
    _DOC_VOICE_LIMIT = 5_000
    if doc_content and doc_name:
        doc_snippet = doc_content[:_DOC_VOICE_LIMIT]
        if len(doc_content) > _DOC_VOICE_LIMIT:
            doc_snippet += "\n... [document truncated — ask follow-up questions for more detail]"
        user_message = (
            f"[DOCUMENT: {doc_name}]\n"
            f"{doc_snippet}\n"
            f"---\n"
            f"{transcription}"
        )
    else:
        user_message = transcription

    # ── 4. Memory pipeline ─────────────────────────────────────────────────
    # Try with the provided session_id first (continues existing chat).
    # If _get_or_create_chat raises 404 (session not found in DB — can happen
    # when useChat's sessionId is from a previous page load that hasn't been
    # persisted yet), fall back to session_id=None which creates a new chat.
    # The memory pipeline still retrieves cross-session context via vectors.
    logger.info(
        "voice_chat: calling process_turn session_id=%r user=%s",
        session_id, current_user.id,
    )
    # Attempt 1: continue existing session (if session_id provided).
    # Attempt 2 (fallback): create a new session when the session lookup
    # raises 404 — happens if the session exists only in React state but
    # the Chat row was deleted or belongs to a previous server run.
    # We catch ALL exceptions from attempt 1 that are session-lookup 404s;
    # other errors (Qwen API failures, DB errors) still propagate.
    _first_attempt_session = session_id  # may be None
    try:
        chat_response = await process_turn(
            user_message=user_message,
            session_id=_first_attempt_session,
            current_user=current_user,
            db=db,
        )
    except HTTPException as exc:
        if exc.status_code == 404 and _first_attempt_session:
            logger.warning(
                "session_id %r not found for user %s — retrying as new session",
                _first_attempt_session, current_user.id,
            )
            # Retry without session_id → auto-creates a fresh chat.
            chat_response = await process_turn(
                user_message=user_message,
                session_id=None,
                current_user=current_user,
                db=db,
            )
        else:
            raise

    # ── 5. Synthesise speech ───────────────────────────────────────────────
    # TTS is best-effort: if audio synthesis fails the text response is still
    # returned (audio_base64=null). The frontend will show the transcript in
    # the chat window and skip audio playback rather than crashing.
    audio_b64 = None
    audio_fmt = None
    try:
        audio_mp3 = await _synthesise(chat_response.response)
        audio_b64 = base64.b64encode(audio_mp3).decode()
        audio_fmt = "mp3"
        logger.info(
            "TTS OK: session=%s bytes=%d",
            chat_response.session_id, len(audio_mp3),
        )
    except Exception as tts_exc:
        logger.warning(
            "TTS failed (text response still delivered): %s", tts_exc,
        )

    logger.info(
        "Voice turn complete: session=%s tts_ok=%s web_searched=%s",
        chat_response.session_id, audio_b64 is not None, chat_response.web_searched,
    )

    return {
        "transcription": transcription,
        "response":      chat_response.response,
        "audio_base64":  audio_b64,
        "audio_format":  audio_fmt,
        "session_id":    chat_response.session_id,
        "chat_id":       chat_response.chat_id,
        "web_searched":  chat_response.web_searched,
    }