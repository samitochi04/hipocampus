/**
 * src/components/chat/MessageBubble.jsx
 *
 * Renders a single message in the conversation — either a user turn or an
 * AI response. Handles alignment, colour, and basic text formatting.
 *
 * Markdown handling:
 *   The AI frequently returns code blocks, bullet lists, and bold text.
 *   Rather than pulling in a full markdown library, this component does
 *   lightweight preprocessing: code blocks are extracted and rendered in
 *   <pre><code> elements; everything else is rendered as plain text.
 *   If the project grows to need full markdown, replace renderContent()
 *   with a `react-markdown` call — the component interface stays identical.
 *
 * Used by: src/components/chat/ChatWindow.jsx.
 */

/**
 * MessageBubble
 * Renders one message turn with appropriate styling for the role.
 *
 * Parameters:
 *   role     ("user" | "assistant") — determines alignment and colour.
 *                                     User bubbles are right-aligned in a
 *                                     darker surface colour; AI bubbles are
 *                                     left-aligned in a slightly lighter tone.
 *   content  (string)               — the raw message text. May contain
 *                                     markdown code fences (``` blocks).
 *   isLatest (boolean)              — true for the most recently added message.
 *                                     Applies a subtle fade-in entrance so the
 *                                     new message draws attention without
 *                                     being jarring.
 *
 * Returns: JSX.Element.
 * Used by: src/components/chat/ChatWindow.jsx (mapped over messages array).
 */
export default function MessageBubble({ role, content, isLatest }) {
  const isUser = role === "user";

  return (
    <div
      style={{
        ...styles.wrapper,
        justifyContent: isUser ? "flex-end" : "flex-start",
        animation: isLatest ? "fadeSlideIn 200ms ease forwards" : "none",
      }}
    >
      {/* ── Avatar dot ───────────────────────────────────────────────────── */}
      {!isUser && (
        <span style={styles.aiDot} aria-hidden="true" title="Hipocampus" />
      )}

      {/* ── Bubble ───────────────────────────────────────────────────────── */}
      <div
        style={{
          ...styles.bubble,
          ...(isUser ? styles.userBubble : styles.aiBubble),
          // Slightly different radius for the "tail" corner
          borderBottomRightRadius: isUser ? "4px" : "var(--radius-md)",
          borderBottomLeftRadius: isUser ? "var(--radius-md)" : "4px",
        }}
        role={isUser ? undefined : "article"}
        aria-label={isUser ? undefined : "AI response"}
      >
        {renderContent(content)}
      </div>

      {/*
        Keyframes injected once — safe to repeat render because browsers
        deduplicate identical <style> tags within the same document.
      */}
      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0);   }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: renderContent
// ---------------------------------------------------------------------------

/**
 * renderContent
 * Splits the message content on triple-backtick code fences and renders
 * each segment as either a <pre><code> block or plain text paragraphs.
 *
 * Strategy:
 *   Split on ``` — alternating segments are code (odd indices) and prose (even).
 *   Prose segments are further split on newlines to produce <p> elements.
 *
 * Parameters:
 *   content (string) — the raw message string from the API.
 *
 * Returns: Array<JSX.Element> — the rendered segments.
 * Used by: MessageBubble render.
 */
function renderContent(content) {
  if (!content) return null;

  // Split on code fences. Segments at odd indices are code blocks.
  const parts = content.split(/```(?:\w+)?\n?/);

  return parts.map((part, i) => {
    const isCode = i % 2 === 1;

    if (isCode) {
      return (
        <pre key={i} style={styles.codeBlock}>
          <code style={styles.codeText}>{part.trimEnd()}</code>
        </pre>
      );
    }

    // Prose — split on double newlines for paragraphs, single newlines for <br>.
    const paragraphs = part.split(/\n\n+/);
    return paragraphs
      .filter((p) => p.trim())
      .map((paragraph, j) => (
        <p key={`${i}-${j}`} style={styles.paragraph}>
          {paragraph.split("\n").map((line, k, arr) => (
            <span key={k}>
              {line}
              {k < arr.length - 1 && <br />}
            </span>
          ))}
        </p>
      ));
  });
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  wrapper: {
    display: "flex",
    alignItems: "flex-end",
    gap: "var(--sp-2)",
    padding: "0 var(--sp-2)",
    // Max width so long messages don't span the full chat width
    maxWidth: "100%",
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

  bubble: {
    maxWidth: "min(680px, 85%)",
    padding: "var(--sp-3) var(--sp-4)",
    borderRadius: "var(--radius-md)",
    fontSize: "var(--fs-base)",
    lineHeight: "1.65",
    wordBreak: "break-word",
    // Smooth entry — controlled by the parent wrapper's animation prop
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-2)",
  },

  userBubble: {
    background: "var(--color-bubble-user)",
    border: "1px solid var(--color-border)",
    color: "var(--color-text-primary)",
  },

  aiBubble: {
    background: "var(--color-bubble-ai)",
    border: "1px solid var(--color-border)",
    color: "var(--color-text-primary)",
  },

  paragraph: {
    margin: 0,
    lineHeight: "1.65",
  },

  codeBlock: {
    margin: 0,
    padding: "var(--sp-3) var(--sp-4)",
    background: "var(--color-bg-base)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    overflowX: "auto",
    // Scrollbar inside code blocks uses the same subtle styling
    scrollbarWidth: "thin",
    scrollbarColor: "var(--color-border) transparent",
  },

  codeText: {
    fontFamily: "'Fira Code', 'Cascadia Code', 'Consolas', monospace",
    fontSize: "var(--fs-sm)",
    color: "var(--color-accent)",
    lineHeight: "1.6",
    whiteSpace: "pre",
  },
};