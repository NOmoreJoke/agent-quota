import { defineConfig } from "@playwright/test";

const port = process.env.AQ_PLAYWRIGHT_PORT ?? "1420";
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "./output/playwright/results",
  reporter: [["list"], ["html", { outputFolder: "./output/playwright/report", open: "never" }]],
  use: {
    baseURL,
    colorScheme: "light",
    contextOptions: { reducedMotion: "reduce" },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `VITE_AQ_FIXTURE_MODE=1 pnpm dev --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
  },
});
