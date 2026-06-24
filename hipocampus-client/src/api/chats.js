/**
 * src/api/chats.js
 *
 * API calls for the multi-chat management surface.
 * Maps to the four endpoints in app/api/v1/chats.py.
 *
 * Used by:
 *   src/components/chat/ChatSidebar.jsx — listChats(), createChat(), renameChat()
 *   src/pages/ChatPage.jsx             — getChatMessages() when opening an old chat
 *   src/hooks/useChat.js               — createChat() on first turn with no session
 */

import { get, patch, post } from "./client.js";

// ---------------------------------------------------------------------------
// Create a new chat
// ---------------------------------------------------------------------------

/**
 * createChat
 * Creates a new Chat row server-side and returns the session_id the client
 * must send with every subsequent turn in this conversation.
 *
 * Parameters: none — the server generates a fresh session_id.
 *
 * Returns:
 *   Promise<{
 *     id:         string,   — UUID of the Chat row
 *     session_id: string,   — e.g. "chat-a3f2c1b4-9d2e"
 *     title:      null,     — null until Qwen generates it after the first turn
 *     created_at: string,
 *   }>
 *
 * Used by: ChatSidebar → "New Chat" button,
 *          useChat → when no session_id exists and user sends first message.
 */
export function createChat() {
  return post("/api/v1/chats");
}

// ---------------------------------------------------------------------------
// List chats
// ---------------------------------------------------------------------------

/**
 * listChats
 * Returns all of the current user's chats, most-recently-active first.
 * Each item includes a message_count and last_message_at for the sidebar
 * without requiring a separate request per chat.
 *
 * Parameters: none — filtered to the authenticated user server-side.
 *
 * Returns:
 *   Promise<Array<{
 *     id:              string,
 *     session_id:      string,
 *     title:           string | null,
 *     created_at:      string,
 *     message_count:   number,
 *     last_message_at: string | null,
 *   }>>
 *
 * Used by: ChatSidebar on mount and after a new chat is created.
 */
export function listChats() {
  return get("/api/v1/chats");
}

// ---------------------------------------------------------------------------
// Get full message archive for a chat
// ---------------------------------------------------------------------------

/**
 * getChatMessages
 * Returns every message ever sent in a chat, oldest first. This is the
 * permanent archive — no TTL, no size limit. Used when the user opens an
 * old conversation to read back context or copy a code snippet.
 *
 * Parameters:
 *   chatId (string) — UUID of the Chat row.
 *
 * Returns:
 *   Promise<{
 *     chat_id:    string,
 *     session_id: string,
 *     title:      string | null,
 *     messages:   Array<{
 *       id:         string,
 *       chat_id:    string,
 *       session_id: string,
 *       role:       "user" | "assistant",
 *       content:    string,
 *       created_at: string,
 *     }>,
 *   }>
 *
 * Throws:
 *   ApiError 404 — chat not found or belongs to another user.
 *
 * Used by: ChatPage when navigating to /chat/:chatId for an existing chat.
 */
export function getChatMessages(chatId) {
  return get(`/api/v1/chats/${chatId}/messages`);
}

// ---------------------------------------------------------------------------
// Rename a chat
// ---------------------------------------------------------------------------

/**
 * renameChat
 * Updates the title of a chat. Called when the user double-clicks a chat
 * name in the sidebar and types a new one, or to override a Qwen-generated
 * title.
 *
 * Parameters:
 *   chatId (string) — UUID of the Chat row to rename.
 *   title  (string) — the new title, 1–256 characters.
 *
 * Returns:
 *   Promise<{
 *     id:         string,
 *     session_id: string,
 *     title:      string,
 *     created_at: string,
 *   }>
 *
 * Throws:
 *   ApiError 404 — chat not found or belongs to another user.
 *
 * Used by: ChatSidebar → inline rename on double-click.
 */
export function renameChat(chatId, title) {
  return patch(`/api/v1/chats/${chatId}`, { title });
}