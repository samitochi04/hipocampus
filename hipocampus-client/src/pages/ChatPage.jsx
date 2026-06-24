/**
 * src/pages/ChatPage.jsx
 *
 * The main chat interface. Renders at both /chat and /chat/:chatId.
 *
 * Layout:
 *   Fixed header (full width)
 *   Body row below header:
 *     ├── ChatSidebar (collapsible, shows conversation list)
 *     └── Chat column (flex: 1)
 *           ├── ChatWindow (scrollable, fills remaining height)
 *           ├── ConflictBanner (conditional, above input)
 *           ├── ErrorBanner    (conditional, above input)
 *           └── ChatInput (fixed at bottom of column)
 *
 * Route variants:
 *   /chat           — no active chat; first send auto-creates one and
 *                     navigates to /chat/:chatId via onChatCreated.
 *   /chat/:chatId   — loads the permanent message archive for that chat.
 *
 * Used by: src/App.jsx (both routes).
 */

import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Header from "../components/layout/Header.jsx";
import ChatWindow from "../components/chat/ChatWindow.jsx";
import ChatInput from "../components/chat/ChatInput.jsx";
import ChatSidebar from "../components/chat/ChatSidebar.jsx";
import { useChat } from "../hooks/useChat.js";

export default function ChatPage() {
  const { chatId }  = useParams();           // undefined on /chat
  const navigate    = useNavigate();
  const [collapsed, setCollapsed] = useState(false);

  /**
   * handleChatCreated
   * Called by useChat after the first turn of a new conversation.
   * Navigates to /chat/:chatId so the URL reflects the active chat and the
   * browser back button works correctly. replace:true removes the bare /chat
   * entry from the history stack since it no longer represents a distinct page.
   */
  const handleChatCreated = useCallback((newChatId) => {
    navigate(`/chat/${newChatId}`, { replace: true });
  }, [navigate]);

  const {
    messages,
    historyLoading,
    loading,
    conflict,
    error,
    send,
    dismissConflict,
    dismissError,
  } = useChat({
    chatId:        chatId ?? null,
    onChatCreated: handleChatCreated,
  });

  /**
   * handleChatSelect
   * Called by ChatSidebar when the user clicks a conversation.
   * Simply navigates — useChat reacts to the chatId change via useEffect.
   */
  function handleChatSelect(chat) {
    navigate(`/chat/${chat.id}`);
  }

  /**
   * handleNewChat
   * Called by ChatSidebar after POST /chats succeeds.
   * Navigates to the new chat URL; useChat loads an empty archive.
   */
  function handleNewChat(chat) {
    navigate(`/chat/${chat.id}`);
  }

  return (
    <div style={styles.page}>
      {/* ── Fixed header ─────────────────────────────────────────────── */}
      <Header />

      {/* ── Body row (sidebar + chat column) ─────────────────────────── */}
      <div style={styles.body}>

        {/* Sidebar */}
        <ChatSidebar
          activeChatId={chatId ?? null}
          onChatSelect={handleChatSelect}
          onNewChat={handleNewChat}
          collapsed={collapsed}
          onToggle={() => setCollapsed((c) => !c)}
        />

        {/* Chat column */}
        <div style={styles.chatColumn}>

          {/* Scrollable message list */}
          <ChatWindow
            messages={messages}
            loading={loading || historyLoading}
          />

          {/* Conflict banner (409) */}
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

          {/* Generic error banner */}
          {error && !conflict && (
            <ErrorBanner message={error} onDismiss={dismissError} />
          )}

          {/* Message input */}
          <ChatInput onSend={send} loading={loading} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: ConflictBanner
// ---------------------------------------------------------------------------

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

  // Full-height row below the fixed header.
  body: {
    display: "flex",
    flexDirection: "row",
    flex: 1,
    marginTop: "var(--header-height)",
    height: "calc(100vh - var(--header-height))",
    overflow: "hidden",
  },

  // Right-hand chat area: takes remaining width, stacks vertically.
  chatColumn: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    minWidth: 0, // Prevent flex child overflow on narrow screens.
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
    flexShrink: 0,
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
    flexShrink: 0,
  },
  content: {
    display: "flex",
    alignItems: "flex-start",
    gap: "var(--sp-3)",
  },
  conflictIcon: { fontSize: "var(--fs-md)", flexShrink: 0 },
  errorIcon:    { fontSize: "var(--fs-sm)", color: "var(--color-error)", flexShrink: 0 },
  text:  { display: "flex", flexDirection: "column", gap: "var(--sp-1)" },
  title: { fontSize: "var(--fs-sm)", fontWeight: "var(--fw-bold)", color: "var(--color-text-primary)" },
  detail: { fontSize: "var(--fs-sm)", color: "var(--color-text-secondary)", lineHeight: "1.5", margin: 0 },
  actions: { display: "flex", gap: "var(--sp-3)", alignItems: "center" },
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