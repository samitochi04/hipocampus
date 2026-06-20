/**
 * src/hooks/useAuth.js
 *
 * Convenience hook that reads from AuthContext.
 * Every component that needs the current user or auth actions imports this
 * hook rather than consuming AuthContext directly. The guard ensures a clear
 * error message if a component is accidentally rendered outside AuthProvider.
 *
 * Returns:
 *   {
 *     user:     object | null — the authenticated user profile, or null.
 *     loading:  boolean       — true while the initial session check is in flight.
 *     register: function      — create a new account; returns the login key.
 *     login:    function      — authenticate with a login key; navigates to /chat.
 *     logout:   function      — clear the session; navigates to /login.
 *   }
 *
 * Throws:
 *   Error — if called outside an AuthProvider. This is a programming error
 *           and should never reach production.
 *
 * Used by:
 *   src/components/layout/Header.jsx         — reads user, calls logout()
 *   src/components/layout/ProtectedRoute.jsx — reads user + loading
 *   src/pages/RegisterPage.jsx               — calls register()
 *   src/pages/LoginPage.jsx                  — calls login()
 *   src/pages/ChatPage.jsx                   — reads user (for display)
 *   src/pages/MemoryPage.jsx                 — reads user (for display)
 */

import { useContext } from "react";
import { AuthContext } from "../context/AuthContext.jsx";

/**
 * useAuth
 * Reads the AuthContext value and returns it.
 * Validates that the hook is used inside an AuthProvider.
 *
 * Parameters: none.
 *
 * Returns:
 *   { user, loading, register, login, logout } — see AuthContext.jsx for
 *   the full shape and documentation of each field.
 *
 * Used by: every component that needs auth state or auth actions.
 */
export function useAuth() {
  const context = useContext(AuthContext);

  if (context === null) {
    throw new Error(
      "useAuth() must be used inside an <AuthProvider>. " +
        "Make sure <AuthProvider> wraps your component tree in main.jsx."
    );
  }

  return context;
}