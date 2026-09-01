import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Same-origin dev proxy (ADR-0020): core-service carries no CORS
    // configuration, so the dashboard must never issue a cross-origin
    // request to it. core-service serves /portfolios/... at its root, with
    // no /api prefix, so no rewrite is applied here.
    proxy: {
      "/portfolios": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
