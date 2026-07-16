import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// /api proxies to the FastAPI backend in dev; in production the backend
// serves the built frontend from the same origin (single Catalyst container).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
