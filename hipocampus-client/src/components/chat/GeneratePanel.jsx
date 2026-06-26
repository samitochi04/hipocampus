/**
 * src/components/chat/GeneratePanel.jsx
 *
 * AI document generation panel rendered inside the ChatPage toolbar.
 * Lets the user describe what they want generated, choose a format
 * (MD / PDF / CSV) and page size (A4 / A3 for PDF), then downloads the
 * result directly from the browser.
 *
 * States:
 *   idle    → user fills the form, clicks Generate
 *   loading → fetch in flight, button disabled, typewriter progress
 *   done    → success banner + "Download again" link
 *   error   → error message, form remains editable
 *
 * Used by: src/pages/ChatPage.jsx (rendered in the toolbar when open).
 */

import { useState } from "react";
import { generateDocument, triggerDownload } from "../../api/generate.js";

// ---------------------------------------------------------------------------
// GeneratePanel
// ---------------------------------------------------------------------------

/**
 * GeneratePanel
 *
 * Parameters:
 *   onClose (function) — called when the user clicks the × button to close.
 *
 * Returns: JSX.Element.
 * Used by: src/pages/ChatPage.jsx.
 */
export default function GeneratePanel({ onClose }) {
  const [prompt,    setPrompt]    = useState("");
  const [format,    setFormat]    = useState("pdf");
  const [size,      setSize]      = useState("A4");
  const [status,    setStatus]    = useState("idle"); // idle | loading | done | error
  const [errorMsg,  setErrorMsg]  = useState("");
  const [lastFile,  setLastFile]  = useState(null);  // { blob, filename }

  async function handleGenerate() {
    if (!prompt.trim()) return;
    setStatus("loading");
    setErrorMsg("");
    setLastFile(null);

    try {
      const result = await generateDocument({ prompt: prompt.trim(), format, size });
      setLastFile(result);
      triggerDownload(result.blob, result.filename);
      setStatus("done");
    } catch (err) {
      setErrorMsg(err.message ?? "Something went wrong. Please try again.");
      setStatus("error");
    }
  }

  function handleDownloadAgain() {
    if (lastFile) triggerDownload(lastFile.blob, lastFile.filename);
  }

  function handleReset() {
    setStatus("idle");
    setErrorMsg("");
    setPrompt("");
  }

  const canGenerate = prompt.trim().length >= 5 && status !== "loading";

  return (
    <div style={s.panel}>
      {/* Header */}
      <div style={s.header}>
        <span style={s.headerTitle}>📄 Generate Document</span>
        <button onClick={onClose} style={s.closeBtn} aria-label="Close panel">×</button>
      </div>

      {/* Format selector */}
      <div style={s.row}>
        <span style={s.label}>Format</span>
        <div style={s.formatGroup}>
          {["md", "pdf", "csv"].map((f) => (
            <button
              key={f}
              onClick={() => setFormat(f)}
              style={format === f ? { ...s.formatBtn, ...s.formatBtnActive } : s.formatBtn}
              disabled={status === "loading"}
            >
              {f === "md" ? "Markdown" : f === "pdf" ? "PDF" : "CSV"}
            </button>
          ))}
        </div>

        {/* Page size — only visible for PDF */}
        {format === "pdf" && (
          <div style={s.sizeGroup}>
            {["A4", "A3"].map((sz) => (
              <button
                key={sz}
                onClick={() => setSize(sz)}
                style={size === sz ? { ...s.sizeBtn, ...s.sizeBtnActive } : s.sizeBtn}
                disabled={status === "loading"}
              >
                {sz}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Prompt input */}
      <textarea
        value={prompt}
        onChange={(e) => {
          setPrompt(e.target.value);
          if (status === "done" || status === "error") setStatus("idle");
        }}
        placeholder={
          format === "csv"
            ? "Describe the data table you need — e.g. 'Monthly sales data for a SaaS company with ARR, churn, and NPS columns'"
            : "Describe the document — e.g. 'Technical architecture overview for a real-time event platform using Go and Kubernetes'"
        }
        style={s.textarea}
        rows={3}
        disabled={status === "loading"}
        maxLength={2000}
      />
      <div style={s.charCount}>{prompt.length} / 2000</div>

      {/* Status banners */}
      {status === "done" && (
        <div style={s.successBanner}>
          <span>✓ Download started — <strong>{lastFile?.filename}</strong></span>
          <button onClick={handleDownloadAgain} style={s.inlineLinkBtn}>Download again</button>
          <button onClick={handleReset} style={s.inlineLinkBtn}>New document</button>
        </div>
      )}

      {status === "error" && (
        <div style={s.errorBanner}>
          <span>✕ {errorMsg}</span>
        </div>
      )}

      {/* Generate button */}
      <button
        onClick={handleGenerate}
        disabled={!canGenerate}
        style={canGenerate ? s.generateBtn : { ...s.generateBtn, ...s.generateBtnDisabled }}
      >
        {status === "loading" ? <GeneratingText format={format} /> : `Generate ${format.toUpperCase()}`}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: GeneratingText
// ---------------------------------------------------------------------------

/**
 * GeneratingText
 * Cycles between two status messages while generation is in flight.
 * Keeps the button informative without needing a full typewriter animation.
 */
function GeneratingText({ format }) {
  const label = format === "pdf" ? "PDF" : format.toUpperCase();
  return <span style={{ opacity: 0.85 }}>Generating {label}…</span>;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const s = {
  panel: {
    background: "var(--color-bg-surface)",
    borderBottom: "1px solid var(--color-border)",
    padding: "var(--sp-4) var(--sp-4) var(--sp-3)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-3)",
    flexShrink: 0,
  },

  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  headerTitle: {
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    letterSpacing: "0.01em",
  },
  closeBtn: {
    background: "transparent",
    border: "none",
    color: "var(--color-text-secondary)",
    fontSize: "var(--fs-lg)",
    cursor: "pointer",
    lineHeight: 1,
    padding: "0 var(--sp-1)",
    fontFamily: "var(--font-body)",
  },

  row: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-3)",
    flexWrap: "wrap",
  },
  label: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-secondary)",
    fontWeight: "var(--fw-medium)",
    minWidth: "44px",
  },

  formatGroup: { display: "flex", gap: "var(--sp-2)" },
  formatBtn: {
    padding: "var(--sp-1) var(--sp-3)",
    background: "transparent",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    color: "var(--color-text-secondary)",
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-medium)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    transition: "all var(--transition-fast)",
  },
  formatBtnActive: {
    background: "var(--color-accent)",
    borderColor: "var(--color-accent)",
    color: "#000000",
  },

  sizeGroup: { display: "flex", gap: "var(--sp-2)", marginLeft: "auto" },
  sizeBtn: {
    padding: "var(--sp-1) var(--sp-3)",
    background: "transparent",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    color: "var(--color-text-secondary)",
    fontSize: "var(--fs-xs)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    transition: "all var(--transition-fast)",
  },
  sizeBtnActive: {
    borderColor: "var(--color-text-secondary)",
    color: "var(--color-text-primary)",
  },

  textarea: {
    width: "100%",
    background: "var(--color-bg-input)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-primary)",
    fontSize: "var(--fs-sm)",
    fontFamily: "var(--font-body)",
    padding: "var(--sp-3)",
    resize: "vertical",
    lineHeight: "1.5",
    outline: "none",
    transition: "border-color var(--transition-fast)",
  },
  charCount: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-placeholder)",
    textAlign: "right",
    marginTop: "-var(--sp-2)",
  },

  successBanner: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-4)",
    padding: "var(--sp-2) var(--sp-3)",
    background: "rgba(52, 211, 153, 0.08)",
    border: "1px solid rgba(52, 211, 153, 0.20)",
    borderRadius: "var(--radius-sm)",
    fontSize: "var(--fs-xs)",
    color: "var(--color-success)",
    flexWrap: "wrap",
  },
  errorBanner: {
    padding: "var(--sp-2) var(--sp-3)",
    background: "rgba(248, 113, 113, 0.08)",
    border: "1px solid rgba(248, 113, 113, 0.20)",
    borderRadius: "var(--radius-sm)",
    fontSize: "var(--fs-xs)",
    color: "var(--color-error)",
  },
  inlineLinkBtn: {
    background: "transparent",
    border: "none",
    color: "var(--color-success)",
    fontSize: "var(--fs-xs)",
    cursor: "pointer",
    textDecoration: "underline",
    fontFamily: "var(--font-body)",
    padding: 0,
  },

  generateBtn: {
    alignSelf: "flex-end",
    padding: "var(--sp-2) var(--sp-5)",
    background: "var(--color-accent)",
    border: "none",
    borderRadius: "var(--radius-sm)",
    color: "#000000",
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-bold)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    transition: "opacity var(--transition-fast)",
    minWidth: "140px",
    textAlign: "center",
  },
  generateBtnDisabled: {
    opacity: 0.35,
    cursor: "not-allowed",
  },
};