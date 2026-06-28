/**
 * src/api/voice.js
 *
 * Voice chat API — sends a recorded audio blob to POST /api/v1/voice/chat
 * and returns the transcription, AI response text, and base64 MP3 audio.
 *
 * Uses raw fetch (not the JSON client) because the request is
 * multipart/form-data (audio blob + optional form fields).
 *
 * Used by: src/components/chat/VoiceMode.jsx
 */

import { getAuthToken } from "./client.js";

/**
 * sendVoiceMessage
 * Posts an audio blob to the voice endpoint and returns the full result.
 *
 * Parameters:
 *   audioBlob   (Blob)        — WebM/Opus blob from MediaRecorder.
 *   sessionId   (string|null) — existing session ID, or null for new chat.
 *   docContent  (string|null) — pre-extracted document text (from upload).
 *   docName     (string|null) — document filename for the AI context prefix.
 *
 * Returns:
 *   Promise<{
 *     transcription: string,    // what the user said
 *     response:      string,    // AI text response
 *     audio_base64:  string,    // base64-encoded MP3
 *     audio_format:  string,    // "mp3"
 *     session_id:    string,
 *     chat_id:       string,
 *     web_searched:  boolean,
 *   }>
 *
 * Throws:
 *   Error — with API detail message on failure.
 */
export async function sendVoiceMessage({ audioBlob, sessionId, docContent, docName }) {
  const token = getAuthToken();

  const form = new FormData();
  form.append("audio", audioBlob, "voice.webm");
  if (sessionId)  form.append("session_id",  sessionId);
  if (docContent) form.append("doc_content", docContent);
  if (docName)    form.append("doc_name",    docName);

  const res = await fetch("/api/v1/voice/chat", {
    method:  "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body:    form,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const err = await res.json(); detail = err.detail ?? detail; } catch {}
    throw new Error(detail);
  }

  return res.json();
}

/**
 * base64ToBlob
 * Converts a base64 string to a Blob for Web Audio API playback.
 *
 * Parameters:
 *   b64    (string) — base64-encoded audio data.
 *   mime   (string) — MIME type, e.g. "audio/mp3".
 *
 * Returns: Blob
 */
export function base64ToBlob(b64, mime = "audio/mp3") {
  const bytes = atob(b64);
  const buf   = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) buf[i] = bytes.charCodeAt(i);
  return new Blob([buf], { type: mime });
}