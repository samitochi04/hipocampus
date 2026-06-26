/**
 * src/components/chat/ChatSidebar.jsx
 *
 * The left-hand sidebar showing the user's conversation history.
 * Sits alongside ChatWindow inside ChatPage.
 *
 * Responsibilities:
 *   - Fetch and display the list of chats (most recent first).
 *   - "New Chat" button — calls createChat() and notifies the parent.
 *   - Highlight the active chat.
 *   - Show relative timestamps and message counts.
 *   - Inline rename on double-click.
 *   - Collapse to an icon-only rail on narrow viewports.
 *
 * Used by: src/pages/ChatPage.jsx.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { createChat, listChats, renameChat } from "../../api/chats.js";

/** Width of the expanded sidebar. */
const SIDEBAR_WIDTH = "248px";

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * ChatSidebar
 * Renders the conversation list and New Chat button.
 *
 * Parameters:
 *   activeChatId  (string | null)   — UUID of the currently open chat.
 *                                     Used to highlight the active item.
 *   onChatSelect  (function)        — called with { id, session_id } when the
 *                                     user clicks a chat. ChatPage uses this to
 *                                     switch the active conversation.
 *   onNewChat     (function)        — called with the newly created chat object
 *                                     { id, session_id, title } after POST /chats.
 *   collapsed     (boolean)         — when true the sidebar shrinks to 48px
 *                                     (icon rail). Toggled by the parent.
 *   onToggle      (function)        — called when the toggle button is clicked.
 *
 * Returns: JSX.Element.
 * Used by: src/pages/ChatPage.jsx.
 */
