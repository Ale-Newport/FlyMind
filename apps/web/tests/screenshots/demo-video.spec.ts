// Records the README demo video from the RUNNING app with the real FlyWire v783 dataset
// (not part of CI). Converted to docs/media/flymind-demo.gif by scripts/media/demo_gif.sh:
//   make dev                         # in one terminal (FlyWire v783 installed)
//   bash scripts/media/demo_gif.sh   # in another
import { expect, test } from "@playwright/test";
import fs from "node:fs";

test.use({
  viewport: { width: 1440, height: 864 },
  video: { mode: "on", size: { width: 1440, height: 864 } },
  // Full Chromium on the GPU: the default headless shell renders WebGL in software
  // (SwiftShader), far too slowly for 139k points.
  channel: "chromium",
  launchOptions: { args: ["--use-angle=metal", "--ignore-gpu-blocklist", "--enable-gpu"] },
});
test.setTimeout(300_000);

// Loading waits are cut out of the GIF: each scene's [start, end] (seconds into the
// video) is written to demo-segments.json next to the video.
test("demo tour: explorer, full-brain simulation, virtual fly in flight", async ({ page, request }, info) => {
  const t0 = Date.now();
  const segments: [number, number][] = [];
  let open = 0;
  const begin = () => { open = (Date.now() - t0) / 1000; };
  const end = () => { segments.push([open, (Date.now() - t0) / 1000]); };
  for (const s of await (await request.get("/api/sim/sessions")).json()) await request.delete(`/api/sim/sessions/${s.id}`);
  for (const s of await (await request.get("/api/fly/sessions")).json()) await request.delete(`/api/fly/sessions/${s.id}`);
  await page.addInitScript(() => window.localStorage.setItem("flymind-theme", "dark"));
  await page.addInitScript(() => window.localStorage.setItem("flymind-prefs", JSON.stringify({ state: { datasetId: "flywire_fafb_783", colorField: "super_class", pointSize: 2.2, opacity: 0.55 }, version: 0 })));

  // 1. Brain Explorer: all 139,255 FlyWire neurons; orbit the brain, then pick DNa02.
  await page.goto("/#/explorer");
  const canvas = page.getByTestId("brain-canvas");
  await expect(canvas).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(1500);
  begin();
  const box = (await canvas.boundingBox())!;
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  for (let i = 0; i <= 60; i++) { await page.mouse.move(cx + i * 6, cy + Math.sin(i / 10) * 25); await page.waitForTimeout(25); }
  await page.mouse.up();
  await page.waitForTimeout(600);
  await page.getByLabel("Search neurons").fill("DNa02");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByTestId("search-results").getByRole("button").first().click();
  await expect(page.getByTestId("neuron-panel")).toContainText("DNa02");
  await page.waitForTimeout(3500);
  end();

  // 2. Brain Simulator: whole-brain LIF model, sugar gustatory receptor neurons at 200 Hz.
  await page.goto("/#/simulator");
  await page.getByRole("radio", { name: "Full" }).click();
  await page.getByRole("button", { name: /Create session|Replace session/ }).click();
  await expect(page.getByTestId("sim-status")).toHaveText("ready", { timeout: 90_000 });
  await page.getByLabel("Neuron group").first().selectOption("sugar_grn_shiu");
  await page.getByLabel("Rate (Hz)").fill("200");
  await page.getByLabel(/^Stop \(ms/).fill("");
  await page.getByRole("button", { name: "Add stimulus" }).click();
  begin();
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await page.waitForTimeout(6000);
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page.waitForTimeout(300);
  end();

  // 3. Virtual Fly: NeuroMechFly in MuJoCo, taking off in the food arena.
  await page.goto("/#/fly");
  await page.getByLabel("Arena").selectOption("food");
  await page.getByRole("radio", { name: "Fly", exact: true }).click();
  await page.getByRole("button", { name: "Create fly session" }).click();
  await expect(page.getByRole("button", { name: "Start", exact: true })).toBeEnabled({ timeout: 90_000 });
  begin();
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await page.waitForTimeout(6500);
  end();
  fs.writeFileSync(info.outputPath("demo-segments.json"), JSON.stringify(segments));
});
