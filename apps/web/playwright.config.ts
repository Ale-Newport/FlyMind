import { defineConfig, devices } from "@playwright/test";

// E2E runs against an isolated backend whose data root contains only the SYNTHETIC
// fixture (built on start), so results are deterministic and need no downloads.
const API_PORT = 8010;
const WEB_PORT = 5180;

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "test-results/e2e-results.json" }]],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    viewport: { width: 1500, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1500, height: 900 } } }],
  webServer: [
    {
      command: `bash ../../scripts/setup/e2e_api.sh ${API_PORT}`,
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: `npx vite --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      env: { FLYMIND_API: `http://127.0.0.1:${API_PORT}`, VITE_WS_ORIGIN: `ws://127.0.0.1:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
