// Renders scripts/media/social_preview.html to docs/media/social-preview.png (1280x640),
// the image used as the GitHub social preview. Run from apps/web: node scripts/render-social-preview.mjs
import { chromium } from "@playwright/test";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 640 } });
await page.goto(pathToFileURL(path.resolve(here, "../../../scripts/media/social_preview.html")).href);
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(300);
await page.screenshot({ path: path.resolve(here, "../../../docs/media/social-preview.png") });
await browser.close();
