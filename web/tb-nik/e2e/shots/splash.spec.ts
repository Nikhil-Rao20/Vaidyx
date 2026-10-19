// The cinematic entrance after a sign-in: the reveal, the product name, the mark gliding into the top bar. Motion on for this
// spec (the suite otherwise runs with reduced motion), light and dark, laptop and phone.
import path from "node:path";
import { expect, test } from "@playwright/test";
import { MOCK, SHOTS, prepare } from "../support/helpers";

test.describe("splash", () => {
  test.skip(!MOCK, "the splash is taken with mocked answers");
  test.use({ reducedMotion: "no-preference" });

  for (const [theme, width, height] of [["light", 1366, 768], ["dark", 1366, 768], ["light", 390, 844]] as const) {
    test(`entrance ${theme} ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.addInitScript((t) => { try { sessionStorage.setItem("tbnik.splash", "1"); localStorage.setItem("tbnik.theme", t); } catch { /* none */ } }, theme);
      await prepare(page, { role: "treating" });
      await page.goto("/tb-nik/cases", { waitUntil: "domcontentloaded" });
      const splash = page.getByTestId("splash");
      await expect(splash).toBeVisible();
      await page.waitForTimeout(1100);
      await page.screenshot({ path: path.join(SHOTS, `splash-1-reveal-${theme}-${width}.png`) });
      await page.waitForTimeout(1300);
      await page.screenshot({ path: path.join(SHOTS, `splash-2-lock-${theme}-${width}.png`) });
      await expect(splash).toHaveAttribute("data-phase", "tagline", { timeout: 4000 });
      await page.waitForTimeout(900);
      await page.screenshot({ path: path.join(SHOTS, `splash-3-name-${theme}-${width}.png`) });
      await expect(splash).toHaveAttribute("data-phase", "morph", { timeout: 4000 });
      await page.waitForTimeout(380);
      await page.screenshot({ path: path.join(SHOTS, `splash-4-morph-${theme}-${width}.png`) });
      await expect(splash).toHaveCount(0, { timeout: 4000 });
      await page.screenshot({ path: path.join(SHOTS, `splash-5-app-${theme}-${width}.png`) });
    });
  }
});

test.describe("entrance after a sign-out", () => {
  test.skip(!MOCK, "mocked");
  test.use({ reducedMotion: "no-preference" });
  test("plays once on the sign-in page", async ({ page }) => {
    await page.addInitScript(() => { try { sessionStorage.setItem("tbnik.splash.out", "1"); } catch { /* none */ } });
    await prepare(page, { signedOut: true });
    await page.goto("/tb-nik/sign-in", { waitUntil: "domcontentloaded" });
    const e = page.getByTestId("signout-entrance");
    await expect(e).toBeVisible();
    await page.waitForTimeout(2200);
    await page.screenshot({ path: path.join(SHOTS, "signout-entrance-light-1366.png") });
    await expect(e).toHaveCount(0, { timeout: 6000 });
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForTimeout(800);
    await expect(page.getByTestId("signout-entrance")).toHaveCount(0);
  });
});
