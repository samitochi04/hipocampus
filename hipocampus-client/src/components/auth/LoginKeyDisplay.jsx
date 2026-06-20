/**
 * src/components/auth/LoginKeyDisplay.jsx
 *
 * Shows the plaintext login key to the user exactly once, immediately after
 * registration. The user cannot proceed to the chat until they click
 * "I've saved my key" — this is the confirmation gate.
 *
 * Security intent:
 *   The login key is never stored on the server. This is the only moment
 *   it will ever be shown. The confirmation requirement and the copy button
 *   reduce the chance of accidental dismissal before the key is saved.
 *
 * Used by: src/pages/RegisterPage.jsx — rendered after RegisterForm succeeds.
 */

import { useState } from "react";

/**
 * LoginKeyDisplay
 * Renders the key display panel with a copy-to-clipboard button and a
 * confirmation checkbox. Calls onConfirmed() when the user explicitly
 * acknowledges they have saved the key.
 *
 * Parameters:
 *   loginKey    (string)   — the plaintext login key returned by the backend.
 *                            Displayed verbatim in a monospace box.
 *   onConfirmed (function) — called with no arguments when the user clicks
 *                            the "I've saved my key" button. RegisterPage uses
 *                            this to navigate to /chat.
 *
 * Returns: JSX.Element.
 * Used by: src/pages/RegisterPage.jsx.
 */
export default function LoginKeyDisplay({ loginKey, onConfirmed }) {
  /**
   * copied state
   * Tracks whether the user has clicked the copy button. Shows a "Copied!"
   * confirmation for 2 seconds then reverts to "Copy".
   */
  const [copied, setCopied] = useState(false);

  /**
   * confirmed state
   * Tracks whether the user has checked the "I've saved my key" checkbox.
   * The proceed button is disabled until this is true.
   */
  const [confirmed, setConfirmed] = useState(false);

  /**
   * handleCopy
   * Writes the login key to the clipboard and shows a brief "Copied!" state.
   * Falls back gracefully if the Clipboard API is unavailable (e.g. non-HTTPS
   * in some environments).
   *
   * Parameters: none.
   * Returns: void (async).
   * Used by: the copy button's onClick handler.
   */
  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(loginKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API unavailable — the user can still manually select the key text.
    }
  }

  return (
    <div style={styles.container}>
      {/* ── Warning banner ───────────────────────────────────────────────── */}
      <div style={styles.warningBanner} role="alert">
        <span style={styles.warningIcon} aria-hidden="true">⚠</span>
        <span>
          <strong>Save this key now.</strong> It cannot be shown again and
          cannot be recovered. Treat it like a password.
        </span>
      </div>

      {/* ── Heading ──────────────────────────────────────────────────────── */}
      <h2 style={styles.heading}>Your login key</h2>
      <p style={styles.subheading}>
        Use this key every time you log in. Copy it to a password manager,
        notes app, or anywhere you keep important credentials.
      </p>

      {/* ── Key display ──────────────────────────────────────────────────── */}
      <div style={styles.keyWrapper}>
        {/*
          The key is displayed in a <code> element for semantic correctness
          and the monospace "mono" class from index.css for readability.
          `user-select: all` lets a single click select the entire key.
        */}
        <code
          style={styles.keyText}
          title="Click to select all"
          onClick={(e) => {
            const range = document.createRange();
            range.selectNodeContents(e.currentTarget);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
          }}
        >
          {loginKey}
        </code>

        {/* Copy button — sits in the top-right corner of the key box */}
        <button
          onClick={handleCopy}
          style={copied ? { ...styles.copyBtn, ...styles.copyBtnCopied } : styles.copyBtn}
          aria-label="Copy login key to clipboard"
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>

      {/* ── Confirmation checkbox ─────────────────────────────────────────── */}
      <label style={styles.checkboxLabel}>
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
          style={styles.checkbox}
        />
        <span>
          I've saved my login key in a safe place and understand it cannot be
          recovered.
        </span>
      </label>

      {/* ── Proceed button ────────────────────────────────────────────────── */}
      <button
        onClick={onConfirmed}
        disabled={!confirmed}
        style={
          !confirmed
            ? { ...styles.proceedBtn, opacity: 0.4, cursor: "not-allowed" }
            : styles.proceedBtn
        }
        aria-disabled={!confirmed}
      >
        Continue to chat →
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-5)",
  },

  warningBanner: {
    display: "flex",
    alignItems: "flex-start",
    gap: "var(--sp-3)",
    padding: "var(--sp-3) var(--sp-4)",
    background: "rgba(251, 191, 36, 0.08)",
    border: "1px solid rgba(251, 191, 36, 0.3)",
    borderRadius: "var(--radius-sm)",
    fontSize: "var(--fs-sm)",
    color: "var(--color-warning)",
    lineHeight: "1.5",
  },

  warningIcon: {
    fontSize: "var(--fs-md)",
    flexShrink: 0,
    marginTop: "1px",
  },

  heading: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-lg)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    margin: 0,
  },

  subheading: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.6",
    margin: 0,
    marginTop: "calc(-1 * var(--sp-3))",
  },

  keyWrapper: {
    position: "relative",
    background: "var(--color-bg-input)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--sp-4)",
    paddingRight: "5rem", // make room for the copy button
  },

  keyText: {
    display: "block",
    fontFamily: "'Fira Code', 'Cascadia Code', 'Consolas', monospace",
    fontSize: "var(--fs-sm)",
    color: "var(--color-accent)",
    lineHeight: "1.6",
    wordBreak: "break-all",
    cursor: "text",
    userSelect: "all",
  },

  copyBtn: {
    position: "absolute",
    top: "var(--sp-3)",
    right: "var(--sp-3)",
    padding: "var(--sp-1) var(--sp-3)",
    background: "var(--color-bg-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-secondary)",
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-medium)",
    cursor: "pointer",
    transition: "border-color var(--transition-fast), color var(--transition-fast)",
    fontFamily: "var(--font-body)",
  },

  copyBtnCopied: {
    color: "var(--color-accent)",
    borderColor: "var(--color-accent)",
  },

  checkboxLabel: {
    display: "flex",
    alignItems: "flex-start",
    gap: "var(--sp-3)",
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.5",
    cursor: "pointer",
  },

  checkbox: {
    width: "16px",
    height: "16px",
    flexShrink: 0,
    marginTop: "2px",
    accentColor: "var(--color-accent)",
    cursor: "pointer",
  },

  proceedBtn: {
    width: "100%",
    padding: "var(--sp-3) var(--sp-4)",
    background: "var(--color-accent)",
    color: "#0D0F1A",
    border: "none",
    borderRadius: "var(--radius-sm)",
    fontSize: "var(--fs-base)",
    fontWeight: "var(--fw-bold)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    transition: "background var(--transition-fast), box-shadow var(--transition-fast)",
  },
};