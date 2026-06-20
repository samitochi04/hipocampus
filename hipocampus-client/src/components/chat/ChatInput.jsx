/**
 * src/components/chat/ChatInput.jsx
 *
 * The message composition area fixed to the bottom of the chat page.
 * Renders an auto-growing textarea and a send button. Handles keyboard
 * shortcuts (Enter to send, Shift+Enter for a newline) and disables
 * all input while a message is in flight.
 *
 * Used by: src/pages/ChatPage.jsx.
 */

import { useRef, useState } from "react";

/** Maximum character count enforced client-side to match the backend schema. */
const MAX_LENGTH = 8000;

/**
 * ChatInput
 * Renders the message composition area.
 *
 * Parameters:
 *   onSend  (function) — called with the trimmed message string when the
 *                        user presses Enter or clicks Send.
 *                        Signature: onSend(message: string) => void.
 *                        The actual send logic lives in useChat.js — this
 *                        component only owns the text field state.
 *   loading (boolean)  — when true, the textarea and button are disabled
 *                        and the button shows "Waiting…".
 *
 * Returns: JSX.Element — a fixed-position input area.
 * Used by: src/pages/ChatPage.jsx.
 */
export default function ChatInput({ onSend, loading }) {
  const [value, setValue] = useState("");
  const textareaRef = useRef(null);

  /**
   * handleSend
   * Trims the current value, calls onSend if non-empty, and resets the field.
   * Also resets the textarea height to its single-line default after sending.
   *
   * Parameters: none.
   * Returns: void.
   * Used by: the send button onClick and the Enter key handler below.
   */
  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    onSend(trimmed);
    setValue("");
    // Reset height after send so the textarea returns to one line.
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  /**
   * handleKeyDown
   * Sends the message on Enter (without Shift). Shift+Enter inserts a newline
   * as the user expects from multi-line editing tools.
   *
   * Parameters:
   *   e (KeyboardEvent) — the keydown event from the textarea.
   *
   * Returns: void.
   * Used by: the textarea's onKeyDown handler.
   */
  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault(); // prevent the newline from being inserted
      handleSend();
    }
  }

  /**
   * handleChange
   * Updates the value state and auto-grows the textarea height to fit the
   * content. The textarea grows up to 160px then scrolls internally.
   *
   * Parameters:
   *   e (ChangeEvent) — the change event from the textarea.
   *
   * Returns: void.
   * Used by: the textarea's onChange handler.
   */
  function handleChange(e) {
    const newValue = e.target.value;
    if (newValue.length > MAX_LENGTH) return; // hard cap
    setValue(newValue);

    // Auto-grow: reset to auto first so shrinking works correctly.
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  const canSend = value.trim().length > 0 && !loading;
  const charsLeft = MAX_LENGTH - value.length;
  const nearLimit = charsLeft < 200;

  return (
    <div style={styles.wrapper}>
      <div style={styles.inputRow}>
        {/* ── Textarea ──────────────────────────────────────────────────── */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="Message Hipocampus…"
          disabled={loading}
          rows={1}
          style={loading ? { ...styles.textarea, opacity: 0.6 } : styles.textarea}
          aria-label="Message input"
          aria-describedby={nearLimit ? "char-count" : undefined}
        />

        {/* ── Send button ────────────────────────────────────────────────── */}
        <button
          onClick={handleSend}
          disabled={!canSend}
          style={canSend ? styles.sendBtn : { ...styles.sendBtn, ...styles.sendBtnDisabled }}
          aria-label="Send message"
        >
          {loading ? (
            // Spinner dot while loading
            <span style={styles.sendSpinner} aria-hidden="true" />
          ) : (
            // Arrow icon when ready
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M8 2L14 8L8 14M14 8H2"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </button>
      </div>

      {/* ── Footer: shortcut hint + character count ────────────────────── */}
      <div style={styles.footer}>
        <span style={styles.hint}>
          Enter to send &nbsp;·&nbsp; Shift+Enter for newline
        </span>
        {nearLimit && (
          <span
            id="char-count"
            style={{
              ...styles.charCount,
              color: charsLeft < 50 ? "var(--color-error)" : "var(--color-warning)",
            }}
            aria-live="polite"
          >
            {charsLeft} left
          </span>
        )}
      </div>

      {/* Spinner keyframe — only used in the send button */}
      <style>{`
        @keyframes spinnerPulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50%       { opacity: 1;   transform: scale(1.1); }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  wrapper: {
    borderTop: "1px solid var(--color-border)",
    background: "var(--color-bg-surface)",
    padding: "var(--sp-3) var(--sp-4) var(--sp-4)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-2)",
  },

  inputRow: {
    display: "flex",
    alignItems: "flex-end",
    gap: "var(--sp-3)",
  },

  textarea: {
    flex: 1,
    resize: "none",
    background: "var(--color-bg-input)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    color: "var(--color-text-primary)",
    fontSize: "var(--fs-base)",
    fontFamily: "var(--font-body)",
    lineHeight: "1.5",
    padding: "var(--sp-3) var(--sp-4)",
    outline: "none",
    transition: "border-color var(--transition-fast)",
    minHeight: "44px",
    maxHeight: "160px",
    overflowY: "auto",
    // Prevent layout shift as the textarea grows
    boxSizing: "border-box",
  },

  sendBtn: {
    flexShrink: 0,
    width: "44px",
    height: "44px",
    borderRadius: "var(--radius-md)",
    background: "var(--color-accent)",
    color: "#0D0F1A",
    border: "none",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "background var(--transition-fast), box-shadow var(--transition-fast)",
    boxShadow: "var(--shadow-accent-glow)",
  },

  sendBtnDisabled: {
    background: "var(--color-bg-input)",
    color: "var(--color-text-placeholder)",
    cursor: "not-allowed",
    boxShadow: "none",
  },

  sendSpinner: {
    display: "inline-block",
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: "currentColor",
    animation: "spinnerPulse 1s ease-in-out infinite",
  },

  footer: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    minHeight: "16px",
  },

  hint: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-placeholder)",
  },

  charCount: {
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-medium)",
    transition: "color var(--transition-fast)",
  },
};