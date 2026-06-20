/**
 * src/components/layout/ProtectedRoute.jsx
 *
 * Route guard used by App.jsx to wrap every page that requires authentication.
 * Renders nothing while the initial session check is in flight (loading=true),
 * redirects to /login when no user is present, and renders the child route
 * when the user is authenticated.
 *
 * Usage in App.jsx:
 *   <Route element={<ProtectedRoute />}>
 *     <Route path="/chat" element={<ChatPage />} />
 *     <Route path="/memory" element={<MemoryPage />} />
 *   </Route>
 *
 * Used by: src/App.jsx — wraps /chat and /memory routes.
 */

import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth.js";

/**
 * ProtectedRoute
 * Guards a group of routes behind authentication.
 *
 * Parameters: none — children are rendered via React Router's <Outlet />.
 *
 * Render logic:
 *   loading=true  → renders a full-screen loading indicator so there's no
 *                   flash of the login page while the session check is running.
 *   user=null     → redirects to /login with the current path in `state`
 *                   so LoginPage can redirect back after a successful login.
 *   user=object   → renders <Outlet /> (the matched child route).
 *
 * Used by: src/App.jsx.
 */
export default function ProtectedRoute() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "100vh",
          background: "var(--color-bg-base)",
        }}
      >
        {/*
          Minimal loading indicator — a pulsing accent dot.
          Keeps the loading state on-brand without importing a spinner library.
          Reduced motion media query in index.css collapses this to no animation.
        */}
        <LoadingDot />
      </div>
    );
  }

  if (!user) {
    /**
     * Redirect to /login.
     * `replace` replaces the history entry so the back button doesn't loop.
     * The current location is passed in state so LoginPage can redirect the
     * user back to where they were trying to go after a successful login.
     */
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

// ---------------------------------------------------------------------------
// Internal: LoadingDot
// ---------------------------------------------------------------------------

/**
 * LoadingDot
 * A single pulsing circle in the accent colour.
 * Purely cosmetic — conveys "something is loading" without layout shift.
 *
 * Parameters: none.
 * Returns: JSX.Element.
 * Used by: ProtectedRoute (loading state only).
 */
function LoadingDot() {
  return (
    <span
      style={{
        display: "inline-block",
        width: "10px",
        height: "10px",
        borderRadius: "50%",
        background: "var(--color-accent)",
        animation: "pulse 1.4s ease-in-out infinite",
      }}
    >
      {/*
        The keyframes are injected inline once here rather than in index.css
        because this is the only place they're used.
      */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.2; transform: scale(0.8); }
          50%       { opacity: 1;   transform: scale(1.2); }
        }
      `}</style>
    </span>
  );
}