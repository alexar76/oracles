import { test, expect } from "@playwright/test";

test.describe("Platon UMBRAL UI", () => {
  test("loads main application shell", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("platon-app")).toBeVisible();
    await expect(page.locator(".logo")).toContainText("UMBRAL");
  });

  test("renders 3D shadow canvas", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("shadow-canvas")).toBeVisible();
    await expect(page.locator("canvas")).toBeVisible({ timeout: 10000 });
  });

  test("shows live telemetry from WebSocket", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("metric-kappa")).not.toHaveText("—", {
      timeout: 15000,
    });
    await expect(page.getByTestId("metric-order")).not.toHaveText("—");
    await expect(page.getByTestId("metric-lyapunov")).not.toHaveText("—");
  });

  test("semantic steering updates kappa", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("metric-kappa")).not.toHaveText("—", {
      timeout: 15000,
    });
    const before = await page.getByTestId("metric-kappa").textContent();
    await page.getByTestId("steer-input").fill("figure-eight bleeding chaos");
    await page.getByTestId("steer-btn").click();
    await page.waitForTimeout(500);
    const after = await page.getByTestId("metric-kappa").textContent();
    expect(after).not.toBe(before);
  });

  test("dream button is clickable", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("dream-btn").click();
    await expect(page.getByTestId("dream-btn")).toBeVisible();
  });

  test("witness feed section exists", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("witness-feed")).toBeVisible();
  });

  test("footer shows aimarket capabilities", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".footer")).toContainText("AIMarket");
    await expect(page.locator(".oracle-badge")).toContainText("ORACLE");
  });

  test("agent feed panel exists", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("agent-feed")).toBeVisible();
  });

  test("ask panel exists and answers", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("ask-panel")).toBeVisible();
    await page.getByTestId("ask-input").fill("What is kappa?");
    await page.getByTestId("ask-send").click();
    await expect(page.getByTestId("ask-log")).toBeVisible({ timeout: 15000 });
  });

  test("renders fallback canvas when WebGL is unavailable", async ({ page }) => {
    await page.addInitScript(() => {
      const getContext = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (type, attrs) {
        if (
          type === "webgl" ||
          type === "webgl2" ||
          type === "experimental-webgl"
        ) {
          return null;
        }
        return getContext.call(this, type, attrs);
      };
    });
    await page.goto("/");
    await expect(page.getByTestId("platon-app")).toBeVisible({ timeout: 15000 });
    // WebGL blocked → ErrorBoundary or 2D mode
    const fallback = page.getByTestId("fallback-canvas");
    const holographic = page.getByTestId("render-mode");
    await expect(fallback.or(holographic)).toBeVisible();
    await expect(page.getByTestId("metric-kappa")).not.toHaveText("—", {
      timeout: 15000,
    });
  });
});
