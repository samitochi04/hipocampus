/**
 * src/api/client.js
 *
 * Centralized HTTP client used by every api/* module.
 * All fetch calls in the app go through `apiRequest()` rather than calling
 * fetch() directly, so error handling, base URL, and cookie forwarding are
 * never duplicated.
 *
 * Key decisions:
 *   - credentials: "include" — sends the httpOnly session cookie on every
 *     request so the backend can authenticate the caller. Without this flag
 *     the browser strips the cookie and every protected route returns 401.
 *   - Base URL — reads VITE_API_BASE_URL from the environment at build time.
 *     In development this is "" (empty) so Vite's proxy handles routing.
 *     In production it is set to the backend's public URL.
 *   - Error shape — all errors are normalized to { status, message } so
 *     callers never have to inspect raw Response objects.
 *
 * Used by: src/api/auth.js, src/api/chat.js, src/api/memory.js
 */

/** Base URL prefix. Empty string in dev (Vite proxy handles /api/*). */
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// ---------------------------------------------------------------------------
// Error class
// ---------------------------------------------------------------------------

/**
 * Typed error thrown by apiRequest() for any non-2xx response.
 * Callers can catch this and check .status to branch on 401, 409, etc.
 *
 * Parameters (set by apiRequest, not by callers):
 *   message (string) — human-readable error detail from the server, or a
 *                       fallback string if the response had no body.
 *   status  (number) — HTTP status code of the failed response.
 *
 * Used by: catch blocks in auth.js, chat.js, memory.js, and React components
 *          that need to handle specific error codes (e.g. 401 → redirect to
 *          login, 409 → show conflict UI).
 */
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// ---------------------------------------------------------------------------
// Core request function
// ---------------------------------------------------------------------------

/**
 * Makes an authenticated JSON request to the backend API.
 * Handles serialisation, deserialisation, and error normalisation.
 *
 * Parameters:
 *   path    (string)  — API path relative to the base URL, e.g. "/api/v1/auth/register".
 *                       Must start with "/".
 *   options (object)  — standard fetch RequestInit options. The caller sets
 *                       `method`, `body` (as a plain object — this function
 *                       JSON.stringifies it), and any extra headers.
 *                       `credentials` and `Content-Type` are set automatically
 *                       and must not be overridden by the caller.
 *
 * Returns:
 *   Promise<any> — the parsed JSON response body on success (2xx).
 *                  Returns undefined for 204 No Content responses.
 *
 * Throws:
 *   ApiError — for any non-2xx response, with `.status` set to the HTTP code
 *              and `.message` set to the server's `detail` field (FastAPI's
 *              standard error shape) or a generic fallback.
 *
 * Used by: every function in auth.js, chat.js, and memory.js.
 */
export async function apiRequest(path, options = {}) {
  const { body, headers: extraHeaders, ...restOptions } = options;

  const headers = {
    "Content-Type": "application/json",
    ...extraHeaders,
  };

  const response = await fetch(`${BASE_URL}${path}`, {
    ...restOptions,
    headers,
    // Send the httpOnly session cookie on every request.
    // Required for the backend to authenticate the caller.
    credentials: "include",
    // Serialize the body if the caller passed a plain object.
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  // 204 No Content — return undefined (no body to parse).
  if (response.status === 204) {
    return undefined;
  }

  // Try to parse the response body as JSON.
  // Some error responses (e.g. 502 from a proxy) might not be JSON.
  let data;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    // FastAPI returns errors as { detail: "..." } or { detail: [...] }
    const message =
      typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((e) => e.msg).join("; ")
          : `Request failed with status ${response.status}`;

    throw new ApiError(message, response.status);
  }

  return data;
}

// ---------------------------------------------------------------------------
// Convenience wrappers
// ---------------------------------------------------------------------------

/**
 * GET request.
 *
 * Parameters:
 *   path (string) — API path, e.g. "/api/v1/auth/me".
 *
 * Returns: Promise<any> — parsed JSON response body.
 * Throws:  ApiError on non-2xx.
 *
 * Used by: auth.js → me(), chat.js → getHistory(), memory.js → getConflicts(),
 *          memory.js → exportMemory().
 */
export function get(path) {
  return apiRequest(path, { method: "GET" });
}

/**
 * POST request with a JSON body.
 *
 * Parameters:
 *   path (string) — API path, e.g. "/api/v1/auth/login".
 *   body (object) — plain JS object to JSON-serialize as the request body.
 *
 * Returns: Promise<any> — parsed JSON response body.
 * Throws:  ApiError on non-2xx.
 *
 * Used by: auth.js → register(), login(), logout(),
 *          chat.js → sendMessage().
 */
export function post(path, body) {
  return apiRequest(path, { method: "POST", body });
}

/**
 * PATCH request with a JSON body.
 *
 * Parameters:
 *   path (string) — API path including the resource ID,
 *                   e.g. "/api/v1/memory/facts/abc-123".
 *   body (object) — partial update payload to JSON-serialize.
 *
 * Returns: Promise<any> — parsed JSON response body.
 * Throws:  ApiError on non-2xx.
 *
 * Used by: memory.js → updateFact().
 */
export function patch(path, body) {
  return apiRequest(path, { method: "PATCH", body });
}