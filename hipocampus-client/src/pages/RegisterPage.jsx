/**
 * src/pages/RegisterPage.jsx
 *
 * The registration flow rendered at /register.
 * Manages the two-step flow:
 *   Step 1 — RegisterForm: user enters their name.
 *   Step 2 — LoginKeyDisplay: user reads and confirms saving their login key.
 *
 * Race condition fix:
 *   Previously, AuthContext.register() called setUser() which immediately
 *   triggered this page's redirect useEffect, sending the user to /chat before
 *   LoginKeyDisplay ever rendered — the login key was never shown.
 *
 *   Fix: register() no longer calls setUser(). Instead, after the user
 *   confirms they have saved the key, handleConfirmed() calls refreshUser()
 *   (fetches /auth/me with the stored Bearer token) to populate user state,
 *   then navigates to /chat.
 *
 * Used by: src/App.jsx (public route).
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth.js";
import RegisterForm from "../components/auth/RegisterForm.jsx";
import LoginKeyDisplay from "../components/auth/LoginKeyDisplay.jsx";

/**
 * RegisterPage
 * Orchestrates the registration flow.
 *
 * Parameters: none.
 * Returns: JSX.Element.
 * Used by: src/App.jsx.
 */
export default function RegisterPage() {
  const { user, loading, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [loginKey, setLoginKey] = useState(null);
  const [confirming, setConfirming] = useState(false);

  /**
   * Redirect already-authenticated users to /chat.
   * Only fires when loginKey is null — i.e. the user arrived at /register
   * while already logged in, NOT during the registration key-display step.
   * This guards against the race condition where setUser() during registration
   * would immediately trigger this redirect before the key is shown.
   */
  useEffect(() => {
    if (!loading && user && !loginKey) {
      navigate("/chat", { replace: true });
    }
  }, [user, loading, navigate, loginKey]);

  if (loading) return null;
  if (user && !loginKey) return null;

  /**
   * handleConfirmed
   * Called when the user checks "I've saved my key" and clicks Continue.
   * Fetches the user profile (token is already in sessionStorage from
   * registration), sets user state, then navigates to chat.
   *
   * Parameters: none.
   * Returns: void (async).
   */
  async function handleConfirmed() {
    setConfirming(true);
    try {
      await refreshUser(); // populates user state via /auth/me + stored token
      navigate("/chat", { replace: true });
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="auth-layout">
      <div className="auth-card">
        {loginKey ? (
          /**
           * Step 2 — LoginKeyDisplay
           * Shows the one-time key. The user MUST confirm before we navigate.
           * onConfirmed calls refreshUser() then navigate("/chat").
           */
          <LoginKeyDisplay
            loginKey={loginKey}
            onConfirmed={handleConfirmed}
          />
        ) : (
          /**
           * Step 1 — RegisterForm
           * On success receives the plaintext login key and moves to step 2.
           */
          <RegisterForm onSuccess={(key) => setLoginKey(key)} />
        )}
      </div>
    </div>
  );
}