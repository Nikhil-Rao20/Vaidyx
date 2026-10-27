// Screenshots of the guided Case File (21 Oct 2026, docs/ui/casefile-steps/DESIGN.md): the Overview and each section (Question,
// Reports, Check, Pre-Authorization, Summary), the draft stage, the resident's view, the consultant's sign-offs, the phone layout,
// errors and print; desktop and phone, light and dark.
// Run: cd web/tb-nik && npx vite build && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts casefile
// Files: docs/ui/build/shots/casefile-<state>-<theme>-<width>.png. The Case File routes (/steps and /staging included) come from
// e2e/support/f2.ts (SYNTHETIC demo data); the shell comes from e2e/support/helpers.ts.
import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { SHOTS, SIZES, login, prepare, shoot, watchConsole } from "../support/helpers";
import {
  CID, baseSlots, caseFile, caseFileAfterBoard, caseFileBoardRounds, caseFileUnsent, routeCaseFile, stepsAfterBoard, stagingOff, stepsAfterSend, stepsCancerWarning, stepsReadyToSend, stepsResident,
  stepsSummaryStale, team, type CaseRouteOptions,
} from "../support/f2";
import type { Role } from "../support/fixtures";

const DESKTOP_MOBILE = [SIZES[0], SIZES[2]];
const PHONE = SIZES[2];
const SECTION_TESTID = { overview: "section-overview", question: "section-question", reports: "section-reports", check: "section-check", "pre-authorization": "section-pre-authorization", summary: "section-summary" } as const;

/** helpers.shoot from the top of the page: full-page captures of a scrolled page put the sticky top bar mid-image. */
const snap: typeof shoot = (page, name, state, opts = {}) => shoot(page, name, state, { ...opts, before: async (p) => { await p.evaluate(() => window.scrollTo(0, 0)); if (opts.before) await opts.before(p); } });

/** Opens the Case File on a section; by default the work is still open (stepsPrepare) and nothing is sent to the board yet. */
/** Back to the laptop width, and wait for the laptop layout: the guided page renders its body in another tree at phone width
 * (SectionChips) than at laptop width (SectionNav), so React mounts the section again on the change; typing or clicking before
 * that lands on the old tree and is lost (a 3 minute hang in the Question test, night-v3 item 1.10). */
async function laptop(page: Page) {
  await page.setViewportSize(SIZES[0]);
  await expect(page.getByTestId("nav-overview")).toBeVisible();
  await page.waitForTimeout(150);
}

async function open(page: Page, o: CaseRouteOptions & { role?: Role; path?: string; wait?: string } = {}) {
  await prepare(page, { role: o.role ?? "treating" });
  await routeCaseFile(page, { caseFile: caseFileUnsent(), ...o });
  await login(page);
  await page.goto(`/tb-nik/cases/${CID}${o.path ?? ""}`);
  await page.getByTestId(o.wait ?? "casefile-page").first().waitFor({ timeout: 20_000 });
  await page.waitForLoadState("networkidle").catch(() => {});
}

/** No sideways scrolling of the whole page at the current width. */
async function noSideways(page: Page) {
  const width = page.viewportSize()?.width ?? 0;
  const scroll = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scroll).toBeLessThanOrEqual(width + 1);
}

