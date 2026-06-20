/**
 * src/components/auth/LoginForm.jsx
 *
 * The login screen for returning users. Accepts the plaintext login key and
 * submits it to the backend. On success AuthContext.login() sets the user
 * state and navigates to /chat.
 *
 * Used by: src/pages/LoginPage.jsx.
 */

import { useState } from "react";
import { useAuth } from "../../hooks/useAuth.js";
import { ApiError } from "../../api/client.js";

/**
 * LoginForm
 * Renders the login key input and submit button. All auth logic is delegated
 * to AuthContext.login() — this component only handles the form state and
 * error display.
 *
 * Parameters: none — login() is consumed from AuthContext via useAuth().
 *
 * Returns: JSX.Element.
 * Used by: src/pages/LoginPage.jsx.
 */
export default function LoginForm() {
  const { login } = useAuth();
  const [loginKey, setLoginKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  /**
   * handleSubmit
   * Prevents the default form submission, calls AuthContext.login() with the
   * trimmed key, and handles the error state on failure. On success,
   * AuthContext.login() navigates to /chat so no navigation logic is needed here.
   *
   * Parameters:
   *   e (SyntheticEvent) — the form submit event.
   *
   * Returns: void (async).
   * Used by: the form's onSubmit handler.
   */
  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    const trimmed = loginKey.trim();
    if (!trimmed) {
      setError("Please enter your login key.");
      return;
    }
    if (trimmed.length < 8) {
      setError("Login key must be at least 8 characters.");
      return;
    }

    setSubmitting(true);
    try {
      await login(trimmed);
      // AuthContext.login() navigates to /chat on success.
      // If we reach here it means navigation didn't happen (edge case) —
      // no action needed; the user is in the right state.
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError(
          "Login key not recognised. Double-check it and try again."
        );
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Login failed. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={styles.container}>
      {/* ── Heading ─────────────────────────────────────────────────────── */}
      <div style={styles.headingGroup}>
        <span style={styles.logoDot} aria-hidden="true" />
        <h1 style={styles.heading}>Welcome back</h1>
      </div>
      <p style={styles.subheading}>
        Enter the login key you saved when you created your account.
      </p>

      {/* ── Form ────────────────────────────────────────────────────────── */}
      <form onSubmit={handleSubmit} noValidate style={styles.form}>
        <label htmlFor="login-key" style={styles.label}>
          Login key
        </label>
        <input
          id="login-key"
          type="text"
          value={loginKey}
          onChange={(e) => setLoginKey(e.target.value)}
          placeholder="your-name-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
          autoComplete="off"
          autoFocus
          spellCheck={false}
          disabled={submitting}
          style={
            submitting
              ? { ...styles.input, opacity: 0.6 }
              : styles.input
          }
          aria-describedby={error ? "key-error" : undefined}
          aria-invalid={!!error}
        />

        {/* Error message */}
        {error && (
          <p id="key-error" role="alert" style={styles.errorMsg}>
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || !loginKey.trim()}
          style={
            submitting || !loginKey.trim()
              ? { ...styles.submitBtn, opacity: 0.5, cursor: "not-allowed" }
              : styles.submitBtn
          }
        >
          {submitting ? "Logging in…" : "Log in"}
        </button>
      </form>

      {/* ── Footer link ─────────────────────────────────────────────────── */}
      <p style={styles.footerText}>
        New here?{" "}
        <a href="/register" style={styles.footerLink}>
          Create an account
        </a>
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-5)",
  },

  headingGroup: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-2)",
  },

  logoDot: {
    display: "inline-block",
    width: "10px",
    height: "10px",
    borderRadius: "50%",
    background: "var(--color-accent)",
    flexShrink: 0,
    boxShadow: "var(--shadow-accent-glow)",
  },

  heading: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-xl)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    margin: 0,
  },

  subheading: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.6",
    margin: 0,
  },

  form: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-3)",
  },

  label: {
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-medium)",
    color: "var(--color-text-secondary)",
  },

  input: {
    width: "100%",
    padding: "var(--sp-3) var(--sp-4)",
    background: "var(--color-bg-input)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-primary)",
    fontSize: "var(--fs-base)",
    fontFamily: "'Fira Code', 'Cascadia Code', 'Consolas', monospace",
    transition: "border-color var(--transition-fast)",
    outline: "none",
    letterSpacing: "0.02em",
  },

  errorMsg: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-error)",
    margin: 0,
  },

  submitBtn: {
    width: "100%",
    padding: "var(--sp-3) var(--sp-4)",
    background: "var(--color-accent)",
    color: "#0D0F1A",
    border: "none",
    borderRadius: "var(--radius-sm)",
    fontSize: "var(--fs-base)",
    fontWeight: "var(--fw-bold)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    transition: "background var(--transition-fast), box-shadow var(--transition-fast)",
    marginTop: "var(--sp-2)",
  },

  footerText: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    textAlign: "center",
    margin: 0,
  },

  footerLink: {
    color: "var(--color-accent)",
    textDecoration: "none",
  },
};