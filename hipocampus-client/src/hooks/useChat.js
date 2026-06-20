/**
 * src/hooks/useChat.js
 *
 * Encapsulates all state and logic for the chat conversation.
 * ChatPage renders nothing except what this hook provides — no fetch calls,
 * no state management, no error handling live in the page itself.
 *
 * State managed:
 *   messages    — ordered array of { role, content } objects for the chat window.
 *   loading     — true while a sendMessage() request is in flight.
 *   conflict    — { detail: string } when the backend returns 409 (memory conflict),
 *                 null otherwise. Triggers the conflict banner in ChatPage.
 *   error       — string error message for non-conflict failures, null otherwise.
 *   sessionId   — the current Redis session ID, used for display/debug.
 *
 * Used by: src/pages/ChatPage.jsx exclusively.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client.js";
import { getHistory, sendMessage as apiSendMessage } from "../api/chat.js";

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * useChat
 * Initializes the chat session: loads history from the Redis buffer on mount,
 * and exposes a send() function the ChatInput component calls.
 *
 * Parameters: none.
 *
 * Returns:
 *   {
 *     messages:       Array<{ role: string, content: string }>,
 *     loading:        boolean,
 *     conflict:       { detail: string } | null,
 *     error:          string | null,
 *     sessionId:      string | null,
 *     send:           (message: string) => Promise<void>,
 *     dismissConflict:() => void,
 *     dismissError:   () => void,
 *   }
 *
 * Used by: src/pages/ChatPage.jsx.
 */
export function useChat() {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [conflict, setConflict] = useState(null);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(null);

  /**
   * historyLoaded ref
   * Prevents the history fetch from running twice in React 18 StrictMode
   * (which mounts effects twice in development). Once history is loaded,
   * this ref stays true for the lifetime of the component.
   */
  const historyLoaded = useRef(false);

  // ── Load history on mount ─────────────────────────────────────────────────

  /**
   * loadHistory
   * Fetches the Redis working-memory buffer on mount and populates the
   * message list so the user sees their recent conversation after a page
   * refresh. If the buffer has expired (TTL exceeded) or is empty, the
   * messages array stays empty — a fresh session.
   *
   * Parameters: none.
   * Returns: void (sets messages state as side-effect).
   * Used by: useEffect below (mount only).
   */
  const loadHistory = useCallback(async () => {
    if (historyLoaded.current) return;
    historyLoaded.current = true;

    try {
      const data = await getHistory();
      if (data?.messages?.length) {
        setMessages(data.messages);
      }
      if (data?.session_id) {
        setSessionId(data.session_id);
      }
    } catch {
      // History load failure is non-fatal — the chat window just starts empty.
      // We deliberately don't set the error state here to avoid showing an
      // error banner on a fresh session where no history exists.
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  // ── Send a message ────────────────────────────────────────────────────────

  /**
   * send
   * Sends the user's message to the backend, optimistically appends it to
   * the message list, and appends the AI response when it arrives.
   *
   * Optimistic update strategy:
   *   The user message is added to messages immediately (before the request
   *   completes) so the UI feels instant. If the request fails, the message
   *   stays in the list with the error shown below it — consistent with how
   *   chat apps handle send failures.
   *
   * Conflict handling:
   *   A 409 response means the message contradicts a stored high-confidence
   *   preference. The conflict detail is stored in state and the ChatPage
   *   renders a ConflictBanner. The message is NOT added to the list when a
   *   conflict occurs — the user must resolve the conflict first.
   *
   * Parameters:
   *   message (string) — the raw text the user typed. Must be non-empty;
   *                      ChatInput enforces this before calling send().
   *
   * Returns: Promise<void> — all outcomes handled via state.
   *
   * Used by: src/components/chat/ChatInput.jsx → handleSend().
   */
  const send = useCallback(async (message) => {
    if (!message.trim() || loading) return;

    // Clear previous conflict / error before each new send.
    setConflict(null);
    setError(null);

    // Optimistically add the user message.
    const userMessage = { role: "user", content: message };
    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      const data = await apiSendMessage(message);

      // Append the AI response.
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response },
      ]);

      if (data.session_id) {
        setSessionId(data.session_id);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Memory conflict — remove the optimistic user message and show the
        // conflict banner so the user can resolve it before retrying.
        setMessages((prev) => prev.slice(0, -1));
        setConflict({ detail: err.message });
      } else {
        // Any other error — keep the user message visible and show an
        // inline error so they know their message wasn't processed.
        setError(
          err instanceof ApiError
            ? err.message
            : "Something went wrong. Please try again."
        );
      }
    } finally {
      setLoading(false);
    }
  }, [loading]);

  // ── Dismiss handlers ──────────────────────────────────────────────────────

  /**
   * dismissConflict
   * Clears the conflict banner state.
   * Called when the user clicks "Dismiss" or navigates to resolve the conflict
   * on the Memory page.
   *
   * Parameters: none.
   * Returns: void.
   * Used by: src/pages/ChatPage.jsx → conflict banner dismiss button.
   */
  const dismissConflict = useCallback(() => setConflict(null), []);

  /**
   * dismissError
   * Clears the error state.
   * Called when the user clicks "Dismiss" on the error banner.
   *
   * Parameters: none.
   * Returns: void.
   * Used by: src/pages/ChatPage.jsx → error banner dismiss button.
   */
  const dismissError = useCallback(() => setError(null), []);

  return {
    messages,
    loading,
    conflict,
    error,
    sessionId,
    send,
    dismissConflict,
    dismissError,
  };
}