// The public landing page (/tb-nik): the hero at every size, the whole page on a laptop and a phone, the phone menu, and the
// signed-in variant of the actions. Mock mode only (nothing is sent anywhere).
import { expect, test } from "@playwright/test";
import { MOCK, SIZES, shoot, visit, watchConsole } from "../support/helpers";

test.describe("landing", () => {
  test.skip(!MOCK, "the landing page is taken with mocked answers");

  test("visitor", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/", { signedOut: true });
    await expect(page.getByTestId("landing-hero")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("The Tumour Board");
    await expect(page.getByTestId("landing-signin")).toHaveText(/Sign in/);
    await shoot(page, "landing", "hero", { fullPage: false, themes: ["light"], before: (pg) => pg.waitForTimeout(2600) });
    await shoot(page, "landing", "full", { fullPage: true, sizes: [SIZES[0], SIZES[2]], themes: ["light"] });
    // the phone menu
    await page.setViewportSize(SIZES[2]);
    await page.getByRole("button", { name: "Open the menu" }).click();
    await expect(page.getByRole("navigation", { name: "Sections" }).last()).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${process.env.TBNIK_SHOTS ?? "../../docs/ui/build/shots"}/landing-menu-light-390.png` });
    await page.getByRole("button", { name: "Close the menu" }).click();
    // every section is there
    for (const id of ["how", "sources", "roles", "safety", "team", "tanuh"]) await expect(page.locator(`#${id}`)).toHaveCount(1);
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("signed in", async ({ page }) => {
    await visit(page, "/", { role: "treating" });
    await expect(page.getByTestId("landing-signin")).toHaveText(/Open Case Files/);
    await page.getByTestId("landing-signin").click();
    await expect(page).toHaveURL(/\/tb-nik\/cases$/);
  });
});
