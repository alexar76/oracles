// Capture oracle family landing + gallery for the monorepo README.
// Usage: npm run preview -- --port 5180 &  then  node scripts/capture-landing.mjs
import { chromium } from "playwright";
import { existsSync, mkdirSync, readdirSync, renameSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";

const UI = process.env.ORACLES_UI ?? "http://127.0.0.1:5180";
const ROOT = resolve(process.cwd(), "..");
const SHOTS = join(ROOT, "docs", "screenshots");
const RECS = join(ROOT, "docs", "recordings");
const MEDIA = join(process.cwd(), "public", "media");

mkdirSync(SHOTS, { recursive: true });
mkdirSync(RECS, { recursive: true });

const browser = await chromium.launch({ headless: false });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

await page.goto(UI + "/", { waitUntil: "networkidle" });
await page.getByTestId("home").waitFor({ state: "visible", timeout: 20000 });
await page.waitForTimeout(5000);
await page.screenshot({ path: join(SHOTS, "01-landing-hero.png") });

await page.evaluate(() => window.scrollTo(0, 420));
await page.waitForTimeout(800);
await page.screenshot({ path: join(SHOTS, "02-economy-flow.png") });

await page.evaluate(() => window.scrollTo(0, 900));
await page.waitForTimeout(1200);
await page.screenshot({ path: join(SHOTS, "03-oracle-cards.png") });

const scenes = ["chronos", "lattice", "murmuration", "lumen", "colony", "turing"];
for (let i = 0; i < scenes.length; i++) {
  const slug = scenes[i];
  await page.goto(`${UI}/?o=${slug}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(4500);
  await page.screenshot({ path: join(SHOTS, `${String(i + 4).padStart(2, "0")}-${slug}-scene.png`) });
}

await page.close();

const tmp = join(RECS, "_tmp");
if (existsSync(tmp)) rmSync(tmp, { recursive: true, force: true });
mkdirSync(tmp, { recursive: true });
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: tmp, size: { width: 1280, height: 720 } },
});
const vp = await ctx.newPage();
await vp.goto(UI + "/", { waitUntil: "networkidle" });
await vp.getByTestId("home").waitFor({ state: "visible", timeout: 20000 });
await vp.waitForTimeout(3500);
await vp.evaluate(() => window.scrollBy(0, 500));
await vp.waitForTimeout(2500);
await vp.evaluate(() => window.scrollBy(0, 600));
await vp.waitForTimeout(2500);
await vp.goto(`${UI}/?o=murmuration`, { waitUntil: "networkidle" });
await vp.waitForTimeout(5000);
await vp.goto(`${UI}/?o=chronos`, { waitUntil: "networkidle" });
await vp.waitForTimeout(4500);
await vp.close();
await ctx.close();

const vids = readdirSync(tmp).filter((f) => f.endsWith(".webm"));
if (vids.length) {
  renameSync(join(tmp, vids[0]), join(RECS, "oracle-portal.webm"));
  rmSync(tmp, { recursive: true, force: true });
  console.log("video -> docs/recordings/oracle-portal.webm");
}

await browser.close();
console.log("screenshots ->", SHOTS);
console.log("card loops (copy to public/media if stale):", MEDIA);
