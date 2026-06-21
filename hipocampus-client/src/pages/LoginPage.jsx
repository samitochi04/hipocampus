/**
 * src/pages/LoginPage.jsx
 *
 * The login page rendered at /login.
 * Thin wrapper around LoginForm. Redirects already-authenticated users
 * to /chat so they don't see the login screen while logged in.
 *
 * Used by: src/App.jsx (public route).
 */

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth.js";
import LoginForm from "../components/auth/LoginForm.jsx";

/**
 * LoginPage
 * Renders the login form. Redirects to /chat if already authenticated.
 *
 * Parameters: none.
 * Returns: JSX.Element | null.
 * Used by: src/App.jsx.
 */
export default function LoginPage() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  /**
   * Redirect if already logged in.
   * Runs after the initial /auth/me session check completes.
   */
  useEffect(() => {
    if (!loading && user) {
      navigate("/chat", { replace: true });
    }
  }, [user, loading, navigate]);

  // Show nothing while the session check is in flight.
  if (loading) return null;
  if (user) return null;

  return (
    <div className="auth-layout">
      <div className="auth-card">
        <LoginForm />
      </div>
    </div>
  );
}