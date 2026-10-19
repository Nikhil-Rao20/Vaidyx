// The public site (/tb-nik): the product page's hero at every size and the whole page on a laptop and a phone, the phone menu, the
// signed-in variant of the actions, and the About, Docs and Contact pages. Mock mode only (nothing is sent anywhere).
import { expect, test } from "@playwright/test";
import { MOCK, SHOTS, SIZES, shoot, visit, watchConsole } from "../support/helpers";

test.describe("landing", () => {
  test.skip(!MOCK, "the public site is taken with mocked answers");

  test("product page", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/", { signedOut: true });
    await expect(page.getByTestId("landing-hero")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(/\S/);  // the words are the owner's, in content.ts
    await expect(page.getByTestId("landing-signin")).toHaveText(/Sign in/);
    await shoot(page, "landing", "hero", { fullPage: false, before: (pg) => pg.waitForTimeout(2600) });
    await shoot(page, "landing", "full", { fullPage: true, sizes: [SIZES[0], SIZES[2]] });
    await page.setViewportSize(SIZES[2]);
    await page.getByRole("button", { name: "Open the menu" }).click();
    await expect(page.getByRole("navigation", { name: "Pages" }).last()).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${SHOTS}/landing-menu-light-390.png` });
    await page.getByRole("button", { name: "Close the menu" }).click();
    for (const id of ["how", "sources", "roles", "safety"]) await expect(page.locator(`#${id}`)).toHaveCount(1);
    await expect(page.getByTestId("slide-case").first()).toBeAttached();
    await expect(page.getByTestId("ask-demo")).toBeAttached();
    await expect(page.getByTestId("roles-table")).toBeAttached();
    await expect(page.locator('#why a[href="https://doi.org/10.3332/ecancer.2026.2090"]').first()).toBeAttached();
    await expect(page.getByTestId("safety")).toBeAttached();
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("about, docs and contact", async ({ page }) => {
    await visit(page, "/about", { signedOut: true });
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Meet");
    for (const id of ["team", "tanuh"]) await expect(page.locator(`#${id}`)).toHaveCount(1);
    await shoot(page, "site", "about", { fullPage: true, sizes: [SIZES[0], SIZES[2]], themes: ["light"] });
    await visit(page, "/docs", { signedOut: true });
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Documentation");
    await shoot(page, "site", "docs", { fullPage: true, sizes: [SIZES[0], SIZES[2]], themes: ["light"] });
    await visit(page, "/contact", { signedOut: true });
    await expect(page.getByTestId("contact-email")).toHaveAttribute("href", /mailto:.*subject=/);
    await expect(page.getByTestId("contact-notice")).toContainText("not built yet");
    await shoot(page, "site", "contact", { fullPage: true, sizes: [SIZES[0], SIZES[2]], themes: ["light"] });
    // the enquiry form posts to the site's own endpoint (answered by the mock) and thanks the visitor
    await page.getByLabel("Your name").fill("Dr Test Person");
    await page.getByLabel("Your email").fill("test.person@example.org");
    await page.getByLabel("Hospital or institution").fill("Example Hospital");
    await page.getByLabel("Message").fill("We would like to try Vaidyx for our breast Tumour Board.");
    await page.getByRole("button", { name: "Send enquiry" }).click();
    await expect(page.getByTestId("contact-done")).toBeVisible();
  });

  test("design lab", async ({ page }) => {
    await visit(page, "/lab", { signedOut: true });
    for (const v of ["A", "B", "C", "D", "E"]) await expect(page.getByTestId(`lab-${v}`)).toBeAttached();
  });

  test("signed in", async ({ page }) => {
    await visit(page, "/", { role: "treating" });
    await expect(page.getByTestId("landing-signin")).toHaveText(/Open Case Files/);
    await page.getByTestId("landing-signin").click();
    await expect(page).toHaveURL(/\/tb-nik\/cases$/);
  });
});
