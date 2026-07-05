/**
 * src/components/chat/ChatInput.jsx
 *
 * Message composition area with document attachment support.
 *
 * Document upload flow:
 *   1. User clicks the paperclip (📎) button → hidden <input type="file"> opens.
 *   2. File is validated client-side (extension, double-extension, size).
 *   3. Valid file is POSTed to /api/v1/upload — send button locks while
 *      processing so the response is ready before the message goes out.
 *   4. Attachment chip appears below the textarea showing filename + char count.
 *   5. On send: document block is prepended to the message —
 *        [DOCUMENT: file.pdf]
 *        {extracted text}
 *        ---
 *        {user message}
 *   6. Attachment is cleared after send. User can attach a new file.
 *
 * Send button is enabled when:
 *   - Not loading a response AND
 *   - Not processing an upload AND
 *   - ( message is non-empty OR a processed attachment is ready )
 *
 * Used by: src/pages/ChatPage.jsx.
 */

import { useRef, useState } from "react";
import { ACCEPTED_FORMATS, uploadDocument, validateFile } from "../../api/upload.js";

const MAX_LENGTH = 8000;

// ---------------------------------------------------------------------------
// ChatInput
// ---------------------------------------------------------------------------

/**
 * ChatInput
 *
 * Parameters:
 *   onSend  (function) — called with the full message string (including any
 *                        prepended document block). Signature: (msg: string) => void.
 *   loading (boolean)  — true while an AI response is in flight.
 *
 * Returns: JSX.Element.
 * Used by: src/pages/ChatPage.jsx.
 */
