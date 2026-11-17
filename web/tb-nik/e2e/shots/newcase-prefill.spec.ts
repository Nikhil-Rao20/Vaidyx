// New Case File, AI pre-fill after the lookup (docs/new-case/DESIGN.md N6), mock only: the job's answer fills the untouched fields
// with an "AI" note and the quote one tap away, editing a field clears its note, urgency is only suggested (never pre-selected, one
// tap to use), the department is chosen for a doctor of several departments, "Clear AI suggestions" puts back what was there, a field
// the doctor touched while the AI was reading is left alone, a value typed before a second lookup is never overwritten (only empty
// fields are filled), the Vaidyx admin never starts it, a Colorectal answer picks its variant, and a failed job is one quiet line.
import { expect, test, type Page } from "@playwright/test";
import { MOCK, SIZES, THEMES, shoot, visit, type Overrides } from "../support/helpers";
import { hisLookup, me } from "../support/fixtures";

const PHONE_AND_LAPTOP = [SIZES[0], SIZES[2]];
const HPE = { id: "R1", title: "Histopathology report (biopsy)", date: "2026-11-05", department: "Pathology" };
const CT = { id: "R2", title: "CECT thorax abdomen pelvis", date: "2026-11-03", department: "Radiology" };
const OPD = { id: "R3", title: "OPD consultation note", date: "2026-11-01", department: "Breast Surgery" };
const RESULT = {
  uhid: "VXH/2026/000140",
  cancer: { name: "Invasive breast carcinoma, left breast", protocol: "breast", label: "Breast cancer", quote: "Invasive breast carcinoma of no special type, left breast", report: HPE },
  setting: { id: "early", label: "Early (operable), as recorded", quote: "No evidence of distant metastasis.", report: CT },
  board_question: { text: "Upfront surgery or neoadjuvant chemotherapy for this left breast carcinoma?", basis: [HPE, OPD], draft: true },
  urgency: { level: 4, reason: "Biopsy-proven cancer and the patient is waiting to start treatment.", quote: "Patient anxious to start treatment early", report: OPD },
  department: { id: "breast_surgery", name: "Breast Surgery", why: "Your department in the patient's visits: OP visit OP/2026/01022 on 05/11/2026" },
  model: { label: "Gemma-4-31B-it", origin: "Google (USA)", medical: false },
  reports_in_window: 9, reports_read: 3, reports_skipped: 6, reports: [HPE, CT, OPD],
  dropped: [{ field: "urgency", reason: "the quote was not found in the reports" }],
};
/** A treating doctor of two departments: the department is asked, so the AI may fill it. */
const TWO_DEPTS = (() => { const m = me("treating"); return { ...m, roles: { ...m.roles, departments: { breast_surgery: "head", surgical_oncology: "member" }, treating: ["breast_surgery", "surgical_oncology"] } }; })();

function overrides(job: Record<string, unknown>, extra: Overrides = {}): Overrides {
  return {
    "POST /api/tb/his/prefill": { body: { job: "PF-mock", state: "running" } },
    "GET /api/tb/his/prefill/PF-mock": { body: { job: "PF-mock", ...job } },
    ...extra,
  };
}

async function toCancerStep(page: Page, o: Overrides) {
  await visit(page, "/cases/new?identifier=VXH%2F2026%2F000140", { overrides: { "GET /api/tb/his/lookup": { body: hisLookup }, ...o } });
  await expect(page.getByText("Registration found")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /Continue/ }).click();
  await expect(page.getByRole("heading", { name: "Which cancer" })).toBeVisible();
}

