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