export default function ChatInput({ onSend, loading }) {
  const [value,      setValue]      = useState("");
  const [attachment, setAttachment] = useState(null);
  // attachment = null
  //   | { file, filename, status: "processing" }
  //   | { file, filename, extractedText, charCount, format, status: "ready" }
  //   | { file, filename, error, status: "error" }

  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  // ── Send ──────────────────────────────────────────────────────────────────

  function handleSend() {
    const trimmed = value.trim();
    const hasAttachment = attachment?.status === "ready";
    if ((!trimmed && !hasAttachment) || loading || attachment?.status === "processing") return;

    let fullMessage;
    if (hasAttachment) {
      const docBlock = `[DOCUMENT: ${attachment.filename}]\n${attachment.extractedText}`;
      fullMessage = trimmed ? `${docBlock}\n---\n${trimmed}` : docBlock;
    } else {
      fullMessage = trimmed;
    }

    onSend(fullMessage.trim());
    setValue("");
    setAttachment(null);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  function handleChange(e) {
    const v = e.target.value;
    if (v.length > MAX_LENGTH) return;
    setValue(v);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  // ── File handling ─────────────────────────────────────────────────────────

  function handleAttachClick() {
    fileInputRef.current?.click();
  }

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    e.target.value = "";   // reset so same file can be re-selected after error
    if (!file) return;

    // Client-side validation
    const validation = validateFile(file);
    if (!validation.valid) {
      setAttachment({ file, filename: file.name, error: validation.error, status: "error" });
      return;
    }

    // Start upload
    setAttachment({ file, filename: file.name, status: "processing" });

    try {
      const result = await uploadDocument(file);
      setAttachment({
        file,
        filename:      result.filename,
        extractedText: result.extracted_text,
        charCount:     result.char_count,
        format:        result.format,
        status:        "ready",
      });
    } catch (err) {
      setAttachment({
        file,
        filename: file.name,
        error:    err.message ?? "Upload failed. Please try again.",
        status:   "error",
      });
    }
  }

  function clearAttachment() {
    setAttachment(null);
  }

  // ── Derived state ─────────────────────────────────────────────────────────

  const isProcessing = attachment?.status === "processing";
  const canSend      = !loading
    && !isProcessing
    && (value.trim().length > 0 || attachment?.status === "ready");
  const charsLeft    = MAX_LENGTH - value.length;
  const nearLimit    = charsLeft < 200;
  const acceptStr    = Object.keys(ACCEPTED_FORMATS).join(",");

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={s.wrapper}>
      {/* Attachment chip — shown when a file is selected */}
      {attachment && (
        <AttachmentChip
          attachment={attachment}
          onClear={clearAttachment}
        />
      )}

      {/* Input row */}
      <div style={s.inputRow}>
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept={acceptStr}
          onChange={handleFileChange}
          style={{ display: "none" }}
          aria-hidden="true"
        />

        {/* Attach button */}
        <button
          onClick={handleAttachClick}
          disabled={loading || isProcessing}
          style={
            attachment?.status === "ready"
              ? { ...s.attachBtn, ...s.attachBtnActive }
              : s.attachBtn
          }
          aria-label="Attach document (PDF, CSV, or Markdown)"
          title="Attach document (.pdf, .csv, .md · max 10 MB)"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            aria-hidden="true">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
          </svg>
        </button>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={attachment ? "Add a message (optional)…" : "Message Hipocampus…"}
          disabled={loading}
          rows={1}
          style={loading ? { ...s.textarea, opacity: 0.6 } : s.textarea}
          aria-label="Message input"
        />

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!canSend}
          style={canSend ? s.sendBtn : { ...s.sendBtn, ...s.sendBtnDisabled }}
          aria-label="Send message"
        >
          {loading ? (
            <span style={s.sendSpinner} aria-hidden="true" />
          ) : (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M8 2L14 8L8 14M14 8H2" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>
      </div>

      {/* Footer */}
      <div style={s.footer}>
        <span style={s.hint}>
          Enter to send · Shift+Enter for newline
          {" · "}
          <span style={s.hintAccent}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
              style={{ verticalAlign: "middle", marginRight: "2px" }} aria-hidden="true">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
            </svg>
            .pdf .csv .md
          </span>
        </span>
        {nearLimit && (
          <span style={{ ...s.charCount,
            color: charsLeft < 50 ? "var(--color-error)" : "var(--color-warning)" }}>
            {charsLeft} left
          </span>
        )}
      </div>

      <style>{`
        @keyframes spinnerPulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50%       { opacity: 1;   transform: scale(1.1); }
        }
        @keyframes attachSpin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: AttachmentChip
// ---------------------------------------------------------------------------

/**
 * AttachmentChip
 * Shows the attachment status above the input row.
 *
 *   processing → grey chip with spinning indicator, send locked
 *   ready      → white chip with filename + char count, send unlocked
 *   error      → red chip with error message, × to dismiss
 */
function AttachmentChip({ attachment, onClear }) {
  const { filename, status, charCount, format, error } = attachment;

  const chipStyle = {
    ...s.chip,
    ...(status === "ready"  ? s.chipReady  : {}),
    ...(status === "error"  ? s.chipError  : {}),
    ...(status === "processing" ? s.chipProcessing : {}),
  };

  return (
    <div style={chipStyle}>
      {/* Icon / spinner */}
      {status === "processing" ? (
        <span style={s.chipSpinner} aria-hidden="true" />
      ) : status === "ready" ? (
        <span aria-hidden="true">
          {format === "pdf" ? (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>
              </svg>
            ) : format === "csv" ? (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/>
                <line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/>
              </svg>
            ) : (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
              </svg>
            )}
        </span>
      ) : (
        <span aria-hidden="true">⚠</span>
      )}

      {/* Label */}
      <span style={s.chipLabel}>
        {status === "processing" && `Processing ${filename}…`}
        {status === "ready"      && `${filename} · ${charCount.toLocaleString()} chars`}
        {status === "error"      && error}
      </span>

      {/* Dismiss */}
      {status !== "processing" && (
        <button onClick={onClear} style={s.chipClose} aria-label="Remove attachment">×</button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const s = {
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
    gap: "var(--sp-2)",
  },

  attachBtn: {
    flexShrink: 0,
    width: "36px",
    height: "44px",
    background: "transparent",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    color: "var(--color-text-secondary)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "1rem",
    transition: "border-color var(--transition-fast)",
  },
  attachBtnActive: {
    borderColor: "var(--color-accent)",
    background: "var(--color-accent-subtle)",
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
    boxSizing: "border-box",
  },

  sendBtn: {
    flexShrink: 0,
    width: "44px",
    height: "44px",
    borderRadius: "var(--radius-md)",
    background: "var(--color-accent)",
    color: "var(--color-on-accent)",
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
  hintAccent: {
    color: "var(--color-text-secondary)",
    fontWeight: "var(--fw-medium)",
  },
  charCount: {
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-medium)",
    transition: "color var(--transition-fast)",
  },

  // ── Attachment chip ────────────────────────────────────────────────────
  chip: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-2)",
    padding: "var(--sp-2) var(--sp-3)",
    borderRadius: "var(--radius-sm)",
    fontSize: "var(--fs-xs)",
    border: "1px solid var(--color-border)",
    background: "var(--color-bg-input)",
    color: "var(--color-text-secondary)",
  },
  chipReady: {
    background: "rgba(255,255,255,0.04)",
    borderColor: "var(--color-accent)",
    color: "var(--color-text-primary)",
  },
  chipProcessing: {
    background: "rgba(255,255,255,0.02)",
    borderColor: "var(--color-border)",
    color: "var(--color-text-secondary)",
  },
  chipError: {
    background: "rgba(248,113,113,0.06)",
    borderColor: "rgba(248,113,113,0.3)",
    color: "var(--color-error)",
  },
  chipSpinner: {
    display: "inline-block",
    width: "12px",
    height: "12px",
    borderRadius: "50%",
    border: "2px solid var(--color-border)",
    borderTopColor: "var(--color-text-secondary)",
    animation: "attachSpin 0.7s linear infinite",
    flexShrink: 0,
  },
  chipLabel: {
    flex: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  chipClose: {
    background: "transparent",
    border: "none",
    color: "inherit",
    fontSize: "1rem",
    cursor: "pointer",
    lineHeight: 1,
    padding: "0 var(--sp-1)",
    flexShrink: 0,
    fontFamily: "var(--font-body)",
  },
};