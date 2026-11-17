// "Choose your hospital system" (docs/new-case/DESIGN.md N7) on the Hospital console's Hospital system tab: pick a preset with its
// honest label, fill only the fields it needs, test without saving (one UHID shows the patient), "Use this system" only after a
// passing test of exactly these values (an edit turns it off again), a failing test in plain words, the save with the test's
// fingerprint, a new hospital with no system, the Vaidyx admin inside a hospital, and the phone width. Mock mode only
// (e2e/support/his_chooser_mock.ts, SYNTHETIC).
// Run: cd web/tb-nik && npx vite build && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts his-chooser
import { expect, test, type Page } from "@playwright/test";
import * as fx from "../support/fixtures";
import { MOCK, SIZES, login, prepare, shoot, watchConsole } from "../support/helpers";
import { routeHisChooser } from "../support/his_chooser_mock";

const LAPTOP_PHONE = [SIZES[0], SIZES[2]];

async function open(page: Page, role: fx.Role = "root_admin", opts: Parameters<typeof routeHisChooser>[1] = {}, overrides = {}) {
  await prepare(page, { role, overrides });
  const log = await routeHisChooser(page, opts);
  await login(page);
  await page.goto("/tb-nik/hospital/system", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
  return log;
}

/** No sideways scroll of the page or inside the open dialog. */
async function noSideScroll(page: Page) {
  const r = await page.evaluate(() => {
    const d = document.querySelector("[data-testid='his-chooser']") as HTMLElement | null;
    return { page: document.documentElement.scrollWidth - document.documentElement.clientWidth, dialog: d ? d.scrollWidth - d.clientWidth : 0 };
  });
  expect(r.page, "page side scroll").toBeLessThanOrEqual(0);
  expect(r.dialog, "dialog side scroll").toBeLessThanOrEqual(1);
}

test.describe("choose your hospital system", () => {
  test.skip(!MOCK, "mock mode only: the chooser's routes are answered from his_chooser_mock.ts");

  test("pick a preset, test it with one UHID, use it only after a passing test", async ({ page }) => {
    const errors = watchConsole(page);
    const log = await open(page);
    // the connection card shows what is saved now
    await expect(page.getByText("Vaidyx Demo Hospital HIS (SYNTHETIC)")).toBeVisible();
    await expect(page.getByLabel("Hospital system address (URL)")).toHaveValue("http://127.0.0.1:7130");
    await page.getByRole("button", { name: "Change hospital system" }).click();
    const dialog = page.getByRole("dialog", { name: "Choose your hospital system" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "A live FHIR server" })).toBeVisible();
    // honest labels
    const demo = dialog.getByTestId("his-preset").filter({ hasText: "Vaidyx demo hospital (SYNTHETIC)" });
    await expect(demo.getByText("Tested with the demo hospital", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "NIC e-Hospital / NextGen eHospital No public API found" })).toBeVisible();   // name and label read together
    await expect(demo.getByText("In use")).toBeVisible();
    await expect(dialog.getByTestId("his-preset").filter({ hasText: "NIC e-Hospital" }).getByText("No public API found", { exact: true })).toBeVisible();
    await shoot(page, "his-chooser", "pick", { sizes: LAPTOP_PHONE, fullPage: false });
    // search
    await dialog.getByRole("searchbox", { name: "Find your hospital system" }).fill("bahmni");
    await expect(dialog.getByTestId("his-preset").first()).toContainText("Bahmni / OpenMRS (FHIR2 module)");   // the notes are searched too
    await expect(dialog.getByTestId("his-preset").filter({ hasText: "NIC e-Hospital" })).toHaveCount(0);
    const bahmni = dialog.getByTestId("his-preset").first();
    await expect(bahmni.getByText("By standard, not tested with this product")).toBeVisible();
    await bahmni.click();

    // details: only the fields this method needs, the preset's defaults filled in
    await expect(dialog.getByLabel("FHIR base path")).toHaveValue("/openmrs/ws/fhir2/R4");
    await expect(dialog.getByLabel("User name")).toBeVisible();
    await expect(dialog.getByLabel("Password")).toHaveAttribute("type", "password");
    await expect(dialog.getByLabel("Client id")).toHaveCount(0);                 // an OAuth2 field is not shown for HTTP basic
    const testBtn = dialog.getByRole("button", { name: "Test these settings" });
    const use = dialog.getByRole("button", { name: "Use this system" });
    await expect(testBtn).toBeDisabled();
    await expect(use).toBeDisabled();
    await dialog.getByLabel("Server address").fill("http://127.0.0.1:8085");
    await dialog.getByLabel("User name").fill("vaidyx_reader");
    await dialog.getByLabel("Password").fill("synthetic-pass");
    await dialog.getByLabel(/Try one UHID/).fill("VXH/26/004201");
    await testBtn.click();
    const result = dialog.getByTestId("his-try-result");
    await expect(result).toContainText("The hospital system answers");
    await expect(result).toContainText("1240 patients, 9876 reports");
    await expect(dialog.getByTestId("his-try-sample")).toHaveText("Found: 3 visits, 8 reports, newest 20/09/2026.");  // counts only: no patient data for an admin
    await expect(dialog.getByText(/Anitha|IHC/)).toHaveCount(0);
    expect(log.tries.at(-1)).toMatchObject({ preset: "bahmni_openmrs", url: "http://127.0.0.1:8085", base_path: "/openmrs/ws/fhir2/R4", auth: "basic", username: "vaidyx_reader", identifier: "VXH/26/004201" });
    expect(log.saves).toHaveLength(0);                                            // a test saves nothing
    await expect(use).toBeEnabled();
    await shoot(page, "his-chooser", "tested", { sizes: LAPTOP_PHONE, fullPage: false });

    // any edit turns Use off again until the next test
    await dialog.getByLabel("Name shown to doctors").fill("Bahmni (SYNTHETIC)");
    await expect(use).toBeDisabled();
    await expect(dialog.getByText("A value changed after the test. Test again to use it.")).toBeVisible();
    await testBtn.click();
    await expect(use).toBeEnabled();

    // use: the confirm says what changes; the save carries the test's fingerprint
    await use.click();
    const confirm = page.getByRole("dialog", { name: "Use Bahmni (SYNTHETIC)?" });
    await expect(confirm).toContainText("Doctors will look up patients in this hospital system from now on.");
    await expect(confirm).toContainText("keep their link to the old system");
    await confirm.getByRole("button", { name: "Use this system" }).click();
    await expect(page.getByText("Bahmni (SYNTHETIC) is now the hospital system")).toBeVisible();
    expect(log.saves).toHaveLength(1);
    expect(log.saves[0]).toMatchObject({ preset: "bahmni_openmrs", label: "Bahmni (SYNTHETIC)", tested_fingerprint: expect.stringMatching(/^fp1-mock-/) });
    expect(log.saves[0].identifier).toBeUndefined();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("not listed: a folder method, a failing test in plain words, Esc closes", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page);
    await page.getByRole("button", { name: "Change hospital system" }).click();
    const dialog = page.getByRole("dialog", { name: "Choose your hospital system" });
    await dialog.getByRole("button", { name: "My system is not listed" }).click();
    await expect(dialog.getByTestId("his-method")).toHaveCount(4);
    await expect(dialog.getByTestId("his-method").filter({ hasText: "HL7 v2 result messages in a folder" })).toContainText("Cannot: no signature check");
    await shoot(page, "his-chooser", "methods", { sizes: LAPTOP_PHONE, fullPage: false });
    await dialog.getByTestId("his-method").filter({ hasText: "HL7 v2 result messages in a folder" }).click();
    await expect(dialog.getByText("Allowed: /data/vaidyx/tb_data/his_inbox")).toBeVisible();
    await dialog.getByLabel("Folder").fill("/data/vaidyx/tb_data/his_inbox/missing");
    await dialog.getByRole("button", { name: "Test these settings" }).click();
    const result = dialog.getByTestId("his-try-result");
    await expect(result).toContainText("The test did not pass");
    await expect(result).toContainText("The hospital-system folder does not exist on this server");
    await expect(result).toContainText("Check that the folder exists on this server");
    await expect(dialog.getByRole("button", { name: "Use this system" })).toBeDisabled();
    await shoot(page, "his-chooser", "failed", { sizes: LAPTOP_PHONE, fullPage: false });
    // a live server that is down
    await dialog.getByRole("button", { name: "Choose another" }).click();
    await dialog.getByRole("button", { name: "My system is not listed" }).click();
    await dialog.getByTestId("his-method").filter({ hasText: "Plain FHIR R4 server" }).click();
    await dialog.getByLabel("Server address").fill("http://127.0.0.1:9");
    await dialog.getByLabel("Token").fill("synthetic-token");
    await dialog.getByRole("button", { name: "Test these settings" }).click();
    await expect(dialog.getByTestId("his-try-result")).toContainText("Check the server address and port");
    await expect(dialog.getByRole("button", { name: "Use this system" })).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("a saved secret reads Saved, leave empty to keep", async ({ page }) => {
    await open(page);
    await page.getByRole("button", { name: "Change hospital system" }).click();
    const dialog = page.getByRole("dialog", { name: "Choose your hospital system" });
    await dialog.getByTestId("his-preset").filter({ hasText: "Vaidyx demo hospital (SYNTHETIC)" }).click();
    await expect(dialog.getByLabel("Server address")).toHaveValue("http://127.0.0.1:7130");
    await expect(dialog.getByText(/^Saved, leave empty to keep/)).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Test these settings" })).toBeEnabled();   // the token is saved: no need to type it
  });

  test("a new hospital with no system starts from Not connected", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, "root_admin", { current: { kind: "none", preset: "", enabled: false, settings: { kind: "none", label: "", url: "", enabled: false, has_token: false, pacs_url: "", connector: "" } } },
      { "GET /api/tb/setup": { body: { ...fx.setup, his: { url: "", kind: "none", enabled: false, has_token: false, tested_at: "", ok: null, error: "" } } } });
    await expect(page.getByRole("heading", { name: "Not connected" })).toBeVisible();
    await expect(page.getByLabel("Hospital system address (URL)")).toHaveCount(0);
    await page.getByRole("button", { name: "Choose your hospital system" }).click();
    await expect(page.getByRole("dialog", { name: "Choose your hospital system" })).toBeVisible();
    await expect(page.getByText("In use")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("the Vaidyx admin inside a hospital uses the same screen", async ({ page }) => {
    await page.addInitScript(() => sessionStorage.setItem("tbnik.actingHospital", JSON.stringify({ id: "svch", name: "Sri Venkateswara Cancer Hospital" })));
    const log = await open(page, "vaidyx_admin");
    await page.getByRole("button", { name: "Change hospital system" }).click();
    const dialog = page.getByRole("dialog", { name: "Choose your hospital system" });
    await dialog.getByTestId("his-preset").filter({ hasText: "HAPI FHIR" }).click();
    await dialog.getByLabel("Server address").fill("http://127.0.0.1:8085/fhir");
    await dialog.getByLabel("Token").fill("synthetic-token");
    await dialog.getByRole("button", { name: "Test these settings" }).click();
    await expect(dialog.getByTestId("his-try-result")).toContainText("The hospital system answers");
    expect(log.headers.some((h) => h["x-tb-hospital"] === "svch")).toBe(true);
  });

  test("phone width: the Dock stays, nothing scrolls sideways", async ({ page }) => {
    await page.setViewportSize(SIZES[2]);
    await open(page);
    await expect(page.getByRole("navigation", { name: "Main" }).first()).toBeVisible();
    await page.getByRole("button", { name: "Change hospital system" }).click();
    await noSideScroll(page);
    const dialog = page.getByRole("dialog", { name: "Choose your hospital system" });
    await dialog.getByTestId("his-preset").filter({ hasText: "Bahmni / OpenMRS" }).click();
    await dialog.getByLabel("Server address").fill("http://127.0.0.1:8085");
    await dialog.getByLabel("User name").fill("vaidyx_reader");
    await dialog.getByLabel("Password").fill("synthetic-pass");
    await dialog.getByLabel(/Try one UHID/).fill("VXH/26/000001");
    await dialog.getByRole("button", { name: "Test these settings" }).click();
    await expect(dialog.getByTestId("his-try-result")).toContainText("No patient with VXH/26/000001");
    await noSideScroll(page);
    await shoot(page, "his-chooser", "phone-details", { sizes: [SIZES[2]], fullPage: false });
    await page.keyboard.press("Escape");
    await noSideScroll(page);
    await shoot(page, "his-chooser", "phone-card", { sizes: [SIZES[2]], fullPage: false });
  });
});
