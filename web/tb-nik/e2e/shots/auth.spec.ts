// Sign in (email + password, the TOTP step, a wrong password, the rate limit), the forced password change and the profile set-up.
import { expect, test } from "@playwright/test";
import { MOCK, SIZES, prepare, runsFor, shoot, visit } from "../support/helpers";
import * as fx from "../support/fixtures";

test.describe("auth", () => {
  test.skip(!MOCK, "the sign-in states are taken with mocked answers so no real login is locked out");

  test("sign in", async ({ page }) => {
    await visit(page, "/sign-in", { signedOut: true });
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await shoot(page, "auth", "sign-in");
    await page.getByLabel("Email").fill("rao@vxh.example");
    await page.getByLabel("Password", { exact: true }).fill("wrong-password");
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await prepare(page, { signedOut: true, overrides: { "POST /api/auth/login": { status: 401, body: { detail: "Invalid credentials" } } } });
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("The email or password is not right.")).toBeVisible();
    await shoot(page, "auth", "sign-in-wrong", { sizes: [SIZES[0], SIZES[2]] });
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await prepare(page, { signedOut: true, overrides: { "POST /api/auth/login": { status: 429, body: { detail: "Too many requests" } } } });
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText(/Too many tries/)).toBeVisible();
    await shoot(page, "auth", "sign-in-rate-limit", { sizes: [SIZES[0]] });
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await prepare(page, { signedOut: true, overrides: { "POST /api/auth/login": { body: { ok: false, requires_totp: true } } } });
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("One more step")).toBeVisible();
    await shoot(page, "auth", "sign-in-totp", { sizes: [SIZES[0], SIZES[2]] });
  });

  test("first login", async ({ page }) => {
    await visit(page, "/first-login", { overrides: { "GET /api/tb/me": { body: { ...fx.me("treating"), must_change_password: true } } } });
    await expect(page.getByRole("heading", { name: "Set your own password" })).toBeVisible();
    await page.getByLabel("New password", { exact: true }).fill("Tumour-Board-2026");
    await shoot(page, "auth", "first-login");
  });

  test("welcome stepper", async ({ page }) => {
    await visit(page, "/welcome", { overrides: { "GET /api/tb/me": { body: { ...fx.me("treating"), display_name: "rao@vxh.example", setup_needed: true, profile: { saved_filters: [] } } } } });
    await expect(page.getByRole("heading", { name: "Make it yours" })).toBeVisible();
    await shoot(page, "auth", "welcome-1");
    await page.getByLabel(/^Name/).fill("Lakshmi Rao");
    await page.getByLabel(/^Registration number/).fill("TNMC 45821");
    await page.getByRole("button", { name: /Continue/ }).click();
    await expect(page.getByRole("heading", { name: "How it looks" })).toBeVisible();
    await shoot(page, "auth", "welcome-2", { sizes: [SIZES[0], SIZES[2]] });
    await page.getByRole("button", { name: /Continue/ }).click();
    await expect(page.getByRole("heading", { name: /Where you start/ })).toBeVisible();
    await shoot(page, "auth", "welcome-3", { sizes: [SIZES[0], SIZES[2]] });
    await page.getByRole("button", { name: /Continue/ }).click();
    await expect(page.getByRole("heading", { name: "Try it on one patient" })).toBeVisible();
    await shoot(page, "auth", "welcome-4-gift", { sizes: [SIZES[0], SIZES[2]] });
  });

  test("welcome for a supporting doctor ends without the gift", async ({ page }) => {
    test.skip(!runsFor("supporting"));
    await visit(page, "/welcome", { role: "supporting", overrides: { "GET /api/tb/me": { body: { ...fx.me("supporting"), setup_needed: true } } } });
    await expect(page.getByRole("heading", { name: "Make it yours" })).toBeVisible();
  });
});
