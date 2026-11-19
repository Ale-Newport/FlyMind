import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// Automated WCAG 2.1 A/AA checks (axe-core) on every page, in both colour themes.
// Fails on serious and critical violations. The WebGL canvases are excluded: axe cannot
// inspect their contents, and they carry their own labels and text alternatives.
const PAGES = [
  ["overview", "/", "Overview"],
  ["explorer", "/#/explorer", "Brain explorer"],
  ["simulator", "/#/simulator", "Brain simulator"],
  ["virtual fly", "/#/fly", "Virtual fly"],
  ["experiments", "/#/experiments", "Experiments"],
  ["datasets", "/#/datasets", "Datasets"],
  ["documentation", "/#/docs", "Documentation"],
] as const;

for (const theme of ["dark", "light"] as const) {
  test.describe(`accessibility (${theme} theme)`, () => {
    test.skip(({ browserName }) => browserName !== "chromium", "axe rules do not depend on the browser; run once");
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((t) => {
        window.localStorage.setItem("flymind-theme", t);
        window.localStorage.setItem("flymind-prefs", JSON.stringify({ state: { datasetId: "synthetic_demo_v1" }, version: 0 }));
      }, theme);
    });

    for (const [name, url, nav] of PAGES) {
      test(`${name} has no serious or critical axe violations`, async ({ page }) => {
        await page.goto(url);
        await expect(page.getByRole("link", { name: nav, exact: true })).toHaveAttribute("aria-current", "page");
        await expect(page.getByTestId("backend-status")).toContainText("backend online");
        await page.waitForLoadState("networkidle");
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .exclude("canvas")
          .analyze();
        const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        const report = blocking.map((v) => `${v.id} (${v.impact}): ${v.help}\n  ${v.nodes.slice(0, 5).map((n) => n.target.join(" ")).join("\n  ")}`).join("\n");
        expect(blocking, report).toEqual([]);
      });
    }
  });
}
