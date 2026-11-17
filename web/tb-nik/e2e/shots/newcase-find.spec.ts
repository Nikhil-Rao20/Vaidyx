// New Case File: find a patient by name or words (docs/new-case/DESIGN.md N1 to N5, piece NC-A; mock only). One box, two ways: the
// number and Look up as before; 2+ letters open the drop-down of GET /his/find (keyboard and mouse), a pick runs the lookup with the
// UHID; the states (searching, nothing found, the hospital system down, the index still building); and the Case File a hospital
// doctor makes by hand (POST /cases with the name, no "anonymized", "Add the reports in Records"). Synthetic names only.
import { expect, test, type Page, type Route } from "@playwright/test";
import { MOCK, SIZES, THEMES, runsFor, shoot, visit } from "../support/helpers";
import * as fx from "../support/fixtures";

const PHONE_AND_LAPTOP = [SIZES[0], SIZES[2]];
const SOURCES = { his_live: true, index: { patients: 30, built_at: "2026-11-17T10:00:00+00:00", building: false } };
const LAKSHMI = { uhid: "VXH/2026/000140", name: "Lakshmi Narayanan (SYNTHETIC)", age: 58, sex: "F", last_visit: { department: "Breast Surgery", date: "2026-10-27" },
  case_files: [{ case_id: "TB-2026-0007", department: "Breast Surgery", cancer: "Breast cancer", status: "Being prepared", can_open: true }],
  matched: { on: "name", snippet: "", terms: [], source: "" }, score: 944, from: "his" };
const LAXMI = { uhid: "VXH/2026/000230", name: "Laxmi Devi (SYNTHETIC)", age: 61, sex: "F", last_visit: { department: "Gynaecologic Oncology", date: "2026-11-12" },
  case_files: [], matched: { on: "name", snippet: "", terms: [], source: "" }, score: 920, from: "his" };
const PRIYA = { uhid: "VXH/2026/004219", name: "Priya Venkatesan (SYNTHETIC)", age: 52, sex: "F", last_visit: { department: "Medical Oncology", date: "2026-11-07" }, case_files: [],
  matched: { on: "words", snippet: "...Plan: neoadjuvant chemotherapy, four cycles, then surgery. Board to confirm the sequence...", terms: ["chemotherapy"], source: "OPD consultation note, 05 Nov 2026" },
  score: 395, from: "his" };

/** GET /his/find answered per query; returns the queries asked. */
async function routeFind(page: Page, answer: (q: string) => { status?: number; body: unknown }) {
  const asked: string[] = [];
  await page.route("**/api/tb/his/find**", async (route: Route) => {
    const q = new URL(route.request().url()).searchParams.get("q") || "";
    asked.push(q);
    const a = answer(q);
    await route.fulfill({ status: a.status ?? 200, contentType: "application/json", body: JSON.stringify(a.body) });
  });
  return asked;
}

const byQuery = (q: string) => {
  const s = q.toLowerCase();
  if (s.startsWith("la")) return { body: { q, results: [LAKSHMI, LAXMI], sources: SOURCES } };
  if (s.startsWith("chemo")) return { body: { q, results: [PRIYA], sources: SOURCES } };
  if (s === "kamla") return { body: { q, results: [{ ...LAKSHMI, uhid: "", name: "Kamala Bai (SYNTHETIC)", last_visit: null, from: "case_file", case_files: [{ case_id: "TB-2026-0012", department: "Breast Surgery", can_open: true }] }], sources: { his_live: false, index: { patients: 0, built_at: null, building: false } } } };
  if (s === "venkatesan") return { body: { q, results: [{ ...PRIYA, matched: { on: "name", snippet: "", terms: [] }, score: 925, from: "live" }], sources: { his_live: true, index: { patients: 0, built_at: null, building: true } } } };
  return { body: { q, results: [], sources: SOURCES } };
};

