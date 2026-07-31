import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "./output/playwright/results",
  reporter: [["list"], ["html", { outputFolder: "./output/playwright/report", open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:1420",
    colorScheme: "light",
    contextOptions: { reducedMotion: "reduce" },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "VITE_AQ_FIXTURE_MODE=1 pnpm dev",
    url: "http://127.0.0.1:1420",
    reuseExistingServer: false,
  },
});
