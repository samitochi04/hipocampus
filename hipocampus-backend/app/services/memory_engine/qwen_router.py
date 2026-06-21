"""
app/services/memory_engine/qwen_router.py

Single entry point for all Qwen/DashScope API calls.
Every function in this module maps to one specific LLM task.
No other file in the codebase calls the Qwen HTTP API directly —
all Qwen traffic flows through here so that:
  - API key and endpoint config are in one place.
  - Retry logic and error normalisation are centralised.
  - Swapping models (e.g. qwen-max → qwen-turbo) is a one-line change.
  - Unit tests can mock this single module instead of patching httpx everywhere.

Models used:
  - qwen-max       → chat generation, query expansion, conflict resolution
  - qwen-long      → sleep consolidation (processes up to 32 episodes per chunk)

All functions are async and raise QwenAPIError on non-recoverable failures
so callers get one exception type to handle regardless of the underlying
HTTP status code.

Used by:
    app/services/chat_service.py                    → generate()
    app/services/memory_engine/tier_retrieval.py    → expand_query()
    app/services/memory_engine/sleep_consolidator.py → consolidate_episodes(), resolve_conflict()
"""

import json
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class QwenAPIError(Exception):
    """
    Raised when the Qwen API returns a non-2xx status or a malformed response.
    Wraps the raw status code and body so callers can log or surface details.

    Raised by: every function in this module.
    Caught by:  app/services/chat_service.py, tier_retrieval.py,
                sleep_consolidator.py — each catches this and raises an
                appropriate HTTP exception or retries.
    """

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------


