import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Routine runs write screenshots to test-results/; set E2E_SCREENSHOT_DIR=docs/evidence/screenshots
// (relative to the repo root) to refresh the committed evidence images.
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const SHOTS = path.resolve(REPO, process.env.E2E_SCREENSHOT_DIR ?? "apps/web/test-results/screenshots");
const shot = (page: Page, name: string) => page.screenshot({ path: path.join(SHOTS, `e2e-${name}.png`) });

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("flymind-prefs", JSON.stringify({ state: { datasetId: "synthetic_demo_v1" }, version: 0 })));
});

test("navigation reaches every module and the backend is online", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("backend-status")).toContainText("backend online");
  await expect(page.getByTestId("system-status")).toContainText("online");
  for (const [label, heading] of [["Datasets", "Datasets"], ["Documentation", "Documentation"]] as const) {
    await page.getByRole("link", { name: label }).click();
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
  }
  await page.keyboard.press("Alt+2");
  await expect(page).toHaveURL(/#\/explorer/);
  await shot(page, "overview-nav");
});

test("datasets page shows provenance and passing validation", async ({ page }) => {
  await page.goto("/#/datasets");
  await expect(page.getByTestId("validation-synthetic_demo_v1")).toContainText("passed");
  await page.getByRole("button", { name: /Show provenance/ }).click();
  await expect(page.getByTestId("validation-table")).toContainText("unique neuron identifiers");
  await shot(page, "datasets");
});

test("explorer: search, inspect, and send a neuron to the simulator", async ({ page }) => {
  await page.goto("/#/explorer");
  await expect(page.getByTestId("brain-canvas")).toBeVisible();
  await page.getByLabel("Search neurons").fill("syn_DN_turn_L");
  await page.getByRole("button", { name: "Search" }).click();
  const results = page.getByTestId("search-results").getByRole("button");
  await expect(results).toHaveCount(5);
  await results.first().click();
  await expect(page.getByTestId("neuron-panel")).toContainText("syn_DN_turn_L");
  const rootId = (await page.getByTestId("neuron-root-id").textContent())!.trim();
  expect(rootId).toMatch(/^99\d{16}$/); // exact 18-digit ID string, never rounded
  await page.getByRole("tab", { name: /Inputs/ }).click();
  await expect(page.getByTestId("partners-table").locator("tbody tr").first()).toBeVisible();
  await expect(page.getByTestId("neuron-panel")).toContainText("Synthetic neurons have no morphology");
  await shot(page, "explorer-neuron");
  await page.getByRole("button", { name: "Stimulate in simulator" }).click();
  await expect(page).toHaveURL(/#\/simulator/);
  await expect(page.getByRole("status").filter({ hasText: "Pending from Explorer" })).toBeVisible();
});

test("simulator: demo session, stimulation, start/stop, live raster", async ({ page }) => {
  await page.goto("/#/simulator");
  await page.getByRole("button", { name: /Create session|Replace session/ }).click();
  await expect(page.getByTestId("sim-status")).toHaveText("ready");
  await page.getByLabel("Neuron group").first().selectOption("orn_attr_l");
  // continuous stimulus, so the live raster (last 500 ms) has spikes for the whole run
  await page.getByLabel(/^Stop \(ms/).fill("");
  await page.getByRole("button", { name: "Add stimulus" }).click();
  await expect(page.getByTestId("stimulus-list")).toContainText("orn_attr_l");
  // 1x real time so the live stream is observable; wait until the server applied it
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/control") && r.request().postData()?.includes("speed") === true),
    page.getByLabel("Speed").selectOption("1"),
  ]);
  await page.getByRole("button", { name: "▶ Start" }).click();
  await expect(page.getByTestId("raster")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("population")).toBeVisible();
  await page.getByRole("button", { name: "❚❚ Pause" }).click();
  await expect(page.getByTestId("sim-status")).toHaveText("paused");
  const t = await page.getByTestId("sim-time").textContent();
  expect(t).not.toBe("0.0 ms");
  await shot(page, "simulator");
  await page.getByRole("button", { name: "Step" }).click();
  await page.getByLabel("Raster window end").fill("400"); // scrub recorded activity
  await expect(page.getByTestId("raster")).toBeVisible();
  await page.getByRole("button", { name: "■ Stop" }).click();
  await expect(page.getByTestId("sim-status")).toHaveText("stopped");
  await page.getByRole("button", { name: "↺ Reset" }).click();
  await expect(page.getByTestId("sim-status")).toHaveText("ready");
});

test("virtual fly: baseline session streams MuJoCo poses", async ({ page }) => {
  await page.goto("/#/fly");
  await page.getByLabel("Arena").selectOption("obstacle");
  await page.getByRole("spinbutton").last().fill("1.5");
  await page.getByRole("button", { name: "Create fly session" }).click();
  await expect(page.getByRole("button", { name: "▶ Start" })).toBeEnabled({ timeout: 60_000 });
  await page.getByRole("button", { name: "▶ Start" }).click();
  await expect.poll(async () => parseFloat((await page.getByTestId("fly-time").textContent()) ?? "0"), { timeout: 60_000 }).toBeGreaterThan(0.3);
  await expect(page.getByTestId("fly-canvas")).toBeVisible();
  await shot(page, "virtual-fly");
});

test("experiments: run a template and inspect results", async ({ page }) => {
  await page.goto("/#/experiments");
  await page.getByLabel("Template").selectOption("intact_vs_lesioned");
  await page.getByRole("spinbutton").first().fill("2");
  await page.getByRole("button", { name: "Run experiment" }).click();
  await expect(page.getByTestId("job-status")).toContainText("done", { timeout: 90_000 });
  await expect(page.getByTestId("readout-bars")).toBeVisible();
  await expect(page.getByText("Model assumptions")).toBeVisible();
  await shot(page, "experiments");
});
