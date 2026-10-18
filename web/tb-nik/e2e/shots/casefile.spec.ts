// Screenshots of the Case File page (fill-in summary): every section and state, desktop and mobile, light and dark.
// Run: cd web/tb-nik && npx vite build && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts casefile
// Files: docs/ui/build/shots/casefile-<state>-<theme>-<width>.png. The Case File routes come from e2e/support/f2.ts
// (SYNTHETIC demo data); the shell comes from e2e/support/helpers.ts.
import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { SHOTS, SIZES, login, prepare, shoot, watchConsole } from "../support/helpers";
import { CID, caseFile, routeCaseFile, slotsAllStates, slotsBeforeReady, team, type CaseRouteOptions } from "../support/f2";
import type { Role } from "../support/fixtures";

const DESKTOP_MOBILE = [SIZES[0], SIZES[2]];

/** helpers.shoot from the top of the page: full-page captures of a scrolled page put the sticky top bar mid-image. */
const snap: typeof shoot = (page, name, state, opts = {}) => shoot(page, name, state, { ...opts, before: async (p) => { await p.evaluate(() => window.scrollTo(0, 0)); if (opts.before) await opts.before(p); } });

async function open(page: Page, o: CaseRouteOptions & { role?: Role; path?: string; wait?: string } = {}) {
  await prepare(page, { role: o.role ?? "treating" });
  await routeCaseFile(page, o);
  await login(page);
  await page.goto(`/tb-nik/cases/${CID}${o.path ?? ""}`);
  await page.getByTestId(o.wait ?? "casefile-page").first().waitFor({ timeout: 20_000 });
  await page.waitForLoadState("networkidle").catch(() => {});
}

