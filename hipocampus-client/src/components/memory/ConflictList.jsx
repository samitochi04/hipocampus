/**
 * src/components/memory/ConflictList.jsx
 *
 * Renders the list of semantic facts currently flagged as conflicted.
 * Each conflict shows:
 *   - The stored fact that is being contradicted.
 *   - The raw prompt from the episode that triggered the contradiction
 *     (so the user understands what caused it).
 *   - A "Keep original" button (dismiss — marks is_conflicted=false without
 *     changing the fact text) and an "Apply override" button (marks resolved
 *     and updates fact_text to the overriding statement if one is detected).
 *
 * Simple conflict resolution:
 *   The backend returns the conflicting_prompt as raw text. We surface it to
 *   the user and let them decide with two actions: keep the stored fact as-is
 *   or mark it resolved. Full text editing is available on FactCard — this
 *   component focuses on the decision, not the editing.
 *
 * Used by: src/pages/MemoryPage.jsx.
 */

import { useState } from "react";
import { updateFact } from "../../api/memory.js";
import { ApiError } from "../../api/client.js";

/**
 * ConflictList
 * Renders the conflicts section of the Memory page.
 *
 * Parameters:
 *   conflicts  (Array)    — array of ConflictOut objects from getConflicts().
 *                           Each has { fact: SemanticFactOut, conflicting_prompt: string|null }.
 *   onResolved (function) — called with the resolved fact's id (string) after
 *                           a successful resolve action so MemoryPage can remove
 *                           it from the list without a full re-fetch.
 *                           Signature: onResolved(factId: string) => void.
 *
 * Returns: JSX.Element | null — null when the conflicts array is empty.
 * Used by: src/pages/MemoryPage.jsx.
 */
