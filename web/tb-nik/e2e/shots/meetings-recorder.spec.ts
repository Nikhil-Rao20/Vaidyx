// Checks and screenshots of meetings-v2 3.4 and 5.2 in the call screens: "Take up another Case File" (added as taken up during the
// meeting and put on the floor; the rail marks it), the coordinator's Record button (Record, Recording with the time, Pause, Resume,
// Stop with its confirmation), the capture with Chromium's fake microphone (a chunk posted as the Board room before Pause and Stop; the
// tab closing posts stop with keepalive; nothing kept in the browser), the red "Recording: text only, no audio kept" line on the
// member's and the room screen, the join and pre-join notice, and the discussion notes ("Discussion notes written for", the panel with
// the "said" chips, Edit and Mark reviewed for the coordinator, read only for a member). The live channel and the routes are mocked.
// Run: cd web/tb-nik && npx vite build && LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts meetings-recorder
// Files: docs/ui/build/shots/meetings-<state>-light-<width>.png. Routes: e2e/support/f2.ts and recorder_mock.ts (SYNTHETIC).
import { expect, test, type Page } from "@playwright/test";
import { SIZES, login, prepare, shoot, watchConsole } from "../support/helpers";
import { CID, MID, meetingState, memberState, routeBoardCases, routeMeetings, type MeetingRouteOptions } from "../support/f2";
import { TAKE_UP, recordingView, routeRecorder } from "../support/recorder_mock";
import type { Role } from "../support/fixtures";

// Chromium's fake microphone and camera (a tone and a test picture) and the permission, so the coordinator's capture runs headless.
test.use({ permissions: ["microphone", "camera"], launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] } });

const LAPTOP = SIZES[0];
const PHONE = SIZES[2];
type AnyObj = any; // eslint-disable-line @typescript-eslint/no-explicit-any

/** One light screenshot per size (the meeting is always light), from the top. */
const snap = (page: Page, state: string, sizes = [LAPTOP], before?: (p: Page) => Promise<void>) =>
  shoot(page, "meetings", state, { sizes, themes: ["light"], fullPage: false, before: async (p) => { await p.evaluate(() => window.scrollTo(0, 0)); if (before) await before(p); } });

async function open(page: Page, to: string, o: MeetingRouteOptions & { role?: Role; wait: string; state: AnyObj }) {
  await prepare(page, { role: o.role ?? "coordinator" });
  await routeBoardCases(page);
  const live = await routeMeetings(page, o);
  const rec = await routeRecorder(page, live, o.state);
  await login(page);
  await page.goto(`/tb-nik${to}`);
  await page.getByTestId(o.wait).first().waitFor({ timeout: 20_000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  return { live, rec };
}

/** Counts getUserMedia calls and records the keepalive flag of every recorder action the page posts. */
async function watchMedia(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __gum: number; __keepalive: boolean[] };
    w.__gum = 0; w.__keepalive = [];
    const md = navigator.mediaDevices;
    if (md?.getUserMedia) { const g = md.getUserMedia.bind(md); md.getUserMedia = (c) => { w.__gum += 1; return g(c); }; }
    const f = window.fetch.bind(window);
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => { if (String(input instanceof Request ? input.url : input).endsWith("/recording")) w.__keepalive.push(!!init?.keepalive); return f(input, init); };
  });
}

