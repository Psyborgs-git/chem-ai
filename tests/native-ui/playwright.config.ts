import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".", workers: 1, timeout: 30_000, reporter: [["list"],["html",{outputFolder:"../../.runtime/evidence/native/visual-report",open:"never"}]],
  outputDir: "../../test-results/native-ui",
  use: {
    baseURL: "http://127.0.0.1:5176", screenshot: "only-on-failure", trace: "retain-on-failure",
    ...(process.env.STUDIO_BROWSER_EXECUTABLE_PATH ? {launchOptions:{executablePath:process.env.STUDIO_BROWSER_EXECUTABLE_PATH}} : {}),
  },
  webServer: {command:"cd ../../apps/studio-web && pnpm dev --port 5176 --strictPort",url:"http://127.0.0.1:5176/",reuseExistingServer:false,timeout:120_000},
});