test.describe("new case file, AI pre-fill", () => {
  test.skip(!MOCK);

  test("fills the steps, each with its proof, and the doctor's edits win", async ({ page }) => {
    let body: Record<string, unknown> | null = null;
    page.on("request", (r) => { if (r.method() === "POST" && r.url().endsWith("/api/tb/cases/from-his")) body = r.postDataJSON(); });
    await toCancerStep(page, overrides({ state: "done", result: RESULT }, { "GET /api/tb/me": { body: TWO_DEPTS } }));
    const status = page.getByTestId("prefill-status");
    await expect(status).toContainText("Filled from 3 reports. Check each value.");
    await expect(status).toContainText("Gemma-4-31B (non-medical)");
    await expect(status).toContainText("1 suggestion left out");
    await expect(page.getByRole("radio", { name: /Breast/ }).first()).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "Early (operable), as recorded" })).toBeChecked();
    const cancer = page.getByTestId("ai-filled-cancer");
    await expect(cancer).toContainText("Filled by AI as Invasive breast carcinoma, left breast from Histopathology report (biopsy)");
    await cancer.getByRole("button", { name: "Show the quote" }).click();
    await expect(cancer.getByTestId("ai-proof")).toContainText("Invasive breast carcinoma of no special type, left breast");
    await expect(cancer.getByTestId("ai-proof")).toContainText("Found word for word in Histopathology report (biopsy)");
    await expect(page.getByTestId("ai-filled-setting")).toBeVisible();
    await shoot(page, "newcase-prefill", "2-filled", { sizes: PHONE_AND_LAPTOP, themes: THEMES });
    // the doctor picks another setting: its AI note goes, the cancer's stays
    await page.getByText("Locally advanced, as recorded").click();
    await expect(page.getByTestId("ai-filled-setting")).toHaveCount(0);
    await expect(cancer).toBeVisible();

    await page.getByRole("button", { name: /Continue/ }).click();
    await expect(page.getByRole("heading", { name: "Logistics" })).toBeVisible();
    await expect(page.getByLabel("The question for the board")).toHaveValue(RESULT.board_question.text);
    await expect(page.getByTestId("ai-filled-boardQuestion")).toContainText("Drafted by AI from 2 reports");
    for (const n of [1, 2, 3, 4, 5]) await expect(page.getByRole("radio", { name: new RegExp(`^Urgency ${n}`) })).toHaveAttribute("aria-checked", "false");  // never pre-selected
    const urgency = page.getByTestId("ai-urgency");
    await expect(urgency).toContainText("AI suggests 4: Biopsy-proven cancer");
    await expect(page.getByRole("combobox", { name: "Responsible Department" })).toContainText("Breast Surgery");
    await expect(page.getByTestId("ai-filled-department")).toContainText("Chosen from the patient's visits");
    await shoot(page, "newcase-prefill", "3-filled", { sizes: PHONE_AND_LAPTOP, themes: THEMES });
    await page.getByLabel("The question for the board").fill("Neoadjuvant chemotherapy first?");
    await expect(page.getByTestId("ai-filled-boardQuestion")).toHaveCount(0);
    await urgency.getByRole("button", { name: "Use 4" }).click();
    await expect(page.getByRole("radio", { name: /^Urgency 4/ })).toHaveAttribute("aria-checked", "true");
    await expect(urgency).toContainText("In use");
    await page.getByRole("button", { name: /Create and fetch records/ }).click();
    await expect(page.locator("#main").getByText("Case File created")).toBeVisible();
    expect(body).toMatchObject({ protocol: "breast", setting: "locally_advanced", department: "breast_surgery", cancer_name: "Breast" });
  });

  test("Clear AI suggestions puts back what was there", async ({ page }) => {
    await toCancerStep(page, overrides({ state: "done", result: RESULT }));
    await expect(page.getByTestId("prefill-status")).toContainText("Filled from 3 reports");
    await expect(page.getByRole("radio", { name: /Breast/ }).first()).toHaveAttribute("aria-checked", "true");
    await page.getByRole("button", { name: "Clear AI suggestions" }).click();
    await expect(page.getByTestId("prefill-status")).toHaveText("AI suggestions cleared.");
    await expect(page.getByRole("radio", { name: /Breast/ }).first()).toHaveAttribute("aria-checked", "false");
    await expect(page.getByTestId("ai-filled-cancer")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await page.getByRole("radio", { name: /Cervix/ }).click();
    await page.getByText("Early (FIGO 2018 IA1 to IIA1), as recorded").click();
    await page.getByRole("button", { name: /Continue/ }).click();
    await expect(page.getByLabel("The question for the board")).toHaveValue("");
    await expect(page.getByTestId("ai-urgency")).toHaveCount(0);
  });

  test("a field touched while the AI reads is left alone", async ({ page }) => {
    await toCancerStep(page, overrides({ state: "done", result: RESULT }, { "GET /api/tb/his/prefill/PF-mock": { delayMs: 3500, body: { job: "PF-mock", state: "done", result: RESULT } } }));
    await expect(page.getByTestId("prefill-status")).toContainText("Reading 9 reports to fill this in. You can carry on.");
    await shoot(page, "newcase-prefill", "2-reading", { sizes: [SIZES[2]], themes: ["light"] });
    await page.getByRole("radio", { name: /Lung/ }).click();
    await expect(page.getByTestId("prefill-status")).toContainText("Filled from 3 reports", { timeout: 15_000 });
    await expect(page.getByRole("radio", { name: /Lung/ })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: /Breast/ }).first()).toHaveAttribute("aria-checked", "false");
    await expect(page.getByTestId("ai-filled-cancer")).toHaveCount(0);
    await expect(page.getByTestId("ai-filled-setting")).toHaveCount(0);  // the AI's setting was for breast, not lung
    await page.getByText("Non-metastatic", { exact: false }).first().click();
    await page.getByRole("button", { name: /Continue/ }).click();
    await expect(page.getByLabel("The question for the board")).toHaveValue(RESULT.board_question.text);  // untouched: filled
  });

  test("a value typed before a second lookup is never overwritten", async ({ page }) => {
    // the first patient's AI is not available; the doctor picks a cancer and writes the question, then goes back and looks up another
    await toCancerStep(page, overrides({ state: "failed", error: "The AI could not read the records just now. Fill the steps yourself; nothing else is affected." }));
    await page.getByRole("radio", { name: /Cervix/ }).click();
    await page.getByText("Early (FIGO 2018 IA1 to IIA1), as recorded").click();
    await page.getByRole("button", { name: /Continue/ }).click();
    await page.getByLabel("The question for the board").fill("My own question for the board?");
    const other = { ...hisLookup, identifier: "VXH/2026/000141", patient: { ...hisLookup.patient, id: "p141", uhid: "VXH/2026/000141", name: "Lakshmi R." } };
    let started = 0;
    await page.route("**/api/tb/his/lookup*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(other) }));
    await page.route("**/api/tb/his/prefill", (route) => { started += 1; return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ job: "PF-two", state: "running" }) }); });
    await page.route("**/api/tb/his/prefill/PF-two", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ job: "PF-two", state: "done", result: { ...RESULT, uhid: "VXH/2026/000141", urgency: undefined } }) }));
    await page.getByRole("button", { name: /^Back/ }).click();
    await page.getByRole("button", { name: /^Back/ }).click();
    await page.getByLabel("UHID, IP No., OP No. or ABHA, or the patient's name").fill("VXH/2026/000141");
    await page.getByRole("button", { name: /Look up/ }).click();
    await expect(page.getByText("VXH/2026/000141").first()).toBeVisible();
    await expect.poll(() => started).toBe(1);
    await page.getByRole("button", { name: /Continue/ }).click();
    await expect(page.getByTestId("prefill-status")).toContainText("The AI read 3 reports. Your own entries were kept", { timeout: 15_000 });
    await expect(page.getByRole("radio", { name: /Cervix/ })).toHaveAttribute("aria-checked", "true");    // the doctor's pick, not the AI's breast
    await expect(page.getByTestId("ai-filled-cancer")).toHaveCount(0);
    await page.getByRole("button", { name: /Continue/ }).click();
    await expect(page.getByLabel("The question for the board")).toHaveValue("My own question for the board?");
    await expect(page.getByTestId("ai-filled-boardQuestion")).toHaveCount(0);
  });

  test("the Vaidyx admin never starts it", async ({ page }) => {
    let started = 0;
    page.on("request", (r) => { if (r.url().includes("/api/tb/his/prefill")) started += 1; });
    const vx = me("vaidyx_admin");
    const VX_TREATING = { ...vx, roles: { ...vx.roles, departments: { breast_surgery: "member" }, treating: ["breast_surgery"] } };
    // even with a treating role and a patient number in the link, no suggestion job is asked for (the server refuses it too: 403)
    await visit(page, "/cases/new?identifier=VXH%2F2026%2F000140", { overrides: { "GET /api/tb/his/lookup": { body: hisLookup }, ...overrides({ state: "done", result: RESULT }), "GET /api/tb/me": { body: VX_TREATING } } });
    await expect(page.getByTestId("no-admin-search")).toBeVisible();  // the Vaidyx admin gets a note instead of the finder
    await page.waitForTimeout(2500);
    await expect(page.getByTestId("prefill-status")).toHaveCount(0);
    expect(started).toBe(0);
  });

  test("a colorectal answer picks its variant", async ({ page }) => {
    const rectum = { ...RESULT, cancer: { name: "Adenocarcinoma of the rectum", protocol: "colorectal_rectum", label: "Rectal cancer", entry: "colorectal", variant: "rectum", quote: "Adenocarcinoma of the rectum", report: HPE }, setting: undefined };
    await toCancerStep(page, overrides({ state: "done", result: rectum }));
    await expect(page.getByRole("radio", { name: /Colorectal/ })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("radio", { name: "Rectum" })).toBeChecked();
    await expect(page.getByTestId("ai-filled-cancer")).toContainText("Adenocarcinoma of the rectum");
    await expect(page.getByRole("button", { name: /Continue/ })).toBeDisabled();  // the setting is still the doctor's to pick
  });

  test("a failed job is one quiet line", async ({ page }) => {
    await toCancerStep(page, overrides({ state: "failed", error: "The AI could not read the records just now. Fill the steps yourself; nothing else is affected." }));
    await expect(page.getByTestId("prefill-status")).toHaveText("The AI could not read the records just now. Fill the steps yourself; nothing else is affected.");
    await expect(page.getByTestId("ai-filled-cancer")).toHaveCount(0);
    await expect(page.locator('[role="radio"][aria-checked="true"]')).toHaveCount(0);
    await shoot(page, "newcase-prefill", "2-failed", { sizes: [SIZES[2]], themes: ["dark"] });
  });
});
