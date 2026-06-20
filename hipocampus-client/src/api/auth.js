/**
 * src/api/auth.js
 *
 * All API calls for the authentication surface.
 * Every function maps 1-to-1 to a backend route in app/api/v1/auth.py.
 * No business logic lives here — these are thin wrappers over client.js.
 *
 * Used by:
 *   src/context/AuthContext.jsx — register(), login(), logout(), me()
 *   src/components/auth/RegisterForm.jsx — register()
 *   src/components/auth/LoginForm.jsx    — login()
 *   src/components/layout/Header.jsx     — logout()
 */

import { get, post } from "./client.js";

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/**
 * Registers a new user account with the given display name.
 * On success the backend:
 *   1. Creates the user row and hashes a login key.
 *   2. Sets an httpOnly session cookie so the user is logged in immediately.
 *   3. Returns the plaintext login key — shown to the user exactly once.
 *
 * Parameters:
 *   name (string) — the display name entered on the registration screen.
 *                   Validated by the backend (1–64 chars, non-blank).
 *
 * Returns:
 *   Promise<{ login_key: string, user_id: string, message: string }>
 *   login_key — the plaintext key the user MUST save; it cannot be recovered.
 *   user_id   — UUID of the newly created account.
 *   message   — human-readable instruction string for the UI.
 *
 * Throws:
 *   ApiError 422 — if the name fails validation (blank, too long, etc.)
 *   ApiError 5xx — server error.
 *
 * Used by: src/context/AuthContext.jsx → register() action,
 *          src/components/auth/RegisterForm.jsx → handleSubmit().
 */
export function register(name) {
  return post("/api/v1/auth/register", { name });
}

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------

/**
 * Authenticates an existing user with their saved login key.
 * On success the backend verifies the Argon2 hash, updates last_login_at,
 * and sets a fresh httpOnly session cookie.
 *
 * Parameters:
 *   loginKey (string) — the plaintext key the user saved at registration.
 *                       Must be at least 8 characters (validated server-side).
 *
 * Returns:
 *   Promise<{ id: string, name: string, created_at: string, last_login_at: string|null }>
 *   The user's public profile — sufficient to populate the AuthContext without
 *   an extra /me call after login.
 *
 * Throws:
 *   ApiError 401 — if the login key doesn't match any stored hash.
 *   ApiError 422 — if the key is too short to pass schema validation.
 *
 * Used by: src/context/AuthContext.jsx → login() action,
 *          src/components/auth/LoginForm.jsx → handleSubmit().
 */
export function login(loginKey) {
  return post("/api/v1/auth/login", { login_key: loginKey });
}

// ---------------------------------------------------------------------------
// Logout
// ---------------------------------------------------------------------------

/**
 * Clears the session cookie server-side, ending the current session.
 * The backend deletes the cookie by setting it with max_age=0.
 * No request body needed — the session is identified by the cookie itself.
 *
 * Parameters: none.
 *
 * Returns:
 *   Promise<undefined> — 204 No Content; nothing to return after logout.
 *
 * Throws:
 *   ApiError 5xx — unlikely, but surface to the caller for graceful handling.
 *
 * Used by: src/context/AuthContext.jsx → logout() action,
 *          src/components/layout/Header.jsx → handleLogout().
 */
export function logout() {
  return post("/api/v1/auth/logout");
}

// ---------------------------------------------------------------------------
// Session check
// ---------------------------------------------------------------------------

/**
 * Asks the backend "is there a valid session attached to this request?".
 * Called once on app mount by AuthContext to restore the session after a
 * page refresh without requiring the user to log in again.
 *
 * The backend reads the httpOnly cookie, decodes the JWT, and returns the
 * user's public profile — or 401 if the cookie is missing/expired.
 *
 * Parameters: none.
 *
 * Returns:
 *   Promise<{ id: string, name: string, created_at: string, last_login_at: string|null }>
 *   The authenticated user's public profile.
 *
 * Throws:
 *   ApiError 401 — no valid session (cookie missing, expired, or invalid).
 *                  AuthContext treats 401 as "not logged in" and redirects
 *                  to /login without surfacing an error to the user.
 *
 * Used by: src/context/AuthContext.jsx → checkSession() on mount.
 */
export function me() {
  return get("/api/v1/auth/me");
}