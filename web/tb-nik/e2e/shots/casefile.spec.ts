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
  CID, baseSlots, caseFile, caseFileUnsent, routeCaseFile, stagingOff, stepsAfterSend, stepsCancerWarning, stepsReadyToSend, stepsResident,
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
