// Screenshots of the meeting pages: list, agenda, coordinator control view, room screen, member view, join and waiting room,
// with the live channel mocked (page.routeWebSocket) so live events (agent states, the decision strip, the card request)
// can be pushed. Run: cd web/tb-nik && npx vite build && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts meetings
// Files: docs/ui/build/shots/meetings-<state>-<theme>-<width>.png. Routes: e2e/support/f2.ts (SYNTHETIC).
import { expect, test, type Page } from "@playwright/test";
import { SIZES, login, prepare, shoot, watchConsole } from "../support/helpers";
import { CID, MID, meetingState, memberState, routeCaseFile, routeMeetings, type MeetingRouteOptions } from "../support/f2";
import type { Role } from "../support/fixtures";

const DESKTOP_MOBILE = [SIZES[0], SIZES[2]];

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

test.describe("Meetings", () => {
  test("list, new meeting", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, "/meetings", { wait: "meetings-page" });
    await expect(page.getByTestId("meetings-list")).toBeVisible();
    await snap(page, "meetings", "list");
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("new-meeting").click();
    await expect(page.getByTestId("new-meeting-dialog")).toBeVisible();
    await snap(page, "meetings", "new-meeting", { sizes: DESKTOP_MOBILE, fullPage: false });
    expect(errors).toEqual([]);
  });

  test("list: empty, error, old sessions fallback", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, "/meetings", { wait: "meetings-page", meetings: { can_manage: true, meetings: [] } });
    await expect(page.getByText("No meetings yet")).toBeVisible();
    await snap(page, "meetings", "list-empty", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.unroute("**/api/tb/meetings**");
    await page.route("**/api/tb/meetings**", (r) => r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: { message: "The server could not answer (test).", code: "test" } }) }));
    await page.reload();
    await expect(page.getByRole("alert").first()).toBeVisible();
    await snap(page, "meetings", "list-error", { sizes: [SIZES[0]], fullPage: false });
    await page.unroute("**/api/tb/meetings**");
    await routeMeetings(page, { notBuilt: true });
    await page.reload();
    await expect(page.getByText("is not available on this server yet").first()).toBeVisible();
    await snap(page, "meetings", "list-not-built", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });

  test("agenda before the meeting (coordinator)", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, `/meetings/${MID}`, { wait: "meeting-page", state: meetingState("planned") });
    await expect(page.getByTestId("agenda-lists")).toBeVisible();
    await expect(page.getByTestId("meeting-code")).toHaveText("305718");
    await page.getByRole("button", { name: /Not ready/ }).click();
    await snap(page, "meetings", "agenda");
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("add-case").click();
    await expect(page.getByTestId("add-case-dialog")).toBeVisible();
    await snap(page, "meetings", "agenda-add-case", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });

  test("agenda read-only for a doctor", async ({ page }) => {
    const errors = watchConsole(page);
    const s = meetingState("planned", { can: { manage: false, record: false, ask: false }, code: null, me: { user: "rao@vxh.example", status: null, department: "breast_surgery" } });
    await open(page, `/meetings/${MID}`, { role: "treating", wait: "meeting-page", state: s });
    await snap(page, "meetings", "agenda-doctor", { sizes: DESKTOP_MOBILE });
    expect(errors).toEqual([]);
  });

  test("control view during the meeting", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, `/meetings/${MID}`, { wait: "control-view", state: meetingState("in_session") });
    await expect(page.getByTestId("waiting-banner")).toContainText("Kiran Shetty");
    await snap(page, "meetings", "control", { fullPage: false });
    await page.getByRole("tab", { name: "Decision" }).click();
    await expect(page.getByTestId("decision-form")).toBeVisible();
    await page.locator("#d-text").fill("Breast conservation surgery with sentinel node biopsy");
    await snap(page, "meetings", "control-decision", { sizes: [SIZES[0]], fullPage: false });
    await page.getByRole("tab", { name: "People" }).click();
    await expect(page.getByTestId("waiting-list")).toContainText("Kiran Shetty");
    await snap(page, "meetings", "control-people", { sizes: [SIZES[0]], fullPage: false });
    live.push({ type: "end_case", case_id: CID, cards_requested: ["radiology", "medical_oncology"], timer: { seconds_left: 300, running: false, total: 600 } });
    await page.getByTestId("end-meeting").click();
    await snap(page, "meetings", "control-end-meeting", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });

  test("room screen: slides, stand-in, questions, live decision strip", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, `/meetings/${MID}/room`, { wait: "room-screen", state: meetingState("in_session") });
    await expect(page.getByTestId("agent-tile")).toHaveAttribute("data-agent-state", "thinking");
    await expect(page.getByTestId("decision-strip")).toContainText("not saved");
    await snap(page, "meetings", "room", { fullPage: false });
    live.push({ type: "agent_state", agent: { active: true, role: "pathology", state: "answering", question: "Q2" } });
    live.push({ type: "open", case_id: CID, opened: { kind: "record", doc_id: "D8a2c165d", title: "HISTOPATHOLOGY REPORT", url: `/api/tb/cases/${CID}/documents/D8a2c165d/file` } });
    await expect(page.getByTestId("shared-screen")).toHaveAttribute("data-opened", "record");
    await expect(page.getByTestId("agent-tile")).toHaveAttribute("data-agent-state", "answering");
    await snap(page, "meetings", "room-record-open", { sizes: [SIZES[0], SIZES[1]], fullPage: false });
    live.push({ type: "decision", case_id: CID, outcome: { outcome: "decision", label: "Decision recorded" }, record: "R1" });
    await expect(page.getByTestId("decision-strip")).toHaveAttribute("data-saved", "true");
    await snap(page, "meetings", "room-saved", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });

  test("room screen before the start", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, `/meetings/${MID}/room`, { wait: "room-screen", state: meetingState("planned") });
    await snap(page, "meetings", "room-waiting", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });

  test("member view: follow, step away, question, card", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: memberState() });
    await expect(page.getByTestId("member-view")).toHaveAttribute("data-following", "true");
    await snap(page, "meetings", "member");
    await page.setViewportSize(SIZES[0]);
    await page.getByRole("button", { name: "Step away" }).click();
    await expect(page.getByTestId("back-to-shared")).toBeVisible();
    await snap(page, "meetings", "member-stepped-away", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.getByTestId("back-to-shared").click();
    live.push({ type: "end_case", case_id: CID, cards_requested: ["radiology"], timer: null });
    await expect(page.getByTestId("card-dialog")).toBeVisible();
    await page.getByTestId("card-concern").click();
    await snap(page, "meetings", "member-card", { sizes: DESKTOP_MOBILE, fullPage: false });
    expect(errors).toEqual([]);
  });

  test("member view with video on (server without video)", async ({ page }) => {
    const errors = watchConsole(page);
    const s = memberState({ meeting: { ...memberState().meeting, video: true }, can: { ...memberState().can, video: true } });
    await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "prejoin", state: s });
    await snap(page, "meetings", "prejoin", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.getByTestId("prejoin-join").click();
    await expect(page.getByTestId("member-view")).toHaveAttribute("data-video-status", "failed", { timeout: 15_000 });
    await snap(page, "meetings", "member-video-off", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });

  test("join with a code, waiting room, wrong code", async ({ page }) => {
    const errors = watchConsole(page);
    const waitingState = memberState({ me: { user: "rao@vxh.example", status: "waiting", department: "breast_surgery" } });
    await open(page, "/meetings/join", { role: "treating", wait: "join-page", state: waitingState });
    await page.locator("#join-code").fill("305718");
    await snap(page, "meetings", "join", { sizes: DESKTOP_MOBILE });
    await page.getByTestId("join-submit").click();
    await expect(page.getByTestId("waiting-room")).toBeVisible();
    await snap(page, "meetings", "waiting-room", { sizes: DESKTOP_MOBILE });
    await page.unroute("**/api/tb/meetings**");
    await routeMeetings(page, { join: { status: 404, body: { detail: { message: "No meeting has this code.", code: "no_such_code" } } } });
    await page.goto("/tb-nik/meetings/join");
    await page.locator("#join-code").fill("111111");
    await page.getByTestId("join-submit").click();
    await expect(page.getByRole("alert")).toContainText("No meeting has this code");
    await snap(page, "meetings", "join-wrong-code", { sizes: [SIZES[2]] });
    expect(errors).toEqual([]);
  });

  test("closed meeting and a missing one", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, `/meetings/${MID}`, { wait: "meeting-closed", state: meetingState("closed") });
    await snap(page, "meetings", "closed", { sizes: [SIZES[0]], fullPage: false });
    await page.unroute("**/api/tb/meetings**");
    await routeMeetings(page, { missing: true });
    await page.reload();
    await expect(page.getByText("This meeting does not exist")).toBeVisible();
    await snap(page, "meetings", "missing", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });
});
