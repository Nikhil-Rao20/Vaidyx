// New Case File: patient lookup (found, similar registrations, existing Case File), cancer picker, logistics, the live fetch.
// Night-v3 items 2.9 and 2.10 (mock only): Colorectal asks colon or rectum, Kidney and Liver ask adult or child (the child's
// option pre-selected under 15; a child's liver tumour goes under the generic rule), a typed cancer (or Others) asks solid or blood (the blood cancer rule), and a draft checklist says so. GET /protocols is the
// backend's real list (support/protocols.json).
import { expect, test, type Page } from "@playwright/test";
import { MOCK, SIZES, THEMES, runsFor, shoot, visit } from "../support/helpers";
import { hisLookup } from "../support/fixtures";

const PHONE_AND_LAPTOP = [SIZES[0], SIZES[2]];

/** Opens the Cancer step for the fixture patient (or one with the given age). */
async function toCancerStep(page: Page, patient: Partial<typeof hisLookup.patient> = {}) {
  await visit(page, "/cases/new?identifier=VXH%2F2026%2F000140", { overrides: { "GET /api/tb/his/lookup": { body: { ...hisLookup, patient: { ...hisLookup.patient, ...patient } } } } });
  await expect(page.getByText("Registration found")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: /Continue/ }).click();
  await expect(page.getByRole("heading", { name: "Which cancer" })).toBeVisible();
}

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
    await page.getByRole("radio", { name: /Thyroid/ }).first().click();  // the one listed cancer with no checklist yet (night-v3 item 2.10)
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

  test("colon or rectum, and a draft checklist", async ({ page }) => {
    test.skip(!MOCK);
    await toCancerStep(page);
    const colorectal = page.getByRole("radio", { name: /Colorectal/ });
    await expect(colorectal).toContainText("checklist built");
    await expect(colorectal).toContainText("draft");  // the colon checklist is a draft
    await expect(page.getByRole("radio", { name: /Breast/ })).not.toContainText("draft");
    await colorectal.click();
    await expect(page.getByText("Where is the tumour?")).toBeVisible();
    await expect(page.getByTestId("cancer-waiting")).toBeVisible();
    await expect(page.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await shoot(page, "newcase", "2-colon-question", { sizes: PHONE_AND_LAPTOP, themes: THEMES });
    await page.getByText("Colon", { exact: true }).click();
    await expect(page.getByText("Colon cancer checklist", { exact: true }).last()).toBeVisible();
    await expect(page.getByTestId("checklist-status")).toHaveText("Checklist built (draft): needs a clinician's check");
    await expect(page.getByRole("region", { name: "Checklist and setting" }).getByText("Draft checklist: needs a clinician's check", { exact: true })).toBeVisible();  // owner decision D6, verbatim
    await expect(page.getByText("Non-metastatic (any T, any N, M0), as recorded")).toBeVisible();  // the settings of colorectal_colon
    await expect(page.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await page.getByText("Non-metastatic (any T, any N, M0), as recorded").click();
    await expect(page.getByRole("button", { name: /Continue/ })).toBeEnabled();
    await shoot(page, "newcase", "2-colon", { sizes: PHONE_AND_LAPTOP, themes: THEMES });
    await page.getByText("Rectum", { exact: true }).click();  // the older rectal checklist: built, not a draft
    await expect(page.getByText("Rectal cancer checklist", { exact: true }).last()).toBeVisible();
    await expect(page.getByTestId("checklist-status")).toHaveText("Checklist built");
    await expect(page.getByRole("region", { name: "Checklist and setting" }).getByText("Draft checklist: needs a clinician's check", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Continue/ })).toBeDisabled();  // a new checklist: its setting is asked again
    // a search finds an entry by a variant's word; an adult gets renal cell carcinoma pre-selected
    await page.getByLabel("Search a cancer").fill("wilms");
    await page.getByRole("radio", { name: /Kidney/ }).click();
    await expect(page.getByRole("radio", { name: "Renal cell carcinoma (adult)" })).toBeChecked();
  });

  test("kidney and liver for a child, and Others", async ({ page }) => {
    test.skip(!MOCK);
    await toCancerStep(page, { name: "Arjun K. (SYNTHETIC)", sex: "male", age: 9, dob: "2017-05-02" });
    await expect(page.getByRole("tab", { name: /Children/ })).toHaveAttribute("aria-selected", "true");
    await page.getByRole("radio", { name: /Kidney/ }).click();
    await expect(page.getByText("Which kidney cancer?")).toBeVisible();
    await expect(page.getByRole("radio", { name: "Wilms tumour (child)" })).toBeChecked();
    await expect(page.getByText("Wilms tumour (child) checklist", { exact: true }).last()).toBeVisible();
    await expect(page.getByText("Unilateral renal mass, suspected Wilms tumour (as recorded)")).toBeVisible();
    await shoot(page, "newcase", "2-kidney-child", { sizes: PHONE_AND_LAPTOP, themes: THEMES });
    // Liver for a child: the child's option is pre-selected and goes under the generic rule, never the adult HCC checklist
    await page.getByRole("radio", { name: /Liver/ }).click();
    await expect(page.getByText("Which liver cancer?")).toBeVisible();
    await expect(page.getByRole("radio", { name: "Hepatoblastoma or another liver tumour of a child" })).toBeChecked();
    const rule = page.getByTestId("generic-rule");
    await expect(rule).toContainText("Hepatoblastoma or another liver tumour of a child: no checklist yet");
    await expect(rule).toContainText("No disease-specific Indian protocol: four core records are checked");
    await expect(page.getByTestId("checklist-status")).toHaveCount(0);  // no built checklist card: the generic rule only
    await expect(page.getByRole("button", { name: /Continue/ })).toBeEnabled();  // the generic rule has no setting to choose
    await shoot(page, "newcase", "2-liver-child", { sizes: PHONE_AND_LAPTOP, themes: THEMES });
    await page.getByText("Hepatocellular carcinoma (adult)", { exact: true }).click();
    await expect(page.getByText("Liver cancer (hepatocellular carcinoma) checklist", { exact: true }).last()).toBeVisible();
    await expect(rule).toHaveCount(0);
    // Others (children): a typed name, which asks solid or blood like any cancer not listed
    await page.getByRole("radio", { name: /Others/ }).click();
    await expect(page.getByText("Is this a solid cancer or a blood cancer?")).toBeVisible();
    await page.getByLabel("Cancer, as written in the record").fill("Neuroblastoma");
    await expect(page.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await page.getByText("Solid cancer (organ, tissue)").click();
    await expect(page.getByTestId("generic-rule")).toContainText("Neuroblastoma: no checklist yet");
    await expect(page.getByRole("button", { name: /Continue/ })).toBeEnabled();
  });

  test("a cancer not listed asks solid or blood", async ({ page }) => {
    test.skip(!MOCK);
    await toCancerStep(page);
    await page.getByRole("button", { name: /The cancer is not listed/ }).click();
    await page.getByLabel("Cancer, as written in the record").fill("Multiple myeloma");
    await expect(page.getByText("Is this a solid cancer or a blood cancer?")).toBeVisible();
    await expect(page.getByRole("radio", { name: /Solid cancer/ })).not.toBeChecked();
    await expect(page.getByRole("radio", { name: /Blood cancer/ })).not.toBeChecked();
    await expect(page.getByRole("button", { name: /Continue/ })).toBeDisabled();  // nothing pre-selected: the step waits for an answer
    await shoot(page, "newcase", "2-blood-question", { sizes: PHONE_AND_LAPTOP, themes: THEMES });
    await page.getByText("Blood cancer (leukaemia, lymphoma, myeloma and the like)").click();
    const rule = page.getByTestId("generic-rule");
    await expect(rule).toContainText("Multiple myeloma: no checklist yet");
    await expect(rule).toContainText("No disease-specific Indian protocol: three core records are checked (blood cancer)");
    await expect(rule).toContainText("Histopathology, bone marrow, flow cytometry or cytogenetics report (any one)");
    await expect(rule).not.toContainText("Staging imaging");
    await expect(rule).not.toContainText("optional");
    await expect(rule.locator("li")).toHaveCount(3);
    await shoot(page, "newcase", "2-blood", { sizes: PHONE_AND_LAPTOP, themes: THEMES });
    await page.getByText("Solid cancer (organ, tissue)").click();
    await expect(rule).toContainText("Staging imaging report (CT, MRI or PET-CT, any one)");
    await page.getByText("Blood cancer (leukaemia, lymphoma, myeloma and the like)").click();
    await page.getByRole("button", { name: /Continue/ }).click();
    await expect(page.getByRole("heading", { name: "Logistics" })).toBeVisible();
    await expect(page.getByTestId("generic-readback")).toContainText("(blood cancer)");
    await expect(page.getByTestId("generic-records")).toContainText("bone marrow");
    let body: Record<string, unknown> | null = null;
    page.on("request", (r) => { if (r.method() === "POST" && r.url().endsWith("/api/tb/cases/from-his")) body = r.postDataJSON(); });
    await page.getByRole("radio", { name: /Urgency 3/ }).click();
    await page.getByRole("button", { name: /Create and fetch records/ }).click();
    await expect(page.locator("#main").getByText("Case File created")).toBeVisible();
    expect(body).toMatchObject({ protocol: "generic_haem", setting: "as_recorded", cancer_name: "Multiple myeloma" });
  });

  test("lookup errors", async ({ page }) => {
    await visit(page, "/cases/new?identifier=VXH%2F2026%2F999999", { overrides: { "GET /api/tb/his/lookup": { body: { found: false, identifier: "VXH/2026/999999" } } } });
    await expect(page.getByText(/Nothing found for/)).toBeVisible();
    await shoot(page, "newcase", "1-not-found", { sizes: [SIZES[0], SIZES[2]] });
    await visit(page, "/cases/new?identifier=VXH%2F2026%2F000140", { overrides: { "GET /api/tb/his/lookup": { status: 502, body: { detail: "The hospital system did not answer: timeout" } } } });
    await shoot(page, "newcase", "1-his-down", { sizes: [SIZES[0]] });
  });
});
