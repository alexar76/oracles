// Capture the gallery screenshots + a video of the 32D structure.
// Usage: node scripts/gallery.mjs  (backend on :9200, vite on :5174 must be up)
import { chromium } from "@playwright/test";
import { existsSync, mkdirSync, readdirSync, renameSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";

const UI = "http://127.0.0.1:5174";
const ROOT = resolve(process.cwd(), "..");
const SHOTS = join(ROOT, "docs", "screenshots");
const RECS = join(ROOT, "docs", "recordings");
mkdirSync(SHOTS, { recursive: true });
mkdirSync(RECS, { recursive: true });

// Headed on macOS uses the real GPU -> the fbm nebula shader renders reliably
// (headless SwiftShader is slow/flaky for heavy WebGL).
const browser = await chromium.launch({ headless: false });

// --- screenshots ---
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto(UI, { waitUntil: "networkidle" });
await page.getByTestId("metric-kappa").waitFor({ state: "visible", timeout: 15000 }).catch(() => {});
await page.waitForTimeout(6000); // let the cosmos animate & oscillators populate

await page.screenshot({ path: join(SHOTS, "01-main-view.png") });
await page.screenshot({ path: join(SHOTS, "05-cosmos.png") });

const shot = async (testidOrSel, file) => {
  const loc = testidOrSel.startsWith(".")
    ? page.locator(testidOrSel)
    : page.getByTestId(testidOrSel);
  if (await loc.count()) await loc.first().screenshot({ path: join(SHOTS, file) });
};
await shot("metrics-panel", "02-telemetry.png");
await shot(".steer-form", "03-steering.png");
await shot("witness-feed", "04-witnesses.png");
await page.close();

// --- video of the 32D structure ---
const tmp = join(RECS, "_tmp");
if (existsSync(tmp)) rmSync(tmp, { recursive: true, force: true });
mkdirSync(tmp, { recursive: true });
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: tmp, size: { width: 1280, height: 720 } },
});
const vp = await ctx.newPage();
await vp.goto(UI, { waitUntil: "networkidle" });
await vp.getByTestId("metric-kappa").waitFor({ state: "visible", timeout: 15000 }).catch(() => {});
await vp.waitForTimeout(4000);
// rotate Stiefel projection so the wireframe icosahedron orbits visibly
if (await vp.getByRole("button", { name: "θ₁=0.3" }).count()) {
  await vp.getByRole("button", { name: "θ₁=0.3" }).click();
  await vp.waitForTimeout(1500);
  await vp.getByRole("button", { name: "θ₂=2.0" }).click();
  await vp.waitForTimeout(1500);
}
if (await vp.getByTestId("steer-input").count()) {
  await vp.getByTestId("steer-input").fill("entropy cathedral at criticality");
  await vp.getByTestId("steer-btn").click();
}
await vp.waitForTimeout(3000);
if (await vp.getByTestId("dream-btn").count()) await vp.getByTestId("dream-btn").click();
await vp.waitForTimeout(3500);
await vp.close();
await ctx.close();

const vids = readdirSync(tmp).filter((f) => f.endsWith(".webm"));
if (vids.length) {
  renameSync(join(tmp, vids[0]), join(RECS, "platon-cosmos.webm"));
  rmSync(tmp, { recursive: true, force: true });
  console.log("video -> docs/recordings/platon-cosmos.webm");
}
await browser.close();
console.log("screenshots ->", SHOTS);
