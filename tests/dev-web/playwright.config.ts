import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  workers: 1,
  timeout: 30_000,
  reporter: "list",
  outputDir: "../../test-results/dev-server",
  use: {
    baseURL: "http://127.0.0.1:5175",
  },
  webServer: {
    command: "cd ../../apps/studio-web && pnpm dev --port 5175 --strictPort",
    url: "http://127.0.0.1:5175/",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
