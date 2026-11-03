// Ask PubMed (docs/pubmed-ask/DESIGN.md section 8): the Case File Ask with its two tabs, the "Ask PubMed?" suggestion under a records
// answer, the live steps, an answer with a quote open, Save; refused, unavailable and no papers; the Home card, the /pubmed page and
// the phone Dock; the meeting's Ask PubMed panel for the coordinator and a member. Laptop 1366 x 768 and phone 390 x 844.
// Run: cd web/tb-nik && npx vite build && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts pubmed
// Files: docs/ui/build/shots/pubmed-<state>-<theme>-<width>.png. Routes: e2e/support/pubmed_mock.ts (public PubMed records from the
// Part 1 proof runs), the Case File and meeting from e2e/support/f2.ts (SYNTHETIC).
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { MOCK, SHOTS, SIZES, login, prepare, watchConsole } from "../support/helpers";
import { CID, MID, caseFileUnsent, chats, meetingState, memberState, routeBoardCases, routeCaseFile, routeMeetings } from "../support/f2";
import { DOWN, REFUSED, chatsWithSuggestion, pmThread, routePubMed } from "../support/pubmed_mock";
import type { Role } from "../support/fixtures";

const LAPTOP_PHONE = [SIZES[0], SIZES[2]];
const Q1 = "What pathological complete response rates did trials report with neoadjuvant pembrolizumab in triple-negative breast cancer?";
const SUGGESTED = "What pathological complete response did trials report with neoadjuvant pembrolizumab in triple-negative breast cancer?";

/** pubmed-<state>-<theme>-<width>.png in the shots folder; the screen as seen unless full. */
async function snap(page: Page, state: string, opts: { full?: boolean; themes?: Array<"light" | "dark"> } = {}) {
  fs.mkdirSync(SHOTS, { recursive: true });
  const width = page.viewportSize()?.width ?? 0;
  for (const theme of opts.themes ?? ["light"]) {
    await page.evaluate((t) => { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("tbnik.theme", t); } catch { /* none */ } }, theme);
    await page.waitForTimeout(200);
    await page.screenshot({ path: path.join(SHOTS, `pubmed-${state}-${theme}-${width}.png`), fullPage: !!opts.full });
  }
  if ((opts.themes ?? ["light"]).includes("dark")) await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
}

