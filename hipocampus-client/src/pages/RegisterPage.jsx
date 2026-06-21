/**
 * src/pages/RegisterPage.jsx
 *
 * The registration flow rendered at /register.
 * Manages the two-step flow:
 *   Step 1 — RegisterForm: user enters their name.
 *   Step 2 — LoginKeyDisplay: user reads and confirms saving their login key.
 *
 * If the user already has a valid session (e.g. they navigated to /register
 * while still logged in), they are immediately redirected to /chat.
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
 * Orchestrates the registration flow. No business logic — delegates to
 * RegisterForm and LoginKeyDisplay.
 *
 * Parameters: none.
 * Returns: JSX.Element.
 * Used by: src/App.jsx.
 */
export default function RegisterPage() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  /**
   * loginKey state
   * Null until RegisterForm succeeds and calls onSuccess with the key.
   * When non-null, the page switches from RegisterForm to LoginKeyDisplay.
   */
  const [loginKey, setLoginKey] = useState(null);

  /**
   * Redirect if already logged in.
   * Runs after the initial session check completes (loading=false).
   * Avoids showing the registration form to a user who is already authenticated.
   */
  useEffect(() => {
    if (!loading && user) {
      navigate("/chat", { replace: true });
    }
  }, [user, loading, navigate]);

  // Show nothing while the session check is in flight.
  if (loading) return null;

  // Don't render the form if already authenticated (redirect is in progress).
  if (user) return null;

  return (
    <div className="auth-layout">
      <div className="auth-card">
        {loginKey ? (
          /**
           * Step 2 — LoginKeyDisplay
           * Shows the one-time key. On confirmation navigates to /chat.
           * The user is already logged in at this point (register() set the cookie).
           */
          <LoginKeyDisplay
            loginKey={loginKey}
            onConfirmed={() => navigate("/chat", { replace: true })}
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