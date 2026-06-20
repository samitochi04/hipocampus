/**
 * src/components/chat/ChatWindow.jsx
 *
 * The scrollable message list in the chat interface.
 * Renders the conversation history as a stack of MessageBubble components
 * and auto-scrolls to the newest message whenever the list changes.
 *
 * Layout contract with ChatPage:
 *   ChatPage allocates a fixed-height scrollable region for ChatWindow using
 *   CSS (full viewport height minus header and input area). ChatWindow fills
 *   that region and manages its own internal scroll.
 *
 * Used by: src/pages/ChatPage.jsx.
 */

import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble.jsx";

/**
 * ChatWindow
 * Renders the list of messages and auto-scrolls to the bottom whenever
 * the messages array or the loading state changes.
 *
 * Parameters:
 *   messages (Array<{ role: string, content: string }>)
 *            — ordered array of conversation turns from useChat().
 *              role is "user" or "assistant".
 *   loading  (boolean) — true while a sendMessage() request is in flight.
 *                        Renders a typing indicator at the bottom of the list.
 *
 * Returns: JSX.Element — a scrollable <div> containing MessageBubble instances.
 * Used by: src/pages/ChatPage.jsx.
 */
export default function ChatWindow({ messages, loading }) {
  /**
   * bottomRef
   * An invisible div pinned to the bottom of the message list.
   * Calling bottomRef.current.scrollIntoView() scrolls the window to
   * the latest message without needing to calculate scroll positions.
   */
  const bottomRef = useRef(null);

  /**
   * Auto-scroll effect
   * Fires whenever messages or loading changes. Using "smooth" behaviour
   * for message arrivals feels natural; the reduced-motion media query in
   * index.css collapses smooth scrolling to instant when the user prefers it.
   *
   * The 10ms timeout gives React one paint cycle to flush the new message
   * into the DOM before we try to scroll to it.
   */
  useEffect(() => {
    const id = setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 10);
    return () => clearTimeout(id);
  }, [messages, loading]);

  return (
    <div style={styles.window} role="log" aria-label="Conversation" aria-live="polite">
      {/* ── Empty state ──────────────────────────────────────────────────── */}
      {messages.length === 0 && !loading && (
        <div style={styles.emptyState}>
          <span style={styles.emptyDot} aria-hidden="true" />
          <p style={styles.emptyHeading}>Ready when you are.</p>
          <p style={styles.emptyBody}>
            Ask anything. Hipocampus remembers your preferences, past decisions,
            and patterns across every session.
          </p>
        </div>
      )}

      {/* ── Message list ─────────────────────────────────────────────────── */}
      {messages.map((message, index) => (
        <MessageBubble
          key={index}
          role={message.role}
          content={message.content}
          /*
           * isLatest marks the final message so MessageBubble can apply a
           * subtle fade-in entrance animation on the newest turn only.
           */
          isLatest={index === messages.length - 1}
        />
      ))}

      {/* ── Typing indicator ─────────────────────────────────────────────── */}
      {loading && <TypingIndicator />}

      {/* ── Scroll anchor ────────────────────────────────────────────────── */}
      <div ref={bottomRef} aria-hidden="true" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: TypingIndicator
// ---------------------------------------------------------------------------

/**
 * TypingIndicator
 * Three dots that animate in sequence to indicate the AI is generating a
 * response. Positioned and styled like an assistant message bubble so the
 * transition to the real response is smooth.
 *
 * Parameters: none.
 * Returns: JSX.Element.
 * Used by: ChatWindow (loading state).
 */
function TypingIndicator() {
  return (
    <div style={styles.typingWrapper} aria-label="AI is responding" role="status">
      <div style={styles.typingBubble}>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{
              ...styles.typingDot,
              animationDelay: `${i * 0.18}s`,
            }}
            aria-hidden="true"
          />
        ))}
      </div>
      {/*
        Inline keyframes for the dot bounce. Only used here so not worth
        polluting index.css.
      */}
      <style>{`
        @keyframes dotBounce {
          0%, 80%, 100% { transform: translateY(0);   opacity: 0.35; }
          40%            { transform: translateY(-6px); opacity: 1;    }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  window: {
    flex: 1,
    overflowY: "auto",
    padding: "var(--sp-6) var(--sp-4)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-2)",
    // Subtle gradient fade at the top so messages "emerge" from nothing
    // rather than appearing at a hard edge.
    maskImage:
      "linear-gradient(to bottom, transparent 0%, black 3%, black 97%, transparent 100%)",
    WebkitMaskImage:
      "linear-gradient(to bottom, transparent 0%, black 3%, black 97%, transparent 100%)",
  },

  emptyState: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    gap: "var(--sp-3)",
    padding: "var(--sp-10)",
    opacity: 0.7,
  },

  emptyDot: {
    display: "inline-block",
    width: "12px",
    height: "12px",
    borderRadius: "50%",
    background: "var(--color-accent)",
    boxShadow: "var(--shadow-accent-glow)",
    marginBottom: "var(--sp-2)",
  },

  emptyHeading: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-lg)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    margin: 0,
  },

  emptyBody: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.6",
    maxWidth: "320px",
    margin: 0,
  },

  typingWrapper: {
    display: "flex",
    justifyContent: "flex-start",
    padding: "0 var(--sp-2)",
  },

  typingBubble: {
    display: "flex",
    alignItems: "center",
    gap: "5px",
    padding: "var(--sp-3) var(--sp-4)",
    background: "var(--color-bubble-ai)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    borderBottomLeftRadius: "4px",
  },

  typingDot: {
    display: "inline-block",
    width: "6px",
    height: "6px",
    borderRadius: "50%",
    background: "var(--color-text-secondary)",
    animation: "dotBounce 1.2s ease-in-out infinite",
  },
};