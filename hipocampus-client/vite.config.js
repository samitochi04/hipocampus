import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Vite configuration for the Hipocampus React client.
 *
 * Two things this config is responsible for:
 *
 * 1. React plugin — enables JSX transform, Fast Refresh (hot module
 *    replacement for React components without losing state), and proper
 *    error overlays during development.
 *
 * 2. /api proxy — in development the client runs on :5173 and the backend
 *    runs on :8000. Browsers block cross-origin requests that don't have
 *    the right CORS headers AND credentials:include. Rather than fight that
 *    in dev, we proxy all /api/* requests through Vite's dev server to the
 *    backend. In production (Docker), nginx handles the proxy instead.
 *
 * Used by: `npm run dev` (dev server), `npm run build` (production bundle),
 *          `npm run preview` (local preview of the production bundle).
 */
export default defineConfig({
  plugins: [
    /**
     * @vitejs/plugin-react
     * Enables Babel-based Fast Refresh for React components.
     * No parameters needed — the defaults handle JSX and HMR correctly.
     * Used by: Vite's dev server transform pipeline.
     */
    react(),
  ],

  server: {
    proxy: {
      /**
       * /api proxy rule.
       * Any request the dev server receives at /api/* is forwarded to the
       * backend at localhost:8000. `changeOrigin: true` rewrites the Host
       * header so the backend sees its own origin, not localhost:5173.
       * `secure: false` skips TLS verification (the backend is plain HTTP).
       *
       * Parameters (set by Vite's proxy config, not called directly):
       *   target   — where to forward the request
       *   changeOrigin — rewrite Host header to match the target
       *   secure   — whether to verify TLS certificates on the target
       *
       * Used by: every api/* fetch call during local development.
       *          In production this proxy is replaced by nginx.conf.
       */
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },

  build: {
    /**
     * Output directory for the production bundle.
     * The Dockerfile's nginx stage copies from this directory.
     * Default is "dist" — kept as-is so the Dockerfile doesn't need a custom path.
     */
    outDir: "dist",
    /**
     * Emit source maps for production — useful for debugging deployed errors.
     * Set to false if bundle size is critical.
     */
    sourcemap: true,
  },
});