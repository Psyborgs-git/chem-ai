import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import relay from "vite-plugin-relay";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
import { helpContentPlugin } from "./scripts/help-content.mjs";

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
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  plugins: [
    tailwindcss(),
    helpContentPlugin(),
    react(),
    // graphql`` tag → generated artifact (reads relay.config.json).
    relay,
  ],
  test: {
    // Build-time content validation uses node:test, separately from browser components.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    maxWorkers: 4,
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy,
    // Native compiler output lives under this app but is not web source.
    watch: { ignored: ["**/src-tauri/**"] },
    fs: {
      // pnpm's workspace root is broader than this app. Keep private
      // runtime inputs, owner credentials and vault blobs off /@fs/.
      deny: [
        ".env", ".env.*", "*.{crt,pem,key,p12,pfx,cer,der}",
        ".npmrc", ".yarnrc.yml", "**/.git/**",
        "**/.runtime/**", "**/.local/**", "**/.venv/**",
      ],
    },
  },
  // vite preview serves the production build — the proxy must be
  // declared here too, it does not inherit server.proxy.
  preview: {
    host: "127.0.0.1",
    proxy,
  },
});
