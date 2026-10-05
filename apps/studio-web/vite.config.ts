import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import relay from "vite-plugin-relay";

// node types are not a workspace dep; the config file runs in node.
declare const process: { env: Record<string, string | undefined> };

// Loopback dev server (E04): proxies API calls to the FastAPI backend.
// Team/LAN exposure requires real auth + TLS — not configured here.
const apiTarget = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8787";
const proxy = {
  "/api": apiTarget,
  "/graphql": apiTarget,
};

export default defineConfig({
  plugins: [
    react(),
    // graphql`` tag → generated artifact (reads relay.config.json).
    relay,
  ],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy,
  },
  // vite preview serves the production build — the proxy must be
  // declared here too, it does not inherit server.proxy.
  preview: {
    host: "127.0.0.1",
    proxy,
  },
});