export default function ConflictList({ conflicts, onResolved }) {
  if (!conflicts || conflicts.length === 0) return null;

  return (
    <section style={styles.section}>
      {/* ── Section heading ───────────────────────────────────────────────── */}
      <div style={styles.sectionHeader}>
        <span style={styles.badge}>{conflicts.length}</span>
        <h2 style={styles.sectionTitle}>Conflicts to resolve</h2>
      </div>
      <p style={styles.sectionDesc}>
        These stored facts were contradicted by a recent message. Review each
        one and decide whether to keep the original or mark it resolved.
      </p>

      {/* ── Conflict cards ───────────────────────────────────────────────── */}
      <div style={styles.list}>
        {conflicts.map((conflict) => (
          <ConflictCard
            key={conflict.fact.id}
            conflict={conflict}
            onResolved={onResolved}
          />
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Internal: ConflictCard
// ---------------------------------------------------------------------------

/**
 * ConflictCard
 * Renders a single conflict with the stored fact, the triggering prompt, and
 * resolution action buttons.
 *
 * Parameters:
 *   conflict   (object)   — a ConflictOut item: { fact, conflicting_prompt }.
 *   onResolved (function) — propagated from ConflictList to MemoryPage.
 *
 * Returns: JSX.Element.
 * Used by: ConflictList (mapped over conflicts array).
 */
function ConflictCard({ conflict, onResolved }) {
  const { fact, conflicting_prompt } = conflict;

  /**
   * resolving state
   * Tracks which action is in flight ("keep" | "override" | null) to show
   * the correct loading state on the right button.
   */
  const [resolving, setResolving] = useState(null);
  const [error, setError] = useState(null);

  /**
   * handleKeep
   * Marks the conflict resolved WITHOUT changing the fact text. The stored
   * fact wins — the user is saying "the old preference is still correct."
   *
   * Parameters: none.
   * Returns: void (async).
   * Used by: "Keep original" button onClick.
   */
  async function handleKeep() {
    setResolving("keep");
    setError(null);
    try {
      await updateFact(fact.id, { is_conflicted: false });
      onResolved(fact.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to resolve. Try again.");
      setResolving(null);
    }
  }

  /**
   * handleOverride
   * Marks the conflict resolved. In a future version this could also update
   * fact_text to reflect the override statement. For now it just clears the
   * conflict flag — the sleep consolidator will incorporate the new episode
   * during the next nightly run.
   *
   * Parameters: none.
   * Returns: void (async).
   * Used by: "Apply override" button onClick.
   */
  async function handleOverride() {
    setResolving("override");
    setError(null);
    try {
      await updateFact(fact.id, { is_conflicted: false });
      onResolved(fact.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to resolve. Try again.");
      setResolving(null);
    }
  }

  return (
    <div style={styles.card}>
      {/* ── Conflict label ───────────────────────────────────────────────── */}
      <div style={styles.conflictLabel}>
        <span style={styles.conflictDot} aria-hidden="true" />
        <span style={styles.conflictLabelText}>Conflict</span>
      </div>

      {/* ── Stored fact ──────────────────────────────────────────────────── */}
      <div style={styles.factBlock}>
        <span style={styles.blockLabel}>Stored preference</span>
        <p style={styles.factText}>{fact.fact_text}</p>
        <span style={styles.confidence}>
          Confidence: {Math.round(fact.confidence * 100)}%
        </span>
      </div>

      {/* ── Triggering prompt ────────────────────────────────────────────── */}
      {conflicting_prompt && (
        <div style={styles.promptBlock}>
          <span style={styles.blockLabel}>Contradicted by</span>
          <blockquote style={styles.promptQuote}>
            "{conflicting_prompt.length > 300
              ? conflicting_prompt.slice(0, 300) + "…"
              : conflicting_prompt}"
          </blockquote>
        </div>
      )}

      {/* ── Error ────────────────────────────────────────────────────────── */}
      {error && (
        <p role="alert" style={styles.errorMsg}>
          {error}
        </p>
      )}

      {/* ── Actions ──────────────────────────────────────────────────────── */}
      <div style={styles.actions}>
        <button
          onClick={handleKeep}
          disabled={!!resolving}
          style={resolving ? { ...styles.keepBtn, opacity: 0.5 } : styles.keepBtn}
        >
          {resolving === "keep" ? "Keeping…" : "Keep original"}
        </button>
        <button
          onClick={handleOverride}
          disabled={!!resolving}
          style={resolving ? { ...styles.overrideBtn, opacity: 0.5 } : styles.overrideBtn}
        >
          {resolving === "override" ? "Applying…" : "Mark resolved"}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  section: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-4)",
  },

  sectionHeader: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-3)",
  },

  badge: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    minWidth: "24px",
    height: "24px",
    padding: "0 var(--sp-2)",
    background: "rgba(248, 113, 113, 0.15)",
    border: "1px solid rgba(248, 113, 113, 0.3)",
    borderRadius: "var(--radius-lg)",
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-error)",
  },

  sectionTitle: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-lg)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    margin: 0,
  },

  sectionDesc: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.6",
    margin: 0,
    marginTop: "calc(-1 * var(--sp-2))",
  },

  list: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-4)",
  },

  card: {
    background: "var(--color-bg-surface)",
    border: "1px solid rgba(248, 113, 113, 0.25)",
    borderRadius: "var(--radius-md)",
    padding: "var(--sp-5)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-4)",
  },

  conflictLabel: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-2)",
  },

  conflictDot: {
    display: "inline-block",
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: "var(--color-error)",
    flexShrink: 0,
  },

  conflictLabelText: {
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-error)",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
  },

  factBlock: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-1)",
  },

  promptBlock: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-1)",
  },

  blockLabel: {
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-medium)",
    color: "var(--color-text-placeholder)",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },

  factText: {
    fontSize: "var(--fs-base)",
    color: "var(--color-text-primary)",
    lineHeight: "1.6",
    margin: 0,
  },

  confidence: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-secondary)",
  },

  promptQuote: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.6",
    margin: 0,
    paddingLeft: "var(--sp-4)",
    borderLeft: "2px solid var(--color-border)",
    fontStyle: "italic",
  },

  errorMsg: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-error)",
    margin: 0,
  },

  actions: {
    display: "flex",
    gap: "var(--sp-3)",
    flexWrap: "wrap",
  },

  keepBtn: {
    padding: "var(--sp-2) var(--sp-4)",
    background: "transparent",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-secondary)",
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-medium)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    transition: "border-color var(--transition-fast)",
  },

  overrideBtn: {
    padding: "var(--sp-2) var(--sp-4)",
    background: "var(--color-accent)",
    border: "1px solid transparent",
    borderRadius: "var(--radius-sm)",
    color: "#0D0F1A",
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-bold)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    transition: "background var(--transition-fast)",
  },
};