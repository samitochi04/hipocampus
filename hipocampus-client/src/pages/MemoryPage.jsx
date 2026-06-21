/**
 * src/pages/MemoryPage.jsx
 *
 * The memory dashboard rendered at /memory (protected route).
 * Shows the user three things:
 *   1. Conflicts — semantic facts that need resolution (ConflictList).
 *   2. Semantic facts — everything the system knows about the user (FactCard list).
 *   3. Export — a button to download all memory tiers as JSON.
 *
 * Data fetching strategy:
 *   Conflicts and facts are fetched in parallel on mount. Resolving a conflict
 *   removes it from the local conflicts list; editing a fact updates the local
 *   facts list. Neither action requires a full re-fetch.
 *
 * Used by: src/App.jsx (protected route, /memory).
 */

import { useCallback, useEffect, useState } from "react";
import Header from "../components/layout/Header.jsx";
import ConflictList from "../components/memory/ConflictList.jsx";
import FactCard from "../components/memory/FactCard.jsx";
import { exportMemory, getConflicts } from "../api/memory.js";
import { ApiError } from "../api/client.js";

/**
 * MemoryPage
 * Fetches and renders the user's memory state.
 *
 * Parameters: none.
 * Returns: JSX.Element.
 * Used by: src/App.jsx.
 */
