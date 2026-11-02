// Screenshots and checks of the case flow (night-v3 5.4, research/04 sections 6.13 and 6.14): the agenda rail's times (planned
// minutes, the time spent and what is left on the case on the floor, amber under 2 minutes and "time up" at 0, the minutes a finished
// case took), the presenter, the quorum line (heads present, the agents standing in apart, the PM-JAY composition) and the move to
// another case (the toast, the announcement, the rail following). The live channel is mocked (page.routeWebSocket).
// Run: cd web/tb-nik && npx vite build && LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts meetings-flow
// Files: docs/ui/build/shots/meetings-<state>-<theme>-<width>.png. Routes: e2e/support/f2.ts (SYNTHETIC).
import { expect, test, type Page } from "@playwright/test";
import { SIZES, login, prepare, shoot, watchConsole } from "../support/helpers";
import { CID, MID, meetingState, memberState, routeCaseFile, routeMeetings, type MeetingRouteOptions } from "../support/f2";
import type { Role } from "../support/fixtures";

/** helpers.shoot from the top of the page: full-page captures of a scrolled page put the sticky top bar mid-image. */
const snap: typeof shoot = (page, name, state, opts = {}) => shoot(page, name, state, { ...opts, before: async (p) => { await p.evaluate(() => window.scrollTo(0, 0)); if (opts.before) await opts.before(p); } });

