// New Case File: patient lookup (found, similar registrations, existing Case File), cancer picker, logistics, the live fetch.
import { expect, test } from "@playwright/test";
import { MOCK, SIZES, runsFor, shoot, visit } from "../support/helpers";

test.describe("new case file", () => {
  test.skip(!runsFor("treating"));

  test("steps", async ({ page }) => {
    await visit(page, "/cases/new");
    await expect(page.getByRole("heading", { name: "New Case File" })).toBeVisible();
    await shoot(page, "newcase", "1-empty", { sizes: [SIZES[0], SIZES[2]] });
    await page.getByLabel(/UHID, IP No/).fill(MOCK ? "VXH/2026/000140" : (process.env.TBNIK_UHID || "VXH/2026/000140"));
    await page.getByRole("button", { name: "Look up" }).click();
    await expect(page.getByText("Registration found")).toBeVisible({ timeout: 20_000 });
    await shoot(page, "newcase", "1-found");
    await page.getByRole("button", { name: /Continue/ }).click();
    await expect(page.getByRole("heading", { name: "Which cancer" })).toBeVisible();
    await shoot(page, "newcase", "2-picker");
    await page.getByRole("radio", { name: /Breast/ }).first().click();
    await page.getByText("Early (operable), as recorded").click();
    await shoot(page, "newcase", "2-picked", { sizes: [SIZES[0], SIZES[2]] });
    await page.getByRole("radio", { name: /Ovary/ }).first().click();
    await shoot(page, "newcase", "2-no-checklist", { sizes: [SIZES[0]] });
    await page.getByRole("radio", { name: /Breast/ }).first().click();
    await page.getByText("Early (operable), as recorded").click();
    await page.getByRole("button", { name: /Continue/ }).click();
    await expect(page.getByRole("heading", { name: "Logistics" })).toBeVisible();
    await page.getByRole("radio", { name: /Urgency 4/ }).click();
    await shoot(page, "newcase", "3-logistics");
    if (!MOCK) return; // a real run stops here: it never creates a Case File
    await page.getByRole("button", { name: /Create and fetch records/ }).click();
    await expect(page.locator("#main").getByText("Case File created")).toBeVisible();
    await shoot(page, "newcase", "4-fetching", { sizes: [SIZES[0], SIZES[2]] });
  });

  test("lookup errors", async ({ page }) => {
    await visit(page, "/cases/new?identifier=VXH%2F2026%2F999999", { overrides: { "GET /api/tb/his/lookup": { body: { found: false, identifier: "VXH/2026/999999" } } } });
    await expect(page.getByText(/Nothing found for/)).toBeVisible();
    await shoot(page, "newcase", "1-not-found", { sizes: [SIZES[0], SIZES[2]] });
    await visit(page, "/cases/new?identifier=VXH%2F2026%2F000140", { overrides: { "GET /api/tb/his/lookup": { status: 502, body: { detail: "The hospital system did not answer: timeout" } } } });
    await shoot(page, "newcase", "1-his-down", { sizes: [SIZES[0]] });
  });
});