test.describe("new case file: find by name or words", () => {
  test.skip(!runsFor("treating") || !MOCK);

  test("a name opens the list; arrow keys and Enter pick; the lookup runs with the UHID", async ({ page }) => {
    await visit(page, "/cases/new");
    const asked = await routeFind(page, byQuery);
    const lookups: string[] = [];
    page.on("request", (r) => { if (r.url().includes("/api/tb/his/lookup")) lookups.push(new URL(r.url()).searchParams.get("identifier") || ""); });
    const box = page.getByRole("combobox", { name: /UHID, IP No/ });
    await expect(box).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByText("Not in the hospital system? Make it by hand")).toBeVisible();
    await box.fill("laxmi");
    const list = page.getByRole("listbox", { name: "Patients found" });
    await expect(list.getByRole("option")).toHaveCount(2);
    await expect(box).toHaveAttribute("aria-expanded", "true");
    expect(asked).toEqual(["laxmi"]);  // debounced: one call for the whole word
    const first = list.getByRole("option").first();
    await expect(first).toContainText("Lakshmi Narayanan");
    await expect(first).toContainText("58 F");
    await expect(first).toContainText("VXH/2026/000140");
    await expect(first).toContainText("Last visit: Breast Surgery");
    await expect(first).toContainText("Has a Case File: TB-2026-0007, Breast Surgery");
    await shoot(page, "newcase", "find-name", { sizes: PHONE_AND_LAPTOP, themes: THEMES });
    await box.press("ArrowDown");
    await expect(first).toHaveAttribute("aria-selected", "true");
    await expect(box).toHaveAttribute("aria-activedescendant", (await first.getAttribute("id")) || "x");
    await box.press("ArrowDown");
    await box.press("ArrowUp");
    await box.press("Enter");
    await expect(box).toHaveValue("VXH/2026/000140");
    await expect(page.getByText("Registration found")).toBeVisible({ timeout: 20_000 });
    expect(lookups).toEqual(["VXH/2026/000140"]);
    await expect(list).toBeHidden();
  });

  test("a click picks; Escape closes; a number and Look up work as before", async ({ page }) => {
    await visit(page, "/cases/new");
    await routeFind(page, byQuery);
    const box = page.getByRole("combobox", { name: /UHID, IP No/ });
    await box.fill("lakshmi");
    await expect(page.getByRole("option")).toHaveCount(2);
    await box.press("Escape");
    await expect(page.getByRole("listbox", { name: "Patients found" })).toBeHidden();
    await expect(box).toHaveAttribute("aria-expanded", "false");
    await box.fill("lakshmi n");
    await page.getByRole("option", { name: /Laxmi Devi/ }).click();
    await expect(box).toHaveValue("VXH/2026/000230");
    await expect(page.getByText("Registration found")).toBeVisible({ timeout: 20_000 });
    // a number that matches nothing opens no list, and Enter is Look up as before
    const lookups: string[] = [];
    page.on("request", (r) => { if (r.url().includes("/api/tb/his/lookup")) lookups.push(new URL(r.url()).searchParams.get("identifier") || ""); });
    await box.fill("VXH/2026/000555");
    await page.waitForTimeout(400);
    await expect(page.getByRole("listbox", { name: "Patients found" })).toBeHidden();
    await box.press("Enter");
    await expect.poll(() => lookups).toEqual(["VXH/2026/000555"]);
  });

  test("words show the matched words in context", async ({ page }) => {
    await visit(page, "/cases/new");
    await routeFind(page, byQuery);
    await page.getByRole("combobox", { name: /UHID, IP No/ }).fill("chemo");
    const opt = page.getByRole("option").first();
    await expect(opt).toContainText("Priya Venkatesan");
    await expect(opt.locator("mark")).toHaveText("chemotherapy");
    await expect(opt).toContainText("(OPD consultation note, 05 Nov 2026)");
    await shoot(page, "newcase", "find-words", { sizes: PHONE_AND_LAPTOP, themes: THEMES });
  });

  test("states: still reading the records, the hospital system down, nothing found", async ({ page }) => {
    await visit(page, "/cases/new");
    await routeFind(page, byQuery);
    const box = page.getByRole("combobox", { name: /UHID, IP No/ });
    await box.fill("venkatesan");
    await expect(page.getByText("Still reading the hospital's records; names already work.")).toBeVisible();
    await expect(page.getByRole("option")).toHaveCount(1);
    await box.fill("kamla");
    await expect(page.getByText("The hospital system is not connected or did not answer. Showing Case Files only.")).toBeVisible();
    await expect(page.getByRole("option").first()).toContainText("No hospital number");
    await expect(page.getByRole("option").first()).toHaveAttribute("aria-disabled", "true");
    await shoot(page, "newcase", "find-his-down", { sizes: [SIZES[2]], themes: ["light"] });
    await box.fill("xyzzy");
    await expect(page.getByText("No patient matches 'xyzzy'. Try the UHID, or make it by hand.")).toBeVisible();
    await shoot(page, "newcase", "find-nothing", { sizes: PHONE_AND_LAPTOP, themes: ["light"] });
    await page.getByTestId("patient-finder").getByRole("button", { name: "Make it by hand" }).click();
    await expect(page.getByRole("heading", { name: "Patient, by hand" })).toBeVisible();
  });

  test("a hospital doctor makes the Case File by hand", async ({ page }) => {
    await visit(page, "/cases/new?identifier=VXH%2F2026%2F000140", { overrides: {
      "GET /api/tb/his/lookup": { status: 502, body: { detail: "The hospital system did not answer: timeout" } },
      "POST /api/tb/cases": { body: { case_id: "TB-2026-0040" } },
    } });
    await expect(page.getByTestId("make-by-hand")).toBeVisible();  // the main next step when the lookup fails
    await shoot(page, "newcase", "find-lookup-down", { sizes: [SIZES[2]], themes: ["light"] });
    await page.getByTestId("make-by-hand").click();
    await expect(page.getByTestId("manual-note")).toContainText("Not linked to the hospital system: add the reports in Records after Create.");
    const next = page.getByRole("button", { name: /Continue/ });
    await expect(next).toBeDisabled();
    await page.getByLabel(/Patient's name/).fill("Rukmini Bai (SYNTHETIC)");
    await page.getByLabel(/Hospital number/).fill("VXH/2026/009001");
    await page.getByLabel(/^Age/).fill("61");
    await page.getByText("Female", { exact: true }).click();
    await shoot(page, "newcase", "1-by-hand", { sizes: PHONE_AND_LAPTOP, themes: THEMES });
    // back to the lookup and here again keeps what was typed
    await page.getByRole("button", { name: "Back to the hospital system lookup" }).click();
    await expect(page.getByRole("combobox", { name: /UHID, IP No/ })).toBeVisible();
    await page.getByText("Not in the hospital system? Make it by hand").click();
    await expect(page.getByLabel(/Patient's name/)).toHaveValue("Rukmini Bai (SYNTHETIC)");
    await next.click();
    await expect(page.getByRole("heading", { name: "Which cancer" })).toBeVisible();
    await page.getByRole("radio", { name: /Breast/ }).first().click();
    await page.getByText("Early (operable), as recorded").click();
    await page.getByRole("button", { name: /Continue/ }).click();
    await page.getByRole("radio", { name: /Urgency 3/ }).click();
    let body: Record<string, unknown> | null = null;
    let fromHis = false;
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().endsWith("/api/tb/cases")) body = r.postDataJSON();
      if (r.url().endsWith("/api/tb/cases/from-his")) fromHis = true;
    });
    await page.getByRole("button", { name: /^Create$/ }).click();
    await expect(page.locator("#main").getByText("Case File created")).toBeVisible();
    await expect(page.getByText("Created. Add the reports in Records.")).toBeVisible();
    expect(fromHis).toBe(false);
    expect(body).toMatchObject({ patient: { name: "Rukmini Bai (SYNTHETIC)", mrn: "VXH/2026/009001", age: 61, sex: "F", source: "manual" }, protocol: "breast", setting: "early" });
    expect((body as unknown as { patient: Record<string, unknown> }).patient.anonymized).toBeUndefined();
    expect((body as unknown as Record<string, unknown>).case_id).toBeUndefined();
  });

  test("nothing found by the lookup offers the hand-made Case File", async ({ page }) => {
    await visit(page, "/cases/new?identifier=VXH%2F2026%2F999999", { overrides: { "GET /api/tb/his/lookup": { body: { found: false, identifier: "VXH/2026/999999" } } } });
    await expect(page.getByText(/Nothing found for/)).toBeVisible();
    await expect(page.getByTestId("make-by-hand")).toBeVisible();
  });
});

