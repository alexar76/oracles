#!/usr/bin/env node
/**
 * Capture embed-mode 3D scenes for all 17 oracles → docs/recordings/loops/*.gif
 * Uses screenshot frames (Playwright recordVideo breaks WebGL on macOS headless).
 *
 * Usage:
 *   cd frontend && npm run build && npm run preview -- --port 5180 &
 *   node scripts/capture-card-loops.mjs
 *   SLUGS=lumen,gauss node scripts/capture-card-loops.mjs
 */
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = resolve(FRONTEND, "..");
const UI = process.env.ORACLES_UI ?? "http://127.0.0.1:5180";
const LOOPS = join(ROOT, "docs", "recordings", "loops");
const MEDIA = join(FRONTEND, "public", "media");
const TMP = join(LOOPS, "_tmp");
const FPS = 10;
const FRAMES = 60; // 6s loop

const ALL_SLUGS = [
  "platon",
  "chronos",
  "lattice",
  "murmuration",
  "lumen",
  "colony",
  "turing",
  "percola",
  "fermat",
  "ablation",
  "landauer",
  "sortes",
  "gauss",
  "aestus",
  "betti",
  "kantor",
  "fourier",
];

const AMBIENT = new Set(["percola", "fermat", "ablation", "landauer"]);
const SLUGS = process.env.SLUGS
  ? process.env.SLUGS.split(",").map((s) => s.trim()).filter(Boolean)
  : ALL_SLUGS;

mkdirSync(LOOPS, { recursive: true });
mkdirSync(MEDIA, { recursive: true });

const BROWSER_ARGS = [
  "--enable-webgl",
  "--ignore-gpu-blocklist",
  "--use-gl=angle",
  "--use-angle=metal",
];

async function waitForScene(page, slug) {
  if (AMBIENT.has(slug)) {
    await page.locator("iframe.ambient-frame").waitFor({ state: "visible", timeout: 60000 });
    await page.waitForTimeout(3000);
    return;
  }
  await page.locator("canvas").first().waitFor({ state: "visible", timeout: 90000 });
  for (let i = 0; i < 40; i++) {
    const shot = await page.screenshot({ type: "jpeg", quality: 55 });
    if (shot.length > 28000) break;
    await page.waitForTimeout(500);
  }
  await page.waitForTimeout(1500);
}

function framesToGif(framesDir, gifPath) {
  execFileSync(
    "ffmpeg",
    [
      "-y",
      "-framerate",
      String(FPS),
      "-i",
      join(framesDir, "frame_%03d.png"),
      "-vf",
      "scale=400:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse",
      "-loop",
      "0",
      gifPath,
    ],
    { stdio: "inherit" }
  );
}

function framesToWebm(framesDir, webmPath) {
  execFileSync(
    "ffmpeg",
    [
      "-y",
      "-framerate",
      String(FPS),
      "-i",
      join(framesDir, "frame_%03d.png"),
      "-c:v",
      "libvpx",
      "-b:v",
      "900k",
      "-pix_fmt",
      "yuv420p",
      webmPath,
    ],
    { stdio: "pipe" }
  );
}

const browser = await chromium.launch({
  headless: true,
  channel: "chrome",
  args: BROWSER_ARGS,
});

for (const slug of SLUGS) {
  const slugTmp = join(TMP, slug);
  if (existsSync(slugTmp)) rmSync(slugTmp, { recursive: true, force: true });
  mkdirSync(slugTmp, { recursive: true });

  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const gif = join(LOOPS, `${slug}.gif`);
  const mediaWebm = join(MEDIA, `${slug}.webm`);

  try {
    await page.goto(`${UI}/?o=${slug}&embed=1`, { waitUntil: "load", timeout: 60000 });
    await waitForScene(page, slug);

    for (let i = 0; i < FRAMES; i++) {
      const frame = join(slugTmp, `frame_${String(i).padStart(3, "0")}.png`);
      await page.screenshot({ path: frame, type: "png" });
      await page.waitForTimeout(1000 / FPS);
    }

    framesToGif(slugTmp, gif);
  } catch (e) {
    console.error(`  ✗ ${slug}: ${e.message}`);
  }

  await page.close();

  try {
    if (existsSync(gif)) {
      const gifKb = Math.round(statSync(gif).size / 1024);
      if (gifKb < 20) {
        console.error(`  ✗ ${slug}: gif too small (${gifKb} KiB)`);
      } else {
        console.log(`  ✓ ${slug}.gif (${gifKb} KiB)`);
      }
    }
    const firstFrame = join(slugTmp, "frame_000.png");
    if (existsSync(firstFrame)) {
      try {
        framesToWebm(slugTmp, mediaWebm);
      } catch {
        /* optional webm fallback */
      }
    }
  } catch (e) {
    console.error(`  ✗ ${slug} export: ${e.message}`);
  }

  rmSync(slugTmp, { recursive: true, force: true });
}

if (existsSync(TMP)) rmSync(TMP, { recursive: true, force: true });
await browser.close();
console.log(`Done → ${LOOPS}`);