async function openCase(page: Page, o: Parameters<typeof routePubMed>[1] & { role?: Role; suggestion?: boolean } = {}) {
  await prepare(page, { role: o.role ?? "treating" });
  await routeCaseFile(page, { caseFile: caseFileUnsent(), chats: o.suggestion ? chatsWithSuggestion(chats) : chats });
  const pm = await routePubMed(page, o);
  await login(page);
  await page.goto(`/tb-nik/cases/${CID}`);
  await page.getByTestId("casefile-page").first().waitFor({ timeout: 20_000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.getByTestId("ask-bubble").click();
  const panel = page.getByTestId("side-panel").getByTestId("ask-panel");
  await expect(panel).toBeVisible();
  return { pm, panel };
}

/** No sideways scrolling of the whole page at the current width. */
async function noSideways(page: Page) {
  const width = page.viewportSize()?.width ?? 0;
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
}

test.describe("Ask PubMed", () => {
  test.skip(!MOCK, "the PubMed screens run with TBNIK_MOCK=1");

  for (const size of LAPTOP_PHONE) {
    test(`Case File Ask: two tabs, the suggestion, the live steps, an answer, a quote and Save at ${size.width}`, async ({ page }) => {
      const errors = watchConsole(page);
      await page.setViewportSize(size);
      const { panel } = await openCase(page, { suggestion: true, outcomes: ["answered"], pollsPerStep: 4 });
      // two equal tabs; the records tab is first and says its scope
      const records = panel.getByRole("tab", { name: "This patient's records" });
      const pubmed = panel.getByRole("tab", { name: "PubMed" });
      await expect(records).toHaveAttribute("aria-selected", "true");
      await expect(pubmed).toHaveAttribute("aria-selected", "false");
      const [a, b] = [await records.boundingBox(), await pubmed.boundingBox()];
      expect(Math.abs((a?.width ?? 0) - (b?.width ?? 0))).toBeLessThan(2);
      await expect(panel.getByTestId("ask-records-scope")).toContainText("From this patient's records only.");
      await expect(panel.getByTestId("chat-model-line").first()).toHaveText("From this patient's records only. Gemma-4-31B (non-medical).");
      await snap(page, "casefile-tabs");
      // a general question the records cannot answer: one click asks PubMed
      const suggest = panel.getByTestId("suggest-pubmed");
      await expect(suggest).toContainText("This is a general question. Ask PubMed?");
      await suggest.scrollIntoViewIfNeeded();
      await snap(page, "casefile-suggestion");
      const posted = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/cases/${CID}/pubmed/ask`));
      await suggest.getByTestId("suggest-pubmed-ask").click();
      expect((await posted).postDataJSON()).toEqual({ question: SUGGESTED });
      await expect(pubmed).toHaveAttribute("aria-selected", "true");
      // the live steps, with the server's words
      const steps = panel.getByTestId("pubmed-steps");
      await expect(steps).toBeVisible();
      await expect(steps).toHaveAttribute("data-step", "fetch", { timeout: 15_000 });
      await expect(steps.getByTestId("pubmed-step").nth(0)).toHaveAttribute("data-state", "done");
      await expect(steps.getByTestId("pubmed-step").nth(1)).toContainText("Searching PubMed (209 found)");
      await expect(steps.getByTestId("pubmed-step-detail")).toContainText("209 papers found, fetching the top 20 records");
      await expect(panel.getByTestId("pubmed-ask-button")).toBeDisabled();
      await snap(page, "casefile-steps");
      // the answer: the label line on top, the lines with their chips, the papers, the footer
      const answer = panel.getByTestId("pubmed-answer").first();
      await expect(answer).toHaveAttribute("data-status", "answered", { timeout: 30_000 });
      await expect(answer.getByTestId("pubmed-label")).toContainText("Published evidence, not advice for this patient.");
      await expect(answer.getByTestId("pubmed-label").getByTestId("pubmed-mark")).toHaveText("PubMed");
      await expect(answer.getByTestId("pubmed-line")).toHaveCount(2);
      await expect(answer.getByTestId("pubmed-quote-chip")).toHaveText(["1", "2"]);
      await expect(answer.getByTestId("pubmed-words")).toContainText("triple-negative breast cancer");
      await expect(answer.getByTestId("pubmed-years").first()).toHaveAttribute("aria-checked", "true");
      await expect(answer.getByTestId("pubmed-footer")).toContainText(/209 papers found, 17 read, searched \d\d\/\d\d\/\d{4}, \d\d:\d\d\./);
      await expect(answer.getByTestId("pubmed-model-line")).toHaveText(" Written by Gemma-4-31B (non-medical).");
      await expect(answer.getByRole("link", { name: "Source: PubMed, U.S. National Library of Medicine" })).toHaveAttribute("href", "https://pubmed.ncbi.nlm.nih.gov/");
      const papers = answer.getByTestId("pubmed-paper");
      await expect(papers).toHaveCount(2);
      await expect(papers.first()).toHaveAttribute("data-pmid", "32101663");
      await expect(papers.first().getByTestId("pubmed-pmid")).toHaveAttribute("href", "https://pubmed.ncbi.nlm.nih.gov/32101663/");
      await expect(papers.first().getByTestId("pubmed-study-type")).toHaveText("Randomised trial");
      await expect(answer.getByRole("button", { name: /^Read the answer aloud/ })).toBeVisible();
      await answer.scrollIntoViewIfNeeded();
      await snap(page, "casefile-answer", { themes: ["light", "dark"] });
      // the other papers: read, not quoted; not read with why (and the India mark)
      await answer.getByTestId("pubmed-more-papers").click();
      await expect(papers).toHaveCount(20);
      await expect(answer.locator("[data-testid=pubmed-paper][data-read=false]").first()).toContainText("Not read: no abstract in PubMed");
      await expect(answer.locator("[data-testid=pubmed-paper][data-pmid='40011935'] [data-testid=pubmed-india]")).toHaveText("India");
      await answer.locator("[data-testid=pubmed-paper][data-pmid='40011935']").scrollIntoViewIfNeeded();
      await snap(page, "casefile-papers");
      await answer.getByTestId("pubmed-more-papers").click();
      // a quote chip opens the exact quote, its section, its mark and the paper on PubMed
      await answer.getByTestId("pubmed-quote-chip").first().scrollIntoViewIfNeeded();
      await answer.getByTestId("pubmed-quote-chip").first().click();
      const pop = page.getByTestId("pubmed-quote");
      await expect(pop).toBeVisible();
      await expect(pop).toContainText("Paper 1 · Abstract, RESULTS");
      await expect(pop.getByTestId("pubmed-quote-text")).toContainText("the percentage of patients with a pathological complete response was 64.8%");
      await expect(pop).toContainText("Added to show the numbers");
      const link = pop.getByTestId("pubmed-open");
      await expect(link).toHaveAttribute("href", "https://pubmed.ncbi.nlm.nih.gov/32101663/");
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(link).toHaveAttribute("rel", /noopener/);
      await snap(page, "casefile-quote");
      await page.keyboard.press("Escape");
      await expect(pop).toBeHidden();
      await expect(panel).toBeVisible();  // Esc closed the quote, not the panel
      await answer.getByTestId("pubmed-quote-chip").nth(1).click();
      await expect(page.getByTestId("pubmed-quote")).toContainText("Whole sentence from the paper");
      await page.keyboard.press("Escape");
      // Save puts the paper in the Case File's Published list
      const saved = page.waitForRequest((r) => r.method() === "POST" && /\/pubmed\/PM-new-PJ1\/save$/.test(r.url()));
      await papers.first().getByTestId("pubmed-save").click();
      expect((await saved).postDataJSON()).toEqual({ pmid: "32101663" });
      await expect(papers.first()).toContainText("Saved");
      // back to the records: the chat is still there
      await records.click();
      await expect(panel.getByTestId("chat-thread").first()).toBeVisible();
      await noSideways(page);
      expect(errors).toEqual([]);
    });

    test(`Case File PubMed: refused, unavailable, no papers, the rate limit at ${size.width}`, async ({ page }) => {
      const errors = watchConsole(page);
      await page.setViewportSize(size);
      const { panel } = await openCase(page, { outcomes: ["refused", "unavailable", "no_papers"], caseThreads: [pmThread("case", { id: "PM-old", pinned: true }, 60 * 26)] });
      await panel.getByTestId("ask-tab-pubmed").click();
      // the team's earlier thread, pinned, opens by default
      await expect(panel.getByTestId("pubmed-answer")).toHaveAttribute("data-thread", "PM-old");
      await expect(panel.getByTestId("pubmed-answer").getByTestId("pubmed-pin")).toHaveAttribute("aria-pressed", "true");
      const box = panel.getByTestId("pubmed-input");
      await box.fill("Should we give her pembrolizumab?");
      await panel.getByTestId("pubmed-ask-button").click();
      const refused = panel.getByTestId("pubmed-refused");
      await expect(refused).toContainText("Ask PubMed did not take this question");
      await expect(refused).toContainText(REFUSED.slice(0, 60));
      await expect(panel.getByTestId("pubmed-answer").first()).toHaveAttribute("data-status", "refused");
      await expect(panel.getByTestId("pubmed-thread-row")).toHaveCount(1);  // the earlier one folds into a row
      await snap(page, "casefile-refused");
      await refused.getByRole("button", { name: "Change the question" }).click();
      await expect(box).toHaveValue("Should we give her pembrolizumab?");
      await box.fill("What did trials report about adjuvant capecitabine in triple-negative breast cancer?");
      await box.press("Enter");
      const down = panel.getByTestId("pubmed-unavailable");
      await expect(down).toContainText("PubMed could not be reached", { timeout: 15_000 });
      await expect(down).toContainText(DOWN);
      await snap(page, "casefile-unavailable");
      const again = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/cases/${CID}/pubmed/ask`));
      await down.getByTestId("pubmed-try-again").click();
      expect((await again).postDataJSON()).toEqual({ question: "What did trials report about adjuvant capecitabine in triple-negative breast cancer?" });
      const none = panel.getByTestId("pubmed-no-papers");
      await expect(none).toContainText("PubMed found no papers", { timeout: 15_000 });
      // the search words open for a change, with the year filter and Search again
      const words = panel.getByTestId("pubmed-words-input");
      await expect(words).toBeVisible();
      await snap(page, "casefile-no-papers");
      await words.fill("capecitabine AND \"triple-negative breast cancer\"");
      await panel.getByTestId("pubmed-answer").first().getByRole("radio", { name: "Last 10 years" }).click();
      const words2 = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/cases/${CID}/pubmed/ask`));
      await panel.getByTestId("pubmed-answer").first().getByTestId("pubmed-search-again").click();
      expect((await words2).postDataJSON()).toEqual({ question: "What did trials report about adjuvant capecitabine in triple-negative breast cancer?", years: 10, words: "capecitabine AND \"triple-negative breast cancer\"" });
      await noSideways(page);
      expect(errors).toEqual([]);
    });
  }

  test("Case File PubMed: the rate limit and Save refused", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(SIZES[0]);
    const { panel } = await openCase(page, { start: { status: 429, body: { detail: { message: "Too many questions", code: "rate_limited" } } }, caseThreads: [pmThread("case", { id: "PM-old" }, 30)], saveForbidden: true });
    await panel.getByTestId("ask-tab-pubmed").click();
    await panel.getByTestId("pubmed-input").fill("What did trials report about ribociclib in early breast cancer?");
    await panel.getByTestId("pubmed-ask-button").click();
    await expect(panel.getByTestId("pubmed-start-error")).toHaveText("Too many PubMed questions in a short time. Please wait a few minutes, then ask again.");
    await expect(panel.getByTestId("pubmed-input")).toHaveValue("What did trials report about ribociclib in early breast cancer?");
    await panel.getByTestId("pubmed-save").first().click();
    await expect(panel.getByTestId("pubmed-save-error")).toHaveText("Only a consultant of the owner team can save a paper to this Case File's Published list.");
    await expect(panel.getByTestId("pubmed-save")).toHaveCount(0);
    await snap(page, "casefile-limits");
    expect(errors).toEqual([]);
  });

  for (const size of LAPTOP_PHONE) {
    test(`Home: the Ask PubMed card, the /pubmed page with the live steps and the history, the Dock at ${size.width}`, async ({ page }) => {
      const errors = watchConsole(page);
      const phone = size.width < 1024;
      await page.setViewportSize(size);
      await prepare(page, { role: "treating" });
      await routePubMed(page, { outcomes: ["answered"], pollsPerStep: 2, homeThreads: [pmThread("home", {}, 60 * 20), pmThread("home2", {}, 60 * 48)] });
      await login(page);
      await page.goto("/tb-nik/cases");
      const card = page.getByTestId("pubmed-home-card");
      await expect(card).toBeVisible({ timeout: 20_000 });
      await page.waitForLoadState("networkidle").catch(() => {});
      // the nav: PubMed after Meetings, in the top bar on a laptop and the Dock on a phone
      const nav = phone ? page.locator("nav[aria-label='Main'].fixed") : page.getByRole("navigation", { name: "Main" }).first();
      await expect(nav.getByRole("link", { name: "PubMed" })).toBeVisible();
      if (phone) await card.scrollIntoViewIfNeeded();
      await snap(page, "home-card", { full: !phone });
      await card.getByTestId("pubmed-card-input").fill(Q1);
      await card.getByTestId("pubmed-card-ask").click();
      await expect(page).toHaveURL(/\/tb-nik\/pubmed$/);
      const ask = page.getByTestId("pubmed-ask");
      await expect(ask).toHaveAttribute("data-variant", "page");
      await expect(page.getByTestId("pubmed-steps")).toBeVisible();
      await expect(page.getByTestId("pubmed-steps")).toHaveAttribute("data-step", /search|fetch|read/, { timeout: 10_000 });
      await expect(page.getByTestId("pubmed-answer")).toHaveCount(0);  // the earlier answers wait in the history
      await snap(page, "page-steps");
      const answer = page.getByTestId("pubmed-answer");
      await expect(answer).toHaveAttribute("data-thread", "PM-new-PJ1", { timeout: 20_000 });
      await expect(page.getByTestId("pubmed-steps")).toBeHidden();
      await expect(answer).toHaveAttribute("data-status", "answered");
      await expect(answer.getByRole("heading", { level: 3 })).toHaveText(Q1);
      await expect(answer.getByTestId("pubmed-label")).toContainText("Published evidence, not advice for any patient.");
      await expect(answer.getByTestId("pubmed-save")).toHaveCount(0);  // no Case File, no Save
      await expect(answer.getByTestId("pubmed-pin")).toHaveCount(0);
      await expect(page.getByTestId("pubmed-history").getByTestId("pubmed-thread-row")).toHaveCount(3);
      await page.evaluate(() => window.scrollTo(0, 0));
      await snap(page, "page-answer", { full: !phone, themes: ["light", "dark"] });
      if (phone) {
        await expect(nav.getByRole("link", { name: "PubMed" })).toHaveAttribute("aria-current", "page");
        await snap(page, "dock");
      }
      // an earlier question from the history opens on the left (laptop) or above (phone)
      await page.getByTestId("pubmed-history").getByTestId("pubmed-thread-row").nth(2).click();
      await expect(answer).toContainText("induction chemotherapy");
      await noSideways(page);
      expect(errors).toEqual([]);
    });
  }

  test("Home: the empty /pubmed page and the not-yet state", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(SIZES[0]);
    await prepare(page, { role: "coordinator" });
    await routePubMed(page, { homeThreads: [] });
    await login(page);
    await page.goto("/tb-nik/pubmed");
    await expect(page.getByTestId("pubmed-intro")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("pubmed-examples").getByRole("button")).toHaveCount(3);
    await page.getByTestId("pubmed-examples").getByRole("button").first().click();
    await expect(page.getByTestId("pubmed-input")).toHaveValue(/metronomic chemotherapy in head and neck cancer/);
    await snap(page, "page-empty", { full: true });
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await prepare(page, { role: "coordinator", overrides: { "GET /api/tb/pubmed/history": { status: 404, body: { detail: "Not Found" } } } });
    await page.goto("/tb-nik/pubmed");
    await expect(page.getByText("Ask PubMed is not available on this server yet.")).toBeVisible({ timeout: 20_000 });
    expect(errors).toEqual([]);
  });

  for (const size of LAPTOP_PHONE) {
    test(`Meeting: the Ask PubMed panel for the coordinator at ${size.width}`, async ({ page }) => {
      const errors = watchConsole(page);
      const phone = size.width < 1024;
      await page.setViewportSize(size);
      await prepare(page, { role: "coordinator" });
      await routeBoardCases(page);
      await routeMeetings(page, { state: meetingState("in_session") });
      await routePubMed(page, { caseThreads: [pmThread("case", {}, 40)], outcomes: ["answered"] });
      await login(page);
      await page.goto(`/tb-nik/meetings/${MID}`);
      await page.getByTestId("control-view").first().waitFor({ timeout: 20_000 });
      await page.waitForLoadState("networkidle").catch(() => {});
      if (phone) {
        await page.getByTestId("more").click();
        await page.getByTestId("sheet-panel-pubmed").click();
      } else {
        const btn = page.getByTestId("panel-pubmed");
        await expect(btn).toHaveAccessibleName("Ask PubMed");
        await btn.click();
      }
      const panel = page.getByTestId("pubmed-panel");
      await expect(panel).toBeVisible();
      await expect(panel.getByTestId("pubmed-panel-body")).toHaveAttribute("data-case", CID);
      await expect(panel.getByTestId("pubmed-ask")).toHaveAttribute("data-variant", "meeting");
      const answer = panel.getByTestId("pubmed-answer");
      await expect(answer).toHaveAttribute("data-status", "answered");
      await expect(answer.getByTestId("pubmed-save")).toHaveCount(0);  // the coordinator is not the owner consultant
      await snap(page, "meeting-coordinator");
      // a question from the meeting goes to the Case File on the floor
      const posted = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/cases/${CID}/pubmed/ask`));
      await panel.getByTestId("pubmed-input").fill("What did trials report about hypofractionated radiotherapy after breast conservation?");
      await panel.getByTestId("pubmed-ask-button").click();
      await posted;
      await expect(panel.getByTestId("pubmed-answer").first()).toHaveAttribute("data-thread", "PM-new-PJ1", { timeout: 20_000 });
      // the bar fits: nothing of the panel group runs under the call buttons
      if (!phone) {
        const group = await page.getByRole("group", { name: "Panels" }).boundingBox();
        const more = await page.getByTestId("more").boundingBox();
        expect((group?.x ?? 0)).toBeGreaterThan((more?.x ?? 0) + (more?.width ?? 0));
      }
      expect(errors).toEqual([]);
    });
  }

  test("Meeting: the Ask PubMed panel for a member, with Save", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(SIZES[0]);
    await prepare(page, { role: "treating" });
    await routeBoardCases(page);
    await routeMeetings(page, { state: memberState() });
    await routePubMed(page, { caseThreads: [pmThread("case", {}, 40)] });
    await login(page);
    await page.goto(`/tb-nik/meetings/${MID}/member`);
    await page.getByTestId("member-view").first().waitFor({ timeout: 20_000 });
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.getByTestId("panel-pubmed").click();
    const panel = page.getByTestId("pubmed-panel");
    await expect(panel.getByTestId("pubmed-answer")).toBeVisible();
    await expect(panel.getByTestId("pubmed-save").first()).toBeVisible();  // the owner team's consultant may Save
    await panel.getByTestId("pubmed-quote-chip").first().click();
    await expect(page.getByTestId("pubmed-quote")).toBeVisible();
    await snap(page, "meeting-member");
    await page.keyboard.press("Escape");
    expect(errors).toEqual([]);
  });
});
