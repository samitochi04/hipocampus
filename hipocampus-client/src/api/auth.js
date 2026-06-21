/**
 * src/api/auth.js
 *
 * All API calls for the authentication surface.
 *
 * Change: register() and login() now call setAuthToken() with the JWT returned
 * in the response body. logout() calls clearAuthToken(). This means every
 * subsequent request in the same session includes Authorization: Bearer <token>,
 * which the backend's get_current_user() reads as the primary auth path.
 *
 * Used by:
 *   src/context/AuthContext.jsx — register(), login(), logout(), me()
 */

import { clearAuthToken, get, post, setAuthToken } from "./client.js";

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/**
 * register
 * Creates a new account. Stores the returned JWT for subsequent requests.
 *
 * Parameters:
 *   name (string) — display name from the registration form.
 *
 * Returns:
 *   Promise<{ login_key, user_id, message, access_token }>
 *   login_key — shown to the user exactly once; cannot be recovered.
 *
 * Side-effects: calls setAuthToken() with the returned JWT.
 *
 * Used by: src/context/AuthContext.jsx → register()
 */
export async function register(name) {
  const result = await post("/api/v1/auth/register", { name });
  // Store the JWT so subsequent requests include Authorization: Bearer.
  if (result?.access_token) {
    setAuthToken(result.access_token);
  }
  return result;
}

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------

/**
 * login
 * Authenticates with the saved login key. Stores the returned JWT.
 *
 * Parameters:
 *   loginKey (string) — plaintext key saved at registration.
 *
 * Returns:
 *   Promise<{ id, name, created_at, last_login_at, access_token }>
 *
 * Side-effects: calls setAuthToken() with the returned JWT.
 *
 * Used by: src/context/AuthContext.jsx → login()
 */
export async function login(loginKey) {
  const result = await post("/api/v1/auth/login", { login_key: loginKey });
  if (result?.access_token) {
    setAuthToken(result.access_token);
  }
  return result;
}

// ---------------------------------------------------------------------------
// Logout
// ---------------------------------------------------------------------------

/**
 * logout
 * Clears the session cookie server-side and discards the in-memory JWT.
 *
 * Parameters: none.
 * Returns: Promise<undefined> — 204 No Content.
 *
 * Side-effects: calls clearAuthToken() so subsequent requests are unauthenticated.
 *
 * Used by: src/context/AuthContext.jsx → logout()
 */
export async function logout() {
  // Clear the token BEFORE the request so even if the request fails,
  // the client is logged out locally.
  clearAuthToken();
  return post("/api/v1/auth/logout");
}

// ---------------------------------------------------------------------------
// Session check
// ---------------------------------------------------------------------------

/**
 * me
 * Checks whether a valid session exists. Called on app mount by AuthContext.
 * If the JWT is already in sessionStorage (page refresh), getAuthToken() in
 * client.js restores it and the Bearer header is sent automatically.
 *
 * Parameters: none.
 * Returns: Promise<{ id, name, created_at, last_login_at }>
 * Throws:  ApiError 401 — no valid session.
 *
 * Used by: src/context/AuthContext.jsx → checkSession()
 */
export function me() {
  return get("/api/v1/auth/me");
}