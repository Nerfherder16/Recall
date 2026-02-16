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
      "/api": "http://192.168.50.19:8200",
      "/health": "http://192.168.50.19:8200",
      "/stats": "http://192.168.50.19:8200",
      "/search": "http://192.168.50.19:8200",
      "/memory": "http://192.168.50.19:8200",
      "/admin": "http://192.168.50.19:8200",
      "/ingest": "http://192.168.50.19:8200",
      "/events": "http://192.168.50.19:8200",
      "/observe": "http://192.168.50.19:8200",
      "/metrics": "http://192.168.50.19:8200",
    },
  },
});
