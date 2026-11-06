// Captures documentation screenshots from the RUNNING app with the real FlyWire v783
// dataset installed (not part of CI). Usage:
//   make dev            # in one terminal
//   cd apps/web && npx playwright test -c playwright.screenshots.config.ts
import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const DOCS = path.resolve(here, "../../../../docs/evidence/screenshots");
const PUBLIC = path.resolve(here, "../../public/screenshots");
const save = async (page: Page, name: string, landing?: string) => {
  await page.screenshot({ path: path.join(DOCS, `${name}.png`) });
  if (landing) await page.screenshot({ path: path.join(PUBLIC, `${landing}.png`) });
};

test.use({ viewport: { width: 1600, height: 960 } });
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("flymind-prefs", JSON.stringify({ state: { datasetId: "flywire_fafb_783", colorField: "super_class", pointSize: 2.2, opacity: 0.55 }, version: 0 })));
});

test("explorer with real neuron morphology", async ({ page }) => {
  await page.goto("/#/explorer");
  await expect(page.getByTestId("brain-canvas")).toBeVisible();
  await page.waitForTimeout(2500);
  await save(page, "explorer-flywire-783-overview");
  await page.getByLabel("Search neurons").fill("DNa02");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByTestId("search-results").getByRole("button").first().click();
  await expect(page.getByTestId("neuron-panel")).toContainText("DNa02");
  await expect(page.getByText(/Skeleton: /)).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(2000);
  await save(page, "explorer-flywire-783-dna02", "explorer");
});

test("full-brain simulation of sugar GRN activation", async ({ page, request }) => {
  for (const s of await (await request.get("/api/sim/sessions")).json()) await request.delete(`/api/sim/sessions/${s.id}`);
  await page.goto("/#/simulator");
  await page.getByRole("radio", { name: "full" }).click();
  await page.getByRole("button", { name: /Create session|Replace session/ }).click();
  await expect(page.getByTestId("sim-status")).toHaveText("ready", { timeout: 60_000 });
  await page.getByLabel("Neuron group").first().selectOption("sugar_grn_shiu");
  await page.getByLabel("Rate (Hz)").fill("200");
  await page.getByLabel(/^Stop \(ms/).fill(""); // blank = continuous
  await page.getByRole("button", { name: "Add stimulus" }).click();
  await page.getByRole("button", { name: "▶ Start" }).click();
  await page.waitForTimeout(5000);
  await page.getByRole("button", { name: "❚❚ Pause" }).click();
  await page.waitForTimeout(1500);
  await save(page, "simulator-flywire-783-sugar", "simulator");
  await page.goto("/#/explorer");
  await page.locator("#colorby").selectOption("activity");
  await page.waitForTimeout(3000);
  await save(page, "explorer-flywire-783-activity-overlay");
});

test("virtual fly in the food arena", async ({ page, request }) => {
  for (const s of await (await request.get("/api/sim/sessions")).json()) await request.delete(`/api/sim/sessions/${s.id}`);
  await page.goto("/#/fly");
  await page.getByLabel("Arena").selectOption("food");
  await page.getByRole("button", { name: "Create fly session" }).click();
  await expect(page.getByRole("button", { name: "▶ Start" })).toBeEnabled({ timeout: 60_000 });
  await page.getByRole("button", { name: "▶ Start" }).click();
  await page.waitForTimeout(7000);
  await page.getByRole("button", { name: "❚❚ Pause" }).click();
  await page.waitForTimeout(800);
  await save(page, "virtual-fly-food-arena", "fly");
});

test("reproduction result and dataset validation", async ({ page }) => {
  await page.goto("/#/experiments");
  await page.getByText("Sugar GRN -> MN9 (reproduction of Shiu et al. 2024)").first().click();
  await expect(page.getByTestId("expected-checks")).toBeVisible();
  await page.waitForTimeout(1500);
  await save(page, "experiment-reproduction-shiu2024");
  await page.goto("/#/datasets");
  await page.getByRole("button", { name: /Show provenance/ }).nth(1).click();
  await page.waitForTimeout(800);
  await save(page, "datasets-flywire-783");
});