test.describe("new case file: a guest reviewer keeps the Case label step", () => {
  test.skip(!MOCK);

  test("no finder, no hand-made step; the private Case File as before", async ({ page }) => {
    await visit(page, "/cases/new", { overrides: {
      "GET /api/tb/me": { body: { ...fx.me("treating"), real_data: true } },
      "POST /api/tb/cases": { body: { case_id: "PRV-1A2B3C4D" } },
    } });
    await expect(page.getByRole("heading", { name: "Case label" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: /UHID, IP No/ })).toHaveCount(0);
    await expect(page.getByText("Not in the hospital system? Make it by hand")).toHaveCount(0);
    await page.getByLabel(/Case label/).fill("Case A");
    await page.getByLabel(/^Age/).fill("52");
    await page.getByText("Female", { exact: true }).click();
    await page.getByRole("button", { name: /Continue/ }).click();
    await page.getByRole("radio", { name: /Breast/ }).first().click();
    await page.getByText("Early (operable), as recorded").click();
    await page.getByRole("button", { name: /Continue/ }).click();
    await page.getByRole("radio", { name: /Urgency 3/ }).click();
    let body: Record<string, unknown> | null = null;
    page.on("request", (r) => { if (r.method() === "POST" && r.url().endsWith("/api/tb/cases")) body = r.postDataJSON(); });
    await page.getByRole("button", { name: /^Create$/ }).click();
    await expect(page.getByText("Created. Add the anonymized files in Records.")).toBeVisible();
    expect(body).toMatchObject({ patient: { name: "Case A", age: 52, sex: "F", anonymized: true }, protocol: "breast" });
  });
});

