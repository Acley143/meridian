import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Same-origin dev proxy (ADR-0020): core-service carries no CORS
    // configuration, so the dashboard must never issue a cross-origin
    // request to it. The REST/SSE surface is versioned under /api/v1
    // (ADR-0021), so a single /api entry routes every current and future
    // endpoint root -- no per-prefix list to keep in sync.
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