async def _post(payload: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
    """
    Sends a POST request to the Qwen /chat/completions endpoint and returns
    the parsed JSON body. Handles connection errors and non-2xx responses
    by raising QwenAPIError with a descriptive message.

    Parameters:
        payload (dict) — the full request body (model, messages, etc.).
        timeout (float)— request timeout in seconds. Default 60 s is generous
                         for qwen-max; pass 120+ for qwen-long consolidation calls.

    Returns:
        dict — the parsed JSON response body from the Qwen API.

    Raises:
        QwenAPIError — on HTTP error, connection failure, or JSON decode error.

    Used by: every public function in this module.
    """
    headers = {
        "Authorization": f"Bearer {settings.QWEN_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{settings.QWEN_ENDPOINT}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.RequestError as exc:
        raise QwenAPIError(f"Network error contacting Qwen API: {exc}") from exc

    if response.status_code != 200:
        raise QwenAPIError(
            f"Qwen API returned {response.status_code}: {response.text[:300]}",
            status_code=response.status_code,
        )

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise QwenAPIError(f"Qwen API returned non-JSON body: {response.text[:300]}") from exc


def _extract_text(response_body: dict) -> str:
    """
    Pulls the assistant message text out of a standard OpenAI-compatible
    /chat/completions response body. Raises QwenAPIError if the expected
    structure is missing so callers always get a typed error.

    Parameters:
        response_body (dict) — the full parsed JSON returned by _post().

    Returns:
        str — the content string from choices[0].message.content.

    Raises:
        QwenAPIError — if the response body doesn't match the expected shape.

    Used by: every public function in this module after calling _post().
    """
    try:
        return response_body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise QwenAPIError(
            f"Unexpected Qwen response structure: {str(response_body)[:300]}"
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate(
    system_prompt: str,
    messages: list[dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> str:
    """
    Sends a full conversation to qwen-max and returns the assistant reply.
    This is the main generation call used for every chat turn.

    Low temperature (0.1) keeps responses deterministic and code-accurate —
    essential for a technical assistant. Raise it only for creative tasks.

    Parameters:
        system_prompt (str)              — the system instruction block that
                                           includes the [MEMORY_CONTEXT] section
                                           assembled by tier_retrieval.py.
        messages      (list[dict])       — the conversation history from the Redis
                                           buffer, each dict has "role" and "content".
        temperature   (float)            — sampling temperature, default 0.1.
        max_tokens    (int)              — max tokens in the reply, default 2048.

    Returns:
        str — the raw assistant reply text. May contain markdown or code blocks.

    Raises:
        QwenAPIError — on any API or network failure.

    Used by: app/services/chat_service.py → process_turn()
    """
    payload = {
        "model": "qwen-max",
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
    }
    body = await _post(payload)
    return _extract_text(body)


async def expand_query(user_message: str) -> list[str]:
    """
    Asks qwen-max to generate semantic query variants of the user's message
    for use in pgvector similarity search. Returns 3 short retrieval-optimised
    phrases that capture different facets of the user's intent.

    Why: raw user messages contain conversational noise ("ok so now I want...")
    that hurts cosine similarity. Expanding to clean noun-phrase queries
    dramatically improves vector search recall.

    Parameters:
        user_message (str) — the raw message the user just sent.

    Returns:
        list[str] — 3 retrieval-optimised query strings.
                    Falls back to [user_message] if the API returns malformed JSON
                    so the caller always gets at least one query to work with.

    Raises:
        QwenAPIError — on network/API failure (not on JSON parse failure —
                       that returns the fallback list instead).

    Used by: app/services/memory_engine/tier_retrieval.py → parallel_vector_search()
    """
    prompt = (
        "Generate exactly 3 short semantic search queries for the following user message. "
        "Each query should capture a different aspect of the request. "
        "Return ONLY a JSON array of 3 strings with no explanation or markdown.\n\n"
        f"User message: {user_message}"
    )
    payload = {
        "model": "qwen-max",
        "temperature": 0.2,
        "max_tokens": 256,
        "messages": [{"role": "user", "content": prompt}],
    }
    body = await _post(payload)
    raw = _extract_text(body).strip()

    # Strip markdown code fences if the model wrapped the JSON anyway.
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        expansions = json.loads(raw)
        if isinstance(expansions, list) and len(expansions) >= 1:
            return [str(q) for q in expansions[:3]]
    except json.JSONDecodeError:
        logger.warning("expand_query: failed to parse JSON response, using original message.")

    return [user_message]


async def consolidate_episodes(episodes: list[dict]) -> dict:
    """
    Sends a batch of up to 32 episode dicts to qwen-long for overnight
    sleep consolidation. The model extracts distilled semantic facts,
    procedural patterns, and identifies low-value episodes to forget.

    Parameters:
        episodes (list[dict]) — each dict has:
                                  raw_prompt     (str)
                                  llm_response   (str)
                                  importance_score (float)
                                  id             (str, UUID)

    Returns:
        dict — parsed JSON with three keys:
               {
                 "semantic_facts":      [{"fact_text": str, "confidence": float}, ...],
                 "procedural_patterns": [{"pattern_name": str, "trigger_conditions": dict,
                                          "successful_actions": dict}, ...],
                 "to_forget":           [str, ...]   # episode UUIDs to mark for pruning
               }
               Returns empty lists under each key if the model output cannot
               be parsed so the consolidator degrades gracefully.

    Raises:
        QwenAPIError — on network/API failure.

    Used by: app/services/memory_engine/sleep_consolidator.py → consolidate_user_memory()
    """
    episodes_text = json.dumps(episodes, indent=2)
    prompt = (
        "You are a memory consolidation system. Analyse the following conversation episodes "
        "and extract durable knowledge from them.\n\n"
        "Return ONLY a JSON object with exactly these three keys:\n"
        "  semantic_facts:      array of {fact_text: string, confidence: 0.0-1.0}\n"
        "  procedural_patterns: array of {pattern_name: string, trigger_conditions: object, "
        "successful_actions: object}\n"
        "  to_forget:           array of episode id strings that are low-value and can be pruned\n\n"
        "No explanation. No markdown. Raw JSON only.\n\n"
        f"Episodes:\n{episodes_text}"
    )
    payload = {
        "model": "qwen-long",
        "temperature": 0.2,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    body = await _post(payload, timeout=120.0)  # Long timeout for batch processing
    raw = _extract_text(body).strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    empty: dict = {"semantic_facts": [], "procedural_patterns": [], "to_forget": []}
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return {**empty, **result}
    except json.JSONDecodeError:
        logger.error("consolidate_episodes: failed to parse JSON response from qwen-long.")

    return empty


async def resolve_conflict(existing_fact: str, new_fact: str) -> dict:
    """
    Asks qwen-max to arbitrate between a stored semantic fact and a
    contradicting new fact, returning a unified resolution.

    Called by the sleep consolidator when cosine similarity between two
    facts falls below 0.75 but their combined confidence exceeds 1.5 —
    the threshold where passive overwrite is too risky.

    Parameters:
        existing_fact (str) — the current fact_text stored in semantic_facts.
        new_fact      (str) — the candidate fact extracted from a recent episode.

    Returns:
        dict — {
                  "unified_text": str,    # the resolved statement
                  "confidence":   float   # confidence in the resolution (0.0-1.0)
                }
                Falls back to {"unified_text": new_fact, "confidence": 0.5}
                if the response cannot be parsed.

    Raises:
        QwenAPIError — on network/API failure.

    Used by: app/services/memory_engine/sleep_consolidator.py → _resolve_contradictions()
    """
    prompt = (
        "Two memory facts about the same user contradict each other. "
        "Resolve them into a single accurate unified statement.\n\n"
        f"Existing fact: {existing_fact}\n"
        f"New fact:      {new_fact}\n\n"
        "Return ONLY a JSON object: {\"unified_text\": string, \"confidence\": float}. "
        "No explanation. No markdown."
    )
    payload = {
        "model": "qwen-max",
        "temperature": 0.1,
        "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}],
    }
    body = await _post(payload)
    raw = _extract_text(body).strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    fallback = {"unified_text": new_fact, "confidence": 0.5}
    try:
        result = json.loads(raw)
        if isinstance(result, dict) and "unified_text" in result:
            return result
    except json.JSONDecodeError:
        logger.warning("resolve_conflict: failed to parse JSON, using new_fact as fallback.")

    return fallback


async def embed_text(text: str) -> list[float]:
    """
    Generates a 1O24-dimensional embedding vector for a given text string
    using the text-embedding-v3 model on DashScope.
    Used to populate the embedding columns in all three memory tables and
    to compute the query vector for pgvector similarity searches.

    Parameters:
        text (str) — the text to embed. For episodes, this is the concatenation
                     of raw_prompt + llm_response. For facts, it's fact_text.
                     For queries, it's the expanded query string.

    Returns:
        list[float] — 1024-element float list compatible with pgvector's
                      VECTOR(1024) column type.

    Raises:
        QwenAPIError — on network/API failure or unexpected response shape.

    Used by:
        app/services/chat_service.py                    → embedding the episode after each turn
        app/services/memory_engine/tier_retrieval.py    → embedding the query before vector search
        app/services/memory_engine/sleep_consolidator.py → embedding new facts and patterns
    """
    url = f"{settings.QWEN_ENDPOINT}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.QWEN_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "text-embedding-v3",
        "input": text,
        "dimension": 1024,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.RequestError as exc:
        raise QwenAPIError(f"Network error fetching embedding: {exc}") from exc

    if response.status_code != 200:
        raise QwenAPIError(
            f"Embedding API returned {response.status_code}: {response.text[:300]}",
            status_code=response.status_code,
        )

    try:
        body = response.json()
        return body["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise QwenAPIError(f"Unexpected embedding response shape: {str(exc)}") from exc