/**
 * src/context/AuthContext.jsx
 *
 * Global authentication state for the entire app.
 * Wraps the tree in main.jsx so every component can read the current user
 * and call auth actions without prop-drilling.
 *
 * What this module owns:
 *   - `user`       — the authenticated UserOut object, or null when logged out.
 *   - `loading`    — true while the initial /auth/me session check is in flight.
 *                    Pages render a loading state instead of flashing /login.
 *   - `register()` — creates a new account, returns the one-time login key.
 *   - `login()`    — authenticates with the login key, populates user state.
 *   - `logout()`   — clears the session cookie and resets user to null.
 *
 * Session restoration:
 *   On every app load, AuthProvider calls /auth/me. If the httpOnly cookie is
 *   present and valid the backend returns the user profile. If the cookie is
 *   missing or expired the backend returns 401, which AuthProvider silently
 *   treats as "not logged in" — no error is shown.
 *
 * Used by:
 *   src/main.jsx                          — wraps <App> in <AuthProvider>
 *   src/hooks/useAuth.js                  — re-exports context value
 *   src/components/layout/ProtectedRoute.jsx — reads user + loading
 *   src/components/layout/Header.jsx      — reads user, calls logout()
 *   src/pages/RegisterPage.jsx            — calls register()
 *   src/pages/LoginPage.jsx               — calls login()
 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as authApi from "../api/auth.js";
import { ApiError } from "../api/client.js";

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

/**
 * AuthContext
 * The raw React context object. Components should NOT consume this directly —
 * use the useAuth() hook from hooks/useAuth.js instead, which validates that
 * the hook is called inside an AuthProvider.
 */
export const AuthContext = createContext(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

/**
 * AuthProvider
 * Must wrap the entire router tree (placed in main.jsx, inside <BrowserRouter>).
 * Manages the user state and exposes auth actions to the tree.
 *
 * Parameters:
 *   children (ReactNode) — the entire app component tree.
 *
 * Provides via context:
 *   user     (object|null) — authenticated user profile, or null.
 *   loading  (boolean)     — true during the initial session check.
 *   register (function)    — see register() below.
 *   login    (function)    — see login() below.
 *   logout   (function)    — see logout() below.
 *
 * Used by: src/main.jsx — wraps <App>.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  // ── Session restoration on mount ─────────────────────────────────────────

  /**
   * checkSession
   * Called once when the AuthProvider mounts. Hits /auth/me to ask the backend
   * whether a valid session cookie exists. On success sets the user state.
   * On 401 (no cookie / expired) silently leaves user as null — the
   * ProtectedRoute component will redirect to /login.
   *
   * Parameters: none.
   * Returns: void (sets state as a side-effect).
   * Used by: useEffect below (mount only).
   */
  const checkSession = useCallback(async () => {
    try {
      const profile = await authApi.me();
      setUser(profile);
    } catch (err) {
      // 401 is the expected "not logged in" case — not an error.
      // Any other error (network, 5xx) is also silently swallowed here
      // so the app doesn't show a crash screen on startup.
      if (!(err instanceof ApiError && err.status === 401)) {
        console.error("Session check failed:", err.message);
      }
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Auth actions ──────────────────────────────────────────────────────────

  /**
   * register
   * Creates a new account. On success the backend sets the session cookie,
   * so the user is immediately logged in. Returns the one-time login key
   * so RegisterPage can pass it to LoginKeyDisplay.
   *
   * Parameters:
   *   name (string) — display name from the registration form.
   *
   * Returns:
   *   Promise<{ login_key: string, user_id: string, message: string }>
   *   login_key — the plaintext key to show to the user exactly once.
   *
   * Throws:
   *   ApiError — propagated to the caller (RegisterForm handles the error state).
   *
   * Side-effects:
   *   - Sets user state from a subsequent /auth/me call so the profile is
   *     populated in context after registration.
   *   - Does NOT navigate — RegisterPage decides where to go after the key
   *     has been acknowledged by the user.
   *
   * Used by: src/pages/RegisterPage.jsx → handleRegister().
   */
  const register = useCallback(async (name) => {
    const result = await authApi.register(name);
    // Fetch the full profile so user state is populated in context.
    // register() already set the session cookie, so /me will succeed.
    try {
      const profile = await authApi.me();
      setUser(profile);
    } catch {
      // If /me fails after registration, the user can still proceed —
      // the login key is the important thing to show.
    }
    return result;
  }, []);

  /**
   * login
   * Authenticates with the saved login key. On success the backend sets a
   * fresh session cookie and returns the user profile.
   *
   * Parameters:
   *   loginKey (string) — the plaintext key the user saved at registration.
   *
   * Returns:
   *   Promise<void> — navigates to /chat on success.
   *
   * Throws:
   *   ApiError 401 — wrong key; LoginForm handles the error message.
   *
   * Side-effects:
   *   - Sets user state.
   *   - Navigates to /chat.
   *
   * Used by: src/pages/LoginPage.jsx → handleLogin(),
   *          src/components/auth/LoginForm.jsx → handleSubmit().
   */
  const login = useCallback(async (loginKey) => {
    const profile = await authApi.login(loginKey);
    setUser(profile);
    navigate("/chat");
  }, [navigate]);

  /**
   * logout
   * Clears the session cookie server-side and resets local auth state.
   * Always navigates to /login afterward, even if the server call fails,
   * so the user is never stuck in an authenticated state with a dead cookie.
   *
   * Parameters: none.
   * Returns: Promise<void>.
   *
   * Side-effects:
   *   - Resets user to null.
   *   - Navigates to /login.
   *
   * Used by: src/components/layout/Header.jsx → handleLogout().
   */
  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Even if the server call fails, clear local state.
      // The cookie may have already expired.
    } finally {
      setUser(null);
      navigate("/login");
    }
  }, [navigate]);

  // ── Context value ─────────────────────────────────────────────────────────

  const value = {
    user,
    loading,
    register,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}