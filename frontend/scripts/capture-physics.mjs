// Record the ambient physics-oracle scenes to card-loop webms (like the first 7).
// Usage (from oracles/frontend):  node scripts/capture-physics.mjs
import { chromium } from "playwright";
import { existsSync, mkdirSync, readdirSync, renameSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND = resolve(dirname(fileURLToPath(import.meta.url)), ".."); // .../oracles/frontend
const ORACLES = resolve(FRONTEND, "..", "oracles"); // .../oracles/oracles
const MEDIA = join(FRONTEND, "public", "media");
mkdirSync(MEDIA, { recursive: true });

const slugs = ["percola", "fermat", "ablation", "landauer"];
const browser = await chromium.launch({ headless: true });
for (const slug of slugs) {
  const scene = join(ORACLES, slug, "frontend", "index.html"); // the ambient fullscreen canvas
  if (!existsSync(scene)) {
    console.log("skip (missing scene):", slug);
    continue;
  }
  const tmp = join(MEDIA, `_tmp_${slug}`);
  if (existsSync(tmp)) rmSync(tmp, { recursive: true, force: true });
  mkdirSync(tmp, { recursive: true });
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: tmp, size: { width: 1280, height: 720 } },
    deviceScaleFactor: 1,
  });
  const page = await ctx.newPage();
  await page.goto("file://" + scene, { waitUntil: "load" });
  await page.waitForTimeout(9000); // ~9s of the loop
  await page.close();
  await ctx.close();
  const vids = readdirSync(tmp).filter((f) => f.endsWith(".webm"));
  if (vids.length) {
    renameSync(join(tmp, vids[0]), join(MEDIA, `${slug}.webm`));
    console.log("wrote media/" + slug + ".webm");
  } else {
    console.log("NO video produced for", slug);
  }
  rmSync(tmp, { recursive: true, force: true });
}
await browser.close();
console.log("done");
