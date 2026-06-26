/**
 * src/api/generate.js
 *
 * Document generation API call.
 * Uses a raw fetch (not the JSON client) because the response is a binary
 * or text file, not JSON. Attaches the Bearer token manually.
 *
 * Used by: src/components/chat/GeneratePanel.jsx
 */

import { getAuthToken } from "./client.js";

/**
 * generateDocument
 * Sends a generation request to POST /api/v1/generate and returns a
 * { blob, filename } pair the caller can use to trigger a browser download.
 *
 * Parameters:
 *   prompt (string)           — plain-text description of the document to create.
 *   format ("md"|"pdf"|"csv") — desired output format.
 *   size   ("A4"|"A3")        — page size; only meaningful for PDF.
 *
 * Returns:
 *   Promise<{ blob: Blob, filename: string }>
 *
 * Throws:
 *   Error — with a human-readable message from the API detail field.
 *
 * Used by: GeneratePanel → handleGenerate()
 */
export async function generateDocument({ prompt, format, size = "A4" }) {
  const token = getAuthToken();

  const res = await fetch("/api/v1/generate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ prompt, format, size }),
  });

  if (!res.ok) {
    // Try to parse the FastAPI detail field for a human-readable message.
    let detail = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      detail = err.detail ?? detail;
    } catch {
      // Ignore parse errors — keep the status code message.
    }
    throw new Error(detail);
  }

  // Extract filename from Content-Disposition: attachment; filename="..."
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match       = disposition.match(/filename="([^"]+)"/);
  const filename    = match?.[1] ?? `hipocampus-document.${format}`;

  const blob = await res.blob();
  return { blob, filename };
}

/**
 * triggerDownload
 * Creates a temporary <a> element to start a browser file download from a
 * Blob. Cleans up the object URL after the click.
 *
 * Parameters:
 *   blob     (Blob)   — file content.
 *   filename (string) — the suggested save-as name.
 *
 * Returns: void.
 * Used by: GeneratePanel after a successful generateDocument() call.
 */
export function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href     = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}