/**
 * src/api/client.js
 *
 * Centralized HTTP client used by every api/* module.
 *
 * Auth strategy:
 *   The backend returns a signed JWT in the response body on every login and
 *   register call. This module stores that token in memory and attaches it as
 *   an Authorization: Bearer header on every subsequent request. This bypasses
 *   browser cookie restrictions (Secure attribute on HTTP, SameSite, nginx
 *   proxy cookie stripping) that caused 401s after successful logins.
 *
 *   The httpOnly cookie is still set by the backend as a backup layer, but
 *   the Bearer header is the primary auth mechanism in this client.
 *
 * Token lifecycle:
 *   setAuthToken(token)  — called by auth.js after register/login
 *   clearAuthToken()     — called by auth.js after logout
 *   getAuthToken()       — read by apiRequest() to build the Authorization header
 *
 * Used by: src/api/auth.js, src/api/chat.js, src/api/memory.js
 */

/** Base URL prefix. Empty string in dev (Vite proxy handles /api/*). */
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// ---------------------------------------------------------------------------
// In-memory token store
// ---------------------------------------------------------------------------

/**
 * _token
 * Module-level variable holding the current JWT.
 * Survives React re-renders. Cleared on logout or page refresh.
 * Page-refresh persistence is handled by sessionStorage below.
 */
let _token = null;

/** Session storage key for persisting the token across page refreshes. */
const SESSION_KEY = "hipocampus_token";

/**
 * setAuthToken
 * Stores the JWT in both the module variable and sessionStorage so the
 * token survives page refreshes within the same browser tab.
 *
 * Parameters:
 *   token (string) — signed JWT returned by the backend on login/register.
 *
 * Returns: void.
 * Used by: src/api/auth.js → register(), login().
 */
export function setAuthToken(token) {
  _token = token;
  try { sessionStorage.setItem(SESSION_KEY, token); } catch { /* storage blocked */ }
}

/**
 * clearAuthToken
 * Removes the JWT from memory and sessionStorage.
 *
 * Parameters: none.
 * Returns: void.
 * Used by: src/api/auth.js → logout().
 */
export function clearAuthToken() {
  _token = null;
  try { sessionStorage.removeItem(SESSION_KEY); } catch { /* storage blocked */ }
}

/**
 * getAuthToken
 * Returns the current JWT, falling back to sessionStorage on a fresh page load.
 *
 * Parameters: none.
 * Returns: string | null.
 * Used by: apiRequest() below.
 */
function getAuthToken() {
  if (!_token) {
    try { _token = sessionStorage.getItem(SESSION_KEY); } 
    catch { 
      console.log("Not token found");
     }
  }
  return _token;
}

// ---------------------------------------------------------------------------
// Error class
// ---------------------------------------------------------------------------

/**
 * ApiError
 * Typed error thrown by apiRequest() for any non-2xx response.
 * Callers can check .status to branch on 401, 409, etc.
 *
 * Parameters:
 *   message (string) — human-readable error detail from the server.
 *   status  (number) — HTTP status code.
 *
 * Used by: catch blocks in auth.js, chat.js, memory.js, and React components.
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
 * apiRequest
 * Makes an authenticated JSON request to the backend API.
 *
 * Auth headers (both sent so either path in the backend works):
 *   Authorization: Bearer <token>  — primary; read first by get_current_user()
 *   Cookie: hipocampus_session     — backup; forwarded automatically by browser
 *
 * Parameters:
 *   path    (string) — API path, e.g. "/api/v1/auth/register".
 *   options (object) — standard fetch RequestInit. `body` is plain object
 *                      (JSON-serialized here). `credentials` and auth headers
 *                      are set automatically.
 *
 * Returns: Promise<any> — parsed JSON on success; undefined for 204.
 * Throws:  ApiError on non-2xx.
 *
 * Used by: every function in auth.js, chat.js, memory.js.
 */
export async function apiRequest(path, options = {}) {
  const { body, headers: extraHeaders, ...restOptions } = options;

  const token = getAuthToken();

  const headers = {
    "Content-Type": "application/json",
    // Include Bearer token when available. The backend's get_current_user()
    // dependency checks this header first, then falls back to the cookie.
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extraHeaders,
  };

  const response = await fetch(`${BASE_URL}${path}`, {
    ...restOptions,
    headers,
    // Still send the cookie too (backup path, works in environments where
    // the cookie isn't blocked).
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  // 204 No Content — nothing to parse.
  if (response.status === 204) {
    return undefined;
  }

  let data;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
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

/** GET request. */
export function get(path) {
  return apiRequest(path, { method: "GET" });
}

/** POST request with a JSON body. */
export function post(path, body) {
  return apiRequest(path, { method: "POST", body });
}

/** PATCH request with a JSON body. */
export function patch(path, body) {
  return apiRequest(path, { method: "PATCH", body });
}