async function open(page: Page, to: string, o: MeetingRouteOptions & { role?: Role; wait: string }) {
  await prepare(page, { role: o.role ?? "coordinator" });
  await routeCaseFile(page);
  const live = await routeMeetings(page, o);
  await login(page);
  await page.goto(`/tb-nik${to}`);
  await page.getByTestId(o.wait).first().waitFor({ timeout: 20_000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  return live;
}

const SECOND = "TB-2026-0030";
const THIRD = "TB-2026-0029";
const presenter = (name: string, user: string) => ({ user, name, department: "breast_surgery", department_name: "Breast Surgery" });
/** The coordinator's Next case as the server sends it: a new case on the floor with its timer, presenter and no time spent yet. */
const moveTo = (cid: string, who = presenter("Lakshmi Rao", "rao@vxh.example")) => ({ type: "current", case_id: cid, slide: 0, opened: null, timer: { seconds_left: 600, running: true, total: 600 }, presenter: who, elapsed_seconds: 0 });

test.describe("Meetings: case flow", () => {
  test("control view: the rail's times, the presenter and the quorum line", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, `/meetings/${MID}`, { wait: "control-view", state: meetingState("in_session") });
    await page.setViewportSize(SIZES[0]);
    const rail = page.getByTestId("agenda-rail");
    await expect(rail).toHaveAttribute("data-open", "true");
    // Now: the time spent (188 s in the fixture, counting up) and what is left (412 s, counting down); the others: planned minutes.
    const now = rail.locator("[data-state=now]");
    await expect(now).toContainText("Priya Venkatesan");
    await expect(now).toContainText("Now");
    await expect(now.getByTestId("rail-elapsed")).toHaveText(/^· 3:\d\d spent$/);
    await expect(now.getByTestId("rail-remaining")).toHaveText(/^· (6:\d\d|7:\d\d) left$/);
    await expect(now.getByTestId("rail-remaining")).toHaveAttribute("data-tone", "normal");
    await expect(now.getByTestId("rail-presenter")).toHaveText("Presenter: Asha Menon");
    await expect(rail.locator("[data-state=next]").getByTestId("rail-planned")).toHaveText("· 10 min");
    await expect(rail.locator("[data-state=later]").first().getByTestId("rail-planned")).toHaveText("· 10 min");
    // The quorum block: the three sentences (no person names in the compact rail); agents listed apart, never counted.
    const q = rail.getByTestId("quorum-line");
    await expect(q.locator("[data-part=heads]")).toHaveText("Heads present 2 of 5: Radiology, Medical Oncology.");
    await expect(q.locator("[data-part=absent]")).toHaveText("Not here: Surgical Oncology, Pathology, Radiation Oncology (AI agents standing in: Pathology, Nuclear Medicine; support only, never counted).");
    await expect(q.locator("[data-part=pmjay]")).toHaveText("PM-JAY advises Surgical, Radiation and Medical Oncology: 1 of 3 present as people.");
    await expect(q).not.toContainText("requires");
    // Under 2 minutes left: amber with the words; at 0: "time up" (the words carry it, the colour repeats it).
    live.push({ type: "timer", timer: { seconds_left: 95, running: true, total: 600 } });
    await expect(now.getByTestId("rail-remaining")).toHaveAttribute("data-tone", "low");
    await expect(now.getByTestId("rail-remaining")).toHaveText(/^· 1:\d\d left$/);
    await expect(now.getByTestId("rail-elapsed")).toHaveText(/^· 3:\d\d spent$/);  // the time spent counts from the moment the case came on the floor, not from the countdown (review M2)
    live.push({ type: "timer", timer: { seconds_left: 0, running: false, total: 600 } });
    await expect(now.getByTestId("rail-remaining")).toHaveText("· time up");
    await expect(now.getByTestId("rail-remaining")).toHaveAttribute("data-tone", "up");
    await expect(now.getByTestId("rail-elapsed")).toHaveText(/^· 3:\d\d spent$/);  // the time spent keeps counting from the case start (review M2)
    live.push({ type: "timer", timer: { seconds_left: 412, running: true, total: 600 } });
    await expect(now.getByTestId("rail-remaining")).toHaveAttribute("data-tone", "normal");
    // The quorum chip opens the full line, with the person beside each head present.
    await expect(page.getByTestId("quorum-chip")).toContainText("Heads 2 of 5");
    await page.getByTestId("quorum-chip").click();
    const pop = page.getByTestId("quorum-popover");
    await expect(pop).toBeVisible();
    await expect(pop.locator("[data-part=heads]")).toHaveText("Heads present 2 of 5: Radiology (Shanthi Raman), Medical Oncology (Thomas Joseph).");
    await expect(pop.locator("[data-part=pmjay]")).toContainText("PM-JAY advises");
    await snap(page, "meetings", "control-quorum", { sizes: [SIZES[0]], fullPage: false });
    await page.keyboard.press("Escape");
    await expect(pop).toHaveCount(0);
    // The Agenda panel: the same times and the presenter per row.
    await page.getByTestId("panel-agenda").click();
    const panel = page.getByTestId("agenda-panel");
    await expect(panel.locator(`[data-case="${CID}"] [data-testid=agenda-row-times]`)).toContainText(/spent · \d+:\d\d left · 10 min planned · Presenter: Asha Menon/);
    await expect(panel.locator(`[data-case="${SECOND}"] [data-testid=agenda-row-times]`)).toContainText("10 min planned · Presenter: Lakshmi Rao");
    await page.getByTestId("panel-agenda").click();
    // The phone: no rail and no chip; the Agenda sheet carries the times and the quorum line. No sideways scroll.
    await page.setViewportSize(SIZES[2]);
    await expect(page.getByTestId("quorum-chip")).toBeHidden();
    await snap(page, "meetings", "control-quorum", { sizes: [SIZES[2]], fullPage: false, before: async (p) => {
      if (!(await p.getByTestId("agenda-panel").isVisible())) { await p.getByTestId("more").click(); await p.getByTestId("sheet-panel-agenda").click(); }
      await expect(p.getByTestId("agenda-panel").getByTestId("quorum-line")).toBeVisible();
    } });
    await expect(page.getByTestId("agenda-panel").getByTestId("quorum-line").locator("[data-part=heads]")).toContainText("Heads present 2 of 5");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });

  test("member view: next case moves everyone", async ({ page }) => {
    const errors = watchConsole(page);
    // The first case was decided earlier in the meeting and took 12 min 14 s; it is still on the floor until the coordinator moves on.
    const s = memberState();
    s.agenda = { ...s.agenda, discussion: s.agenda.discussion.map((r: Record<string, unknown>) => (r.case_id === CID ? { ...r, outcome: "decision", outcome_label: "Decision recorded", ended: true, elapsed_seconds: 734 } : r)) };
    const live = await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: s });
    await page.setViewportSize(SIZES[0]);
    const rail = page.getByTestId("agenda-rail");
    await expect(rail.locator("[data-state=now]")).toContainText("Priya Venkatesan");
    await expect(page.getByTestId("case-toast")).toHaveCount(0);
    // The coordinator presses Next case: the toast, the announcement, the rail's highlight and the presenter move.
    live.push(moveTo(SECOND));
    const toast = page.getByTestId("case-toast");
    await expect(toast).toBeVisible();
    await expect(toast).toHaveAttribute("role", "status");
    await expect(toast).toHaveText("Moved to case 2 of 4: Fatima B., 46 F, UHID VXH/2026/000118");
    await expect(page.locator(".sr-only[aria-live=polite]", { hasText: "The meeting moved to case 2 of 4. Presenter: Lakshmi Rao." })).toHaveCount(1);
    await expect(rail.locator("[data-state=now]")).toContainText("Fatima B.");
    await expect(rail.locator("[data-state=now]").getByTestId("rail-presenter")).toHaveText("Presenter: Lakshmi Rao");
    await expect(rail.locator("[data-state=now]").getByTestId("rail-remaining")).toHaveText(/^· (10:00|9:\d\d) left$/);
    // The finished case shows its outcome and the minutes it took.
    const done = rail.locator("li", { hasText: "Priya Venkatesan" });
    await expect(done).toHaveAttribute("data-state", "done");
    await expect(done.getByTestId("rail-took")).toHaveText("· 12 min");
    await expect(page.getByTestId("member-view")).toHaveAttribute("data-following", "true");
    // The toast goes after 3 s.
    await expect(toast).toHaveCount(0, { timeout: 6000 });
    // A new presenter on the same case is announced.
    live.push({ type: "current", case_id: SECOND, presenter: presenter("Asha Menon", "asha@vxh.example") });
    await expect(page.locator(".sr-only[aria-live=polite]", { hasText: "Presenter: Asha Menon" })).toHaveCount(1);
    await expect(page.getByTestId("case-toast")).toHaveCount(0);
    // The shots: each capture moves the meeting again so the toast is on the screen (laptop and phone, light and dark).
    let k = 0;
    await snap(page, "meetings", "member-moved", { sizes: [SIZES[0], SIZES[2]], fullPage: false, before: async (p) => {
      k += 1;
      live.push(moveTo(k % 2 ? THIRD : SECOND, k % 2 ? presenter("Radha Devi", "radha@vxh.example") : undefined));
      await expect(p.getByTestId("case-toast")).toContainText(k % 2 ? "Moved to case 3 of 4: Kamala S." : "Moved to case 2 of 4: Fatima B.");
    } });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });

  test("room screen: the move toast in large type", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, `/meetings/${MID}/room`, { wait: "room-screen", state: meetingState("in_session") });
    await page.setViewportSize(SIZES[1]);
    await expect(page.getByTestId("quorum-chip")).toContainText("Heads 2 of 5");
    live.push(moveTo(SECOND));
    await expect(page.getByTestId("case-toast")).toHaveText("Moved to case 2 of 4: Fatima B., 46 F, UHID VXH/2026/000118");
    await snap(page, "meetings", "room-moved", { sizes: [SIZES[1]], fullPage: false, themes: ["dark"], before: async (p) => {
      live.push(moveTo(THIRD));
      await expect(p.getByTestId("case-toast")).toContainText("Moved to case 3 of 4");
    } });
    expect(errors).toEqual([]);
  });

  test("control view: the coordinator who moved the case gets no toast", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, `/meetings/${MID}`, { wait: "control-view", state: meetingState("in_session") });
    live.push(moveTo(SECOND));
    await expect(page.getByTestId("agenda-rail").locator("[data-state=now]")).toContainText("Fatima B.");
    await expect(page.locator(".sr-only[aria-live=polite]", { hasText: "The meeting moved to case 2 of 4." })).toHaveCount(1);
    await expect(page.getByTestId("case-toast")).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});
