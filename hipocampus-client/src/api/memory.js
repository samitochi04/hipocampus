/**
 * src/api/memory.js
 *
 * API calls for the memory management surface.
 * Maps to app/api/v1/memory.py on the backend.
 *
 * Used by:
 *   src/pages/MemoryPage.jsx — getConflicts(), exportMemory()
 *   src/components/memory/ConflictList.jsx — updateFact() (resolve conflicts)
 *   src/components/memory/FactCard.jsx     — updateFact() (edit fact text)
 */

import { get, patch } from "./client.js";

// ---------------------------------------------------------------------------
// Conflicts
// ---------------------------------------------------------------------------

/**
 * Returns all semantic facts currently flagged as conflicted for the
 * authenticated user.
 *
 * A conflict occurs when the sleep consolidator detects that a new episode
 * contradicts a high-confidence stored fact. The user must resolve it before
 * the fact can be used in future memory context blocks.
 *
 * Each result includes the conflicted fact AND the raw prompt from the
 * episode that triggered the contradiction, so the UI can show the user
 * exactly what caused the conflict.
 *
 * Parameters: none — filtered to the authenticated user server-side.
 *
 * Returns:
 *   Promise<Array<{
 *     fact: {
 *       id:                 string,   — UUID of the semantic fact
 *       fact_text:          string,   — the stored declarative statement
 *       confidence:         number,   — 0.0–1.0
 *       is_conflicted:      boolean,  — always true in this list
 *       source_episode_ids: string[], — UUIDs of contributing episodes
 *       created_at:         string,
 *       updated_at:         string,
 *     },
 *     conflicting_prompt: string | null,
 *     — raw_prompt from the episode that set is_conflicted=true,
 *       null if the episode was already pruned by the decay worker.
 *   }>>
 *   Returns an empty array if no conflicts exist.
 *
 * Throws:
 *   ApiError 401 — session expired.
 *
 * Used by: src/pages/MemoryPage.jsx → loadConflicts(),
 *          src/components/memory/ConflictList.jsx (passed as prop).
 */
export function getConflicts() {
  return get("/api/v1/memory/conflicts");
}

// ---------------------------------------------------------------------------
// Fact editing
// ---------------------------------------------------------------------------

/**
 * Partially updates a semantic fact owned by the authenticated user.
 * All fields in the update payload are optional — only provided fields are
 * written to the database. The most common uses are:
 *   - Pass { is_conflicted: false } to mark a conflict resolved.
 *   - Pass { fact_text: "..." } to correct or override the stored statement.
 *   - Pass { confidence: 0.9 } to manually boost or reduce confidence.
 *
 * Parameters:
 *   factId (string) — UUID of the SemanticFact row to update.
 *                     Ownership is enforced server-side; the backend returns
 *                     404 (not 403) if the fact belongs to another user, to
 *                     avoid leaking whether the ID exists at all.
 *   data   (object) — partial update payload:
 *     fact_text?    (string)  — replacement declarative statement (1–2000 chars).
 *     confidence?   (number)  — new confidence value (0.0–1.0).
 *     is_conflicted?(boolean) — pass false to mark a conflict resolved.
 *
 * Returns:
 *   Promise<{
 *     updated: {
 *       id:            string,
 *       fact_text:     string,
 *       confidence:    number,
 *       is_conflicted: boolean,
 *       updated_at:    string,
 *       ...
 *     },
 *     message: string,  — "Fact updated successfully."
 *   }>
 *
 * Throws:
 *   ApiError 401 — session expired.
 *   ApiError 404 — fact not found or belongs to another user.
 *   ApiError 422 — validation failure (e.g. fact_text too long, confidence out of range).
 *
 * Used by: src/components/memory/ConflictList.jsx → resolveConflict(),
 *          src/components/memory/FactCard.jsx     → saveEdit().
 */
export function updateFact(factId, data) {
  return patch(`/api/v1/memory/facts/${factId}`, data);
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

/**
 * Returns the complete contents of all three persistent memory tiers for
 * the authenticated user, bundled into a single JSON payload.
 *
 * Intended for two use cases:
 *   1. User-facing "Download my memory" feature on the MemoryPage.
 *   2. Debugging — lets the user inspect exactly what the system knows about them.
 *
 * Parameters: none — filtered to the authenticated user server-side.
 *
 * Returns:
 *   Promise<{
 *     user_id:  string,
 *     exported_at: string,   — ISO timestamp of the export
 *     episodes: Array<{
 *       id:               string,
 *       session_id:       string,
 *       raw_prompt:       string,
 *       llm_response:     string,
 *       importance_score: number,
 *       promoted:         boolean,
 *       created_at:       string,
 *     }>,
 *     semantic_facts: Array<{
 *       id:                 string,
 *       fact_text:          string,
 *       confidence:         number,
 *       is_conflicted:      boolean,
 *       source_episode_ids: string[],
 *       created_at:         string,
 *       updated_at:         string,
 *     }>,
 *     procedural_patterns: Array<{
 *       id:                 string,
 *       pattern_name:       string,
 *       trigger_conditions: object,
 *       successful_actions: object,
 *       success_rate:       number,
 *       last_used_at:       string | null,
 *     }>,
 *   }>
 *   Note: embedding vectors are omitted — they are binary and not useful
 *   in a JSON export.
 *
 * Throws:
 *   ApiError 401 — session expired.
 *
 * Used by: src/pages/MemoryPage.jsx → handleExport() (triggers JSON download).
 */
export function exportMemory() {
  return get("/api/v1/memory/export");
}