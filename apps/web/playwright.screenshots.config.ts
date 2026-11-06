import { defineConfig, devices } from "@playwright/test";

// Screenshots of the running dev servers (`make dev`) with real data; not run in CI.
export default defineConfig({
  testDir: "./tests/screenshots",
  timeout: 180_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: process.env.FLYMIND_URL ?? "http://127.0.0.1:5173" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
