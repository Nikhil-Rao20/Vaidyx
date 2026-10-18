// The root admin's guided set-up (five steps) and the department admin's People page.
import { expect, test } from "@playwright/test";
import { SIZES, runsFor, shoot, visit } from "../support/helpers";

test.describe("admin", () => {
  test("guided set-up", async ({ page }) => {
    test.skip(!runsFor("root_admin"));
    await visit(page, "/admin", { role: "root_admin" });
    await expect(page.getByRole("heading", { name: "Hospital set-up" })).toBeVisible();
    await shoot(page, "admin", "setup-open-step");
    for (const [index, name] of [[0, "1-hospital"], [1, "2-departments"], [2, "3-people"], [4, "5-board"]] as const) {
      await page.setViewportSize(SIZES[0]);
      await page.getByRole("complementary", { name: "Set-up so far" }).getByRole("button").nth(index).click();
      await shoot(page, "admin", `setup-${name}`, { sizes: [SIZES[0], SIZES[2]] });
    }
  });

  test("people", async ({ page }) => {
    test.skip(!runsFor("dept_admin"));
    await visit(page, "/people", { role: "dept_admin" });
    await expect(page.getByRole("heading", { name: "People" })).toBeVisible();
    await shoot(page, "admin", "people");
    await page.setViewportSize(SIZES[0]);
    await page.getByRole("button", { name: /Actions for Kiran Shetty/ }).click();
    await shoot(page, "admin", "people-actions", { sizes: [SIZES[0]], fullPage: false });
  });

  test("no permission", async ({ page }) => {
    test.skip(!runsFor("treating"));
    await visit(page, "/admin");
    await expect(page.getByText(/Only the root admin/)).toBeVisible();
    await shoot(page, "admin", "no-permission", { sizes: [SIZES[0]] });
  });
});
