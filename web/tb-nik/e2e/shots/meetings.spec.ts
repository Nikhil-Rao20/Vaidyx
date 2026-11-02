// Screenshots of the meeting pages: list, agenda, coordinator control view, room screen, member view, join and waiting room,
// with the live channel mocked (page.routeWebSocket) so live events (agent states, the decision strip, the card request, the Board
// view's follow state) can be pushed. Meetings-v2 2.5 and 2.6: the stage is the Board view of the Case File on the floor (the
// coordinator leads, the room follows, a member follows and may look around, an outside expert reads the stripped summary); no slides.
// Run: cd web/tb-nik && npx vite build && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts meetings
// Files: docs/ui/build/shots/meetings-<state>-<theme>-<width>.png. Routes: e2e/support/f2.ts (SYNTHETIC).
import { expect, test, type Page } from "@playwright/test";
import { SIZES, login, prepare, shoot, watchConsole } from "../support/helpers";
import { CID, MID, boardView, meetingState, memberState, routeBoardCases, routeMeetings, type MeetingRouteOptions } from "../support/f2";
import type { Role } from "../support/fixtures";

const DESKTOP_MOBILE = [SIZES[0], SIZES[2]];

/** helpers.shoot from the top of the page: full-page captures of a scrolled page put the sticky top bar mid-image. */
const snap: typeof shoot = (page, name, state, opts = {}) => shoot(page, name, state, { ...opts, before: async (p) => { await p.evaluate(() => window.scrollTo(0, 0)); if (opts.before) await opts.before(p); } });

