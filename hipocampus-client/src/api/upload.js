/**
 * src/api/upload.js
 *
 * Document upload API — sends a file to POST /api/v1/upload and returns
 * the extracted text. Uses raw fetch (not the JSON client) because the
 * request body is multipart/form-data, not JSON.
 *
 * Client-side validation is done before the request to give instant
 * feedback rather than waiting for a server round-trip.
 *
 * Used by: src/components/chat/ChatInput.jsx
 */

import { getAuthToken } from "./client.js";

/** Accepted extensions and their display names. */
export const ACCEPTED_FORMATS = {
  ".pdf": "PDF",
  ".csv": "CSV",
  ".md":  "Markdown",
};

const MAX_BYTES = 10 * 1024 * 1024; // 10 MB

/**
 * validateFile
 * Checks extension, double-extension, and size on the client before uploading.
 * Matches the server-side rules so errors surface instantly.
 *
 * Parameters:
 *   file (File) — the File object from the input element.
 *
 * Returns:
 *   { valid: true, ext: string }   — on success.
 *   { valid: false, error: string } — on failure.
 */
export function validateFile(file) {
  const name    = file.name;
  const lastDot = name.lastIndexOf(".");
  if (lastDot < 0) {
    return { valid: false, error: "File has no extension. Only .pdf, .csv, and .md are accepted." };
  }

  const ext  = name.slice(lastDot).toLowerCase();
  const stem = name.slice(0, lastDot);

  if (!Object.keys(ACCEPTED_FORMATS).includes(ext)) {
    return { valid: false, error: `Extension '${ext}' is not allowed. Use .pdf, .csv, or .md.` };
  }

  // Double-extension guard (mirrors the server check)
  const stemLastDot = stem.lastIndexOf(".");
  if (stemLastDot >= 0) {
    const stemExt = stem.slice(stemLastDot);
    return {
      valid: false,
      error: `Suspicious filename detected (double extension '${stemExt}${ext}'). Upload blocked.`,
    };
  }

  if (file.size > MAX_BYTES) {
    return { valid: false, error: `File is ${(file.size / 1024 / 1024).toFixed(1)} MB — max is 10 MB.` };
  }

  return { valid: true, ext };
}

/**
 * uploadDocument
 * POSTs the file as multipart/form-data and returns the extracted text
 * object from the backend.
 *
 * Parameters:
 *   file (File) — the validated File object to upload.
 *
 * Returns:
 *   Promise<{
 *     filename:       string,
 *     format:         "pdf" | "csv" | "md",
 *     char_count:     number,
 *     extracted_text: string,
 *   }>
 *
 * Throws:
 *   Error — with a human-readable message from the API.
 *
 * Used by: ChatInput → handleFileChange()
 */
export async function uploadDocument(file) {
  const token    = getAuthToken();
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch("/api/v1/upload", {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
    // Do NOT set Content-Type — the browser sets it automatically with the
    // correct boundary when the body is FormData.
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const err = await res.json(); detail = err.detail ?? detail; } catch {}
    throw new Error(detail);
  }

  return res.json();
}