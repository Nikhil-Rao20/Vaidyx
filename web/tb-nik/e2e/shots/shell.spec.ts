// The shell: top bar, Dock (390 wide), bell, profile menu, action search, the error page and the offline banner.
import { expect, test } from "@playwright/test";
import { MOCK, SIZES, runsFor, shoot, visit, watchConsole } from "../support/helpers";

test.describe("shell", () => {
  test.skip(!runsFor("treating"), "for the treating doctor's login");

  test("top bar, bell, profile menu, search", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/home");
    await expect(page.getByRole("navigation", { name: "Main" }).first()).toBeVisible();
    await shoot(page, "shell", "home");
    await page.setViewportSize(SIZES[0]);
    await page.getByRole("button", { name: /Notifications/ }).click();
    await shoot(page, "shell", "bell-open", { sizes: [SIZES[0], SIZES[2]], fullPage: false });
    await page.keyboard.press("Escape");
    await page.setViewportSize(SIZES[0]);
    await page.getByRole("button", { name: /Your menu/ }).click();
    await shoot(page, "shell", "profile-menu", { sizes: [SIZES[0]], fullPage: false });
    await page.keyboard.press("Escape");
    await page.setViewportSize(SIZES[0]);
    await page.getByRole("combobox", { name: /Search Case Files/ }).first().fill("Lakshmi");
    await shoot(page, "shell", "search", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });

  test("error pages and offline banner", async ({ page }) => {
    await visit(page, "/no-such-page");
    await expect(page.getByText("This page does not exist")).toBeVisible();
    await shoot(page, "shell", "404", { fullPage: false });
    await visit(page, "/home");
    await page.evaluate(() => { Object.defineProperty(navigator, "onLine", { configurable: true, get: () => false }); window.dispatchEvent(new Event("offline")); });
    await expect(page.getByText(/You are offline/)).toBeVisible();
    await shoot(page, "shell", "offline", { sizes: [SIZES[0], SIZES[2]], fullPage: false });
  });

  test("not signed in goes to sign-in", async ({ page }) => {
    test.skip(!MOCK, "mock mode only (a real session would stay signed in)");
    await visit(page, "/home", { signedOut: true });
    await expect(page).toHaveURL(/\/tb-nik\/sign-in/);
  });
});
