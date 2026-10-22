// The department inbox: request cards (open, done), the Done popover, empty and error states.
import { expect, test } from "@playwright/test";
import { SIZES, runsFor, shoot, visit } from "../support/helpers";

test.describe("requests", () => {
  test.skip(!runsFor("supporting"));

  test("open and done", async ({ page }) => {
    await visit(page, "/requests", { role: "supporting" });
    await expect(page.getByRole("tab", { name: /Open/ })).toBeVisible();
    await shoot(page, "requests", "open");
    await page.setViewportSize(SIZES[0]);
    await page.getByRole("button", { name: "Done", exact: true }).first().click();
    await shoot(page, "requests", "done-popover", { sizes: [SIZES[0]], fullPage: false });
    await page.keyboard.press("Escape");
    await page.getByRole("tab", { name: "Done" }).click();
    await shoot(page, "requests", "done-tab", { sizes: [SIZES[0], SIZES[2]] });
  });

  test("empty and error", async ({ page }) => {
    await visit(page, "/requests", { role: "supporting", overrides: { "GET /api/tb/inbox": { body: { departments: [{ id: "radiology", name: "Radiology", group: "supporting", requests: [], open: 0, overdue: 0 }], open: 0, overdue: 0 } } } });
    await expect(page.getByText("No open requests")).toBeVisible();
    await shoot(page, "requests", "empty", { sizes: [SIZES[0], SIZES[2]] });
    await visit(page, "/requests", { role: "supporting", overrides: { "GET /api/tb/inbox": { status: 500 } } });
    await shoot(page, "requests", "error", { sizes: [SIZES[0]] });
  });
});
