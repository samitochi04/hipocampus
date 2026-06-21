/**
 * src/pages/ChatPage.jsx
 *
 * The main chat interface rendered at /chat (protected route).
 * Composes Header, ChatWindow, and ChatInput into a full-viewport layout.
 * Also renders inline banners for memory conflicts (409) and general errors.
 *
 * Layout:
 *   Fixed header (--header-height, 56px)
 *   Scrollable chat window (fills remaining height)
 *   Optional conflict / error banner (above input, inline)
 *   Fixed input area (--input-area-height, 80px)
 *
 * All state and send logic lives in useChat() — this page is a pure composer.
 *
 * Used by: src/App.jsx (protected route, /chat).
 */

import { useNavigate } from "react-router-dom";
import Header from "../components/layout/Header.jsx";
import ChatWindow from "../components/chat/ChatWindow.jsx";
import ChatInput from "../components/chat/ChatInput.jsx";
import { useChat } from "../hooks/useChat.js";

/**
 * ChatPage
 * Renders the full chat UI.
 *
 * Parameters: none — all data comes from useChat() and useAuth() (via Header).
 * Returns: JSX.Element.
 * Used by: src/App.jsx.
 */
export default function ChatPage() {
  const { messages, loading, conflict, error, send, dismissConflict, dismissError } =
    useChat();
  const navigate = useNavigate();

  return (
    <div style={styles.page}>
      {/* ── Fixed header ──────────────────────────────────────────────────── */}
      <Header />

      {/* ── Scrollable chat area ──────────────────────────────────────────── */}
      <main style={styles.main}>
        <div style={styles.chatColumn}>
          <ChatWindow messages={messages} loading={loading} />

          {/* ── Conflict banner ─────────────────────────────────────────── */}
          {conflict && (
            <ConflictBanner
              detail={conflict.detail}
              onDismiss={dismissConflict}
              onGoToMemory={() => {
                dismissConflict();
                navigate("/memory");
              }}
            />
          )}

          {/* ── Error banner ────────────────────────────────────────────── */}
          {error && !conflict && (
            <ErrorBanner message={error} onDismiss={dismissError} />
          )}

          {/* ── Input area ──────────────────────────────────────────────── */}
          <ChatInput onSend={send} loading={loading} />
        </div>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: ConflictBanner
// ---------------------------------------------------------------------------

/**
 * ConflictBanner
 * Shown when the backend returns 409 — the user's message contradicted a
 * stored high-confidence preference. Explains what happened and offers two
 * actions: dismiss (retry the message) or navigate to /memory to resolve.
 *
 * Parameters:
 *   detail       (string)   — the conflict detail from the ApiError message.
 *   onDismiss    (function) — clears the conflict state so the user can retry.
 *   onGoToMemory (function) — navigates to /memory to resolve the conflict.
 *
 * Returns: JSX.Element.
 * Used by: ChatPage.
 */
function ConflictBanner({ detail, onDismiss, onGoToMemory }) {
  return (
    <div style={bannerStyles.conflict} role="alert">
      <div style={bannerStyles.content}>
        <span style={bannerStyles.conflictIcon} aria-hidden="true">⚡</span>
        <div style={bannerStyles.text}>
          <strong style={bannerStyles.title}>Memory conflict detected</strong>
          <p style={bannerStyles.detail}>{detail}</p>
        </div>
      </div>
      <div style={bannerStyles.actions}>
        <button onClick={onGoToMemory} style={bannerStyles.primaryAction}>
          Resolve in Memory →
        </button>
        <button onClick={onDismiss} style={bannerStyles.dismissAction}>
          Dismiss
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: ErrorBanner
// ---------------------------------------------------------------------------

/**
 * ErrorBanner
 * Shown for non-conflict errors (e.g. 503 Qwen unavailable, network error).
 * Displays the error message and a dismiss button.
 *
 * Parameters:
 *   message   (string)   — the error message string from the ApiError.
 *   onDismiss (function) — clears the error state.
 *
 * Returns: JSX.Element.
 * Used by: ChatPage.
 */
function ErrorBanner({ message, onDismiss }) {
  return (
    <div style={bannerStyles.error} role="alert">
      <div style={bannerStyles.content}>
        <span style={bannerStyles.errorIcon} aria-hidden="true">✕</span>
        <p style={{ ...bannerStyles.detail, margin: 0 }}>{message}</p>
      </div>
      <button onClick={onDismiss} style={bannerStyles.dismissAction}>
        Dismiss
      </button>
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
    height: "100vh",
    overflow: "hidden",
    background: "var(--color-bg-base)",
  },

  main: {
    flex: 1,
    overflow: "hidden",
    marginTop: "var(--header-height)",
    display: "flex",
    justifyContent: "center",
  },

  chatColumn: {
    width: "100%",
    maxWidth: "var(--chat-max-width)",
    display: "flex",
    flexDirection: "column",
    height: "100%",
    overflow: "hidden",
  },
};

const bannerStyles = {
  conflict: {
    margin: "0 var(--sp-4)",
    padding: "var(--sp-3) var(--sp-4)",
    background: "rgba(126, 232, 162, 0.06)",
    border: "1px solid rgba(126, 232, 162, 0.2)",
    borderRadius: "var(--radius-sm)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-3)",
  },

  error: {
    margin: "0 var(--sp-4)",
    padding: "var(--sp-3) var(--sp-4)",
    background: "rgba(248, 113, 113, 0.06)",
    border: "1px solid rgba(248, 113, 113, 0.2)",
    borderRadius: "var(--radius-sm)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "var(--sp-4)",
  },

  content: {
    display: "flex",
    alignItems: "flex-start",
    gap: "var(--sp-3)",
  },

  conflictIcon: {
    fontSize: "var(--fs-md)",
    flexShrink: 0,
  },

  errorIcon: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-error)",
    flexShrink: 0,
  },

  text: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-1)",
  },

  title: {
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
  },

  detail: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.5",
    margin: 0,
  },

  actions: {
    display: "flex",
    gap: "var(--sp-3)",
    alignItems: "center",
  },

  primaryAction: {
    padding: "var(--sp-1) var(--sp-3)",
    background: "var(--color-accent)",
    border: "none",
    borderRadius: "var(--radius-sm)",
    color: "#0D0F1A",
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-bold)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
  },

  dismissAction: {
    padding: "var(--sp-1) var(--sp-3)",
    background: "transparent",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-secondary)",
    fontSize: "var(--fs-sm)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
  },
};