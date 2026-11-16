// The admin consoles (docs/admin-console/DESIGN.md section 4): the Vaidyx console (/platform) for the Vaidyx admin and the Hospital
// console (/hospital) for the hospital admin and for a Vaidyx admin working inside a hospital. Mock mode only (the backend routes of
// DESIGN 5.3 are answered from e2e/support/fixtures.ts, SYNTHETIC). Laptop 1366 x 768 and phone 390 x 844, light and dark.
// Run: cd web/tb-nik && npx vite build && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts consoles
import { expect, test, type Page, type Request } from "@playwright/test";
import { MOCK, SIZES, shoot, visit, watchConsole } from "../support/helpers";

const LAPTOP_PHONE = [SIZES[0], SIZES[2]];

/** No sideways scroll at the laptop and the phone width. */
async function noSideScroll(page: Page) {
  for (const size of LAPTOP_PHONE) {
    await page.setViewportSize(size);
    await page.waitForTimeout(250);
    const r = await page.evaluate(() => {
      const cw = document.documentElement.clientWidth;
      // what sticks out, to say in the failure
      const wide = [...document.querySelectorAll("body *")].filter((el) => el.getBoundingClientRect().right > cw + 1).slice(0, 5)
        .map((el) => `${el.tagName.toLowerCase()}.${String((el as HTMLElement).className || "").slice(0, 60)} "${(el.textContent || "").trim().slice(0, 40)}"`);
      return { sw: document.documentElement.scrollWidth, cw, wide };
    });
    expect(r.sw, `no sideways scroll at ${size.width}: ${r.wide.join(" | ")}`).toBeLessThanOrEqual(r.cw);
  }
  await page.setViewportSize(SIZES[0]);
}

