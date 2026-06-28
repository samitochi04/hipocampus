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

import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Header from "../components/layout/Header.jsx";
import ChatWindow from "../components/chat/ChatWindow.jsx";
import ChatInput from "../components/chat/ChatInput.jsx";
import ChatSidebar from "../components/chat/ChatSidebar.jsx";
import GeneratePanel from "../components/chat/GeneratePanel.jsx";
import VoiceMode    from "../components/chat/VoiceMode.jsx";
import { useChat } from "../hooks/useChat.js";

export default function ChatPage() {
  const { chatId }  = useParams();           // undefined on /chat
  const navigate    = useNavigate();

  // Mobile detection — sidebar is a drawer overlay below 768 px.
  const [isMobile,     setIsMobile]     = useState(() => window.innerWidth < 768);
  const [collapsed,    setCollapsed]    = useState(() => window.innerWidth < 768);
  const [showGenPanel, setShowGenPanel] = useState(false);
  const [voiceMode,    setVoiceMode]    = useState(false);

  useEffect(() => {
    function onResize() {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      // Auto-collapse when resizing into mobile, auto-expand into desktop.
      setCollapsed(mobile);
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

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
    webSearched,
    conflict,
    error,
    sessionId,
    send,
    addVoiceTurn,
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
      <Header />

      <div style={styles.body}>
        {/* Mobile backdrop — dims chat when drawer is open */}
        {isMobile && !collapsed && (
          <div
            style={styles.backdrop}
            onClick={() => setCollapsed(true)}
            aria-hidden="true"
          />
        )}

        <ChatSidebar
          activeChatId={chatId ?? null}
          onChatSelect={handleChatSelect}
          onNewChat={handleNewChat}
          collapsed={collapsed}
          onToggle={() => setCollapsed((c) => !c)}
          isMobile={isMobile}
        />

        {/* Chat column */}
        <div style={styles.chatColumn}>

          {/* Toolbar — sits above the message list */}
          <div style={styles.toolbar}>
            <button
              onClick={() => setShowGenPanel((v) => !v)}
              style={showGenPanel ? { ...styles.toolbarBtn, ...styles.toolbarBtnActive } : styles.toolbarBtn}
              title="Generate a document (MD / PDF / CSV)"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                style={{ flexShrink: 0 }} aria-hidden="true">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
              </svg>
              Document
            </button>

            {/* Voice mode toggle */}
            <button
              onClick={() => setVoiceMode(v => !v)}
              style={voiceMode
                ? { ...styles.toolbarBtn, ...styles.toolbarBtnActive }
                : styles.toolbarBtn}
              title="Voice mode — speak with Hipocampus"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                style={{ marginRight: "5px", verticalAlign: "middle" }} aria-hidden="true">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                <line x1="12" y1="19" x2="12" y2="23"/>
                <line x1="8"  y1="23" x2="16" y2="23"/>
              </svg>
              Voice
            </button>
          </div>

          {/* Generate panel — slides in below toolbar */}
          {showGenPanel && (
            <GeneratePanel onClose={() => setShowGenPanel(false)} />
          )}

          {/* Scrollable message list */}
          <ChatWindow
            messages={messages}
            loading={loading || historyLoading}
            webSearched={webSearched}
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

          {/* Message input / Voice mode */}
          {voiceMode ? (
            <VoiceMode
              sessionId={sessionId}
              onTurn={({ transcription, response, chatId: newChatId }) => {
                // Inject messages directly — no page reload, no navigate.
                addVoiceTurn(transcription, response);
                // If brand-new chat, update URL so sidebar reflects it.
                if (newChatId && !chatId) {
                  navigate(`/chat/${newChatId}`, { replace: true });
                }
              }}
            />
          ) : (
            <ChatInput onSend={send} loading={loading} />
          )}
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
    // dvh = dynamic viewport height — handles iOS browser chrome correctly.
    // Falls back to vh in browsers that don't support dvh.
    height: "100dvh",
    overflow: "hidden",
    background: "var(--color-bg-base)",
  },

  body: {
    display: "flex",
    flexDirection: "row",
    flex: 1,
    marginTop: "var(--header-height)",
    height: "calc(100dvh - var(--header-height))",
    overflow: "hidden",
  },

  toolbar: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-2)",
    padding: "var(--sp-2) var(--sp-4)",
    borderBottom: "1px solid var(--color-border)",
    background: "var(--color-bg-base)",
    flexShrink: 0,
  },
  toolbarBtn: {
    padding: "var(--sp-1) var(--sp-3)",
    background: "transparent",
    borderWidth: "1px",
    borderStyle: "solid",
    borderColor: "var(--color-border)",
    borderRadius: "var(--radius-lg)",
    color: "var(--color-text-secondary)",
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-medium)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    transition: "all var(--transition-fast)",
  },
  toolbarBtnActive: {
    background: "var(--color-accent-subtle)",
    borderColor: "var(--color-accent)",
    color: "var(--color-accent)",
  },

  chatColumn: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    minWidth: 0,
  },

  // Semi-transparent scrim shown behind the mobile sidebar drawer.
  backdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(0, 0, 0, 0.65)",
    zIndex: 199,
    backdropFilter: "blur(1px)",
    WebkitBackdropFilter: "blur(1px)",
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
    color: "var(--color-on-accent)",
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