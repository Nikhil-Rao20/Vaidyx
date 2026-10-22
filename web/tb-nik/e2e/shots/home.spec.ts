// Homes per role: treating (list, filters, waiting strip), resident (own proposals), coordinator (next meeting, ready, chase),
// supporting (request cards); empty, error and loading states.
import { expect, test } from "@playwright/test";
import { SIZES, runsFor, shoot, visit } from "../support/helpers";

test.describe("home", () => {
  test("treating doctor", async ({ page }) => {
    test.skip(!runsFor("treating"));
    await visit(page, "/home");
    await expect(page.getByRole("region", { name: "Case Files" })).toBeVisible();
    await shoot(page, "home", "treating");
    await page.setViewportSize(SIZES[0]);
    await page.getByRole("button", { name: /^Filters/ }).click();
    await shoot(page, "home", "filter-open", { sizes: [SIZES[0]], fullPage: false });
    await page.keyboard.press("Escape");
    await page.getByRole("searchbox").first().fill("118");
    await shoot(page, "home", "search", { sizes: [SIZES[0]], fullPage: false });
    await visit(page, "/cases?urgency=5,4&status=needs_me,waiting_department");
    await shoot(page, "home", "filtered", { sizes: [SIZES[0], SIZES[2]] });
  });

  test("empty, error, loading", async ({ page }) => {
    test.skip(!runsFor("treating"));
    await visit(page, "/home", { overrides: { "GET /api/tb/case-list": { body: { cases: [], filters: {} } }, "GET /api/tb/waiting": { body: { items: [] } } } });
    await expect(page.getByText("No Case Files yet")).toBeVisible();
    await shoot(page, "home", "empty");
    await visit(page, "/home", { overrides: { "GET /api/tb/case-list": { status: 500 } } });
    await expect(page.getByText("The server could not answer").first()).toBeVisible();
    await shoot(page, "home", "error", { sizes: [SIZES[0], SIZES[2]] });
    await visit(page, "/home", { overrides: { "GET /api/tb/case-list": { status: 404, body: { detail: "Not Found" } } } });
    await shoot(page, "home", "not-built", { sizes: [SIZES[0]] });
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await visit(page, "/home", { overrides: { "GET /api/tb/case-list": { delayMs: 30_000 } } });
    await shoot(page, "home", "loading", { sizes: [SIZES[0], SIZES[2]], fullPage: false });
  });

  test("resident", async ({ page }) => {
    test.skip(!runsFor("resident"));
    await visit(page, "/home", { role: "resident" });
    await expect(page.getByText("Your proposals")).toBeVisible();
    await shoot(page, "home", "resident", { sizes: [SIZES[0], SIZES[2]] });
  });

  test("coordinator", async ({ page }) => {
    test.skip(!runsFor("coordinator"));
    await visit(page, "/home", { role: "coordinator" });
    await expect(page.getByRole("region", { name: "Next meeting" })).toBeVisible();
    await shoot(page, "home", "coordinator");
  });

  test("supporting doctor", async ({ page }) => {
    test.skip(!runsFor("supporting"));
    await visit(page, "/home", { role: "supporting" });
    await expect(page.getByRole("heading", { name: /requests/i }).first()).toBeVisible();
    await shoot(page, "home", "supporting");
  });
});
