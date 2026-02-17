import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/dashboard/",
  build: {
    outDir: "../src/api/static/dashboard",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8200",
      "/health": "http://localhost:8200",
      "/stats": "http://localhost:8200",
      "/search": "http://localhost:8200",
      "/memory": "http://localhost:8200",
      "/admin": "http://localhost:8200",
      "/ingest": "http://localhost:8200",
      "/events": "http://localhost:8200",
      "/observe": "http://localhost:8200",
      "/metrics": "http://localhost:8200",
    },
  },
});