test.describe("Case File", () => {
  test("summary, the main view", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page);
    await expect(page.getByTestId("header-strip")).toContainText("Priya Venkatesan");
    await expect(page.getByTestId("summary-column")).toContainText("Pathology");
    await expect(page.getByTestId("prose-text")).toBeVisible();
    await snap(page, "casefile", "summary");
    expect(errors).toEqual([]);
  });

  test("every line state: found, entered, waiting, not found, needs confirmation", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { slots: slotsAllStates() });
    await expect(page.locator('[data-slot-status="waiting"]').first()).toBeVisible();
    await expect(page.locator('[data-slot-status="entered"]').first()).toBeVisible();
    await expect(page.locator('[data-slot-status="needs_confirmation"]').first()).toBeVisible();
    await page.locator("#section-imaging").scrollIntoViewIfNeeded();
    await snap(page, "casefile", "line-states", { fullPage: true });
    expect(errors).toEqual([]);
  });

  test("before the ready mark: narrative waits, Mark ready read-back", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { slots: slotsBeforeReady(), caseFile: caseFile({ case: { ...caseFile().case, board_ready: null } }) });
    await snap(page, "casefile", "before-ready", { sizes: DESKTOP_MOBILE });
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("mark-ready").click();
    await expect(page.getByTestId("mark-ready-dialog")).toBeVisible();
    await snap(page, "casefile", "mark-ready-dialog", { sizes: DESKTOP_MOBILE, fullPage: false });
    expect(errors).toEqual([]);
  });

  test("in-place step with Undo (ask the department)", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { slots: slotsAllStates() });
    await page.getByTestId("slot-ask").first().click();
    await expect(page.getByText("Undo within 10 seconds").first()).toBeVisible();
    await snap(page, "casefile", "undo", { sizes: [SIZES[0]], fullPage: false, before: async (p) => { await p.getByText("Undo within 10 seconds").first().scrollIntoViewIfNeeded(); } });
    await page.getByRole("button", { name: "Undo" }).first().click();
    await expect(page.getByText("Undo within 10 seconds")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("source page with the quote marked", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page);
    await page.getByTestId("quote-chip").first().click();
    await expect(page.getByTestId("source-viewer")).toBeVisible();
    await snap(page, "casefile", "source-viewer", { sizes: SIZES, fullPage: false });
    expect(errors).toEqual([]);
  });

  test("review in the side panel", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { slots: slotsAllStates() });
    await page.getByTestId("slot-review").first().click();
    await expect(page.getByTestId("review-panel")).toBeVisible();
    await snap(page, "casefile", "review", { sizes: DESKTOP_MOBILE, fullPage: false });
    expect(errors).toEqual([]);
  });

  for (const panel of ["helpers", "team", "board", "published"] as const) {
    test(`one click away: ${panel}`, async ({ page }) => {
      const errors = watchConsole(page);
      await open(page, { path: `/${panel}` });
      await expect(page.getByTestId("side-panel")).toBeVisible();
      if (panel === "helpers") {
        await snap(page, "casefile", "helpers", { sizes: DESKTOP_MOBILE, fullPage: false });
        await page.getByTestId("helper-pathology").click();
        await expect(page.getByTestId("helper-brief")).toBeVisible();
        await snap(page, "casefile", "helper-pathology", { sizes: DESKTOP_MOBILE, fullPage: false });
      } else {
        await snap(page, "casefile", panel, { sizes: DESKTOP_MOBILE, fullPage: false });
      }
      if (panel === "published") {
        await page.getByLabel("Search words (diagnosis words only)").fill("early breast cancer sentinel node");
        await page.getByTestId("published-panel").getByRole("button", { name: "Search" }).click();
        await expect(page.getByText("Results")).toBeVisible();
        await snap(page, "casefile", "published-results", { sizes: [SIZES[0]], fullPage: false });
      }
      expect(errors).toEqual([]);
    });
  }

  test("resident: every sign-off goes to the consultant", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { role: "resident", slots: slotsAllStates(), team: team({ can: { manage: false, leave: true, set_urgency: false, propose: true, archive: false, consent: false } }) });
    await expect(page.getByText(/Dr Lakshmi Rao signs off/).first()).toBeVisible();
    await snap(page, "casefile", "resident", { sizes: DESKTOP_MOBILE });
    expect(errors).toEqual([]);
  });

  test("consultant: residents' proposals strip", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page);
    await expect(page.getByTestId("proposals-strip")).toBeVisible();
    await snap(page, "casefile", "proposals", { sizes: DESKTOP_MOBILE, fullPage: false });
    expect(errors).toEqual([]);
  });

  test("mobile tabs: Ask and Reports", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(SIZES[2]);
    await open(page);
    await page.getByRole("tab", { name: "Ask" }).click();
    await expect(page.getByTestId("ask-panel")).toBeVisible();
    await snap(page, "casefile", "tab-ask", { sizes: [SIZES[2]] });
    await page.getByRole("tab", { name: "Reports" }).click();
    await expect(page.getByTestId("reports-panel")).toBeVisible();
    await snap(page, "casefile", "tab-reports", { sizes: [SIZES[2]] });
    await page.getByRole("button", { name: "Timeline" }).click();
    await expect(page.getByTestId("timeline")).toBeVisible();
    await snap(page, "casefile", "tab-timeline", { sizes: [SIZES[2]] });
    expect(errors).toEqual([]);
  });

  test("new records since you looked", async ({ page }) => {
    const errors = watchConsole(page);
    await page.clock.install();
    await open(page);
    const changed = caseFile({ signature: { hash: "changed-for-the-test" }, documents: [...caseFile().documents, { ...caseFile().documents[4], doc_id: "Dnew0001" }] });
    await page.unroute(`**/api/tb/cases/${CID}**`);
    await routeCaseFile(page, { caseFile: changed });
    await page.clock.fastForward(31_000);
    await expect(page.getByTestId("stale-banner")).toBeVisible({ timeout: 10_000 });
    await snap(page, "casefile", "stale-banner", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.clock.resume();
    await page.getByTestId("stale-banner").getByRole("button", { name: "Show" }).click();
    // The banner fades out with Motion, which the installed fake clock does not drive; the announcement is the check.
    await expect(page.getByText("Showing the latest records.")).toBeAttached();
    expect(errors).toEqual([]);
  });

  test("the server has no slot routes yet: honest fallback", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { notBuilt: ["slots", "chats", "helpers", "published", "team", "proposals"] });
    await expect(page.getByText("is not available on this server yet").first()).toBeVisible();
    await snap(page, "casefile", "not-built", { sizes: DESKTOP_MOBILE });
    expect(errors).toEqual([]);
  });

  test("errors and loading", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, { caseFile: { status: 500 }, wait: "casefile-error" });
    await expect(page.getByRole("alert").first()).toBeVisible();
    await snap(page, "casefile", "error-500", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.unroute(`**/api/tb/cases/${CID}**`);
    await routeCaseFile(page, { caseFile: { status: 404, body: { detail: "Case not found" } } });
    await page.reload();
    await expect(page.getByText("This Case File does not exist")).toBeVisible();
    await snap(page, "casefile", "error-404", { sizes: [SIZES[0]], fullPage: false });
    await page.unroute(`**/api/tb/cases/${CID}**`);
    await routeCaseFile(page, { caseFile: { status: 403, body: { detail: "Forbidden" } } });
    await page.reload();
    await expect(page.getByText("You do not have access to this Case File")).toBeVisible();
    await snap(page, "casefile", "error-403", { sizes: [SIZES[0]], fullPage: false });
    await page.unroute(`**/api/tb/cases/${CID}**`);
    await routeCaseFile(page, { delayMs: 60_000 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.getByLabel("Loading the Case File")).toBeVisible();
    await page.screenshot({ path: path.join(SHOTS, "casefile-loading-light-1366.png") });
    expect(errors).toEqual([]);
  });

  test("print: the summary only", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page);
    await page.emulateMedia({ media: "print" });
    await snap(page, "casefile", "print", { sizes: [SIZES[0]] });
    await page.emulateMedia({ media: "screen" });
    expect(errors).toEqual([]);
  });
});