async function open(page: Page, to: string, o: MeetingRouteOptions & { role?: Role; wait: string }) {
  await prepare(page, { role: o.role ?? "coordinator" });
  await routeBoardCases(page);
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
    // The mirrored laptop (D1): the Board view of the Case File on the floor in the middle, led from here; no slides; the Record button
    // (meetings-v2 5.2) is ready while the meeting is in session.
    const board = page.getByTestId("board-view");
    await expect(board).toHaveAttribute("data-mode", "drive");
    await expect(board).toHaveAttribute("data-tab", "summary");
    await expect(page.getByTestId("board-question")).toContainText("breast conservation surgery");
    await expect(page.getByTestId("board-follow")).toContainText("You lead: everyone follows what you open.");
    await expect(page.getByTestId("shared-screen")).toHaveAttribute("data-stage", "board");
    await expect(page.getByTestId("record")).toBeEnabled();  // meetings-v2 5.2: the recorder (meetings-recorder.spec.ts checks it)
    await expect(page.getByTestId("stage-tabs")).toHaveCount(0);
    await expect(page.getByTestId("slide")).toHaveCount(0);
    await expect(page.getByTestId("panel-case")).toHaveCount(0);
    // The admit line sits under the stage, never over the Board view.
    await page.setViewportSize(SIZES[0]);
    const stageBox = await page.getByTestId("shared-screen").boundingBox();
    const admitBox = await page.getByTestId("waiting-banner").boundingBox();
    expect(stageBox && admitBox && admitBox.y >= stageBox.y + stageBox.height - 1, "the admit line is under the stage").toBeTruthy();
    // The bar's panel buttons carry their words: People, Chat, Agents, Decision (the agenda is the rail).
    for (const k of ["chat", "people", "agents", "decision"]) await expect(page.getByTestId(`panel-${k}`)).toBeVisible();
    await expect(page.getByTestId("panel-agenda")).toHaveCount(0);
    await expect(page.getByTestId("panel-decision")).toContainText("Decision");
    await snap(page, "meetings", "control", { fullPage: false });
    // Every click moves the room: a tab, then a report opened inside the Board view at its page.
    await page.setViewportSize(SIZES[0]);
    let viewPost = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/view`));
    await page.getByTestId("board-tab-reports").click();
    expect((await viewPost).postDataJSON()).toEqual({ tab: "reports" });
    await expect(board).toHaveAttribute("data-tab", "reports");
    viewPost = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/view`));
    await page.locator('[data-testid=board-report-row][data-doc="D8a2c165d"]').click();
    expect((await viewPost).postDataJSON()).toEqual({ tab: "reports", doc_id: "D8a2c165d", page: 0 });
    await expect(board).toHaveAttribute("data-doc", "D8a2c165d");
    await expect(page.getByTestId("board-report-page")).toBeVisible();
    await snap(page, "meetings", "control-board-report", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.setViewportSize(SIZES[0]);
    viewPost = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/view`));
    await page.getByTestId("board-tab-summary").click();
    expect((await viewPost).postDataJSON()).toEqual({ tab: "summary" });
    // The agenda rail (laptop) and the Agenda panel (phone, from the More sheet's panels).
    await page.setViewportSize(SIZES[0]);
    await expect(page.getByTestId("agenda-rail")).toHaveAttribute("data-open", "true");
    await expect(page.getByTestId("agenda-rail").locator("[data-state=now]")).toContainText("Priya Venkatesan");
    await snap(page, "meetings", "control-agenda-rail", { sizes: [SIZES[0]], fullPage: false });
    await snap(page, "meetings", "control-agenda-rail", { sizes: [SIZES[2]], fullPage: false, before: async (p) => {
      if (!(await p.getByTestId("agenda-panel").isVisible())) { await p.getByTestId("more").click(); await p.getByTestId("sheet-panel-agenda").click(); }
      await expect(p.getByTestId("agenda-panel")).toBeVisible();
    } });
    await page.setViewportSize(SIZES[0]);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("agenda-panel")).toHaveCount(0);
    // The Decision panel opens from the bar's Decision button.
    await page.getByTestId("panel-decision").click();
    await expect(page.getByTestId("decision-panel")).toBeVisible();
    await expect(page.getByTestId("decision-form")).toBeVisible();
    // Step 1, the outcome: nothing is chosen for the board except the outcome as today; step 2 waits for the decision text.
    await expect(page.getByTestId("decision-step-1")).toHaveAttribute("aria-current", "step");
    await expect(page.getByTestId("decision-step-2")).toHaveAttribute("data-missing", "true");
    await snap(page, "meetings", "control-decision-outcome", { sizes: [SIZES[0]], fullPage: false });
    await page.getByTestId("save-decision").click();
    await expect(page.getByTestId("decision-problems")).toContainText("Step 2: write the board's decision");
    await expect(page.getByTestId("decision-problems")).toContainText("Step 2: record the treatment intent");
    // Step 2, the board's recommendation: the live strip still follows the decision text.
    await page.getByTestId("decision-next").click();
    await expect(page.getByTestId("decision-step-2")).toHaveAttribute("aria-current", "step");
    await expect(page.locator("[data-field=intent] [role=radio][aria-checked=true]")).toHaveCount(0);
    await page.locator("#d-text").fill("Breast conservation surgery with sentinel node biopsy");
    await expect(page.getByTestId("live-strip-note")).toContainText("not saved");
    await page.getByRole("radio", { name: "Curative" }).click();
    await page.getByRole("button", { name: "Surgery", exact: true }).click();
    await page.locator("#d-sequence").fill("Surgery then adjuvant therapy as per final histopathology");
    await snap(page, "meetings", "control-decision", { sizes: [SIZES[0]], fullPage: false, before: async () => { await page.getByTestId("decision-step-2").scrollIntoViewIfNeeded(); } });
    // Step 4, what happens next: an investigation and a referral, each with a department from the meeting's list.
    await page.getByTestId("decision-step-4").click();
    await page.getByTestId("add-investigation").click();
    await page.getByLabel("Investigation 1", { exact: true }).fill("Bone scan");
    await page.getByLabel("Department for investigation 1").fill("Nuclear Medicine");
    await page.getByTestId("add-referral").click();
    await page.getByLabel("Kind of referral 1").selectOption("genetics");
    await page.getByLabel("Department for referral 1").fill("Medical Oncology");
    await page.getByLabel("Note for referral 1", { exact: true }).fill("BRCA testing and counselling");  // exact: the mic beside it is "Dictate the note for referral 1" (night-v3 item 4.4)
    const panel = page.getByTestId("decision-panel-4");
    // Laptop only here: across 1024 px the side panel turns into a bottom sheet and the form inside is drawn again (unsaved steps reset).
    await snap(page, "meetings", "control-decision-next", { sizes: [SIZES[0]], fullPage: false, before: async () => { await panel.scrollIntoViewIfNeeded(); } });
    // The responsible clinician comes from the agenda row's owner doctor; the saved body carries the new fields.
    await page.getByTestId("decision-step-5").click();
    await expect(page.locator("#d-responsible_doctor")).toHaveValue("Lakshmi Rao");
    const posted = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/cases/${CID}/decision`));
    await page.getByTestId("save-decision").click();
    const body = (await posted).postDataJSON();
    expect(body).toMatchObject({ outcome: "decision", intent: "curative", modalities: ["surgery"], responsible_doctor: "Lakshmi Rao", investigations: [{ item: "Bone scan", department: "Nuclear Medicine" }], referrals: [{ kind: "genetics", department: "Medical Oncology", note: "BRCA testing and counselling" }] });
    expect(body.awaited).toBe("");
    await expect(page.getByTestId("save-decision")).toContainText("Saved");
    // People from the bar's People button: the waiting room is inside the People panel.
    await page.getByTestId("panel-people").click();
    await expect(page.getByTestId("people-panel").getByTestId("waiting-list")).toContainText("Kiran Shetty");
    await expect(page.getByTestId("waiting-banner")).toHaveCount(0);
    await snap(page, "meetings", "control-people", { sizes: [SIZES[0]], fullPage: false });
    // The phone: the People panel as a bottom sheet, no sideways scroll; the Coordinator sheet carries the case moves.
    await page.setViewportSize(SIZES[2]);
    await expect(page.getByTestId("people-panel")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await snap(page, "meetings", "control-people", { sizes: [SIZES[2]], fullPage: false });
    await page.getByRole("button", { name: "Close the panel" }).click();
    await page.getByTestId("coordinator-sheet").click();
    await expect(page.getByTestId("coordinator-menu")).toBeVisible();
    await expect(page.getByTestId("sheet-next")).toBeEnabled();
    await snap(page, "meetings", "control-coordinator-sheet", { sizes: [SIZES[2]], fullPage: false });
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await page.setViewportSize(SIZES[0]);
    live.push({ type: "end_case", case_id: CID, cards_requested: ["radiology", "medical_oncology"], timer: { seconds_left: 300, running: false, total: 600 } });
    await page.getByTestId("end-meeting").click();
    await snap(page, "meetings", "control-end-meeting", { sizes: [SIZES[0]], fullPage: false });
    expect(errors).toEqual([]);
  });

  test("room screen: the Board view following, stand-in, questions, live decision strip", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, `/meetings/${MID}/room`, { wait: "room-screen", state: meetingState("in_session") });
    const pathology = page.locator("[data-testid=agent-tile][data-role=pathology]");
    await expect(pathology).toHaveAttribute("data-agent-state", "thinking");
    await expect(page.locator("[data-testid=agent-tile][data-role=nuclear_medicine]")).toHaveAttribute("data-agent-state", "ready");
    await expect(page.getByTestId("decision-strip")).toContainText("not saved");
    // The room screen is signed in as the coordinator, yet it never leads: it follows, and nothing in the Board view takes a click.
    const board = page.getByTestId("board-view");
    await expect(board).toHaveAttribute("data-mode", "follow");
    await expect(page.getByTestId("board-follow")).toContainText("Following Priya Nair");
    await expect(page.getByTestId("board-look-around")).toHaveCount(0);
    await expect(page.getByTestId("board-tab-reports")).toBeDisabled();
    await expect(page.getByTestId("room-summary")).toHaveCount(0);
    await expect(page.getByTestId("summary-toggle")).toHaveCount(0);
    await snap(page, "meetings", "room", { fullPage: false });
    live.push({ type: "agent_state", agent: { active: true, role: "pathology", state: "answering", question: "Q2" } });
    // The coordinator opens the histopathology report at its line: the room follows (tab, report, page, the line boxed).
    live.push({ type: "view", view: boardView({ tab: "reports", doc_id: "D8a2c165d", page: 0, quote: "Grade: Grade 2 (Nottingham score 6)", opened: { kind: "record", doc_id: "D8a2c165d", title: "HISTOPATHOLOGY REPORT", url: `/api/tb/cases/${CID}/documents/D8a2c165d/file` } }) });
    await expect(board).toHaveAttribute("data-tab", "reports");
    await expect(board).toHaveAttribute("data-doc", "D8a2c165d");
    await expect(page.getByTestId("board-report-page")).toBeVisible();
    await expect(pathology).toHaveAttribute("data-agent-state", "answering");
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

  test("member view: follow, look around, back to the room, question, card", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: memberState() });
    const view = page.getByTestId("member-view");
    const board = page.getByTestId("board-view");
    await expect(view).toHaveAttribute("data-following", "true");
    await expect(board).toHaveAttribute("data-mode", "follow");
    await expect(page.getByTestId("board-follow")).toContainText("Following Priya Nair");
    await expect(page.getByTestId("stage-tabs")).toHaveCount(0);
    let viewPosts = 0;
    page.on("request", (r) => { if (r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/view`)) viewPosts += 1; });
    // The coordinator opens a report: the member's Board view follows.
    live.push({ type: "view", view: boardView({ tab: "reports", doc_id: "D8a2c165d", page: 0, quote: "Grade: Grade 2 (Nottingham score 6)" }) });
    await expect(board).toHaveAttribute("data-tab", "reports");
    await expect(board).toHaveAttribute("data-doc", "D8a2c165d");
    await snap(page, "meetings", "member");
    await page.setViewportSize(SIZES[0]);
    // Look around: the member clicks freely on this screen only; nothing is posted and the room does not move.
    await page.getByTestId("board-look-around").click();
    await expect(view).toHaveAttribute("data-following", "false");
    await expect(board).toHaveAttribute("data-mode", "look");
    await page.getByTestId("board-tab-stage").click();
    await expect(board).toHaveAttribute("data-tab", "stage");
    await expect(page.getByTestId("board-back-to-room")).toBeVisible();
    // The room moves on meanwhile; the member stays where they are until Back to the room.
    live.push({ type: "view", view: boardView({ tab: "summary" }) });
    await expect(board).toHaveAttribute("data-tab", "stage");
    await snap(page, "meetings", "member-looking-around", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("board-back-to-room").click();
    await expect(view).toHaveAttribute("data-following", "true");
    await expect(board).toHaveAttribute("data-tab", "summary");
    expect(viewPosts, "a member never moves the room").toBe(0);
    // One side panel at a time: People, then Chat replaces it; Esc closes.
    await page.getByTestId("panel-people").click();
    await expect(page.getByTestId("people-panel")).toBeVisible();
    await snap(page, "meetings", "member-panel-people", { sizes: DESKTOP_MOBILE, fullPage: false });
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("panel-chat").click();
    await expect(page.getByTestId("questions-panel")).toBeVisible();
    await expect(page.getByTestId("people-panel")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("chat-panel")).toHaveCount(0);
    // The More menu: a dropdown on a laptop, a bottom sheet on a phone.
    await page.getByTestId("more").click();
    await expect(page.getByTestId("more-menu")).toBeVisible();
    await expect(page.getByTestId("call-button")).toBeVisible();
    await snap(page, "meetings", "member-more", { sizes: [SIZES[0]], fullPage: false });
    await page.keyboard.press("Escape");
    await page.setViewportSize(SIZES[2]);
    await page.getByTestId("more").click();
    await expect(page.getByTestId("more-menu")).toBeVisible();
    await snap(page, "meetings", "member-more", { sizes: [SIZES[2]], fullPage: false });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await page.setViewportSize(SIZES[0]);
    // The shortcuts: "?" opens the list.
    await page.keyboard.press("?");
    await expect(page.getByTestId("shortcuts-dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    live.push({ type: "end_case", case_id: CID, cards_requested: ["radiology"], timer: null });
    await expect(page.getByTestId("card-dialog")).toBeVisible();
    await page.getByTestId("card-concern").click();
    await snap(page, "meetings", "member-card", { sizes: DESKTOP_MOBILE, fullPage: false });
    expect(errors).toEqual([]);
  });

  test("member view: an offline member has no tile, 16 px boxes, the meeting ended card (night-v3 5.6)", async ({ page }) => {
    const errors = watchConsole(page);
    // Thirteen people (the People panel shows its search box from 13); Thomas Joseph is remote, offline and not in the video.
    const extra = Array.from({ length: 9 }, (_, i) => ({ user: `extra${i}@vxh.example`, name: `Extra Member ${i + 1}`, department: "pathology", department_name: "Pathology", status: "remote", mode: "remote", online: true, head: false }));
    const base = memberState();
    const state = memberState({ attendance: [...(base.attendance as object[]), ...extra] });
    const live = await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state });
    await page.setViewportSize(SIZES[0]);
    const strip = page.getByTestId("tile-grid").first();
    await expect(strip.locator('[data-testid=tile][data-user="shanthi@vxh.example"]')).toHaveCount(1);
    await expect(page.locator('[data-testid=tile][data-user="joseph@vxh.example"]')).toHaveCount(0);
    await page.getByTestId("panel-people").click();
    await expect(page.getByTestId("people-panel")).toContainText("Thomas Joseph");
    const fontPx = (sel: string) => page.locator(sel).evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(await fontPx("#people-search")).toBe(16);
    await page.getByTestId("panel-chat").click();
    await expect(page.getByTestId("questions-panel")).toBeVisible();
    expect(await fontPx("#member-q")).toBe(16);
    await page.keyboard.press("Escape");
    // The coordinator ends the meeting: the card over the stage, the bar keeps Leave only, no timer.
    const closed = { ...(state as Record<string, unknown>), meeting: { ...(state.meeting as Record<string, unknown>), status: "closed" } };
    live.push({ type: "state", ...closed });
    const card = page.getByTestId("meeting-ended");
    await expect(card).toBeVisible();
    await expect(card).toContainText("The meeting has ended");
    await expect(card.getByRole("link", { name: "Back to the meeting page" })).toHaveAttribute("href", `/tb-nik/meetings/${MID}`);
    await expect(page.getByTestId("leave")).toBeVisible();
    await expect(page.getByTestId("mic")).toHaveCount(0);
    await expect(page.getByTestId("raise-hand")).toHaveCount(0);
    await expect(page.getByTestId("timer")).toHaveCount(0);
    await snap(page, "meetings", "member-ended", { sizes: DESKTOP_MOBILE, fullPage: false });
    expect(errors).toEqual([]);
  });

  test("room screen: Meeting closed over the stage (night-v3 5.6)", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(SIZES[1]);
    const live = await open(page, `/meetings/${MID}/room`, { wait: "room-screen", state: meetingState("in_session") });
    await expect(page.getByTestId("meeting-ended")).toHaveCount(0);
    const st = meetingState("in_session") as Record<string, unknown>;
    live.push({ type: "state", ...st, meeting: { ...(st.meeting as Record<string, unknown>), status: "closed" } });
    await expect(page.getByTestId("meeting-ended")).toContainText("Meeting closed");
    await expect(page.getByTestId("room-screen")).toHaveAttribute("data-meeting-status", "closed");
    expect(errors).toEqual([]);
  });

  test("outside expert: the identity-stripped summary, never the Board view", async ({ page }) => {
    const errors = watchConsole(page);
    const base = memberState();
    const attendance = (base.attendance as Array<Record<string, unknown>>).map((a) => (a.user === "rao@vxh.example" ? { ...a, outside_expert: true, status: "remote", mode: "remote" } : a));
    const state = memberState({ attendance, can: { ...(base.can as object), ask: false, card: false, card_required: false, ask_agents: false } });
    let caseReads = 0;
    page.on("request", (r) => { if (r.url().includes(`/api/tb/cases/${CID}`)) caseReads += 1; });
    await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state });
    const summary = page.getByTestId("expert-summary");
    await expect(summary).toBeVisible();
    await expect(summary).toContainText("outside expert");
    await expect(page.getByTestId("board-view")).toHaveCount(0);
    await expect(page.getByTestId("stage-tabs")).toHaveCount(0);
    expect(caseReads, "no Case File route is asked for an outside expert").toBe(0);
    await snap(page, "meetings", "member-expert", { sizes: DESKTOP_MOBILE, fullPage: false });
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

  // night-v3 5.2: someone presents a screen. No LiveKit in mock mode, so the stage shows the placeholder until the picture comes.
  const withVideo = (st: Record<string, any>) => ({ ...st, meeting: { ...st.meeting, video: true }, can: { ...st.can, video: true } }); // eslint-disable-line @typescript-eslint/no-explicit-any

  test("present a screen: the member sees who presents and may not present", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "prejoin", state: withVideo(memberState({ presenting: "mdt@vxh.example" })) });
    await page.getByTestId("prejoin-join").click();
    await expect(page.getByTestId("member-view")).toHaveAttribute("data-video-status", "failed", { timeout: 15_000 });
    const stage = page.getByTestId("shared-screen");
    await expect(stage).toHaveAttribute("data-stage", "share-waiting");
    await expect(stage).toContainText("Priya Nair is presenting: waiting for the picture");
    await expect(page.getByTestId("share-badge")).toContainText("Priya Nair is presenting");
    await expect(page.getByTestId("share-stop")).toHaveCount(0);  // only the sharer and the coordinator stop a share
    const present = page.getByTestId("present");
    await expect(present).toBeDisabled();
    await expect(present).toHaveAttribute("title", "Ask the MDT Coordinator to allow you to present");
    await expect(present).toHaveAttribute("data-may-present", "false");
    // The People panel names the sharer.
    await page.getByTestId("panel-people").click();
    await expect(page.getByTestId("person-row").filter({ hasText: "Priya Nair" }).getByTestId("present-word")).toHaveText("presenting");
    await page.getByTestId("panel-people").click();
    await snap(page, "meetings", "member-presenting", { sizes: DESKTOP_MOBILE, fullPage: false });
    // A phone cannot capture a screen: no Present button, the share still shows.
    await page.setViewportSize(SIZES[2]);
    await expect(page.getByTestId("present")).toHaveCount(0);
    await expect(stage).toHaveAttribute("data-stage", "share-waiting");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.setViewportSize(SIZES[0]);
    // The share ends: the Board view again.
    live.push({ type: "presenting", user: "mdt@vxh.example", name: "Priya Nair", on: false, by: "mdt@vxh.example" });
    await expect(stage).toHaveAttribute("data-stage", "board");
    await expect(page.getByTestId("board-view")).toBeVisible();
    await expect(page.getByTestId("share-badge")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("present a screen: the coordinator allows, withdraws and stops", async ({ page }) => {
    const errors = watchConsole(page);
    const st = withVideo(meetingState("in_session", { presenting: "shanthi@vxh.example", present_allowed: ["shanthi@vxh.example", "joseph@vxh.example"] }));
    await open(page, `/meetings/${MID}`, { wait: "prejoin", state: st });
    await page.getByTestId("prejoin-join").click();
    await expect(page.getByTestId("control-view")).toHaveAttribute("data-video-status", "failed", { timeout: 15_000 });
    const present = page.getByTestId("present");
    await expect(present).toHaveAttribute("data-may-present", "true");  // the coordinator may present; here only the video is missing
    await expect(present).toHaveAttribute("title", "Join the video to present a screen");
    await expect(page.getByTestId("shared-screen")).toHaveAttribute("data-stage", "share-waiting");
    await expect(page.getByTestId("share-badge")).toContainText("Shanthi Raman is presenting");
    // With Present in it, the coordinator's bar still fits a 1366 px laptop: End meeting stays clear of the panel buttons.
    const endBox = await page.getByTestId("end-meeting").boundingBox();
    const chatBox = await page.getByTestId("panel-chat").boundingBox();
    expect(endBox && chatBox && endBox.x + endBox.width <= chatBox.x, `End meeting ends at ${endBox && endBox.x + endBox.width}, the panels start at ${chatBox?.x}`).toBeTruthy();
    // The tile menu: allow a person, or withdraw the right and stop the share of the one presenting; none on the coordinator.
    const tile = (u: string) => page.locator(`[data-testid="tile"][data-user="${u}"]`).first();
    await tile("mdt@vxh.example").getByTestId("tile-menu").click();
    await expect(page.getByTestId("tile-pin")).toBeVisible();
    await expect(page.locator("[data-testid^=tile-present-]")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await tile("shanthi@vxh.example").getByTestId("tile-menu").click();
    await expect(page.getByTestId("tile-present-withdraw")).toHaveText("Withdraw the right to present");
    await expect(page.getByTestId("tile-present-stop")).toHaveText("Stop their share");
    await page.keyboard.press("Escape");
    await tile("rao@vxh.example").getByTestId("tile-menu").click();
    await expect(page.getByTestId("tile-present-allow")).toHaveText("Allow to present");
    await snap(page, "meetings", "control-present-menu", { sizes: [SIZES[0]], fullPage: false, before: async (p) => {
      if (!(await p.getByTestId("tile-present-allow").isVisible())) await tile("rao@vxh.example").getByTestId("tile-menu").click();
      await expect(p.getByTestId("tile-present-allow")).toBeVisible();
    } });
    const allowed = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/present-allow`));
    await page.getByTestId("tile-present-allow").click();
    expect((await allowed).postDataJSON()).toEqual({ user: "rao@vxh.example", allowed: true });
    // The People panel: "presenting" and "may present" on the rows; the row menu withdraws the right.
    await page.getByTestId("panel-people").click();
    const row = (name: string) => page.getByTestId("people-panel").getByTestId("person-row").filter({ hasText: name });
    await expect(row("Shanthi Raman").getByTestId("present-word")).toHaveText("presenting");
    await expect(row("Thomas Joseph").getByTestId("present-word")).toHaveText("may present");
    await row("Thomas Joseph").getByRole("button", { name: "More for Thomas Joseph" }).click();
    const withdrawn = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/present-allow`));
    await page.getByTestId("row-present-withdraw").click();
    expect((await withdrawn).postDataJSON()).toEqual({ user: "joseph@vxh.example", allowed: false });
    await page.getByTestId("panel-people").click();
    // Stop on the stage ends anyone's share for everyone.
    const stopped = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/presenting`));
    await page.getByTestId("share-stop").click();
    expect((await stopped).postDataJSON()).toEqual({ on: false });
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
