/**
 * src/api/chat.js
 *
 * API calls for the chat surface.
 * Maps to app/api/v1/chat.py on the backend.
 *
 * Used by:
 *   src/hooks/useChat.js — sendMessage(), getHistory()
 *   src/pages/ChatPage.jsx (indirectly via useChat)
 */

import { get, post } from "./client.js";

// ---------------------------------------------------------------------------
// Send a message
// ---------------------------------------------------------------------------

/**
 * Sends one user message through the full memory pipeline and returns the
 * AI's response.
 *
 * What the backend does (in order):
 *   1. Pushes the message to the Redis working-memory buffer.
 *   2. Retrieves multi-tier memory context (episodic, semantic, procedural).
 *   3. Assembles the prompt: system prompt + [MEMORY_CONTEXT] + history.
 *   4. Calls Qwen-Max and gets the response.
 *   5. Pushes the reply to the Redis buffer.
 *   6. Scores importance and writes the episode row to PostgreSQL.
 *   7. Returns the response payload.
 *
 * Parameters:
 *   message (string) — the raw user message, 1–8000 characters.
 *                      Validated by the Pydantic ChatRequest schema.
 *
 * Returns:
 *   Promise<{
 *     session_id:          string,  — identifies the current Redis buffer key
 *     response:            string,  — the AI's reply text (may contain markdown)
 *     context_tokens_used: number,  — how many tokens the [MEMORY_CONTEXT] block used
 *     importance_score:    number,  — 0.0–1.0 importance of this turn
 *   }>
 *
 * Throws:
 *   ApiError 401 — session expired; AuthContext will redirect to /login.
 *   ApiError 409 — the message contradicts a stored high-confidence preference.
 *                  The response body includes { type: "memory_conflict", detail: "..." }.
 *                  useChat.js surfaces this to the ConflictBanner component.
 *   ApiError 422 — message is empty or exceeds 8000 characters.
 *   ApiError 503 — Qwen API or Redis temporarily unavailable.
 *
 * Used by: src/hooks/useChat.js → send().
 */
export function sendMessage(message) {
  return post("/api/v1/chat", { message });
}

// ---------------------------------------------------------------------------
// Get session history
// ---------------------------------------------------------------------------

/**
 * Returns the contents of the Redis working-memory buffer for the current
 * session — up to the last 10 messages (5 full user↔AI turns).
 *
 * Used on ChatPage mount so the visible conversation is restored after a
 * page refresh without needing to re-query PostgreSQL. The buffer has a
 * 1-hour TTL; if it has expired the returned messages array will be empty
 * and the chat window shows a fresh session.
 *
 * Parameters: none — the session is identified by the backend via the cookie.
 *
 * Returns:
 *   Promise<{
 *     session_id: string,
 *     messages: Array<{ role: "user" | "assistant", content: string }>,
 *   }>
 *   Messages are ordered oldest → newest.
 *
 * Throws:
 *   ApiError 401 — session expired.
 *   ApiError 503 — Redis temporarily unavailable.
 *
 * Used by: src/hooks/useChat.js → loadHistory() on mount.
 */
export function getHistory() {
  return get("/api/v1/chat/history");
}