export default function MemoryPage() {
  const [conflicts, setConflicts] = useState([]);
  const [facts, setFacts] = useState([]);
  const [loadingData, setLoadingData] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [exporting, setExporting] = useState(false);

  // ── Fetch on mount ─────────────────────────────────────────────────────

  /**
   * loadData
   * Fetches conflicts and the full memory export in parallel.
   * Extracts semantic_facts from the export payload for the FactCard list.
   *
   * Parameters: none.
   * Returns: void (async, sets state as side-effect).
   * Used by: useEffect on mount.
   */
  const loadData = useCallback(async () => {
    setLoadingData(true);
    setFetchError(null);
    try {
      const [conflictsData, exportData] = await Promise.all([
        getConflicts(),
        exportMemory(),
      ]);
      setConflicts(conflictsData ?? []);
      // Sort facts by confidence descending so high-confidence facts appear first.
      const sortedFacts = (exportData?.semantic_facts ?? []).sort(
        (a, b) => b.confidence - a.confidence
      );
      setFacts(sortedFacts);
    } catch (err) {
      setFetchError(
        err instanceof ApiError ? err.message : "Failed to load memory data."
      );
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Conflict resolved handler ──────────────────────────────────────────

  /**
   * handleConflictResolved
   * Removes the resolved conflict from the local list without re-fetching.
   * Called by ConflictList after a successful updateFact() call.
   *
   * Parameters:
   *   factId (string) — UUID of the resolved fact.
   *
   * Returns: void.
   * Used by: ConflictList → onResolved prop.
   */
  function handleConflictResolved(factId) {
    setConflicts((prev) => prev.filter((c) => c.fact.id !== factId));
    // Also clear the is_conflicted flag in the facts list so the badge
    // on the FactCard updates immediately.
    setFacts((prev) =>
      prev.map((f) => (f.id === factId ? { ...f, is_conflicted: false } : f))
    );
  }

  // ── Fact updated handler ───────────────────────────────────────────────

  /**
   * handleFactUpdated
   * Replaces the matching fact in the local list with the server's updated
   * version without re-fetching. Called by FactCard after a successful save.
   *
   * Parameters:
   *   updatedFact (object) — the SemanticFactOut returned by the PATCH endpoint.
   *
   * Returns: void.
   * Used by: FactCard → onUpdated prop.
   */
  function handleFactUpdated(updatedFact) {
    setFacts((prev) =>
      prev.map((f) => (f.id === updatedFact.id ? updatedFact : f))
    );
  }

  // ── Export handler ────────────────────────────────────────────────────

  /**
   * handleExport
   * Fetches the full memory export and triggers a JSON file download in
   * the browser using a temporary anchor element.
   *
   * Parameters: none.
   * Returns: void (async).
   * Used by: the Export button onClick.
   */
  async function handleExport() {
    setExporting(true);
    try {
      const data = await exportMemory();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `hipocampus-memory-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      // Non-critical — a toast would be ideal here in a future iteration.
    } finally {
      setExporting(false);
    }
  }

  // ── Render ───────────────────────────────────────────────────────────

  return (
    <div style={styles.page}>
      <Header />

      <main style={styles.main}>
        <div style={styles.container}>

          {/* ── Page header ─────────────────────────────────────────────── */}
          <div style={styles.pageHeader}>
            <div>
              <h1 style={styles.pageTitle}>Memory</h1>
              <p style={styles.pageSubtitle}>
                Everything Hipocampus knows about you — your preferences,
                decisions, and patterns.
              </p>
            </div>
            <button
              onClick={handleExport}
              disabled={exporting || loadingData}
              style={
                exporting || loadingData
                  ? { ...styles.exportBtn, opacity: 0.5, cursor: "not-allowed" }
                  : styles.exportBtn
              }
            >
              {exporting ? "Exporting…" : "↓ Export JSON"}
            </button>
          </div>

          {/* ── Loading state ─────────────────────────────────────────── */}
          {loadingData && (
            <div style={styles.loadingRow} aria-label="Loading memory data">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  style={{
                    ...styles.skeleton,
                    animationDelay: `${i * 0.15}s`,
                  }}
                />
              ))}
              <style>{`
                @keyframes shimmer {
                  0%   { opacity: 0.4; }
                  50%  { opacity: 0.7; }
                  100% { opacity: 0.4; }
                }
              `}</style>
            </div>
          )}

          {/* ── Fetch error ───────────────────────────────────────────── */}
          {fetchError && !loadingData && (
            <div style={styles.errorBox} role="alert">
              <p style={styles.errorMsg}>{fetchError}</p>
              <button onClick={loadData} style={styles.retryBtn}>
                Retry
              </button>
            </div>
          )}

          {/* ── Conflicts ─────────────────────────────────────────────── */}
          {!loadingData && !fetchError && (
            <ConflictList
              conflicts={conflicts}
              onResolved={handleConflictResolved}
            />
          )}

          {/* ── Semantic facts ────────────────────────────────────────── */}
          {!loadingData && !fetchError && (
            <section style={styles.factsSection}>
              <h2 style={styles.sectionTitle}>
                Stored preferences
                {facts.length > 0 && (
                  <span style={styles.factCount}>{facts.length}</span>
                )}
              </h2>

              {facts.length === 0 ? (
                <p style={styles.emptyMsg}>
                  No stored preferences yet. Hipocampus learns from your
                  conversations — preferences are extracted during the nightly
                  consolidation run.
                </p>
              ) : (
                <div style={styles.factList}>
                  {facts.map((fact) => (
                    <FactCard
                      key={fact.id}
                      fact={fact}
                      onUpdated={handleFactUpdated}
                    />
                  ))}
                </div>
              )}
            </section>
          )}

        </div>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  page: {
    display: "flex",
    flexDirection: "column",
    minHeight: "100vh",
    background: "var(--color-bg-base)",
  },

  main: {
    flex: 1,
    marginTop: "var(--header-height)",
    overflowY: "auto",
    padding: "var(--sp-8) var(--sp-4)",
  },

  container: {
    maxWidth: "var(--chat-max-width)",
    margin: "0 auto",
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-8)",
  },

  pageHeader: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "var(--sp-4)",
    flexWrap: "wrap",
  },

  pageTitle: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-2xl)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    margin: 0,
    letterSpacing: "-0.02em",
  },

  pageSubtitle: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.6",
    margin: "var(--sp-2) 0 0",
  },

  exportBtn: {
    padding: "var(--sp-2) var(--sp-4)",
    background: "transparent",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-secondary)",
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-medium)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    flexShrink: 0,
    transition: "border-color var(--transition-fast), color var(--transition-fast)",
  },

  loadingRow: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-3)",
  },

  skeleton: {
    height: "72px",
    background: "var(--color-bg-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    animation: "shimmer 1.5s ease-in-out infinite",
  },

  errorBox: {
    padding: "var(--sp-4)",
    background: "rgba(248, 113, 113, 0.06)",
    border: "1px solid rgba(248, 113, 113, 0.2)",
    borderRadius: "var(--radius-sm)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "var(--sp-4)",
  },

  errorMsg: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-error)",
    margin: 0,
  },

  retryBtn: {
    padding: "var(--sp-1) var(--sp-3)",
    background: "transparent",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-secondary)",
    fontSize: "var(--fs-sm)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    flexShrink: 0,
  },

  factsSection: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-4)",
  },

  sectionTitle: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-lg)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    margin: 0,
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-3)",
  },

  factCount: {
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-secondary)",
    background: "var(--color-bg-input)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    padding: "2px var(--sp-2)",
  },

  emptyMsg: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.6",
    margin: 0,
  },

  factList: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-3)",
  },
};