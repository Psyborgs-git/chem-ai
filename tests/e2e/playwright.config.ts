import { defineConfig } from "@playwright/test";

// Browser journeys (§25.1 e2e tier). Two servers: the real FastAPI
// backend on 8790 (isolated `studio_e2e` database) and a production
// `vite preview` build on 4173 proxying to it.
export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4173",
  },
  webServer: [
    {
      command: "cd ../.. && bash tests/e2e/serve.sh",
      url: "http://127.0.0.1:8790/healthz",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command:
        "cd ../../apps/studio-web && pnpm build && VITE_API_TARGET=http://127.0.0.1:8790 pnpm preview --port 4173 --host 127.0.0.1",
      url: "http://127.0.0.1:4173/dev/components",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
