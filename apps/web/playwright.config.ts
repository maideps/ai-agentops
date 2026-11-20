import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  outputDir: "test-results/artifacts",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "off",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "node scripts/serve-static.mjs out 4173",
    url: "http://127.0.0.1:4173/",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
