// Settings (profile, appearance, saved filters, notifications, security) and Activity (own; full log for the auditor).
import { expect, test } from "@playwright/test";
import { SIZES, runsFor, shoot, visit } from "../support/helpers";

test.describe("settings", () => {
  test("settings page", async ({ page }) => {
    test.skip(!runsFor("treating"));
    await visit(page, "/settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await shoot(page, "settings", "all");
    await visit(page, "/settings", { overrides: { "GET /api/tb/me/notifications": { status: 500 } } });
    await page.locator("#notifications").scrollIntoViewIfNeeded();
    await shoot(page, "settings", "notifications-error", { sizes: [SIZES[0]], fullPage: false, before: async (p) => { await p.locator("#notifications").scrollIntoViewIfNeeded(); } });
  });

  test("activity", async ({ page }) => {
    test.skip(!runsFor("treating"));
    await visit(page, "/activity");
    await expect(page.getByRole("heading", { name: "Activity" })).toBeVisible();
    await shoot(page, "activity", "mine", { sizes: [SIZES[0], SIZES[2]] });
    await visit(page, "/activity", { overrides: { "GET /api/tb/me/activity": { body: { events: [] } } } });
    await shoot(page, "activity", "empty", { sizes: [SIZES[0]] });
  });

  test("full log for the auditor", async ({ page }) => {
    test.skip(!runsFor("auditor"));
    await visit(page, "/activity", { role: "auditor" });
    await expect(page.getByRole("tab", { name: "Full log" })).toBeVisible();
    await shoot(page, "activity", "full-log", { sizes: [SIZES[0], SIZES[2]] });
  });
});
