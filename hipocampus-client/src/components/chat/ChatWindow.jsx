/**
 * src/components/chat/ChatWindow.jsx
 *
 * Scrollable message list. Auto-scrolls to the newest message on every
 * update and shows a typewriter loading indicator while the AI is responding.
 *
 * Loading indicator:
 *   Cycles through 5 phrases every ~2 seconds with a character-by-character
 *   typewriter animation and a blinking cursor. Each phrase types in at
 *   40 ms/char, holds for 1.6 s when complete, then the next phrase begins.
 *   Phrases: Thinking... → Processing... → Analyzing... → Gathering... → Wrapping up...
 *
 * Used by: src/pages/ChatPage.jsx.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import MessageBubble from "./MessageBubble.jsx";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LOADING_PHRASES = [
  "Thinking...",
  "Processing...",
  "Analyzing...",
  "Gathering...",
  "Wrapping up...",
];

const CHAR_DELAY_MS  = 40;   // time between each typed character
const HOLD_AFTER_MS  = 1600; // how long to pause on the completed phrase

// ---------------------------------------------------------------------------
// ChatWindow
// ---------------------------------------------------------------------------

/**
 * ChatWindow
 *
 * Parameters:
 *   messages (Array<{ role, content }>) — conversation turns from useChat().
 *   loading  (boolean)                  — true while a turn is in flight.
 *
 * Returns: JSX.Element.
 * Used by: src/pages/ChatPage.jsx.
 */
export default function ChatWindow({ messages, loading, webSearched = false }) {
  const bottomRef = useRef(null);

  // Scroll to the bottom whenever messages change or loading starts/stops.
  useEffect(() => {
    const id = setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 10);
    return () => clearTimeout(id);
  }, [messages, loading]);

  return (
    <div
      style={styles.window}
      role="log"
      aria-label="Conversation"
      aria-live="polite"
    >
      {/* Empty state */}
      {messages.length === 0 && !loading && <EmptyState />}

      {/* Message list */}
      {messages.map((msg, i) => (
        <MessageBubble
          key={i}
          role={msg.role}
          content={msg.content}
          isLatest={i === messages.length - 1}
        />
      ))}

      {/* Web search badge — shown after the latest AI reply when search was used */}
      {webSearched && !loading && messages.length > 0 &&
       messages[messages.length - 1].role === "assistant" && (
        <WebSearchBadge />
      )}

      {/* Typewriter loading indicator */}
      {loading && <TypewriterIndicator />}

      {/* Scroll anchor */}
      <div ref={bottomRef} aria-hidden="true" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: WebSearchBadge
// ---------------------------------------------------------------------------

/**
 * WebSearchBadge
 * Subtle pill shown below the latest AI response when Qwen's web search
 * MCP tool was invoked for that turn. Communicates the tool use to the user
 * without cluttering the message bubble itself.
 */
function WebSearchBadge() {
  return (
    <div style={styles.searchBadgeWrapper} aria-label="Web search was used">
      <span style={styles.searchBadge}>
        🔍 Searched the web · Powered by Qwen MCP
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: EmptyState
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div style={styles.emptyState}>
      <span style={styles.emptyDot} aria-hidden="true" />
      <p style={styles.emptyHeading}>Ready when you are.</p>
      <p style={styles.emptyBody}>
        Ask anything. Hipocampus remembers your preferences, past decisions,
        and patterns across every session.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: TypewriterIndicator
// ---------------------------------------------------------------------------

/**
 * TypewriterIndicator
 * Renders an AI-bubble-styled box containing a phrase that types in
 * character by character, holds, then transitions to the next phrase.
 * A blinking cursor tracks the typing position.
 */
function TypewriterIndicator() {
  const [phraseIndex, setPhraseIndex] = useState(0);
  const [charCount,   setCharCount]   = useState(0);
  const [cursorOn,    setCursorOn]    = useState(true);

  const phrase    = LOADING_PHRASES[phraseIndex];
  const displayed = phrase.slice(0, charCount);
  const done      = charCount >= phrase.length;

  // Blink the cursor on a 530 ms interval — same rhythm as most OS cursors.
  useEffect(() => {
    const id = setInterval(() => setCursorOn((v) => !v), 530);
    return () => clearInterval(id);
  }, []);

  // Typing progression.
  useEffect(() => {
    if (done) {
      // Phrase fully typed → wait, then move to next phrase.
      const id = setTimeout(() => {
        setPhraseIndex((i) => (i + 1) % LOADING_PHRASES.length);
        setCharCount(0);
      }, HOLD_AFTER_MS);
      return () => clearTimeout(id);
    }
    // Type next character.
    const id = setTimeout(() => setCharCount((c) => c + 1), CHAR_DELAY_MS);
    return () => clearTimeout(id);
  }, [charCount, done]);

  return (
    <div style={styles.typerWrapper} aria-label="AI is responding" role="status">
      {/* Hipocampus avatar dot */}
      <span style={styles.aiDot} aria-hidden="true" />

      <div style={styles.typerBubble}>
        <span style={styles.typerText} aria-live="off">
          {displayed}
          {/* Blinking cursor — visible while typing, blinks after done */}
          <span
            style={{
              ...styles.cursor,
              opacity: done ? (cursorOn ? 1 : 0) : 1,
            }}
            aria-hidden="true"
          >
            |
          </span>
        </span>
      </div>
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
    maskImage:
      "linear-gradient(to bottom, transparent 0%, black 3%, black 97%, transparent 100%)",
    WebkitMaskImage:
      "linear-gradient(to bottom, transparent 0%, black 3%, black 97%, transparent 100%)",
  },

  // ── Web search badge ───────────────────────────────────────────────────
  searchBadgeWrapper: {
    display: "flex",
    justifyContent: "flex-start",
    padding: "0 var(--sp-2)",
  },
  searchBadge: {
    display: "inline-flex",
    alignItems: "center",
    gap: "var(--sp-2)",
    padding: "var(--sp-1) var(--sp-3)",
    background: "rgba(255, 255, 255, 0.04)",
    border: "1px solid rgba(255, 255, 255, 0.10)",
    borderRadius: "var(--radius-lg)",
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-placeholder)",
    letterSpacing: "0.01em",
  },

  // ── Empty state ────────────────────────────────────────────────────────
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

  // ── Typewriter indicator ───────────────────────────────────────────────
  typerWrapper: {
    display: "flex",
    alignItems: "flex-end",
    gap: "var(--sp-2)",
    padding: "0 var(--sp-2)",
  },

  aiDot: {
    flexShrink: 0,
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: "var(--color-accent)",
    boxShadow: "var(--shadow-accent-glow)",
    marginBottom: "var(--sp-2)",
  },

  typerBubble: {
    padding: "var(--sp-3) var(--sp-4)",
    background: "var(--color-bubble-ai)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    borderBottomLeftRadius: "4px",
    minWidth: "140px",   // prevents jarring width jump between short phrases
  },

  typerText: {
    fontFamily: "var(--font-body)",
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    letterSpacing: "0.01em",
  },

  cursor: {
    display: "inline-block",
    marginLeft: "1px",
    color: "var(--color-accent)",
    fontWeight: "var(--fw-bold)",
    fontSize: "var(--fs-base)",
    lineHeight: 1,
    transition: "opacity 100ms ease",
    userSelect: "none",
  },
};