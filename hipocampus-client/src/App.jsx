/**
 * src/App.jsx
 *
 * Top-level route definitions for the entire application.
 * Uses React Router v6's nested route API so ProtectedRoute wraps the
 * authenticated routes without repeating the guard on every page.
 *
 * Route map:
 *   /              → redirect to /register (entry point for new users)
 *   /register      → RegisterPage   (public)
 *   /login         → LoginPage      (public)
 *   /chat          → ChatPage       (protected — requires valid session)
 *   /memory        → MemoryPage     (protected — requires valid session)
 *   *              → redirect to /register (catch-all for unknown paths)
 *
 * Used by: src/main.jsx.
 */

import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/layout/ProtectedRoute.jsx";
import RegisterPage from "./pages/RegisterPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import MemoryPage from "./pages/MemoryPage.jsx";

/**
 * App
 * Renders the route tree. No state, no side-effects — purely declarative.
 *
 * Parameters: none.
 * Returns: JSX.Element — the Routes tree.
 * Used by: src/main.jsx.
 */
export default function App() {
  return (
    <Routes>
      {/* ── Root redirect ─────────────────────────────────────────────── */}
      {/*
        New users land on /register. Returning users with a valid cookie will
        be caught by ProtectedRoute's /me check and redirected from /register
        to /chat by the RegisterPage's own useEffect if already logged in.
        Keeping /register as the default avoids a flash of the login page.
      */}
      <Route path="/" element={<Navigate to="/register" replace />} />

      {/* ── Public routes ─────────────────────────────────────────────── */}
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/login" element={<LoginPage />} />

      {/* ── Protected routes ──────────────────────────────────────────── */}
      {/*
        ProtectedRoute renders an Outlet when authenticated, redirects to
        /login when not, and shows a loading dot while checkSession() runs.
        All children inherit this guard automatically.
      */}
      <Route element={<ProtectedRoute />}>
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/memory" element={<MemoryPage />} />
      </Route>

      {/* ── Catch-all ─────────────────────────────────────────────────── */}
      <Route path="*" element={<Navigate to="/register" replace />} />
    </Routes>
  );
}