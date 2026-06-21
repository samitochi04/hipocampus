/**
 * src/components/memory/FactCard.jsx
 *
 * Displays a single semantic fact from the user's long-term memory.
 * Supports inline editing of the fact text so the user can correct or
 * refine what the system knows about them without going through the
 * conflict resolution flow.
 *
 * Two modes:
 *   View  — shows fact text, confidence meter, and an Edit button.
 *   Edit  — replaces the fact text with a textarea, Save / Cancel buttons.
 *
 * Used by: src/pages/MemoryPage.jsx (mapped over semantic_facts).
 */

import { useState } from "react";
import { updateFact } from "../../api/memory.js";
import { ApiError } from "../../api/client.js";

/**
 * FactCard
 * Renders one semantic fact in view or edit mode.
 *
 * Parameters:
 *   fact      (object)   — a SemanticFactOut item:
 *                          { id, fact_text, confidence, is_conflicted,
 *                            created_at, updated_at }
 *   onUpdated (function) — called with the updated fact object after a
 *                          successful save so MemoryPage can update its list
 *                          without a full re-fetch.
 *                          Signature: onUpdated(updatedFact: object) => void.
 *
 * Returns: JSX.Element.
 * Used by: src/pages/MemoryPage.jsx.
 */
export default function FactCard({ fact, onUpdated }) {
  const [editing, setEditing] = useState(false);
  const [draftText, setDraftText] = useState(fact.fact_text);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  /**
   * handleEdit
   * Enters edit mode, seeding the textarea with the current fact text.
   *
   * Parameters: none.
   * Returns: void.
   * Used by: the "Edit" button onClick.
   */
  function handleEdit() {
    setDraftText(fact.fact_text);
    setError(null);
    setEditing(true);
  }

  /**
   * handleCancel
   * Exits edit mode without saving, discarding any changes to draftText.
   *
   * Parameters: none.
   * Returns: void.
   * Used by: the "Cancel" button onClick.
   */
  function handleCancel() {
    setDraftText(fact.fact_text);
    setError(null);
    setEditing(false);
  }

  /**
   * handleSave
   * Submits the edited fact text to the backend via PATCH.
   * On success calls onUpdated with the server's updated fact object and
   * exits edit mode. On failure shows an inline error.
   *
   * Parameters: none.
   * Returns: void (async).
   * Used by: the "Save" button onClick.
   */
  async function handleSave() {
    const trimmed = draftText.trim();
    if (!trimmed) {
      setError("Fact text cannot be empty.");
      return;
    }
    if (trimmed === fact.fact_text) {
      // No changes — just exit edit mode.
      setEditing(false);
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const result = await updateFact(fact.id, { fact_text: trimmed });
      onUpdated(result.updated);
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed. Try again.");
    } finally {
      setSaving(false);
    }
  }

  /**
   * confidenceColor
   * Maps a 0–1 confidence value to one of three colours so the meter
   * gives an immediate visual signal without requiring the user to read
   * the number.
   *
   * Parameters:
   *   confidence (number) — 0.0–1.0 from the SemanticFact row.
   *
   * Returns: string — a CSS color value.
   * Used by: the confidence meter bar.
   */
  function confidenceColor(confidence) {
    if (confidence >= 0.75) return "var(--color-success)";
    if (confidence >= 0.5) return "var(--color-warning)";
    return "var(--color-error)";
  }

  return (
    <div style={styles.card}>
      {/* ── Fact text — view or edit ───────────────────────────────────── */}
      {editing ? (
        <div style={styles.editArea}>
          <label htmlFor={`fact-${fact.id}`} style={styles.editLabel}>
            Edit fact
          </label>
          <textarea
            id={`fact-${fact.id}`}
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
            rows={3}
            maxLength={2000}
            disabled={saving}
            style={saving ? { ...styles.editTextarea, opacity: 0.6 } : styles.editTextarea}
            autoFocus
          />
          {draftText.length > 1800 && (
            <span style={styles.charCount}>{2000 - draftText.length} chars left</span>
          )}
          {error && (
            <p role="alert" style={styles.errorMsg}>
              {error}
            </p>
          )}
          <div style={styles.editActions}>
            <button
              onClick={handleCancel}
              disabled={saving}
              style={styles.cancelBtn}
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              style={saving ? { ...styles.saveBtn, opacity: 0.5 } : styles.saveBtn}
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      ) : (
        <div style={styles.viewArea}>
          <p style={styles.factText}>{fact.fact_text}</p>
          <button onClick={handleEdit} style={styles.editBtn} aria-label="Edit this fact">
            Edit
          </button>
        </div>
      )}

      {/* ── Confidence meter ─────────────────────────────────────────────── */}
      <div style={styles.metaRow}>
        <div style={styles.confidenceGroup} title={`Confidence: ${Math.round(fact.confidence * 100)}%`}>
          {/*
            Track bar — a fixed-width background. The fill bar overlays it
            at `confidence * 100%` width so the meter is purely CSS, no SVG.
          */}
          <div style={styles.meterTrack} aria-hidden="true">
            <div
              style={{
                ...styles.meterFill,
                width: `${Math.round(fact.confidence * 100)}%`,
                background: confidenceColor(fact.confidence),
              }}
            />
          </div>
          <span style={styles.confidenceLabel}>
            {Math.round(fact.confidence * 100)}% confidence
          </span>
        </div>

        {/* Conflict badge — visible only when is_conflicted=true */}
        {fact.is_conflicted && (
          <span style={styles.conflictBadge} role="status">
            Conflicted
          </span>
        )}

        {/* Last updated timestamp */}
        <span style={styles.timestamp}>
          Updated {formatDate(fact.updated_at)}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * formatDate
 * Converts an ISO timestamp to a short human-readable relative string.
 * Falls back to the locale date string if the date is older than 7 days.
 *
 * Parameters:
 *   isoString (string) — ISO 8601 date string from the backend.
 *
 * Returns: string — e.g. "2 hours ago", "yesterday", "Jun 12".
 * Used by: the timestamp span in each FactCard.
 */
function formatDate(isoString) {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return "yesterday";
    if (diffDays < 7) return `${diffDays} days ago`;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  card: {
    background: "var(--color-bg-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    padding: "var(--sp-4) var(--sp-5)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-3)",
    transition: "border-color var(--transition-fast)",
  },

  viewArea: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "var(--sp-4)",
  },

  factText: {
    fontSize: "var(--fs-base)",
    color: "var(--color-text-primary)",
    lineHeight: "1.6",
    margin: 0,
    flex: 1,
  },

  editBtn: {
    flexShrink: 0,
    padding: "var(--sp-1) var(--sp-3)",
    background: "transparent",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-secondary)",
    fontSize: "var(--fs-sm)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    transition: "border-color var(--transition-fast), color var(--transition-fast)",
  },

  editArea: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-2)",
  },

  editLabel: {
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-medium)",
    color: "var(--color-text-placeholder)",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },

  editTextarea: {
    width: "100%",
    resize: "vertical",
    background: "var(--color-bg-input)",
    border: "1px solid var(--color-accent)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-primary)",
    fontSize: "var(--fs-base)",
    fontFamily: "var(--font-body)",
    lineHeight: "1.6",
    padding: "var(--sp-3) var(--sp-4)",
    outline: "none",
    minHeight: "80px",
    boxSizing: "border-box",
  },

  charCount: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-warning)",
    textAlign: "right",
  },

  errorMsg: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-error)",
    margin: 0,
  },

  editActions: {
    display: "flex",
    gap: "var(--sp-3)",
    justifyContent: "flex-end",
  },

  cancelBtn: {
    padding: "var(--sp-2) var(--sp-4)",
    background: "transparent",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-secondary)",
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-medium)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
  },

  saveBtn: {
    padding: "var(--sp-2) var(--sp-4)",
    background: "var(--color-accent)",
    border: "none",
    borderRadius: "var(--radius-sm)",
    color: "#0D0F1A",
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-bold)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
  },

  metaRow: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-4)",
    flexWrap: "wrap",
  },

  confidenceGroup: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-2)",
  },

  meterTrack: {
    width: "60px",
    height: "4px",
    background: "var(--color-bg-input)",
    borderRadius: "var(--radius-lg)",
    overflow: "hidden",
  },

  meterFill: {
    height: "100%",
    borderRadius: "var(--radius-lg)",
    transition: "width var(--transition-smooth)",
  },

  confidenceLabel: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-secondary)",
  },

  conflictBadge: {
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-error)",
    background: "rgba(248, 113, 113, 0.1)",
    border: "1px solid rgba(248, 113, 113, 0.3)",
    borderRadius: "var(--radius-lg)",
    padding: "2px var(--sp-2)",
  },

  timestamp: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-placeholder)",
    marginLeft: "auto",
  },
};