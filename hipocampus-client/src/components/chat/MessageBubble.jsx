/**
 * src/components/chat/MessageBubble.jsx
 *
 * Renders a single message turn — user or assistant.
 *
 * AI messages are rendered with react-markdown + remark-gfm + syntax
 * highlighting so the user sees formatted headings, lists, tables, and
 * coloured code blocks instead of raw markdown characters.
 *
 * User messages are kept as plain text — users type prose, not markdown.
 *
 * Design notes (B&W theme):
 *   User bubbles are WHITE (#FFFFFF) with BLACK text — the human's words
 *   appear on a white ground. AI bubbles are dark charcoal (#141414) with
 *   white text. The contrast is intentional and mirrors the logo.
 *
 * Used by: src/components/chat/ChatWindow.jsx.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

// ---------------------------------------------------------------------------
// Markdown component overrides
// ---------------------------------------------------------------------------

/**
 * mdComponents
 * Custom renderers passed to ReactMarkdown. Only code blocks need special
 * treatment (syntax highlighting). Everything else uses the .md-body CSS
 * classes defined in index.css.
 */
const mdComponents = {
  code({ node, inline, className, children, ...props }) {
    const langMatch = /language-(\w+)/.exec(className || "");
    if (!inline && langMatch) {
      return (
        <SyntaxHighlighter
          style={oneDark}
          language={langMatch[1]}
          PreTag="div"
          customStyle={{
            margin: "0.75em 0",
            borderRadius: "var(--radius-sm)",
            border: "1px solid #2A2A2A",
            fontSize: "0.85em",
          }}
          codeTagProps={{ style: { fontFamily: "var(--font-mono)" } }}
          {...props}
        >
          {String(children).replace(/\n$/, "")}
        </SyntaxHighlighter>
      );
    }
    // Inline code — styled via .md-body code in index.css
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  },
};

// ---------------------------------------------------------------------------
// MessageBubble
// ---------------------------------------------------------------------------

/**
 * MessageBubble
 *
 * Parameters:
 *   role     ("user" | "assistant") — alignment and colour.
 *   content  (string)               — raw message text (may contain markdown
 *                                     for assistant turns).
 *   isLatest (boolean)              — applies fade-in entrance animation.
 *
 * Returns: JSX.Element.
 * Used by: ChatWindow.
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
      {/* AI avatar dot */}
      {!isUser && (
        <span
          style={styles.aiDot}
          aria-hidden="true"
          title="Hipocampus"
        />
      )}

      {/* Bubble */}
      <div
        style={{
          ...styles.bubble,
          ...(isUser ? styles.userBubble : styles.aiBubble),
          borderBottomRightRadius: isUser ? "4px" : "var(--radius-md)",
          borderBottomLeftRadius:  isUser ? "var(--radius-md)" : "4px",
        }}
        role={isUser ? undefined : "article"}
        aria-label={isUser ? undefined : "AI response"}
      >
        {isUser ? (
          // Plain text for user messages
          <PlainText content={content} />
        ) : (
          // Full markdown for assistant messages
          <div className="md-body">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={mdComponents}
            >
              {content}
            </ReactMarkdown>
          </div>
        )}
      </div>

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
// Internal: PlainText
// ---------------------------------------------------------------------------

/**
 * PlainText
 * Renders a user message as plain paragraphs with line-break support.
 * No markdown parsing — users type prose.
 */
function PlainText({ content }) {
  if (!content) return null;
  return content
    .split(/\n\n+/)
    .filter((p) => p.trim())
    .map((para, i) => (
      <p key={i} style={styles.paragraph}>
        {para.split("\n").map((line, j, arr) => (
          <span key={j}>
            {line}
            {j < arr.length - 1 && <br />}
          </span>
        ))}
      </p>
    ));
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
  },

  userBubble: {
    background: "var(--color-bubble-user)",
    border: "1px solid var(--color-border)",
    // White bubble — MUST use black text (set in CSS var --color-bubble-user-text)
    color: "var(--color-bubble-user-text)",
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
};