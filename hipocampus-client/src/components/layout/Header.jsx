/**
 * src/components/layout/Header.jsx
 *
 * Top navigation bar rendered on every authenticated page (ChatPage and
 * MemoryPage). Displays the app name, a link to the Memory dashboard, and
 * the logout button with the current user's name.
 *
 * Layout: fixed to the top of the viewport so the content area below can
 * independently scroll. Height matches the --header-height CSS variable
 * (56px) so page-level layouts can offset their content correctly.
 *
 * Used by: src/pages/ChatPage.jsx, src/pages/MemoryPage.jsx.
 */

import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth.js";

/**
 * Header
 * Renders the top navigation bar.
 *
 * Parameters: none — reads user from AuthContext via useAuth().
 *
 * Returns: JSX.Element — a <header> fixed to the top of the viewport.
 *
 * Used by: src/pages/ChatPage.jsx, src/pages/MemoryPage.jsx.
 */
export default function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  /**
   * loggingOut state
   * Disables the logout button while the logout request is in flight to
   * prevent double-clicks. AuthContext.logout() navigates to /login when
   * done, so this state is automatically discarded.
   */
  const [loggingOut, setLoggingOut] = useState(false);

  /**
   * handleLogout
   * Calls the AuthContext logout action which clears the cookie and
   * navigates to /login. Shows a brief disabled state on the button.
   *
   * Parameters: none.
   * Returns: void.
   * Used by: the logout button's onClick handler.
   */
  async function handleLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      // AuthContext.logout() navigates away, so this runs only on error.
      setLoggingOut(false);
    }
  }

  return (
    <header style={styles.header}>
      {/* ── Left: logo / wordmark ─────────────────────────────────────── */}
      <button
        onClick={() => navigate("/chat")}
        style={styles.logo}
        aria-label="Go to chat"
      >
        {/*
          The accent dot before the wordmark is the signature design element
          carried into the header — one phosphor-green pixel of bioluminescence
          against the near-black surface.
        */}
        <span style={styles.logoDot} aria-hidden="true" />
        <span style={styles.logoText}>hipocampus</span>
      </button>

      {/* ── Right: nav links + user info ──────────────────────────────── */}
      <nav style={styles.nav} aria-label="Main navigation">
        {/*
          NavLink automatically applies the active class when the current
          path matches. We use inline styles instead of class names so the
          active state is explicit and doesn't depend on CSS specificity.
        */}
        <NavLink
          to="/chat"
          style={({ isActive }) =>
            isActive ? { ...styles.navLink, ...styles.navLinkActive } : styles.navLink
          }
        >
          Chat
        </NavLink>

        <NavLink
          to="/memory"
          style={({ isActive }) =>
            isActive ? { ...styles.navLink, ...styles.navLinkActive } : styles.navLink
          }
        >
          Memory
        </NavLink>

        {/* Separator */}
        <span style={styles.separator} aria-hidden="true" />

        {/* User name — display only, not a link */}
        {user && (
          <span style={styles.userName} title={`Logged in as ${user.name}`}>
            {user.name}
          </span>
        )}

        {/*
          Logout button.
          Uses a <button> not a link — it performs an action (clears cookie)
          rather than navigating to a resource.
        */}
        <button
          onClick={handleLogout}
          disabled={loggingOut}
          style={loggingOut ? { ...styles.logoutBtn, opacity: 0.5 } : styles.logoutBtn}
          aria-label="Log out"
        >
          {loggingOut ? "Logging out…" : "Log out"}
        </button>
      </nav>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

/**
 * styles
 * Inline style objects for the Header component.
 * Inline styles are used here (rather than CSS classes) because Header is
 * the only consumer and co-location makes the layout intent immediately clear.
 *
 * Used by: Header() JSX above.
 */
const styles = {
  header: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    height: "var(--header-height)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 var(--sp-6)",
    background: "var(--color-bg-surface)",
    borderBottom: "1px solid var(--color-border)",
    zIndex: 100,
    // Subtle blur so content scrolling under the header doesn't look harsh
    backdropFilter: "blur(8px)",
    WebkitBackdropFilter: "blur(8px)",
  },

  logo: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-2)",
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: 0,
  },

  logoDot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: "var(--color-accent)",
    flexShrink: 0,
    // Subtle glow to reinforce the phosphor-green signature
    boxShadow: "var(--shadow-accent-glow)",
  },

  logoText: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-md)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    letterSpacing: "-0.02em",
  },

  nav: {
    display: "flex",
    alignItems: "center",
    gap: "var(--sp-5)",
  },

  navLink: {
    fontFamily: "var(--font-body)",
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-medium)",
    color: "var(--color-text-secondary)",
    textDecoration: "none",
    transition: "color var(--transition-fast)",
    padding: "var(--sp-1) 0",
  },

  navLinkActive: {
    color: "var(--color-text-primary)",
    // A 2px accent underline marks the active page
    borderBottom: "2px solid var(--color-accent)",
    paddingBottom: "calc(var(--sp-1) - 2px)",
  },

  separator: {
    width: "1px",
    height: "16px",
    background: "var(--color-border)",
  },

  userName: {
    fontFamily: "var(--font-body)",
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-secondary)",
    maxWidth: "140px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },

  logoutBtn: {
    fontFamily: "var(--font-body)",
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-medium)",
    color: "var(--color-text-secondary)",
    background: "none",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm)",
    padding: "var(--sp-1) var(--sp-3)",
    cursor: "pointer",
    transition: "border-color var(--transition-fast), color var(--transition-fast)",
  },
};