/**
 * src/main.jsx
 *
 * Application entry point. Mounts the React tree into the #root div in
 * index.html. This is the only file that calls ReactDOM.createRoot().
 *
 * Provider order (outer → inner):
 *   StrictMode    — catches common mistakes in development (double-invokes
 *                   effects, checks deprecated APIs). Stripped in production.
 *   BrowserRouter — provides routing context. Must wrap AuthProvider because
 *                   AuthProvider uses useNavigate(), which requires a router.
 *   AuthProvider  — provides the auth state and actions to the entire tree.
 *   App           — the route definitions.
 *
 * Used by: index.html (via <script type="module" src="/src/main.jsx">).
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext.jsx";
import App from "./App.jsx";

// Global stylesheet — imported here so it applies before any component renders.
import "./index.css";

/**
 * Mount
 * Renders the full application tree into #root.
 * No parameters — reads the DOM element directly.
 * Used by: the browser (called as module entry point by Vite).
 */
createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>
);