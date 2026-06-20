/**
 * src/components/auth/RegisterForm.jsx
 *
 * The first screen a new user sees. Accepts a display name and submits it
 * to the backend. On success, hands off to LoginKeyDisplay so the user can
 * copy their one-time login key before proceeding.
 *
 * This component does NOT handle the key display itself — that's deliberately
 * split into LoginKeyDisplay so the two responsibilities are independent and
 * testable.
 *
 * Used by: src/pages/RegisterPage.jsx.
 */

import { useState } from "react";
import { useAuth } from "../../hooks/useAuth.js";
import { ApiError } from "../../api/client.js";

/**
 * RegisterForm
 * Renders the name input and submit button. Calls register() from AuthContext
 * on submit and passes the returned login key up to the parent page via
 * onSuccess so RegisterPage can switch to the LoginKeyDisplay step.
 *
 * Parameters:
 *   onSuccess (function) — called with the login key string when registration
 *                          succeeds. RegisterPage uses this to show LoginKeyDisplay.
 *                          Signature: onSuccess(loginKey: string) => void.
 *
 * Returns: JSX.Element.
 * Used by: src/pages/RegisterPage.jsx.
 */
export default function RegisterForm({ onSuccess }) {
  const { register } = useAuth();
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  /**
   * handleSubmit
   * Prevents the default form submission, validates the name client-side,
   * calls register(), and calls onSuccess with the login key on success.
   *
   * Parameters:
   *   e (SyntheticEvent) — the form submit event; we call preventDefault() on it.
   *
   * Returns: void (async, sets state as side-effect).
   * Used by: the form's onSubmit handler.
   */
  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);

    const trimmed = name.trim();
    if (!trimmed) {
      setError("Please enter a name.");
      return;
    }
    if (trimmed.length > 64) {
      setError("Name must be 64 characters or fewer.");
      return;
    }

    setSubmitting(true);
    try {
      const result = await register(trimmed);
      // Pass the plaintext key up to RegisterPage — it will render
      // LoginKeyDisplay which shows it to the user exactly once.
      onSuccess(result.login_key);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Registration failed. Please try again.");
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
        <h1 style={styles.heading}>Create your account</h1>
      </div>
      <p style={styles.subheading}>
        Choose a display name. You'll receive a login key — save it somewhere
        safe, it's the only way back in.
      </p>

      {/* ── Form ────────────────────────────────────────────────────────── */}
      <form onSubmit={handleSubmit} noValidate style={styles.form}>
        <label htmlFor="name" style={styles.label}>
          Display name
        </label>
        <input
          id="name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Alice"
          maxLength={64}
          autoComplete="name"
          autoFocus
          disabled={submitting}
          style={submitting ? { ...styles.input, opacity: 0.6 } : styles.input}
          aria-describedby={error ? "name-error" : undefined}
          aria-invalid={!!error}
        />

        {/* Character counter — appears once the field has content */}
        {name.length > 0 && (
          <span style={styles.charCount} aria-live="polite">
            {name.length}/64
          </span>
        )}

        {/* Error message */}
        {error && (
          <p id="name-error" role="alert" style={styles.errorMsg}>
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting || !name.trim()}
          style={
            submitting || !name.trim()
              ? { ...styles.submitBtn, opacity: 0.5, cursor: "not-allowed" }
              : styles.submitBtn
          }
        >
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>

      {/* ── Footer link ─────────────────────────────────────────────────── */}
      <p style={styles.footerText}>
        Already have a login key?{" "}
        <a href="/login" style={styles.footerLink}>
          Log in
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
    transition: "border-color var(--transition-fast)",
    outline: "none",
  },

  charCount: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-placeholder)",
    textAlign: "right",
    marginTop: "calc(-1 * var(--sp-2))",
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
    transition: "background var(--transition-fast), box-shadow var(--transition-fast)",
    fontFamily: "var(--font-body)",
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