export default function ChatSidebar({
  activeChatId,
  onChatSelect,
  onNewChat,
  collapsed = false,
  onToggle,
  isMobile = false,
}) {
  const [chats, setChats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creatingChat, setCreatingChat] = useState(false);

  /**
   * editingId — UUID of the chat whose title is currently being edited inline.
   * editDraft  — controlled value of the inline rename input.
   */
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState("");
  const editInputRef = useRef(null);

  // ── Load chat list ─────────────────────────────────────────────────────

  /**
   * loadChats
   * Fetches the user's chat list and stores it in state.
   * Called on mount and after creating a new chat.
   *
   * Parameters: none.
   * Returns: void (async).
   * Used by: useEffect on mount + after handleNewChat.
   */
  const loadChats = useCallback(async () => {
    try {
      const data = await listChats();
      setChats(data ?? []);
    } catch {
      // Non-critical — sidebar failing shouldn't break the chat.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadChats();
  }, [loadChats]);

  useEffect(() => {
    if (!activeChatId) return;
    loadChats();
    const id = setTimeout(loadChats, 5000);
    return () => clearTimeout(id);
  }, [activeChatId, loadChats]);

  // ── New chat ──────────────────────────────────────────────────────────

  /**
   * handleNewChat
   * Creates a new Chat row via POST /api/v1/chats and notifies ChatPage.
   * The list is refreshed after creation so the new entry appears.
   *
   * Parameters: none.
   * Returns: void (async).
   * Used by: the "New Chat" button onClick.
   */
  async function handleNewChat() {
    if (creatingChat) return;
    setCreatingChat(true);
    try {
      const newChat = await createChat();
      await loadChats();
      onNewChat(newChat);
      if (isMobile) onToggle(); // close drawer after action
    } catch {
    } finally {
      setCreatingChat(false);
    }
  }

  // ── Inline rename ─────────────────────────────────────────────────────

  /**
   * startEditing
   * Enters rename mode for a chat. Seeds the input with the current title.
   *
   * Parameters:
   *   e      (MouseEvent) — the double-click event; stops propagation to
   *                         prevent the chat from being selected simultaneously.
   *   chat   (object)     — the ChatListItem being renamed.
   *
   * Returns: void.
   * Used by: each chat row's onDoubleClick handler.
   */
  function startEditing(e, chat) {
    e.stopPropagation();
    setEditingId(chat.id);
    setEditDraft(chat.title ?? "");
    // Focus the input after React renders it.
    setTimeout(() => editInputRef.current?.focus(), 0);
  }

  /**
   * commitRename
   * Submits the new title to the backend and updates local state.
   * Exits edit mode regardless of success or failure.
   *
   * Parameters: none.
   * Returns: void (async).
   * Used by: the rename input's onBlur and onKeyDown (Enter) handlers.
   */
  async function commitRename() {
    if (!editingId) return;
    const trimmed = editDraft.trim();
    const originalChat = chats.find((c) => c.id === editingId);
    setEditingId(null);

    if (!trimmed || trimmed === originalChat?.title) return;

    try {
      const updated = await renameChat(editingId, trimmed);
      setChats((prev) =>
        prev.map((c) => (c.id === editingId ? { ...c, title: updated.title } : c))
      );
    } catch {
      // Silently revert — the original title stays in state.
    }
  }

  /**
   * handleRenameKey
   * Commits on Enter, cancels on Escape.
   *
   * Parameters:
   *   e (KeyboardEvent) — keydown event from the rename input.
   *
   * Returns: void.
   * Used by: the rename input's onKeyDown handler.
   */
  function handleRenameKey(e) {
    if (e.key === "Enter") { e.preventDefault(); commitRename(); }
    if (e.key === "Escape") { setEditingId(null); }
  }

  // ── Render ────────────────────────────────────────────────────────────

  // On mobile the sidebar is a fixed full-height drawer that slides in from
  // the left. `collapsed` means hidden (width 0). On desktop it's the normal
  // inline collapsible rail (48px narrow / 248px expanded).
  const sidebarStyle = isMobile
    ? {
        ...styles.sidebar,
        position: "fixed",
        top: 0,
        left: 0,
        height: "100vh",
        zIndex: 200,
        width: collapsed ? "0" : "280px",
        minWidth: 0,
        overflow: "hidden",
        transition: "width 250ms cubic-bezier(0.4, 0, 0.2, 1)",
        boxShadow: collapsed ? "none" : "4px 0 24px rgba(0,0,0,0.8)",
      }
    : {
        ...styles.sidebar,
        width: collapsed ? "48px" : SIDEBAR_WIDTH,
        minWidth: collapsed ? "48px" : SIDEBAR_WIDTH,
      };

  return (
    <aside style={sidebarStyle} aria-label="Conversation history">
      {/* ── Header: toggle + New Chat ──────────────────────────────────── */}
      <div style={styles.header}>
        {/* Toggle collapse button */}
        <button
          onClick={onToggle}
          style={styles.toggleBtn}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? "›" : "‹"}
        </button>

        {/* New Chat button — hidden when collapsed */}
        {!collapsed && (
          <button
            onClick={handleNewChat}
            disabled={creatingChat}
            style={
              creatingChat
                ? { ...styles.newChatBtn, opacity: 0.5 }
                : styles.newChatBtn
            }
            aria-label="Start a new chat"
            title="New chat"
          >
            {creatingChat ? "…" : "+ New Chat"}
          </button>
        )}
      </div>

      {/* ── Chat list ──────────────────────────────────────────────────── */}
      {!collapsed && (
        <nav style={styles.list} aria-label="Chats">
          {loading ? (
            // Skeleton placeholders while loading
            [0, 1, 2].map((i) => (
              <div key={i} style={styles.skeleton} />
            ))
          ) : chats.length === 0 ? (
            <p style={styles.emptyMsg}>
              No conversations yet.
              <br />
              Click + New Chat to start.
            </p>
          ) : (
            chats.map((chat) => (
              <ChatRow
                key={chat.id}
                chat={chat}
                isActive={chat.id === activeChatId}
                isEditing={editingId === chat.id}
                editDraft={editDraft}
                editInputRef={editInputRef}
                onSelect={() => onChatSelect(chat)}
                onDoubleClick={(e) => startEditing(e, chat)}
                onEditChange={(e) => setEditDraft(e.target.value)}
                onEditBlur={commitRename}
                onEditKey={handleRenameKey}
              />
            ))
          )}
        </nav>
      )}

      {/* Shimmer keyframe — only used for skeleton loading */}
      <style>{`
        @keyframes sidebarShimmer {
          0%   { opacity: 0.3; }
          50%  { opacity: 0.6; }
          100% { opacity: 0.3; }
        }
      `}</style>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Internal: ChatRow
// ---------------------------------------------------------------------------

/**
 * ChatRow
 * Renders a single chat entry in the sidebar list. Supports two modes:
 *   View   — shows title + metadata, double-click starts editing.
 *   Edit   — shows an inline input for renaming.
 *
 * Parameters:
 *   chat          (object)      — ChatListItem from the API.
 *   isActive      (boolean)     — whether this is the currently open chat.
 *   isEditing     (boolean)     — whether this row is in rename mode.
 *   editDraft     (string)      — controlled value of the rename input.
 *   editInputRef  (ref)         — ref for auto-focusing the rename input.
 *   onSelect      (function)    — called on single click to open the chat.
 *   onDoubleClick (function)    — called on double-click to enter rename mode.
 *   onEditChange  (function)    — onChange handler for the rename input.
 *   onEditBlur    (function)    — onBlur handler (commits rename).
 *   onEditKey     (function)    — onKeyDown handler (Enter = commit, Esc = cancel).
 *
 * Returns: JSX.Element.
 * Used by: ChatSidebar (mapped over chats array).
 */
function ChatRow({
  chat,
  isActive,
  isEditing,
  editDraft,
  editInputRef,
  onSelect,
  onDoubleClick,
  onEditChange,
  onEditBlur,
  onEditKey,
}) {
  const displayTitle = chat.title ?? "New conversation";
  const isPending = !chat.title; // Title not yet generated

  return (
    <button
      onClick={onSelect}
      onDoubleClick={onDoubleClick}
      style={{
        ...styles.chatRow,
        ...(isActive ? styles.chatRowActive : {}),
      }}
      aria-current={isActive ? "page" : undefined}
      aria-label={`Open chat: ${displayTitle}`}
      title="Double-click to rename"
    >
      {isEditing ? (
        /* ── Inline rename input ─────────────────────────────────── */
        <input
          ref={editInputRef}
          value={editDraft}
          onChange={onEditChange}
          onBlur={onEditBlur}
          onKeyDown={onEditKey}
          onClick={(e) => e.stopPropagation()}
          style={styles.renameInput}
          maxLength={200}
          aria-label="Rename chat"
        />
      ) : (
        /* ── View mode ───────────────────────────────────────────── */
        <>
          <span
            style={{
              ...styles.chatTitle,
              ...(isPending ? styles.chatTitlePending : {}),
            }}
          >
            {displayTitle}
          </span>
          <span style={styles.chatMeta}>
            {chat.message_count > 0
              ? `${chat.message_count} msg${chat.message_count !== 1 ? "s" : ""}`
              : "Empty"}
            {chat.last_message_at && (
              <> · {formatRelative(chat.last_message_at)}</>
            )}
          </span>
        </>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Helper: relative timestamp
// ---------------------------------------------------------------------------

/**
 * formatRelative
 * Converts an ISO timestamp to a compact relative string for the sidebar.
 * Keeps it short so it fits on one line next to the message count.
 *
 * Parameters:
 *   isoString (string) — ISO 8601 date string from the API.
 *
 * Returns: string — "2m", "1h", "3d", "Jun 12", etc.
 * Used by: ChatRow.
 */
function formatRelative(isoString) {
  try {
    const diffMs = Date.now() - new Date(isoString).getTime();
    const mins  = Math.floor(diffMs / 60000);
    const hours = Math.floor(diffMs / 3600000);
    const days  = Math.floor(diffMs / 86400000);

    if (mins < 1)   return "now";
    if (mins < 60)  return `${mins}m`;
    if (hours < 24) return `${hours}h`;
    if (days < 7)   return `${days}d`;
    return new Date(isoString).toLocaleDateString(undefined, {
      month: "short", day: "numeric",
    });
  } catch {
    return "";
  }
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  sidebar: {
    display: "flex",
    flexDirection: "column",
    background: "var(--color-bg-surface)",
    borderRight: "1px solid var(--color-border)",
    overflow: "hidden",
    transition: "width 200ms cubic-bezier(0.4, 0, 0.2, 1), min-width 200ms cubic-bezier(0.4, 0, 0.2, 1)",
    flexShrink: 0,
  },

  header: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-2)",
    padding: "var(--sp-3) var(--sp-3)",
    borderBottom: "1px solid var(--color-border)",
    flexShrink: 0,
  },

  toggleBtn: {
    flexShrink: 0,
    width: "28px",
    height: "28px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "transparent",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-secondary)",
    cursor: "pointer",
    fontSize: "var(--fs-md)",
    fontFamily: "var(--font-body)",
    lineHeight: 1,
    transition: "border-color var(--transition-fast), color var(--transition-fast)",
  },

  newChatBtn: {
    flex: 1,
    padding: "var(--sp-1) var(--sp-2)",
    background: "var(--color-accent-subtle)",
    border: "1px solid var(--color-accent)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-accent)",
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-bold)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    whiteSpace: "nowrap",
    transition: "background var(--transition-fast)",
  },

  list: {
    flex: 1,
    overflowY: "auto",
    padding: "var(--sp-2) var(--sp-2)",
    display: "flex",
    flexDirection: "column",
    gap: "2px",
  },

  chatRow: {
    width: "100%",
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-start",
    gap: "2px",
    padding: "var(--sp-2) var(--sp-3)",
    background: "transparent",
    border: "none",
    borderRadius: "var(--radius-sm)",
    cursor: "pointer",
    textAlign: "left",
    fontFamily: "var(--font-body)",
    transition: "background var(--transition-fast)",
  },

  chatRowActive: {
    background: "var(--color-bg-input)",
  },

  chatTitle: {
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-medium)",
    color: "var(--color-text-primary)",
    width: "100%",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    display: "block",
  },

  chatTitlePending: {
    color: "var(--color-text-placeholder)",
    fontStyle: "italic",
  },

  chatMeta: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-placeholder)",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    width: "100%",
  },

  renameInput: {
    width: "100%",
    background: "var(--color-bg-input)",
    border: "1px solid var(--color-accent)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-primary)",
    fontSize: "var(--fs-sm)",
    fontFamily: "var(--font-body)",
    padding: "2px var(--sp-2)",
    outline: "none",
  },

  skeleton: {
    height: "48px",
    background: "var(--color-bg-input)",
    borderRadius: "var(--radius-sm)",
    margin: "2px 0",
    animation: "sidebarShimmer 1.5s ease-in-out infinite",
  },

  emptyMsg: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-placeholder)",
    lineHeight: "1.6",
    padding: "var(--sp-4) var(--sp-3)",
    margin: 0,
    textAlign: "center",
  },
};