test.describe("guided Case File", () => {
  test("Overview: to do, waiting, the question, the patient at a glance, Continue", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page);
    await expect(page.getByTestId("casefile-page")).toHaveAttribute("data-section", "overview");
    const header = page.getByTestId("case-header");
    await expect(header).toContainText("Priya Venkatesan");
    await expect(header).toContainText("VXH/26/004219");
    await expect(page.getByTestId("send-to-board")).toHaveText(/Send to the board/);
    await expect(page.getByTestId("section-nav")).toBeVisible();
    await expect(page.getByTestId("nav-check")).toHaveAttribute("data-status", "todo");
    await expect(page.getByTestId("nav-pre_authorization")).toHaveAttribute("data-status", "todo");
    const todo = page.getByTestId("todo-row");
    await expect(todo).toHaveCount(4);
    await expect(todo.nth(0)).toContainText("Write the question for the board");
    await expect(todo.nth(1).getByRole("button", { name: "Send request to Radiology" })).toBeVisible();
    await expect(todo.nth(2)).toContainText("Two reports differ");
    await expect(todo.nth(3)).toContainText("Confirm 6 key values");
    const waiting = page.getByTestId("waiting-row");
    await expect(waiting).toHaveCount(1);
    await expect(waiting).toContainText("Overdue. Request sent to Nuclear Medicine");
    await expect(waiting.getByRole("link", { name: "Call the department" })).toHaveAttribute("href", "tel:+91 44 2345 6789");
    await expect(page.getByTestId("overview-question")).toContainText("Not written yet");
    await expect(page.getByTestId("glance").getByTestId(/^glance-/)).toHaveCount(4);
    await expect(page.getByTestId("glance")).toContainText("Positive (Allred score 8/8)");
    await expect(page.getByTestId("warning")).toHaveCount(0);
    await snap(page, "casefile", "overview");
    await page.setViewportSize(PHONE);
    await noSideways(page);
    await laptop(page);
    await page.getByTestId("continue").click();
    await expect(page).toHaveURL(/\/cases\/TB-DEMO-P19\/question$/);
    await expect(page.getByTestId("casefile-page")).toHaveAttribute("data-section", "question");
    expect(errors).toEqual([]);
  });

  test("Overview: a warning with its fixes", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { steps: stepsCancerWarning() });
    const w = page.getByTestId("warning");
    await expect(w).toHaveAttribute("data-kind", "cancer_mismatch");
    await expect(w).toContainText("This Case File is set to Breast cancer.");
    await expect(page.getByTestId("continue")).toContainText("Check the cancer chosen");
    await snap(page, "casefile", "warning", { sizes: DESKTOP_MOBILE, fullPage: false });
    await laptop(page);
    await w.getByRole("button", { name: "Change the cancer" }).click();
    await expect(page.getByTestId("change-cancer")).toBeVisible();
    await snap(page, "casefile", "change-cancer", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });

  test("Overview: the draft stage with its proof, confirmed by the doctor", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page);
    const card = page.getByTestId("staging-card");
    await expect(card).toBeVisible();
    await expect(page.getByTestId("staging-preview")).toContainText("not yet checked by a clinician");
    await expect(page.getByTestId("stage-result")).toContainText("Vaidyx draft stage, for the board to confirm");
    await expect(page.getByTestId("stage-result")).toContainText("Stage IA");
    await expect(page.getByTestId("stage-step-T")).toContainText("Lesion size: 1.9 x 1.6 cm");
    await expect(page.getByTestId("stage-step-N")).toContainText("No suspicious axillary lymph nodes");
    await expect(page.getByTestId("stage-step-M")).toContainText("Clinical examination, no symptoms of spread");
    await snap(page, "casefile", "staging", { sizes: DESKTOP_MOBILE, fullPage: false, before: async (p) => { await p.getByTestId("staging-card").scrollIntoViewIfNeeded(); } });
    await laptop(page);
    await page.getByTestId("confirm-stage").click();
    await expect(page.getByTestId("stage-result")).toContainText("Confirmed by Lakshmi Rao");
    await expect(page.getByTestId("confirm-stage")).toHaveCount(0);
    await snap(page, "casefile", "staging-confirmed", { sizes: [SIZES[0]], fullPage: false, before: async (p) => { await p.getByTestId("staging-card").scrollIntoViewIfNeeded(); } });
    expect(errors).toEqual([]);
  });

  test("Overview: no Stage card when draft staging is off", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { staging: stagingOff() });
    await expect(page.getByTestId("glance")).toBeVisible();
    await expect(page.getByTestId("staging-card")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("Question: the board's question, the reason and the urgency", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { path: "/question" });
    await expect(page.getByTestId("section-question")).toBeVisible();
    await expect(page.getByTestId("nav-question")).toHaveAttribute("aria-current", "page");
    await snap(page, "casefile", "question", { sizes: DESKTOP_MOBILE });
    await laptop(page);
    await page.getByTestId("question-input").fill("Is she fit for breast conservation surgery, or should she get chemotherapy first?");
    await page.getByTestId("question-save").click();
    await expect(page.getByTestId("question-save")).toHaveText("Saved");
    await expect(page.getByTestId("question-text")).toContainText("Written by Lakshmi Rao");
    const reason = page.getByTestId("question-reason").getByRole("radio", { name: "New diagnosis: plan first treatment" });
    await reason.click();
    await expect(reason).toHaveAttribute("aria-checked", "true");
    const urgent = page.getByTestId("question-urgency").getByRole("radio", { name: "4 Urgent" });
    await urgent.click();
    await expect(urgent).toHaveAttribute("aria-checked", "true");
    await page.getByTestId("extra-patient_awareness").getByRole("radio", { name: "Yes" }).click();
    await expect(page.getByTestId("extra-patient_awareness")).toContainText("Entered by Lakshmi Rao");
    await snap(page, "casefile", "question-filled", { sizes: DESKTOP_MOBILE });
    expect(errors).toEqual([]);
  });

  test("Reports: every report with its check and the values read", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { path: "/reports" });
    const rows = page.getByTestId("report-row");
    await expect(rows).toHaveCount(8);
    await expect(rows.first().getByTestId("checked-tag")).toHaveText("Checked by Vaidyx");
    await rows.first().getByTestId("values-read").click();
    await expect(rows.first().getByTestId("values-list")).toBeVisible();
    await snap(page, "casefile", "reports", { sizes: DESKTOP_MOBILE });
    expect(errors).toEqual([]);
  });

  test("Check: two reports differ, then the key values", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { path: "/check" });
    const problem = page.getByTestId("problem-row");
    await expect(problem).toHaveCount(1);
    await expect(problem).toContainText("Primary lesion size");
    await expect(problem.getByTestId("review-panel")).toBeVisible();
    await expect(page.getByTestId("check-source").getByTestId("source-viewer")).toBeVisible();
    await expect(page.getByTestId("key-row")).toHaveCount(6);
    await snap(page, "casefile", "check", { sizes: DESKTOP_MOBILE });
    await laptop(page);
    const first = page.getByTestId("key-row").first();
    await expect(first.getByTestId("confirm-key")).toHaveText(/Confirm Histologic type/);
    await first.getByTestId("confirm-key").click();
    await expect(first).toHaveAttribute("data-confirmed", "yes");
    await expect(first).toContainText("Confirmed by Lakshmi Rao");
    await expect(page.getByText("Key values (1 of 6 confirmed)")).toBeVisible();
    await first.getByRole("button", { name: "Undo" }).click();
    await expect(first).toHaveAttribute("data-confirmed", "no");
    await snap(page, "casefile", "check-key", { sizes: [SIZES[0]], fullPage: false, before: async (p) => { await p.getByTestId("key-row").first().scrollIntoViewIfNeeded(); } });
    expect(errors).toEqual([]);
  });

  test("Pre-Authorization: one request per department, waiting, the board may also ask", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { path: "/pre-authorization" });
    const group = page.getByTestId("missing-group");
    await expect(group).toHaveCount(1);
    await expect(group).toContainText("Radiology");
    await expect(group.getByTestId("missing-item")).toContainText("MRI breast");
    const waiting = page.getByTestId("waiting-group");
    await expect(waiting.getByTestId("waiting-item")).toContainText("Overdue. Request sent to Nuclear Medicine");
    await expect(waiting.getByRole("button", { name: "Send reminder" })).toBeVisible();
    await page.getByRole("button", { name: /The board may also ask for/ }).click();
    await expect(page.getByTestId("missing-item")).toHaveCount(5);
    await snap(page, "casefile", "pre-authorization", { sizes: DESKTOP_MOBILE });
    await laptop(page);
    await group.getByTestId("send-request").click();
    await expect(page.getByText("Request to Radiology. Undo within 10 seconds.")).toBeVisible();
    await snap(page, "casefile", "pre-authorization-undo", { sizes: [SIZES[0]], fullPage: false });
    await page.getByRole("button", { name: "Undo" }).first().click();
    await expect(page.getByText("Undo within 10 seconds")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("Summary: read, then the send dialog, then sent", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { path: "/summary", steps: stepsReadyToSend(), slots: { ...baseSlots, left_before_board: 0, blockers: [] } });
    await expect(page.getByTestId("prose-text")).toBeVisible();
    await expect(page.getByTestId("summary-card")).toContainText("Read by Lakshmi Rao");
    await expect(page.getByTestId("summary-entered")).toContainText("Is she fit for breast conservation surgery");
    await expect(page.getByTestId("summary-briefs")).toBeVisible();
    await expect(page.getByTestId("summary-published")).toBeVisible();
    await expect(page.getByTestId("continue")).toContainText("Send to the board");
    await snap(page, "casefile", "summary", { sizes: DESKTOP_MOBILE });
    await laptop(page);
    await page.getByTestId("summary-send").click();
    const dialog = page.getByTestId("mark-ready-dialog");
    await expect(dialog).toBeVisible();
    // the multi-step send (night-v3 item 1.4, design B7): meeting (the next one pre-selected), list, presenter, note, confirm
    await expect(dialog.getByTestId("send-meeting").first()).toHaveAttribute("aria-checked", "true");
    await snap(page, "casefile", "send-dialog", { sizes: DESKTOP_MOBILE, fullPage: false });
    await laptop(page);
    for (let i = 0; i < 3; i++) await dialog.getByTestId("send-next").click();
    await expect(dialog).toContainText("Nothing left before the board.");
    await dialog.getByTestId("send-next").click();
    await snap(page, "casefile", "send-confirm", { sizes: DESKTOP_MOBILE, fullPage: false });
    await laptop(page);
    await dialog.getByRole("button", { name: "Send to the board" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByTestId("summary-card")).toContainText("Sent to the board");
    await expect(page.getByTestId("continue-done")).toContainText("Sent to the board");
    await expect(page.getByTestId("send-to-board")).toHaveCount(0);
    await snap(page, "casefile", "sent", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });

  test("Summary: after it went to the board", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { path: "/summary", steps: stepsAfterSend(), caseFile: caseFile() });
    await expect(page.getByTestId("summary-send")).toHaveCount(0);
    await expect(page.getByTestId("case-header")).toContainText("Sent to the board");
    await expect(page.getByTestId("continue-done")).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("Summary: the reports changed after it was written", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { path: "/summary", steps: stepsSummaryStale() });
    await expect(page.getByTestId("summary-card")).toContainText("The reports changed after this was written: A new report arrived.");
    await expect(page.getByTestId("summary-card").getByRole("button", { name: "Write it again" })).toBeVisible();
    await expect(page.getByTestId("nav-summary")).toContainText("Records changed: write it again");
    await snap(page, "casefile", "summary-stale", { sizes: DESKTOP_MOBILE, fullPage: false });
    expect(errors).toEqual([]);
  });

  test("resident: every step goes to the consultant for sign-off", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { role: "resident", steps: stepsResident(), team: team({ can: { manage: false, leave: true, set_urgency: false, propose: true, archive: false, consent: false } }) });
    await expect(page.getByTestId("send-to-board")).toHaveText(/Send to Dr Lakshmi Rao for sign-off/);
    await expect(page.getByTestId("proposals-strip")).toHaveCount(0);
    await expect(page.getByTestId("staging-card")).toBeVisible();
    await expect(page.getByTestId("confirm-stage")).toHaveCount(0);
    await snap(page, "casefile", "resident", { sizes: DESKTOP_MOBILE });
    await laptop(page);
    await page.getByTestId("nav-question").click();
    await page.getByTestId("question-input").fill("Is she fit for breast conservation surgery, or should she get chemotherapy first?");
    await expect(page.getByTestId("question-save")).toHaveText("Send to Dr Lakshmi Rao for sign-off");
    await expect(page.getByTestId("question-urgency")).toContainText("Dr Lakshmi Rao signs off the urgency.");
    await page.getByTestId("question-save").click();
    await expect(page.getByText("Sent to Dr Lakshmi Rao for sign-off").first()).toBeVisible();
    await page.getByTestId("question-urgency").getByRole("radio", { name: "5 Most urgent" }).click();
    await expect(page.getByText("Dr Lakshmi Rao asked to set urgency 5")).toBeVisible();
    await snap(page, "casefile", "resident-question", { sizes: DESKTOP_MOBILE });
    await laptop(page);
    await page.getByTestId("nav-check").click();
    await expect(page.getByTestId("section-check")).toBeVisible();
    await expect(page.getByTestId("confirm-key")).toHaveCount(0);
    await expect(page.getByText("Dr Lakshmi Rao confirms the key values.").first()).toBeVisible();
    await page.getByTestId("nav-pre_authorization").click();
    await expect(page.getByTestId("send-request")).toHaveText("Send to Dr Lakshmi Rao for sign-off");
    await snap(page, "casefile", "resident-pre-authorization", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });

  test("consultant: sign-offs from the team on the Overview", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page);
    const strip = page.getByTestId("proposals-strip");
    await expect(strip).toBeVisible();
    await expect(strip).toContainText("Asha Menon");
    await expect(strip.getByRole("button", { name: "Approve" })).toHaveCount(2);
    await snap(page, "casefile", "proposals", { sizes: DESKTOP_MOBILE, fullPage: false });
    expect(errors).toEqual([]);
  });

  test("phone: the sections as chips, no sideways scroll", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(PHONE);
    await open(page);
    await expect(page.getByTestId("section-chips")).toBeVisible();
    await expect(page.getByTestId("section-nav")).toHaveCount(0);
    await noSideways(page);
    await snap(page, "casefile", "phone-overview", { sizes: [PHONE] });
    for (const [label, slug] of [["Question", "question"], ["Reports", "reports"], ["Check", "check"], ["Pre-Authorization", "pre-authorization"], ["Summary", "summary"]] as const) {
      await page.setViewportSize(PHONE);
      await page.getByTestId("section-chips").getByRole("button", { name: label, exact: false }).first().click();
      await expect(page.getByTestId(SECTION_TESTID[slug])).toBeVisible();
      await expect(page).toHaveURL(new RegExp(`/${slug}$`));
      await noSideways(page);
      await snap(page, "casefile", `phone-${slug}`, { sizes: [PHONE] });
    }
    expect(errors).toEqual([]);
  });

  test("Ask about this patient, from every section", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { path: "/check" });
    await page.getByTestId("ask-bubble").click();
    await expect(page.getByTestId("side-panel").getByTestId("ask-panel")).toBeVisible();
    await expect(page.getByTestId("chat-thread").first()).toBeVisible();
    await snap(page, "casefile", "ask", { sizes: DESKTOP_MOBILE, fullPage: false });
    expect(errors).toEqual([]);
  });

  for (const panel of ["team", "board"] as const) {
    test(`one click away: ${panel}`, async ({ page }) => {
      const errors = watchConsole(page);
      await open(page, { path: `/${panel}` });
      await expect(page.getByTestId("side-panel").getByTestId(panel === "team" ? "team-panel" : "board-form")).toBeVisible();
      await snap(page, "casefile", panel, { sizes: DESKTOP_MOBILE, fullPage: false });
      expect(errors).toEqual([]);
    });
  }

  test("Board decisions: every round, the correction and its versions", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { path: "/board", caseFile: caseFileBoardRounds() });
    const panel = page.getByTestId("side-panel").getByTestId("board-form");
    await expect(panel).toBeVisible();
    // newest first, counted from the oldest
    await expect(panel.locator("article").first()).toHaveAttribute("data-testid", "board-round-2");
    const r2 = panel.getByTestId("board-round-2");
    const r1 = panel.getByTestId("board-round-1");
    await expect(r2.locator("h3")).toHaveText("Round 2, 23/10/2026");
    await expect(r1.locator("h3")).toHaveText("Round 1, 09/10/2026");
    await expect(r2).toContainText("Decision recorded");
    await expect(r1).toContainText("Deferred: information awaited");
    await expect(r1.locator("[data-field=awaited_from]")).toContainText("Radiology");
    await expect(r2.locator("[data-field=intent]")).toContainText("Curative");
    await expect(r2.locator("[data-field=modalities]")).toContainText("Surgery, Radiotherapy");
    await expect(r2.locator("[data-field=investigations]")).toContainText("Bone scan (Nuclear Medicine, due 02/11/2026)");
    await expect(r2.locator("[data-field=referrals]")).toContainText("Genetics and counselling (Medical Oncology): BRCA testing and counselling");
    await expect(r2.locator("[data-field=concerns]")).toContainText("Thomas Joseph: Would like Ki-67 repeated");
    await expect(r2.getByTestId("round-actions")).toContainText("Investigation: Bone scan (Nuclear Medicine, due 02/11/2026)");
    await expect(r2.getByTestId("corrected-line")).toHaveText("Corrected by Lakshmi Rao on 24/10/2026 (version 2): The board named radiotherapy after surgery; it was left out in the meeting.");
    await r2.getByTestId("earlier-versions").locator("summary").click();
    await expect(r2.getByTestId("earlier-versions")).toContainText("Modalities: was Surgery, now Surgery, Radiotherapy");
    await expect(r2.getByTestId("earlier-versions")).toContainText("Sequence: was Surgery first, now Surgery, then adjuvant radiotherapy");
    // only the round the login may correct has the button
    await expect(r1.getByTestId("correct-record")).toHaveCount(0);
    await snap(page, "casefile", "board-decisions", { sizes: DESKTOP_MOBILE, fullPage: false });
    await laptop(page);
    await r2.getByTestId("correct-record").click();
    const dialog = page.getByTestId("correct-dialog");
    await expect(dialog.getByTestId("correct-outcome")).toContainText("Decision recorded");
    await expect(dialog.getByTestId("live-strip-note")).toHaveCount(0);
    await dialog.getByTestId("decision-step-2").click();
    await expect(dialog.locator("#d-text")).toHaveValue(/Breast conservation surgery/);
    await expect(dialog.getByRole("radio", { name: "Curative" })).toHaveAttribute("aria-checked", "true");
    await snap(page, "casefile", "board-correct", { sizes: [SIZES[0]], fullPage: false });
    await dialog.locator("#d-stage_as_agreed").fill("cT1c cN0 cM0, as in the MRI breast");
    await dialog.getByTestId("save-correction").click();
    await expect(dialog.getByTestId("decision-problems")).toContainText("Step 6: give the reason for the correction");
    await dialog.getByTestId("decision-step-6").click();
    await dialog.getByTestId("correction-reason").fill("The stage as agreed was read out with its source.");
    const posted = page.waitForRequest((r) => r.method() === "POST" && r.url().includes("/board-records/") && r.url().endsWith("/correct"));
    await dialog.getByTestId("save-correction").click();
    const body = (await posted).postDataJSON();
    expect(body).toEqual({ changes: { stage_as_agreed: "cT1c cN0 cM0, as in the MRI breast" }, reason: "The stage as agreed was read out with its source." });
    await expect(dialog).toHaveCount(0);
    await expect(r2.getByTestId("corrected-line")).toContainText("(version 3): The stage as agreed was read out with its source.");
    await expect(r2.locator("[data-field=stage_as_agreed]")).toContainText("as in the MRI breast");
    expect(errors).toEqual([]);
  });

  test("Case summary after the board: the main summary, its versions, an edit, the review, the header line", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { path: "/summary", steps: stepsAfterBoard(), caseFile: caseFileAfterBoard() });
    const card = page.getByTestId("case-summary-card");
    await expect(card).toBeVisible();
    await expect(card.getByTestId("cs-header-line")).toHaveText("Version 2, written 24/10/2026, 10:20 by Gemma-4-31B (non-medical)");
    await expect(card).toContainText("AI draft, not reviewed");
    for (const id of ["presentation", "stage", "rounds", "since", "status"]) await expect(card.getByTestId(`cs-section-${id}`)).toBeVisible();
    await expect(card.getByTestId("cs-round")).toHaveCount(2);
    await expect(card.getByTestId("cs-section-rounds")).toContainText("Board 23/10/2026, Decision, in the board's words");
    await expect(card.getByTestId("cs-section-rounds")).toContainText("Member's card");
    await expect(card.getByTestId("cs-section-status")).toContainText("Action: task");
    await expect(card.getByTestId("cs-section-stage")).toContainText("Board 23/10/2026, Stage as agreed by the board");
    await expect(card.getByTestId("cs-edited").first()).toHaveText(/edited by Dr Lakshmi Rao on 24\/10\/2026, not checked against the record/);
    await expect(card.locator("[data-id=presentation-1]").getByTestId("cs-suggested")).toContainText("Vaidyx wrote");
    await card.locator("[data-id=presentation-1]").getByTestId("cs-suggested").locator("summary").click();
    await expect(card.locator("[data-id=presentation-1]").getByTestId("cs-suggested")).toContainText("Vaidyx wrote: Presenting complaint: lump in the right breast noticed 6 weeks ago.");
    await expect(card.locator("[data-id=presentation-1]").getByTestId("cs-suggested").locator("button.quote-chip")).toHaveCount(1);
    await expect(card.locator("[data-id=presentation-4]").getByTestId("cs-unmatched")).toHaveText("kept from an earlier version; no current sentence matches");
    await expect(card.getByTestId("cs-unmatched")).toHaveCount(1);
    await expect(card.getByTestId("cs-removed")).toHaveText("1 sentence dropped because it could not be checked against the records.");
    // code sentences carry no AI mark and no pencil; the model sentences do
    await expect(card.locator("[data-id=rBade0ac-decision_text] [aria-label='Written by the AI model']")).toHaveCount(0);
    await expect(card.locator("[data-id=presentation-2] [aria-label='Written by the AI model']")).toHaveCount(1);
    await expect(card.getByTestId("cs-edit")).toHaveCount(3);
    // the pre-board summary folds under "Before the board on", closed
    const pre = page.getByTestId("summary-card");
    await expect(pre).toContainText("Before the board on 09/10/2026");
    await expect(pre).not.toHaveAttribute("open", "");
    await snap(page, "casefile", "case-summary", { sizes: DESKTOP_MOBILE });
    await laptop(page);
    await pre.locator("summary").first().click();
    await expect(pre.getByTestId("prose-text")).toBeVisible();
    await expect(pre.getByTestId("preboard-history")).toContainText("Earlier versions (2)");
    await pre.getByTestId("preboard-history").locator("summary").click();
    await expect(pre.getByTestId("preboard-history").locator("li")).toHaveCount(2);
    await expect(pre.getByTestId("preboard-history").locator("li").last()).toHaveText("Written 28/09/2026, 08:00, by Gemma-4-31B (non-medical), read");
    // version 1, read-only
    await card.getByTestId("cs-version").selectOption("1");
    await expect(card.getByTestId("cs-header-line")).toContainText("Version 1, written 23/10/2026, 18:10");
    await expect(card).toContainText("Reviewed by Dr Lakshmi Rao");
    await expect(card.getByTestId("cs-edit")).toHaveCount(0);
    await card.getByRole("button", { name: "Back to the current version" }).click();
    // an edit of a model sentence
    await card.locator("[data-id=presentation-2]").getByTestId("cs-edit").click();
    await card.getByRole("textbox", { name: "The sentence, in your words" }).fill("The histopathology report records Grade 2 (Nottingham score 6).");
    await card.getByTestId("cs-edit-save").click();
    await expect(card.locator("[data-id=presentation-2]")).toContainText("The histopathology report records Grade 2 (Nottingham score 6).");
    await expect(card.locator("[data-id=presentation-2]").getByTestId("cs-edited")).toContainText("edited by Dr Lakshmi Rao");
    // the review
    await card.getByTestId("cs-review").click();
    await expect(card).toContainText("Reviewed by Dr Lakshmi Rao");
    await expect(card.getByTestId("cs-review")).toHaveCount(0);
    // the summary line in the header, edited by the consultant
    const line = page.getByTestId("summary-line");
    await expect(line).toContainText("52 F, early breast cancer: board 23/10/2026 decision recorded");
    await expect(line.getByTestId("summary-line-edited")).toHaveText("edited by Dr Lakshmi Rao");
    await expect(line.getByTestId("summary-line-vaidyx-tag")).toHaveCount(0);
    await snap(page, "casefile", "header-summary-line", { sizes: DESKTOP_MOBILE, fullPage: false });
    await laptop(page);
    await page.getByTestId("summary-line-pencil").click();
    await page.getByLabel("Summary line").fill("Early breast cancer, decision recorded 23/10/2026; bone scan open (SYNTHETIC)");
    const posted = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith("/summary-line"));
    await page.getByTestId("summary-line-save").click();
    expect((await posted).postDataJSON()).toEqual({ text: "Early breast cancer, decision recorded 23/10/2026; bone scan open (SYNTHETIC)" });
    await expect(page.getByTestId("summary-line")).toContainText("bone scan open");
    await page.getByTestId("summary-line-pencil").click();
    await page.getByTestId("summary-line-vaidyx").click();
    await expect(page.getByTestId("summary-line")).toContainText("1 action open");
    await expect(page.getByTestId("summary-line-edited")).toHaveCount(0);
    await expect(page.getByTestId("summary-line-vaidyx-tag")).toHaveText("Vaidyx line");
    await noSideways(page);
    expect(errors).toEqual([]);
  });

  test("Case summary on the Overview", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { steps: stepsAfterBoard(), caseFile: caseFileAfterBoard() });
    const ov = page.getByTestId("overview-case-summary");
    await expect(ov).toBeVisible();
    await expect(ov.getByTestId("overview-summary-line")).toContainText("52 F, early breast cancer");
    await expect(ov).toContainText("Outcome as recorded: Decision recorded.");
    await expect(ov).toContainText("Decision as recorded:");
    await expect(ov).toContainText("She presented with a lump in the right breast");
    await expect(ov).not.toContainText("Deferred: information awaited");
    // above the question for the board
    const y = async (id: string) => (await page.getByTestId(id).boundingBox())!.y;
    expect(await y("overview-case-summary")).toBeLessThan(await y("overview-question"));
    await snap(page, "casefile", "overview-case-summary", { sizes: DESKTOP_MOBILE, fullPage: false, before: async () => { await ov.scrollIntoViewIfNeeded(); } });
    await laptop(page);
    await ov.getByTestId("open-case-summary").click();
    await expect(page.getByTestId("case-summary-card")).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("new records since you looked", async ({ page }) => {
    const errors = watchConsole(page);
    await page.clock.install();
    await open(page);
    const base = caseFileUnsent();
    const changed = { ...base, signature: { hash: "changed-for-the-test" }, documents: [...base.documents, { ...base.documents[4], doc_id: "Dnew0001" }] };
    await page.unroute(`**/api/tb/cases/${CID}**`);
    await routeCaseFile(page, { caseFile: changed });
    await page.clock.fastForward(31_000);
    await expect(page.getByTestId("stale-banner")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("stale-banner")).toContainText("1 new report since you looked.");
    await snap(page, "casefile", "stale-banner", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.clock.resume();
    await page.getByTestId("stale-banner").getByRole("button", { name: "Show" }).click();
    // The banner fades out with Motion, which the installed fake clock does not drive; the announcement is the check.
    await expect(page.getByText("Showing the latest reports.")).toBeAttached();
    expect(errors).toEqual([]);
  });

  test("errors and loading", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { caseFile: { status: 500 }, wait: "casefile-error" });
    await expect(page.getByTestId("casefile-error")).toHaveAttribute("data-status", "500");
    await expect(page.getByRole("alert").first()).toContainText("The server could not answer.");
    await snap(page, "casefile", "error-500", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.unroute(`**/api/tb/cases/${CID}**`);
    await routeCaseFile(page, { caseFile: { status: 404, body: { detail: "Case not found" } } });
    await page.reload();
    await expect(page.getByText("This Case File does not exist")).toBeVisible();
    await snap(page, "casefile", "error-404", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.unroute(`**/api/tb/cases/${CID}**`);
    await routeCaseFile(page, { caseFile: { status: 403, body: { detail: "Forbidden" } } });
    await page.reload();
    await expect(page.getByText("You do not have access to this Case File")).toBeVisible();
    await snap(page, "casefile", "error-403", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.unroute(`**/api/tb/cases/${CID}**`);
    await routeCaseFile(page, { delayMs: 60_000 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByLabel("Loading the Case File")).toBeVisible();
    await page.screenshot({ path: path.join(SHOTS, "casefile-loading-light-1366.png") });
    expect(errors).toEqual([]);
  });

  test("the guided view fails or is missing: the header stays, the cause is said, no older page", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { steps: { status: 500 } });
    await expect(page.getByTestId("case-header")).toContainText("Priya Venkatesan");
    await expect(page.getByRole("alert").first()).toContainText("The server could not answer.");
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
    await snap(page, "casefile", "steps-error", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.unroute(`**/api/tb/cases/${CID}**`);
    await routeCaseFile(page, { caseFile: caseFileUnsent(), notBuilt: ["steps"] });
    await page.reload();
    await expect(page.getByTestId("case-header")).toBeVisible();
    await expect(page.getByText("This is not on the server.")).toBeVisible();
    await expect(page.getByTestId("summary-column")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("print: the section, without the navigation", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { path: "/summary", steps: stepsReadyToSend() });
    await page.emulateMedia({ media: "print" });
    await expect(page.getByTestId("section-nav")).toBeHidden();
    await expect(page.getByTestId("ask-bubble")).toBeHidden();
    await expect(page.getByTestId("prose-text")).toBeVisible();
    await snap(page, "casefile", "print", { sizes: [SIZES[0]], themes: ["light"] });
    await page.emulateMedia({ media: "screen" });
    expect(errors).toEqual([]);
  });
});
