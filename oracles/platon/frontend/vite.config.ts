/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: process.env.VITE_BASE_PATH || "/",
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      "/api": "http://127.0.0.1:9200",
      "/ws": { target: "ws://127.0.0.1:9200", ws: true },
      "/.well-known": "http://127.0.0.1:9200",
      "/ai-market": "http://127.0.0.1:9200",
    },
  },
  test: {
    // Playwright specs under tests/e2e/ run via `npm run test:ui`, not vitest.
    exclude: ["node_modules/**", "tests/e2e/**", "dist/**"],
  },
});
