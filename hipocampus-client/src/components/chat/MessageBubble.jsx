/**
 * src/components/chat/MessageBubble.jsx
 *
 * Renders a single conversation turn. Four improvements in this version:
 *
 *   1. Document display   — user messages prefixed with [DOCUMENT: file]
 *      show only a small attachment chip + the user's actual typed text.
 *      The extracted document content is hidden to keep the UI clean, exactly
 *      as major LLM products handle file attachments.
 *
 *   2. Markdown rendering — AI responses go through react-markdown + remark-gfm
 *      so the user sees formatted headings, lists, tables, code blocks, etc.
 *
 *   3. Copy code button   — each fenced code block has a "Copy" button in
 *      its top-right corner.
 *
 *   4. Copy response button — every AI bubble has a "Copy response" button
 *      that copies the raw markdown content to the clipboard.
 *
 * Used by: src/components/chat/ChatWindow.jsx.
 */

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

// ---------------------------------------------------------------------------
// CopyButton — reusable copy-to-clipboard button
// ---------------------------------------------------------------------------

function CopyButton({ text, style = {} }) {
  const [state, setState] = useState("idle"); // idle | copied

  async function handleCopy(e) {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
      setTimeout(() => setState("idle"), 2000);
    } catch {
      // Clipboard API may be blocked in some contexts — fail silently.
    }
  }

  return (
    <button
      onClick={handleCopy}
      style={{ ...copyBtnBase, ...style }}
      aria-label={state === "copied" ? "Copied!" : "Copy to clipboard"}
      title={state === "copied" ? "Copied!" : "Copy"}
    >
      {state === "copied" ? "✓ Copied" : "Copy"}
    </button>
  );
}

const copyBtnBase = {
  padding: "2px 8px",
  background: "rgba(0,0,0,0.45)",
  border: "1px solid rgba(255,255,255,0.15)",
  borderRadius: "4px",
  color: "#cccccc",
  fontSize: "0.72rem",
  fontFamily: "var(--font-mono)",
  cursor: "pointer",
  lineHeight: "1.6",
  transition: "background 120ms ease, color 120ms ease",
  whiteSpace: "nowrap",
};

// ---------------------------------------------------------------------------
// Markdown component overrides
// ---------------------------------------------------------------------------

function buildMdComponents() {
  return {
    code({ node, inline, className, children, ...props }) {
      const langMatch = /language-(\w+)/.exec(className || "");
      const codeString = String(children).replace(/\n$/, "");

      if (!inline && langMatch) {
        return (
          <div style={{ position: "relative", margin: "0.75em 0" }}>
            {/* Copy button — top right of the code block */}
            <CopyButton
              text={codeString}
              style={{
                position: "absolute",
                top: "8px",
                right: "8px",
                zIndex: 1,
              }}
            />
            <SyntaxHighlighter
              style={oneDark}
              language={langMatch[1]}
              PreTag="div"
              customStyle={{
                margin: 0,
                borderRadius: "var(--radius-sm)",
                border: "1px solid #2A2A2A",
                fontSize: "0.85em",
                paddingTop: "2.2em", // room for the copy button
              }}
              codeTagProps={{ style: { fontFamily: "var(--font-mono)" } }}
              {...props}
            >
              {codeString}
            </SyntaxHighlighter>
          </div>
        );
      }

      return (
        <code className={className} {...props}>
          {children}
        </code>
      );
    },
  };
}

const mdComponents = buildMdComponents();

// ---------------------------------------------------------------------------
// Document prefix parser
// ---------------------------------------------------------------------------

/**
 * parseUserContent
 * Detects the [DOCUMENT: filename] prefix injected by the file upload flow
 * and separates it from the user's actual message text.
 *
 * Input:  "[DOCUMENT: report.pdf]\n...extracted text...\n---\nHere is my question"
 * Output: { filename: "report.pdf", userText: "Here is my question" }
 *
 * Input:  "Plain message with no attachment"
 * Output: { filename: null, userText: "Plain message with no attachment" }
 */
function parseUserContent(content) {
  const DOC_RE = /^\[DOCUMENT: (.+?)\]\n/;
  const match = DOC_RE.exec(content);
  if (!match) return { filename: null, userText: content };

  const filename = match[1];
  const afterHeader = content.slice(match[0].length);
  const sepIdx = afterHeader.indexOf("\n---\n");

  if (sepIdx === -1) {
    // Entire message is document content with no typed text.
    return { filename, userText: "" };
  }

  const userText = afterHeader.slice(sepIdx + 5).trim();
  return { filename, userText };
}

// ---------------------------------------------------------------------------
// MessageBubble
// ---------------------------------------------------------------------------

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
        <span style={styles.aiDot} aria-hidden="true" title="Hipocampus" />
      )}

      {/* Bubble */}
      <div
        style={{
          ...styles.bubble,
          ...(isUser ? styles.userBubble : styles.aiBubble),
          borderBottomRightRadius: isUser ? "4px" : "var(--radius-md)",
          borderBottomLeftRadius:  isUser ? "var(--radius-md)" : "4px",
          position: "relative",
        }}
        role={isUser ? undefined : "article"}
        aria-label={isUser ? undefined : "AI response"}
      >
        {isUser ? (
          <UserContent content={content} />
        ) : (
          <>
            {/* Copy full response — top right of AI bubble */}
            <CopyButton
              text={content}
              style={{
                position: "absolute",
                top: "8px",
                right: "8px",
                opacity: 0.7,
              }}
            />
            <div className="md-body" style={{ paddingRight: "56px" }}>
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={mdComponents}
              >
                {content}
              </ReactMarkdown>
            </div>
          </>
        )}
      </div>

      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal: UserContent
// ---------------------------------------------------------------------------

/**
 * UserContent
 * Renders a user message. If the message contains a [DOCUMENT: …] prefix
 * (added by the file upload flow), shows a clean attachment chip + the
 * user's typed text only — hides the raw extracted document content.
 */
function UserContent({ content }) {
  const { filename, userText } = parseUserContent(content);

  return (
    <div>
      {/* Attachment chip — only shown when a document was attached */}
      {filename && (
        <div style={styles.docChip}>
          <span aria-hidden="true">📄</span>
          <span style={styles.docChipName}>{filename}</span>
        </div>
      )}

      {/* User's typed text */}
      {userText
        ? userText
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
            ))
        : filename && (
            // Document-only message with no typed text
            <p style={{ ...styles.paragraph, color: "inherit", opacity: 0.75, fontSize: "var(--fs-sm)" }}>
              Analyse this document.
            </p>
          )}
    </div>
  );
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

  docChip: {
    display: "inline-flex",
    alignItems: "center",
    gap: "var(--sp-2)",
    padding: "2px var(--sp-2)",
    background: "rgba(128,128,128,0.15)",
    border: "1px solid rgba(128,128,128,0.25)",
    borderRadius: "var(--radius-sm)",
    fontSize: "var(--fs-xs)",
    marginBottom: "var(--sp-2)",
    maxWidth: "100%",
    overflow: "hidden",
  },

  docChipName: {
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    fontWeight: "var(--fw-medium)",
  },
};