test.describe("Meetings: take up a Case File, the recorder and the notes", () => {
  test("take up another Case File: added as taken up during the meeting and put on the floor", async ({ page }) => {
    const errors = watchConsole(page);
    const state: AnyObj = meetingState("in_session");
    const { rec } = await open(page, `/meetings/${MID}`, { wait: "control-view", state });
    await page.setViewportSize(LAPTOP);
    const rail = page.getByTestId("agenda-rail");
    await rail.getByTestId("rail-take-up").click();
    const dlg = page.getByTestId("take-up-dialog");
    await expect(dlg).toBeVisible();
    // Only the Case Files not on this meeting's lists, with a cancer chosen (the linked file without one is left out).
    const rows = dlg.getByTestId("take-up-row");
    await expect(rows.first()).toBeVisible();
    await expect(dlg.locator(`[data-case="${TAKE_UP.case_id}"]`)).toContainText("Lakshmi R.");
    await expect(dlg.locator('[data-case="TB-2026-0027"]')).toContainText("Lung cancer (NSCLC)");
    await expect(dlg.locator('[data-case="TB-2026-0024"]')).toContainText("On this meeting's not ready list");
    await expect(dlg.locator('[data-case="TB-2026-0030"]')).toHaveCount(0);
    await expect(dlg.locator('[data-case="TB-2026-0019"]')).toHaveCount(0);
    await expect(dlg.locator('[data-case="TB-2026-0032"]')).toHaveCount(0);
    // Search by any part of the UHID, then by the cancer.
    await dlg.getByTestId("take-up-search").fill("000123");
    await expect(rows).toHaveCount(1);
    await dlg.getByTestId("take-up-search").fill("lung");
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toHaveAttribute("data-case", "TB-2026-0027");
    await dlg.getByTestId("take-up-search").fill("Lakshmi");
    await expect(rows).toHaveCount(1);
    await snap(page, "takeup-dialog");
    const moved = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/current`));
    await rows.first().getByTestId("take-up-pick").click();
    await moved;
    await expect.poll(() => rec.calls.findIndex((c) => c.path === "/current")).toBeGreaterThan(0);
    const add = rec.calls.find((c) => c.path === "/agenda/add");
    expect(add?.body).toEqual({ case_id: TAKE_UP.case_id, list: "discussion", reason: "Taken up during the meeting", unplanned: true });
    expect(rec.calls.findIndex((c) => c.path === "/agenda/add")).toBeLessThan(rec.calls.findIndex((c) => c.path === "/current"));
    expect(rec.calls.find((c) => c.path === "/current")?.body).toEqual({ case_id: TAKE_UP.case_id });
    await expect(dlg).toHaveCount(0);
    // The rail: the new Case File is on the floor and marked Taken up; the Board view leads on it.
    const now = rail.locator("[data-state=now]");
    await expect(now).toContainText("Lakshmi R.");
    await expect(now.getByTestId("rail-taken-up")).toHaveText("Taken up");
    await expect(page.getByTestId("case-headline")).toContainText("Lakshmi R.");
    await expect(page.locator(".sr-only[aria-live=polite]", { hasText: "Lakshmi R. is taken up and on the screen now." })).toHaveCount(1);
    await snap(page, "takeup-done");
    // The More menu offers it too; the phone's Coordinator sheet as well.
    await page.getByTestId("more").click();
    await expect(page.getByTestId("menu-take-up")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.setViewportSize(PHONE);
    await page.getByTestId("coordinator-sheet").click();
    await page.getByTestId("sheet-take-up").click();
    await expect(dlg).toBeVisible();
    await snap(page, "takeup-dialog", [PHONE]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });

  test("the Record button: record, pause, resume, stop; the laptop microphone posted as the Board room", async ({ page }) => {
    const errors = watchConsole(page);
    await watchMedia(page);
    const state: AnyObj = meetingState("in_session");
    const { rec } = await open(page, `/meetings/${MID}`, { wait: "control-view", state });
    await page.setViewportSize(LAPTOP);
    await expect(page.getByTestId("record-placeholder")).toHaveCount(0);
    const record = page.getByTestId("record");
    await expect(record).toHaveText(/Record/);
    await expect(record).toBeEnabled();
    await expect(page.getByTestId("recording-badge")).toHaveCount(0);
    await record.click();
    const pill = page.getByTestId("recording-pill");
    await expect(pill).toHaveAttribute("data-state", "on");
    await expect(pill).toContainText("Recording");
    await expect(page.getByTestId("recording-badge")).toHaveText("Recording: text only, no audio kept");
    expect(rec.calls.filter((c) => c.path === "/recording").map((c) => c.body.action)).toEqual(["start"]);
    // the capture: without the video call, the laptop microphone as the Board room
    await pill.click();
    await expect(page.getByTestId("recording-tracks")).toHaveText(/Laptop microphone \(Board room\)/);
    await page.waitForTimeout(2600);
    await expect(page.getByTestId("recording-time")).toHaveText(/^0:0[2-9]$/);
    await snap(page, "recorder-on");
    await page.keyboard.press("Escape");
    // Pause: the running segment is posted first, then the pause
    await page.getByTestId("record-pause").click();
    await expect(pill).toHaveAttribute("data-state", "paused");
    await expect(pill).toContainText("Paused");
    await expect(page.getByTestId("recording-badge")).toHaveText("Recording paused: text only, no audio kept");
    const firstChunk = rec.calls.findIndex((c) => c.path === "/transcribe");
    const pauseAt = rec.calls.findIndex((c) => c.path === "/recording" && c.body.action === "pause");
    expect(firstChunk, "a chunk was posted").toBeGreaterThanOrEqual(0);
    expect(firstChunk).toBeLessThan(pauseAt);
    const chunk = rec.calls[firstChunk];
    expect(chunk.speaker).toBe("room");
    expect(chunk.contentType).toMatch(/^audio\/(webm|ogg|mp4)/);
    expect(chunk.size ?? 0).toBeGreaterThan(500);
    await snap(page, "recorder-paused");
    // Resume, then Stop with its confirmation
    await page.getByTestId("record-resume").click();
    await expect(pill).toHaveAttribute("data-state", "on");
    await page.waitForTimeout(1500);
    await page.getByTestId("record-stop").click();
    const confirm = page.getByTestId("stop-recording-dialog");
    await expect(confirm).toContainText("Stop recording?");
    await expect(confirm).toContainText("The text so far is kept; no audio is kept.");
    await snap(page, "recorder-stop-confirm");
    await confirm.getByTestId("confirm-stop-recording").click();
    await expect(record).toBeVisible();
    await expect(record).toHaveAttribute("data-state", "off");
    await expect(page.getByTestId("recording-badge")).toHaveCount(0);
    const actions = rec.calls.filter((c) => c.path === "/recording").map((c) => c.body.action);
    expect(actions).toEqual(["start", "pause", "resume", "stop"]);
    const stopAt = rec.calls.findIndex((c) => c.path === "/recording" && c.body.action === "stop");
    expect(rec.calls.slice(pauseAt + 1, stopAt).some((c) => c.path === "/transcribe" && c.speaker === "room"), "the last words before Stop were posted first").toBe(true);
    // nothing kept in the browser: no IndexedDB, nothing new in the storages about audio
    expect(await page.evaluate(async () => (indexedDB.databases ? (await indexedDB.databases()).length : 0))).toBe(0);
    expect(await page.evaluate(() => [...Object.keys(localStorage), ...Object.keys(sessionStorage)].filter((k) => /audio|record|chunk/i.test(k)))).toEqual([]);
    // The tab closing while recording: stop is posted with keepalive
    await record.click();
    await expect(pill).toHaveAttribute("data-state", "on");
    await page.waitForTimeout(1200);
    const stopped = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/recording`) && (r.postDataJSON() as AnyObj)?.action === "stop");
    await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent("pagehide", { persisted: false })));
    await stopped;
    const flags = await page.evaluate(() => (window as unknown as { __keepalive: boolean[] }).__keepalive);
    expect(flags[flags.length - 1], "stop on pagehide is keepalive").toBe(true);
    // The phone: the recorder in the Coordinator sheet
    await page.setViewportSize(PHONE);
    await page.getByTestId("coordinator-sheet").click();
    await expect(page.getByTestId("sheet-record")).toBeVisible();
    await snap(page, "recorder-sheet", [PHONE]);
    expect(errors).toEqual([]);
  });

  test("a failing chunk shows one quiet line", async ({ page }) => {
    const errors = watchConsole(page);
    const state: AnyObj = meetingState("in_session", { recording: recordingView("on") });
    await prepare(page, { role: "coordinator" });
    await routeBoardCases(page);
    const live = await routeMeetings(page, { state });
    await routeRecorder(page, live, state, { transcribe: { status: 503, body: { detail: { message: "The speech service is not available.", code: "voice_unavailable" } } } });
    await login(page);
    await page.goto(`/tb-nik/meetings/${MID}`);
    await page.getByTestId("control-view").waitFor();
    await page.setViewportSize(LAPTOP);
    await expect(page.getByTestId("recording-pill")).toHaveAttribute("data-state", "on");
    await page.waitForTimeout(1500);
    // Next case: the running segment is posted first (it fails twice here), then the move
    await page.getByTestId("next-case").click();
    await expect(page.getByTestId("recorder-line")).toContainText("The speech service is not available", { timeout: 15_000 });
    await expect(page.getByTestId("recorder-line")).toContainText("1 part not turned into text");
    await snap(page, "recorder-failed");
    expect(errors.filter((e) => !/503/.test(e))).toEqual([]);
  });

  test("the badge on the member's screen and the room screen; members never capture", async ({ page, browser }) => {
    const errors = watchConsole(page);
    await watchMedia(page);
    const state: AnyObj = memberState({ recording: recordingView("on") });
    const { live, rec } = await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state });
    await page.setViewportSize(LAPTOP);
    const badge = page.getByTestId("recording-badge");
    await expect(badge).toHaveText("Recording: text only, no audio kept");
    await expect(page.getByTestId("record")).toHaveCount(0);
    await expect(page.getByTestId("recording-pill")).toHaveCount(0);
    await snap(page, "recorder-member", [LAPTOP, PHONE]);
    await page.setViewportSize(LAPTOP);
    live.push({ type: "recording", recording: recordingView("paused") });
    await expect(badge).toHaveText("Recording paused: text only, no audio kept");
    live.push({ type: "recording", recording: recordingView("off") });
    await expect(badge).toHaveCount(0);
    live.push({ type: "recording", recording: recordingView("on") });
    await expect(badge).toBeVisible();
    await page.waitForTimeout(1000);
    expect(rec.calls.filter((c) => c.path === "/transcribe")).toEqual([]);
    expect(await page.evaluate(() => (window as unknown as { __gum: number }).__gum), "a member's screen never opens the microphone for the recorder").toBe(0);
    expect(errors).toEqual([]);

    // the room screen (a separate projector PC, signed in as the coordinator): the same line, larger; it never captures either
    const ctx = await browser.newContext({ viewport: LAPTOP, colorScheme: "light", locale: "en-IN", timezoneId: "Asia/Kolkata", reducedMotion: "reduce", permissions: ["microphone"] });
    const room = await ctx.newPage();
    const roomErrors = watchConsole(room);
    await watchMedia(room);
    const rs: AnyObj = meetingState("in_session", { recording: recordingView("on") });
    const r2 = await open(room, `/meetings/${MID}/room`, { role: "coordinator", wait: "room-screen", state: rs });
    await expect(room.getByTestId("recording-badge")).toHaveText("Recording: text only, no audio kept");
    await expect(room.getByTestId("recording-pill")).toHaveCount(0);
    await snap(room, "recorder-room", [LAPTOP, PHONE]);
    await room.waitForTimeout(1000);
    expect(r2.rec.calls.filter((c) => c.path === "/transcribe")).toEqual([]);
    expect(await room.evaluate(() => (window as unknown as { __gum: number }).__gum)).toBe(0);
    expect(roomErrors).toEqual([]);
    await ctx.close();
  });

  test("the join page, the waiting room and the pre-join say the meeting is recorded as text", async ({ page }) => {
    const errors = watchConsole(page);
    const waitingState: AnyObj = memberState({ recording: recordingView("on") });
    waitingState.me = { ...waitingState.me, status: "waiting" };
    await open(page, "/meetings/join", { role: "treating", wait: "join-page", state: waitingState, join: { status: 200, body: { meeting_id: MID, status: "waiting", meeting: { ...waitingState.meeting, recording: "on" } } } });
    await page.setViewportSize(LAPTOP);
    await page.locator("#join-code").fill("305718");
    await page.getByTestId("join-submit").click();
    await expect(page.getByTestId("waiting-room")).toBeVisible();
    await expect(page.getByTestId("recording-notice")).toHaveText("This meeting is being recorded as text. No audio is kept.");
    await snap(page, "recorder-join-notice", [LAPTOP, PHONE]);
    expect(errors).toEqual([]);
  });

  test("the pre-join and the member's waiting screen say so too", async ({ page }) => {
    const errors = watchConsole(page);
    const s: AnyObj = memberState({ recording: recordingView("on") });
    s.meeting = { ...s.meeting, video: true };
    s.can = { ...s.can, video: true };
    await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "prejoin", state: s });
    await page.setViewportSize(LAPTOP);
    await expect(page.getByTestId("prejoin").getByTestId("recording-notice")).toHaveText("This meeting is being recorded as text. No audio is kept.");
    await expect(page.getByTestId("prejoin")).toContainText("No audio is ever kept.");
    await snap(page, "recorder-prejoin", [LAPTOP, PHONE]);
    expect(errors).toEqual([]);
  });

  test("the discussion notes: written line, the panel with the said chips, edit and mark reviewed; a member reads them", async ({ page }) => {
    const errors = watchConsole(page);
    const state: AnyObj = meetingState("in_session", { recording: recordingView("on") });
    const { live, rec } = await open(page, `/meetings/${MID}`, { wait: "control-view", state });
    await page.setViewportSize(LAPTOP);
    live.push({ type: "notes", case_id: CID, lines: 3, generated_at: rec.notes.cases[0].generated_at, review: "draft" });
    const written = page.getByTestId("notes-written");
    await expect(written).toContainText("Discussion notes written for Priya Venkatesan (SYNTHETIC)");
    await snap(page, "notes-written");
    await written.getByTestId("read-notes").click();
    const panel = page.getByTestId("notes-panel");
    await expect(panel).toBeVisible();
    await expect(written).toHaveCount(0);
    await expect(panel.getByTestId("notes-label")).toHaveText("AI draft, not reviewed");
    await expect(panel).toContainText("Written by Gemma-4-31B (non-medical)");
    await expect(panel.getByTestId("notes-dropped")).toContainText("1 line was left out");
    const lines = panel.getByTestId("note-line");
    await expect(lines).toHaveCount(3);
    await lines.first().getByTestId("said-chip").click();
    await expect(lines.first().getByTestId("said-quote")).toContainText("Shanthi Raman, 16:31, said:");
    await expect(lines.first().getByTestId("said-quote")).toContainText("“the axillary ultrasound shows no suspicious nodes”");
    await expect(lines.nth(1).getByTestId("said-chip")).toContainText("said · Board room · 16:33");
    await snap(page, "notes-panel");
    // Edit a line: the said stays, the line is marked edited
    await lines.nth(2).getByTestId("note-edit").click();
    await lines.nth(2).getByTestId("note-edit-text").fill("Thomas Joseph asked for the Ki-67 value to be read out to the board.");
    await lines.nth(2).getByTestId("note-edit-save").click();
    await expect(lines.nth(2).getByTestId("note-edited")).toContainText("Edited by Priya Nair");
    await expect(lines.nth(2).getByTestId("note-text")).toHaveText("Thomas Joseph asked for the Ki-67 value to be read out to the board.");
    expect(rec.calls.find((c) => c.method === "PUT")?.body).toEqual({ text: "Thomas Joseph asked for the Ki-67 value to be read out to the board." });
    // An edit sends a notes event with the same build time: no second "written" line
    await expect(written).toHaveCount(0);
    // Mark reviewed
    await panel.getByTestId("notes-review").click();
    await expect(panel.getByTestId("notes-label")).toHaveText(/^AI notes, reviewed by Priya Nair on \d{2}\/\d{2}\/\d{4}$/);
    expect(rec.calls.find((c) => c.path.endsWith("/notes/review"))?.body).toEqual({ status: "reviewed" });
    await snap(page, "notes-reviewed");
    await page.setViewportSize(PHONE);
    await snap(page, "notes-panel", [PHONE]);
    expect(errors).toEqual([]);
  });

  test("a member reads the notes from the More menu, read only", async ({ page }) => {
    const errors = watchConsole(page);
    const state: AnyObj = memberState({ recording: recordingView("on") });
    await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state });
    await page.setViewportSize(LAPTOP);
    await page.getByTestId("more").click();
    await page.getByTestId("menu-notes").click();
    const panel = page.getByTestId("notes-panel");
    await expect(panel.getByTestId("note-line")).toHaveCount(3);
    await expect(panel.getByTestId("notes-label")).toHaveText("AI draft, not reviewed");
    await expect(panel.getByTestId("note-edit")).toHaveCount(0);
    await expect(panel.getByTestId("notes-review")).toHaveCount(0);
    await panel.getByTestId("said-chip").nth(2).click();
    await expect(panel.getByTestId("said-quote")).toContainText("can someone read out the Ki-67 value");
    await snap(page, "notes-member", [LAPTOP, PHONE], async (p) => {
      if (!(await p.getByTestId("notes-panel").isVisible())) { await p.getByTestId("more").click(); await p.getByTestId("sheet-panel-notes").click(); }
      await expect(p.getByTestId("notes-panel").getByTestId("note-line").first()).toBeVisible();
    });
    expect(errors).toEqual([]);
  });
});