test.describe("admin consoles", () => {
  test.skip(!MOCK, "mock mode only: the console routes are answered from fixtures");

  test("Vaidyx console overview", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/platform", { role: "vaidyx_admin" });
    await expect(page.getByRole("heading", { level: 1, name: "Vaidyx console" })).toBeVisible();
    await expect(page.getByText("Hospitals active")).toBeVisible();
    await expect(page.getByRole("table", { name: "Hospitals" }).getByRole("link", { name: "Sri Venkateswara Cancer Hospital" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Needs attention" })).toBeVisible();
    await expect(page.getByText("No hospital admin yet")).toBeVisible();
    const nav = page.getByRole("navigation", { name: "Main" }).first();
    await expect(nav.getByRole("link", { name: "Vaidyx console" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Hospital", exact: true })).toHaveCount(0);  // not working inside a hospital yet
    await noSideScroll(page);
    await shoot(page, "consoles", "platform-overview", { sizes: LAPTOP_PHONE });
    expect(errors).toEqual([]);
  });

  test("home of the Vaidyx admin is the Vaidyx console; others cannot open it", async ({ page }) => {
    await visit(page, "/cases", { role: "vaidyx_admin" });
    await expect(page).toHaveURL(/\/tb-nik\/platform$/);
    await visit(page, "/platform", { role: "treating" });
    await expect(page.getByText("Only the Vaidyx admin opens the Vaidyx console")).toBeVisible();
  });

  test("hospitals list, add a hospital through to the first password", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/platform/hospitals", { role: "vaidyx_admin" });
    await expect(page.getByRole("link", { name: "Kaveri Medical College Hospital" })).toBeVisible();
    await page.getByRole("searchbox", { name: "Find a hospital" }).fill("Tirupati");
    await expect(page.getByRole("link", { name: "Sri Venkateswara Cancer Hospital" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Vaidyx Demo Hospital" })).toHaveCount(0);
    await page.getByRole("searchbox", { name: "Find a hospital" }).fill("");
    await page.getByRole("button", { name: /^Suspended/ }).click();
    await expect(page.getByRole("link", { name: "Narmada Regional Hospital" })).toBeVisible();
    await page.getByRole("button", { name: /^All/ }).click();
    await noSideScroll(page);
    await shoot(page, "consoles", "platform-hospitals", { sizes: LAPTOP_PHONE });

    await page.getByRole("button", { name: "Add a hospital" }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Add a hospital" })).toBeVisible();
    await dialog.getByRole("button", { name: "Continue" }).click();
    await expect(dialog.getByText("Give the hospital's name.")).toBeVisible();
    await dialog.getByLabel("Hospital name").fill("Godavari Cancer Centre");
    await dialog.getByLabel("City").fill("Rajahmundry");
    await shoot(page, "consoles", "add-hospital-1", { sizes: LAPTOP_PHONE, fullPage: false });
    await dialog.getByRole("button", { name: "Continue" }).click();
    await dialog.getByRole("button", { name: "Continue" }).click();
    await expect(dialog.getByText("Type the admin's email address; it becomes their login.")).toBeVisible();
    await dialog.getByRole("textbox", { name: /^Name\b/ }).fill("Ravi Teja");
    await dialog.getByLabel("Email (the login)").fill("Ravi.Teja@Godavari.example");
    await dialog.getByRole("button", { name: "Continue" }).click();
    await expect(dialog.getByText("ravi.teja@godavari.example")).toBeVisible();
    await shoot(page, "consoles", "add-hospital-3-review", { sizes: LAPTOP_PHONE, fullPage: false });
    const posted = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/tb/platform/hospitals");
    await dialog.getByRole("button", { name: "Add the hospital" }).click();
    const body = (await posted).postDataJSON();
    expect(body).toMatchObject({ name: "Godavari Cancer Centre", city: "Rajahmundry", admin: { display_name: "Ravi Teja", email: "ravi.teja@godavari.example" } });
    await expect(dialog.getByText("Godavari Cancer Centre is added")).toBeVisible();
    await expect(dialog.getByTestId("first-password")).toHaveText("Mock-First-Pass-7Q2");
    await expect(dialog.getByRole("button", { name: "Copy the first password" })).toBeVisible();
    await expect(dialog.getByRole("link", { name: "Open mail draft" })).toHaveAttribute("href", /^mailto:/);
    await shoot(page, "consoles", "add-hospital-result", { sizes: LAPTOP_PHONE, fullPage: false });
    await dialog.getByRole("button", { name: "Done" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("hospital detail with suspend", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/platform/hospitals/svch", { role: "vaidyx_admin" });
    await expect(page.getByRole("heading", { level: 1, name: /Sri Venkateswara Cancer Hospital/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Hospital admins" })).toBeVisible();
    await expect(page.getByText("Ravi Teja")).toBeVisible();
    await expect(page.getByRole("button", { name: "Manage inside this hospital" })).toBeEnabled();
    await noSideScroll(page);
    await shoot(page, "consoles", "hospital-detail", { sizes: LAPTOP_PHONE });
    await page.getByRole("button", { name: "More actions" }).click();
    await page.getByRole("menuitem", { name: "Suspend" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Suspend Sri Venkateswara Cancer Hospital?" })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Suspend" })).toBeDisabled();  // a reason first
    await dialog.getByLabel("Reason (kept in the record)").fill("Test of the suspend dialog");
    await expect(dialog.getByRole("button", { name: "Suspend" })).toBeEnabled();
    await shoot(page, "consoles", "hospital-suspend", { sizes: [SIZES[0]], fullPage: false });
    const posted = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/tb/platform/hospitals/svch/status");
    await dialog.getByRole("button", { name: "Suspend" }).click();
    expect((await posted).postDataJSON()).toEqual({ status: "suspended", reason: "Test of the suspend dialog" });
    expect(errors).toEqual([]);
  });

  test("logins with filters and a password reset", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/platform/logins", { role: "vaidyx_admin" });
    await expect(page.getByTestId("login-row")).toHaveCount(8);
    await expect(page.getByTestId("login-row").filter({ hasText: "Vaidyx Admin" })).toContainText("Server login");
    await page.getByRole("combobox", { name: "Role" }).click();
    await page.getByRole("option", { name: "Hospital admin" }).click();
    await expect(page.getByTestId("login-row")).toHaveCount(3);
    const req = page.waitForRequest((r) => r.url().includes("/api/tb/platform/logins?") && r.url().includes("role=hospital_admin") && r.url().includes("hospital=svch"));
    await page.getByRole("combobox", { name: "Hospital" }).click();
    await page.getByRole("option", { name: "Sri Venkateswara Cancer Hospital" }).click();
    await req;  // the server filters too
    await expect(page.getByTestId("login-row")).toHaveCount(1);
    await noSideScroll(page);
    await shoot(page, "consoles", "platform-logins", { sizes: LAPTOP_PHONE });
    await page.getByRole("button", { name: "Actions for Ravi Teja" }).click();
    await page.getByRole("menuitem", { name: "Reset the password" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByTestId("first-password")).toHaveText("Mock-Reset-Pass-4K9");
    await shoot(page, "consoles", "platform-login-reset", { sizes: LAPTOP_PHONE, fullPage: false });
    await dialog.getByRole("button", { name: "Done" }).click();
    await page.getByRole("button", { name: "Actions for Ravi Teja" }).click();
    await page.getByRole("menuitem", { name: "Disable the login" }).click();
    await expect(page.getByRole("dialog").getByRole("heading", { name: "Disable Ravi Teja?" })).toBeVisible();
    const posted = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith("/platform/logins/it.admin%40svch.example/disable"));
    await page.getByRole("dialog").getByRole("button", { name: "Disable" }).click();
    await posted;
    expect(errors).toEqual([]);
  });

  test("Vaidyx activity", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/platform/activity", { role: "vaidyx_admin" });
    await expect(page.getByText("Hospital added: Kaveri Medical College Hospital")).toBeVisible();
    await page.getByRole("searchbox", { name: "Search the activity" }).fill("reset");
    await expect(page.getByText("Password reset for Asha Menon")).toBeVisible();
    await expect(page.getByText("Hospital added: Kaveri Medical College Hospital")).toHaveCount(0);
    await noSideScroll(page);
    await shoot(page, "consoles", "platform-activity", { sizes: LAPTOP_PHONE, themes: ["light"] });
    expect(errors).toEqual([]);
  });

  test("manage inside a hospital: the acting-in bar, the header, switching and back", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/platform/hospitals/default", { role: "vaidyx_admin" });
    const overview = page.waitForRequest((r: Request) => new URL(r.url()).pathname === "/api/tb/hospital/overview");
    await page.getByRole("button", { name: "Manage inside this hospital" }).click();
    await expect(page).toHaveURL(/\/tb-nik\/hospital$/);
    expect((await overview).headers()["x-tb-hospital"]).toBe("default");
    const bar = page.getByTestId("acting-bar");
    await expect(bar).toContainText("Managing Vaidyx Demo Hospital as Vaidyx admin");
    await expect(page.getByRole("heading", { level: 1, name: "Vaidyx Demo Hospital" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Main" }).first().getByRole("link", { name: "Hospital", exact: true })).toBeVisible();
    expect(await page.evaluate(() => sessionStorage.getItem("tbnik.actingHospital"))).toContain("\"default\"");
    await noSideScroll(page);
    await shoot(page, "consoles", "acting-hospital", { sizes: LAPTOP_PHONE, fullPage: false });

    // Switch hospital: a small picker; every request then names the new hospital
    await bar.getByRole("button", { name: "Switch hospital" }).click();
    await expect(page.getByTestId("switch-list")).toBeVisible();
    await shoot(page, "consoles", "acting-switch", { sizes: LAPTOP_PHONE, fullPage: false });
    const again = page.waitForRequest((r: Request) => new URL(r.url()).pathname === "/api/tb/hospital/overview" && r.headers()["x-tb-hospital"] === "svch");
    await page.getByTestId("switch-list").getByRole("button", { name: /Sri Venkateswara Cancer Hospital/ }).click();
    await again;
    await expect(bar).toContainText("Managing Sri Venkateswara Cancer Hospital as Vaidyx admin");
    await expect(page.getByRole("heading", { level: 1, name: "Sri Venkateswara Cancer Hospital" })).toBeVisible();

    // The People tab of the hospital worked in carries the header too
    const people = page.waitForRequest((r: Request) => new URL(r.url()).pathname === "/api/tb/accounts" && r.headers()["x-tb-hospital"] === "svch");
    await page.getByRole("navigation", { name: "Hospital console sections" }).getByRole("link", { name: "People" }).click();
    await people;

    // Back to the Vaidyx console: no hospital any more, no header
    await bar.getByRole("button", { name: "Back to Vaidyx console" }).click();
    await expect(page).toHaveURL(/\/tb-nik\/platform$/);
    await expect(page.getByTestId("acting-bar")).toHaveCount(0);
    expect(await page.evaluate(() => sessionStorage.getItem("tbnik.actingHospital"))).toBeNull();
    const plain = await page.waitForRequest((r: Request) => r.url().includes("/api/tb/") && r.method() === "GET", { timeout: 10_000 }).catch(() => null);
    if (plain) expect(plain.headers()["x-tb-hospital"]).toBeUndefined();
    expect(errors).toEqual([]);
  });

  test("Hospital console overview for the hospital admin", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/cases", { role: "root_admin" });
    await expect(page).toHaveURL(/\/tb-nik\/hospital$/);  // the hospital admin's home
    await expect(page.getByRole("heading", { level: 1, name: "Vaidyx Demo Hospital" })).toBeVisible();
    await expect(page.getByText(/Good (morning|afternoon|evening), Hospital IT\. Here is how Vaidyx Demo Hospital stands today\./)).toBeVisible();
    await expect(page.getByText("Microbiology has no head yet")).toBeVisible();
    await expect(page.getByRole("button", { name: "Add an MDT Coordinator" })).toBeVisible();
    const nav = page.getByRole("navigation", { name: "Main" }).first();
    await expect(nav.getByRole("link", { name: "Hospital", exact: true })).toHaveAttribute("aria-current", "page");
    await expect(nav.getByRole("link", { name: "Admin", exact: true })).toHaveCount(0);
    await expect(page.getByTestId("acting-bar")).toHaveCount(0);
    await page.getByRole("button", { name: "Test now" }).click();
    await expect(page.getByText("The hospital system answers").first()).toBeVisible();
    await noSideScroll(page);
    await shoot(page, "consoles", "hospital-overview", { sizes: LAPTOP_PHONE });
    // the role word is "Hospital admin" everywhere on screen
    await page.getByRole("button", { name: /Your menu/ }).click();
    await expect(page.getByRole("menu").getByText("Hospital admin", { exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    expect(errors).toEqual([]);
  });

  test("People: add an MDT Coordinator, see the first password once", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/hospital", { role: "root_admin" });
    await page.getByRole("button", { name: "Add an MDT Coordinator" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Add an MDT Coordinator" })).toBeVisible();
    await expect(dialog.getByRole("radio", { name: /MDT Coordinator/ })).toHaveAttribute("aria-checked", "true");
    await expect(dialog.getByRole("group", { name: "Departments" })).toHaveCount(0);  // no department for a coordinator
    await dialog.getByRole("textbox", { name: /^Name\b/ }).fill("Sunita Rao");
    await dialog.getByLabel("Email (the login)").fill("sunita.rao@vxh.example");
    await shoot(page, "consoles", "add-person-coordinator", { sizes: LAPTOP_PHONE, fullPage: false });
    const posted = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/tb/accounts");
    await dialog.getByRole("button", { name: "Add an MDT Coordinator" }).click();
    expect((await posted).postDataJSON()).toMatchObject({ email: "sunita.rao@vxh.example", display_name: "Sunita Rao", coordinator: true, root_admin: false, departments: {}, admin_of: [] });
    await expect(dialog.getByText("Sunita Rao is added")).toBeVisible();
    await expect(dialog.getByTestId("first-password")).toHaveText("Mock-Acct-Pass-8T3");
    await shoot(page, "consoles", "add-person-result", { sizes: LAPTOP_PHONE, fullPage: false });
    await dialog.getByRole("button", { name: "Done" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);

    // a doctor needs a department
    await page.getByRole("button", { name: "Add a doctor" }).click();
    await page.getByRole("dialog").getByRole("textbox", { name: /^Name\b/ }).fill("Dr Kiran Rao");
    await page.getByRole("dialog").getByLabel("Email (the login)").fill("kiran.rao@vxh.example");
    await page.getByRole("dialog").getByRole("button", { name: "Add a doctor" }).click();
    await expect(page.getByRole("dialog").getByText("Pick at least one department.")).toBeVisible();
    await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();

    // the People tab: role chips and the actions
    await page.getByRole("navigation", { name: "Hospital console sections" }).getByRole("link", { name: "People" }).click();
    await expect(page.getByTestId("hospital-person-row").first()).toBeVisible();
    await page.getByRole("button", { name: /^MDT Coordinators/ }).click();
    await expect(page.getByTestId("hospital-person-row")).toHaveCount(1);
    await expect(page).toHaveURL(/role=coordinator/);
    await page.getByRole("button", { name: /^Everyone/ }).click();
    await noSideScroll(page);
    await shoot(page, "consoles", "hospital-people", { sizes: LAPTOP_PHONE });
    await page.getByRole("button", { name: "Actions for Lakshmi Rao" }).click();
    await page.getByRole("menuitem", { name: "Change the role or departments" }).click();
    await expect(page.getByRole("dialog").getByRole("radio", { name: /Head of department/ })).toHaveAttribute("aria-checked", "true");
    await shoot(page, "consoles", "hospital-change-role", { sizes: [SIZES[0]], fullPage: false });
    await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
    expect(errors).toEqual([]);
  });

  test("Departments, Set-up, Hospital system and Activity tabs", async ({ page }) => {
    const errors = watchConsole(page);
    await visit(page, "/hospital/departments", { role: "root_admin" });
    await expect(page.getByTestId("department-row").first()).toBeVisible();
    await page.getByRole("searchbox", { name: "Find a department" }).fill("Radiology");
    await expect(page.getByTestId("department-row")).toHaveCount(1);
    await page.getByRole("searchbox", { name: "Find a department" }).fill("");
    await noSideScroll(page);
    await shoot(page, "consoles", "hospital-departments", { sizes: LAPTOP_PHONE });
    await page.getByRole("button", { name: "Edit the contact of Radiology" }).click();
    await expect(page.getByRole("dialog").getByLabel("Desk phone")).toHaveValue("044 2345 1014");
    await page.getByRole("dialog").getByLabel("Desk email").fill("radiology.desk@vxh.example");
    await page.getByRole("dialog").getByLabel("Desk phone").fill("040 2312 4101");
    const posted = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/tb/setup/departments");
    await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
    expect((await posted).postDataJSON()).toEqual({ contacts: { radiology: { email: "radiology.desk@vxh.example", phone: "040 2312 4101" } } });

    await page.getByRole("navigation", { name: "Hospital console sections" }).getByRole("link", { name: "Set-up" }).click();
    await expect(page.getByText(/of 5 steps done/).first()).toBeVisible();
    await noSideScroll(page);
    await shoot(page, "consoles", "hospital-setup", { sizes: LAPTOP_PHONE, themes: ["light"], fullPage: false });
    await page.getByRole("navigation", { name: "Hospital console sections" }).getByRole("link", { name: "Hospital system" }).click();
    await expect(page.getByLabel("Hospital system address (URL)")).toHaveValue("http://127.0.0.1:7130");
    await noSideScroll(page);
    await shoot(page, "consoles", "hospital-system", { sizes: LAPTOP_PHONE, themes: ["light"], fullPage: false });
    await page.getByRole("navigation", { name: "Hospital console sections" }).getByRole("link", { name: "Activity" }).click();
    await expect(page.getByRole("tab", { name: "Full log" })).toHaveAttribute("aria-selected", "true");
    await noSideScroll(page);
    // the old addresses keep working
    await visit(page, "/admin", { role: "root_admin" });
    await expect(page.getByRole("heading", { name: "Hospital set-up" })).toBeVisible();
    await visit(page, "/people", { role: "root_admin" });
    await expect(page.getByRole("heading", { level: 1, name: "People" })).toBeVisible();
    await visit(page, "/activity", { role: "root_admin" });
    await expect(page.getByRole("heading", { level: 1, name: "Activity" })).toBeVisible();
    expect(errors).toEqual([]);
  });
});
