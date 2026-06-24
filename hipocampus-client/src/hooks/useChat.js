/**
 * src/hooks/useChat.js
 *
 * Multi-chat-aware hook. Manages all state for one conversation thread.
 *
 * Works in two modes determined by the chatId prop:
 *
 *   Existing chat (/chat/:chatId)
 *     On mount / chatId change: calls getChatMessages(chatId) to load the
 *     full permanent archive (no TTL). The session_id is read from the
 *     response and attached to every subsequent send.
 *
 *   New / unidentified chat (/chat with no chatId)
 *     On mount: calls getHistory() to restore the Redis buffer if still warm.
 *     The first send returns chat_id + session_id from the backend; the hook
 *     stores session_id internally and calls onChatCreated(chatId, sessionId)
 *     so ChatPage can navigate to /chat/:chatId.
 *
 * Used by: src/pages/ChatPage.jsx exclusively.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client.js";
import { getHistory, sendMessage as apiSendMessage } from "../api/chat.js";
import { getChatMessages } from "../api/chats.js";

/**
 * useChat
 *
 * Parameters (object):
 *   chatId        (string | null) — UUID of the open chat. Null for new chats.
 *   onChatCreated (function)      — called with (chatId, sessionId) the first time
 *                                   a new chat turn succeeds. ChatPage uses this to
 *                                   navigate to /chat/:chatId.
 *
 * Returns:
 *   {
 *     messages:        Array<{ role, content }>,
 *     historyLoading:  boolean — true while the archive / buffer is loading
 *     loading:         boolean — true while a send() request is in flight,
 *     conflict:        { detail: string } | null,
 *     error:           string | null,
 *     sessionId:       string | null,
 *     send:            (message: string) => Promise<void>,
 *     dismissConflict: () => void,
 *     dismissError:    () => void,
 *   }
 *
 * Used by: src/pages/ChatPage.jsx.
 */
export function useChat({ chatId = null, onChatCreated } = {}) {
  const [messages, setMessages]           = useState([]);
  const [historyLoading, setHistLoading]  = useState(false);
  const [loading, setLoading]             = useState(false);
  const [conflict, setConflict]           = useState(null);
  const [error, setError]                 = useState(null);

  /**
   * sessionId is internal: populated from the loaded archive (existing chat)
   * or from the first send response (new chat). The send() function captures
   * it via ref so it always uses the latest value without re-creating.
   */
  const [sessionId, setSessionId]         = useState(null);
  const sessionIdRef                      = useRef(null);

  // Keep ref in sync with state so the send callback is always current.
  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

  // Store onChatCreated in a ref to avoid it being a dependency of send().
  const onChatCreatedRef = useRef(onChatCreated);
  useEffect(() => { onChatCreatedRef.current = onChatCreated; }, [onChatCreated]);

  // ── Load history whenever chatId changes ───────────────────────────────

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setHistLoading(true);
      setMessages([]);
      setConflict(null);
      setError(null);
      setSessionId(null);

      try {
        if (chatId) {
          // Existing chat → load permanent archive from PostgreSQL.
          const data = await getChatMessages(chatId);
          if (cancelled) return;
          setMessages(
            (data.messages ?? []).map((m) => ({ role: m.role, content: m.content }))
          );
          if (data.session_id) setSessionId(data.session_id);
        } else {
          // No chatId → try to restore the Redis buffer (warm session).
          const data = await getHistory();
          if (cancelled) return;
          if (data?.messages?.length) setMessages(data.messages);
          if (data?.session_id)       setSessionId(data.session_id);
        }
      } catch {
        // History load failure is non-fatal; chat starts empty.
      } finally {
        if (!cancelled) setHistLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [chatId]);

  // ── Send a message ─────────────────────────────────────────────────────

  /**
   * send
   * Sends the user's message to the backend and handles the response.
   *
   * Optimistic: the user message is appended immediately; on failure it is
   * either left visible (generic error) or removed (conflict — user must
   * resolve before retrying).
   *
   * On the first turn of a new chat, the backend auto-creates the Chat row
   * and returns chat_id + session_id. We store session_id and call the
   * onChatCreated callback so ChatPage can navigate to /chat/:chatId.
   *
   * Parameters:
   *   message (string) — validated non-empty text from ChatInput.
   *
   * Returns: Promise<void> — all outcomes handled via state.
   * Used by: src/components/chat/ChatInput.jsx → handleSend().
   */
  const send = useCallback(async (message) => {
    if (!message.trim() || loading) return;

    setConflict(null);
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setLoading(true);

    try {
      const data = await apiSendMessage(message, sessionIdRef.current);

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response },
      ]);

      // Update session_id from the response (populated on first turn).
      if (data.session_id) setSessionId(data.session_id);

      // First turn of a brand-new chat → notify ChatPage to navigate.
      if (!chatId && data.chat_id) {
        onChatCreatedRef.current?.(data.chat_id, data.session_id);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Conflict: remove optimistic message, show resolution banner.
        setMessages((prev) => prev.slice(0, -1));
        setConflict({ detail: err.message });
      } else {
        setError(
          err instanceof ApiError
            ? err.message
            : "Something went wrong. Please try again."
        );
      }
    } finally {
      setLoading(false);
    }
  }, [loading, chatId]); // sessionId accessed via ref — not a dep

  // ── Dismiss handlers ───────────────────────────────────────────────────

  const dismissConflict = useCallback(() => setConflict(null), []);
  const dismissError    = useCallback(() => setError(null), []);

  return {
    messages,
    historyLoading,
    loading,
    conflict,
    error,
    sessionId,
    send,
    dismissConflict,
    dismissError,
  };
}