test.describe("new case file: review fixes (17 Nov)", () => {
  test.skip(!runsFor("treating") || !MOCK);

  test("a second pick while the first lookup runs: the latest pick wins, box and registration agree", async ({ page }) => {
    await visit(page, "/cases/new");
    await routeFind(page, byQuery);
    const asked: string[] = [];
    const person: Record<string, string> = { [LAKSHMI.uhid]: LAKSHMI.name, [LAXMI.uhid]: LAXMI.name };
    await page.route("**/api/tb/his/lookup**", async (route: Route) => {
      const id = new URL(route.request().url()).searchParams.get("identifier") || "";
      asked.push(id);
      if (id === LAKSHMI.uhid) await new Promise((r) => setTimeout(r, 1500));  // the first pick answers slowly
      const body = { ...fx.hisLookup, identifier: id, patient: { ...fx.hisLookup.patient, uhid: id, name: person[id] ?? "Unknown (SYNTHETIC)" }, similar: [] };
      try { await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) }); } catch { /* the page stopped this lookup */ }
    });
    const box = page.getByRole("combobox", { name: /UHID, IP No/ });
    await box.fill("laxmi");
    await page.getByRole("option", { name: /Lakshmi Narayanan/ }).click();
    await expect(box).toHaveValue(LAKSHMI.uhid);
    await expect(page.getByLabel("Looking up the patient")).toBeVisible();
    await box.fill("laxmi");
    await page.getByRole("option", { name: /Laxmi Devi/ }).click();
    await expect(box).toHaveValue(LAXMI.uhid);
    const reg = page.getByRole("region", { name: "Registration found" });
    await expect(reg).toContainText("Laxmi Devi", { timeout: 20_000 });
    await page.waitForTimeout(2000);  // past the first lookup's slow answer
    await expect(box).toHaveValue(LAXMI.uhid);
    await expect(reg).toContainText("Laxmi Devi");
    await expect(reg).not.toContainText("Lakshmi Narayanan");
    await expect(reg).toContainText(LAXMI.uhid);
    expect(asked).toEqual([LAKSHMI.uhid, LAXMI.uhid]);
  });

  test("a Case File the doctor may not open: only that it exists and its department", async ({ page }) => {
    await visit(page, "/cases/new");
    await routeFind(page, (q) => ({ body: { q, results: [{ ...LAXMI, case_files: [{ department: "Medical Oncology", can_open: false }] }], sources: SOURCES } }));
    await page.getByRole("combobox", { name: /UHID, IP No/ }).fill("devi");
    const opt = page.getByRole("option").first();
    await expect(opt).toContainText("A Case File exists (Medical Oncology)");
    await expect(opt).not.toContainText("Has a Case File");
  });

  test("the Vaidyx admin: no search and no lookup, a plain note instead", async ({ page }) => {
    const base = fx.me("treating");
    await visit(page, "/cases/new", { overrides: { "GET /api/tb/me": { body: { ...base, roles: { ...base.roles, admin: true, vaidyx_admin: true } } } } });
    const finds: string[] = [];
    page.on("request", (r) => { if (r.url().includes("/api/tb/his/find") || r.url().includes("/api/tb/his/lookup")) finds.push(r.url()); });
    await expect(page.getByTestId("no-admin-search")).toHaveText("The Vaidyx admin does not search patients; open a Case File through break-glass.");
    const box = page.getByRole("combobox", { name: /UHID, IP No/ });
    await box.fill("laxmi");
    await page.waitForTimeout(500);
    await expect(page.getByRole("listbox", { name: "Patients found" })).toBeHidden();
    await expect(page.getByRole("button", { name: /Look up/ })).toBeDisabled();
    expect(finds).toEqual([]);
  });
});
