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
  });
});
