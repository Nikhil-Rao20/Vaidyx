// The one-page planner of the MDT Coordinator (meetings-v2 3.3, owner D7 to D10) and the PDF buttons (4.1): "Plan a Tumour Board"
// with Every week or Once, the planner of a meeting of a weekly series (when and where edited in place, Change the series, the lists in
// urgency order, reorder by drag and by Up and Down, Put back in urgency order, Move, Remove, Add a Case File, the members and the join
// code made by themselves, Send agenda, Start meeting, the meeting PDF, More with Cancel), and the Case File's board record PDF in
// place of the .pptx deck (4.2). Light theme, laptop 1366 and phone 390.
// Run: cd web/tb-nik && npx vite build && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts meetings-planner
// Files: docs/ui/build/shots/meetings-planner-<state>-light-<width>.png. Routes: e2e/support/f2.ts and planner.ts (SYNTHETIC).
import { expect, test, type Page } from "@playwright/test";
import { SIZES, login, prepare, shoot, watchConsole } from "../support/helpers";
import { caseFileAfterBoard, caseFileUnsent, routeBoardCases, routeCaseFile, routeMeetings, stepsAfterBoard } from "../support/f2";
import { CID, MID, NEXT, SID, WEEKDAYS, dmy, istDay, openMeetings, plannerHandState, plannerState, routePlanner, weekdayOf } from "../support/planner";

const LIGHT = ["light"] as const;
const BOTH = [SIZES[0], SIZES[2]];
const LAPTOP = [SIZES[0]];

/** helpers.shoot, light only, from the top of the page. */
const snap = (page: Page, state: string, opts: { sizes?: typeof SIZES; fullPage?: boolean; before?: (p: Page) => Promise<void> } = {}) =>
  shoot(page, "meetings-planner", state, { themes: LIGHT, sizes: opts.sizes ?? BOTH, fullPage: opts.fullPage, before: async (p) => { await p.evaluate(() => window.scrollTo(0, 0)); if (opts.before) await opts.before(p); } });

async function openPlanner(page: Page, state = plannerState(), o: { series?: unknown[]; to?: string; wait?: string } = {}) {
  await prepare(page, { role: "coordinator" });
  await routeBoardCases(page);
  await routeMeetings(page, { state });
  const calls = await routePlanner(page, state, { series: o.series as never });
  await login(page);
  await page.goto(`/tb-nik${o.to ?? `/meetings/${MID}`}`);
  await page.getByTestId(o.wait ?? "plan-header").first().waitFor({ timeout: 20_000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  return calls;
}

const order = (page: Page, list: "discussion" | "noting") => page.getByTestId(`list-${list}`).locator("[data-testid=agenda-row]").evaluateAll((els) => els.map((e) => e.getAttribute("data-case-id")));
const last = <T extends { method: string; path: string }>(calls: T[], method: string, end: string) => [...calls].reverse().find((c) => c.method === method && c.path.endsWith(end));

test.describe("Meetings planner", () => {
  test("Plan a Tumour Board: Every week (the usual), then Once for an extra meeting", async ({ page }) => {
    const errors = watchConsole(page);
    const state = plannerState();
    const calls = await openPlanner(page, state, { series: [], to: "/meetings", wait: "meetings-page" });
    await page.getByTestId("new-meeting").click();
    const dlg = page.getByTestId("new-meeting-dialog");
    await expect(dlg).toBeVisible();
    // No weekly series yet: the dialog starts on Every week, with the next four dates made at once.
    await expect(page.getByTestId("plan-weekly")).toHaveAttribute("aria-checked", "true");
    await dlg.getByRole("radio", { name: "Friday" }).click();
    await page.locator("#nm-time").fill("16:00");
    await page.locator("#nm-room").fill("Seminar hall 2");
    await page.locator("#nm-room").press("Tab");
    await expect(page.getByTestId("plan-ahead")).toContainText("Every week on Friday at 16:00. The next four are made now:");
    await snap(page, "plan-weekly", { fullPage: false });
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("plan-submit").click();
    await expect(page).toHaveURL(new RegExp(`/meetings/${MID}$`));
    expect(last(calls, "POST", "/meeting-series")?.body).toMatchObject({ weekday: 4, time: "16:00", room: "Seminar hall 2" });
    await expect(page.getByTestId("plan-header")).toBeVisible();
    // Back on the list, a weekly series runs: the dialog starts on Once (an extra meeting); the date is asked.
    await page.goto("/tb-nik/meetings");
    await expect(page.getByTestId("series-strip")).toContainText("Every week on Friday at 16:00");
    await page.getByTestId("new-meeting").click();
    await expect(page.getByTestId("plan-once")).toHaveAttribute("aria-checked", "true");
    const extra = istDay(1);
    await page.locator("#nm-date").fill(dmy(extra));
    await page.locator("#nm-time").fill("11:00");
    await page.locator("#nm-room").fill("Board room");
    await page.locator("#nm-room").press("Tab");
    await snap(page, "plan-once", { fullPage: false });
    await page.setViewportSize(SIZES[0]);
    const created = page.waitForRequest((r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/tb/meetings");
    await page.getByTestId("plan-submit").click();
    expect((await created).postDataJSON()).toMatchObject({ date: extra, time: "11:00", room: "Board room" });
    expect(errors).toEqual([]);
  });

  test("the list: upcoming meetings of a series say Every week on <day>, the past below", async ({ page }) => {
    const errors = watchConsole(page);
    await openPlanner(page, plannerState(), { to: "/meetings", wait: "meetings-list" });
    const wd = WEEKDAYS[weekdayOf(istDay(3))];
    await expect(page.getByTestId("meetings-list").getByTestId("row-series")).toContainText(`Every week on ${wd}`);
    await expect(page.getByTestId("meetings-past")).toBeVisible();
    await snap(page, "list");
    expect(errors).toEqual([]);
  });

  test("the planner of a weekly meeting: when and where in place, the series, members and code, the lists", async ({ page }) => {
    const errors = watchConsole(page);
    const state = plannerState();
    const calls = await openPlanner(page, state);
    const wd = WEEKDAYS[weekdayOf(istDay(3))];
    await expect(page.getByTestId("plan-date")).toContainText(`${wd} ${dmy(istDay(3))}`);
    await expect(page.getByTestId("plan-series")).toContainText(`Every week on ${wd} at 16:00`);
    await expect(page.getByTestId("meeting-code")).toHaveText("305718");
    await expect(page.getByTestId("members-heads")).toContainText("Radiation Oncology");
    await expect(page.getByTestId("members-teams")).toContainText("Breast Surgery");
    await expect(page.getByTestId("order-discussion")).toContainText("Most urgent first");
    expect(await order(page, "discussion")).toEqual(["TB-2026-0030", CID, "TB-2026-0029"]);
    await expect(page.getByTestId("agenda-sent")).toHaveText("Not sent yet");
    await expect(page.getByTestId("start-meeting")).toBeDisabled();
    await expect(page.getByTestId("start-hint")).toContainText(`Opens on the day, ${wd} ${dmy(istDay(3))}`);
    await expect(page.getByTestId("meeting-pdf")).toHaveAttribute("href", `/api/tb/meetings/${MID}/pdf`);
    await expect(page.getByTestId("meeting-pdf")).toContainText("Download the agenda (PDF)");
    await snap(page, "planner");
    // The time, edited in place: Enter saves; the server takes it.
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("plan-time").click();
    const timeBox = page.getByTestId("plan-time-edit").getByRole("textbox");
    await timeBox.fill("15:30");
    await snap(page, "edit-in-place", { sizes: LAPTOP, fullPage: false });
    await timeBox.press("Enter");
    await expect(page.getByTestId("plan-time")).toContainText("15:30");
    expect(last(calls, "PUT", `/meetings/${MID}`)?.body).toEqual({ time: "15:30" });
    // A date that passed is refused before it is sent; Escape leaves it as it was.
    await page.getByTestId("plan-date").click();
    const dateBox = page.getByTestId("plan-date-edit").getByRole("textbox");
    await dateBox.fill(dmy(istDay(-2)));
    await page.getByRole("button", { name: "Save the date" }).click();
    await expect(page.getByTestId("plan-date-edit").getByRole("alert")).toContainText("That date has passed");
    await dateBox.press("Escape");
    await expect(page.getByTestId("plan-date")).toContainText(dmy(istDay(3)));
    expect(errors).toEqual([]);
  });

  test("Change the series: the weekday, time and room; pause; stop with a clear warning", async ({ page }) => {
    const errors = watchConsole(page);
    const calls = await openPlanner(page);
    await page.getByTestId("change-series").click();
    const dlg = page.getByTestId("series-dialog");
    await expect(dlg).toBeVisible();
    const other = (weekdayOf(istDay(3)) + 1) % 7;
    await dlg.getByRole("radio", { name: WEEKDAYS[other] }).click();
    await expect(dlg).toContainText(`The future meetings move to ${WEEKDAYS[other]}`);
    await snap(page, "series", { fullPage: false });
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("series-save").click();
    await expect(dlg).toHaveCount(0);
    expect(last(calls, "PUT", `/meeting-series/${SID}`)?.body).toEqual({ weekday: other });
    await expect(page.getByTestId("plan-series")).toContainText(`Every week on ${WEEKDAYS[other]} at 16:00`);
    await page.getByTestId("change-series").click();
    await page.getByTestId("series-pause").click();
    expect(last(calls, "POST", "/pause")).toBeTruthy();
    await expect(page.getByTestId("series-dialog")).toContainText("paused");
    await page.getByTestId("series-stop").click();
    const warn = page.getByRole("dialog", { name: "Stop the weekly series?" });
    await expect(warn).toContainText("No new meetings are made after this");
    await expect(warn).toContainText("already have Case Files");
    await snap(page, "series-stop", { fullPage: false });
    await page.setViewportSize(SIZES[0]);
    await warn.getByRole("button", { name: "Stop the series" }).click();
    await expect.poll(() => !!last(calls, "POST", "/stop")).toBe(true);
    await expect(page.getByTestId("plan-series")).toContainText("series stopped");
    expect(errors).toEqual([]);
  });

  test("reorder: Up and Down keep the keyboard on the row, drag, then Put back in urgency order", async ({ page }) => {
    const errors = watchConsole(page);
    const state = plannerState();
    const calls = await openPlanner(page, state);
    // Up and Down: Fatima B. (urgency 5) one down; the list is now in the coordinator's order.
    await page.getByRole("button", { name: "Move Fatima B. down" }).click();
    await expect.poll(() => order(page, "discussion")).toEqual([CID, "TB-2026-0030", "TB-2026-0029"]);
    expect(last(calls, "PUT", "/agenda")?.body).toEqual({ discussion: [CID, "TB-2026-0030", "TB-2026-0029"], noting: ["TB-2026-0019"] });
    await expect(page.getByRole("button", { name: "Move Fatima B. down" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect.poll(() => order(page, "discussion")).toEqual([CID, "TB-2026-0029", "TB-2026-0030"]);
    // At the end Down is off: the keyboard stays on the row's Up button.
    await expect(page.getByRole("button", { name: "Move Fatima B. up" })).toBeFocused();
    await expect(page.getByTestId("list-discussion")).toHaveAttribute("data-order", "hand");
    await expect(page.getByTestId("order-discussion")).toContainText("In your order");
    // Drag: the third row to the top by its handle.
    const handles = page.getByTestId("list-discussion").getByTestId("drag-handle");
    const from = await handles.nth(2).boundingBox();
    const to = await handles.nth(0).boundingBox();
    await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2);
    await page.mouse.down();
    await page.mouse.move(from!.x + from!.width / 2, from!.y - 10, { steps: 4 });
    await page.mouse.move(to!.x + to!.width / 2, to!.y + 2, { steps: 12 });
    await page.mouse.up();
    await expect.poll(() => order(page, "discussion")).toEqual(["TB-2026-0030", CID, "TB-2026-0029"]);
    await expect.poll(() => last(calls, "PUT", "/agenda")?.body?.discussion).toEqual(["TB-2026-0030", CID, "TB-2026-0029"]);
    await page.waitForTimeout(400);  // the drag's own click guard ends
    // Put back in urgency order: the server sorts it again.
    await page.getByTestId("urgency-order-discussion").click();
    await expect.poll(() => last(calls, "PUT", "/agenda")?.body?.by_urgency).toEqual(["discussion"]);
    await expect(page.getByTestId("list-discussion")).toHaveAttribute("data-order", "urgency");
    await expect(page.getByTestId("urgency-order-discussion")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("a list arranged by hand: a Case File sent since goes at the end, marked New", async ({ page }) => {
    const errors = watchConsole(page);
    await openPlanner(page, plannerHandState());
    const row = page.locator('[data-testid=agenda-row][data-new="true"]');
    await expect(row).toContainText("New");
    await expect(row).toHaveAttribute("data-case-id", "TB-2026-0031");
    expect((await order(page, "discussion")).at(-1)).toBe("TB-2026-0031");
    await expect(page.getByTestId("urgency-order-discussion")).toBeVisible();
    await snap(page, "hand-order");
    expect(errors).toEqual([]);
  });

  test("move to another meeting, remove with a reason, add a Case File by search", async ({ page }) => {
    const errors = watchConsole(page);
    const state = plannerState();
    const calls = await openPlanner(page, state);
    await page.getByRole("button", { name: "Move Kamala S. to another meeting" }).click();
    const move = page.getByTestId("move-dialog");
    await expect(move.getByTestId("move-meeting")).toHaveCount(openMeetings().length - 1);
    await move.getByTestId("move-meeting").filter({ hasText: dmy(istDay(10)) }).click();
    await move.locator("#move-reason").fill("The MRI pelvis report is due next week (SYNTHETIC)");
    await snap(page, "move", { fullPage: false });
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("move-confirm").click();
    await expect(move).toHaveCount(0);
    expect(last(calls, "POST", "/meeting/move")).toMatchObject({ path: "/api/tb/cases/TB-2026-0029/meeting/move", body: { meeting_id: NEXT, reason: "The MRI pelvis report is due next week (SYNTHETIC)" } });
    await expect.poll(() => order(page, "discussion")).toEqual(["TB-2026-0030", CID]);
    // Remove: the reason is asked; the row leaves.
    await page.getByRole("button", { name: "Remove Fatima B. from this meeting" }).click();
    const rm = page.getByRole("dialog", { name: "Remove from this meeting?" });
    await expect(rm.getByRole("button", { name: "Remove" })).toBeDisabled();
    await rm.getByRole("textbox").fill("Patient chose treatment elsewhere (SYNTHETIC)");
    await snap(page, "remove", { fullPage: false });
    await page.setViewportSize(SIZES[0]);
    await rm.getByRole("button", { name: "Remove" }).click();
    await expect.poll(() => last(calls, "POST", "/meeting/withdraw")?.body).toEqual({ reason: "Patient chose treatment elsewhere (SYNTHETIC)" });
    await expect.poll(() => order(page, "discussion")).toEqual([CID]);
    // Add a Case File: search by name; the added row is ringed.
    await page.getByTestId("add-case").click();
    await expect(page.getByTestId("add-case-dialog")).toBeVisible();
    await page.getByTestId("add-search").fill("Lakshmi");
    await expect(page.getByTestId("add-result")).toHaveCount(1);
    await expect(page.getByTestId("add-result")).toContainText("VXH/2026/000123");
    await snap(page, "add-case", { fullPage: false });
    await page.setViewportSize(SIZES[0]);
    const added = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith(`/meetings/${MID}/agenda/add`));
    await page.getByRole("button", { name: "Add Lakshmi R. for discussion" }).click();
    expect((await added).postDataJSON()).toMatchObject({ case_id: "TB-2026-0031", list: "discussion" });
    await expect(page.locator('[data-testid=agenda-row][data-just-added="true"]')).toContainText("Lakshmi R.");
    expect(errors).toEqual([]);
  });

  test("the code is made by itself; Send agenda says when; the PDF downloads; Start on the day", async ({ page }) => {
    const errors = watchConsole(page);
    const state = plannerState({ date: istDay(0), code: null });
    const calls = await openPlanner(page, state);
    await expect(page.getByTestId("meeting-code")).toHaveText("482913");
    expect(calls.filter((c) => c.path.endsWith("/code"))).toHaveLength(1);
    await page.getByTestId("send-agenda").click();
    await expect(page.getByTestId("agenda-sent")).toContainText(`Sent ${dmy(istDay(0))}`);
    await expect(page.getByTestId("send-agenda")).toContainText("Send again");
    // The PDF link (a download in the browser goes past the test's routes, so it is read through fetch here, as the page would get it).
    const pdf = page.getByTestId("meeting-pdf");
    await expect(pdf).toHaveAttribute("href", `/api/tb/meetings/${MID}/pdf`);
    await expect(pdf).toHaveAttribute("download", "");
    const got = await page.evaluate(async (u) => { const r = await fetch(u); return { type: r.headers.get("content-type"), disp: r.headers.get("content-disposition"), head: (await r.text()).slice(0, 5) }; }, `/api/tb/meetings/${MID}/pdf`);
    expect(got).toMatchObject({ type: "application/pdf", head: "%PDF-" });
    expect(got.disp).toMatch(/filename="Tumour-Board-meeting-.*\.pdf"/);
    await expect(page.getByTestId("start-meeting")).toBeEnabled();
    await snap(page, "on-the-day");
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("start-meeting").click();
    await expect(page.getByTestId("control-view")).toBeVisible({ timeout: 20_000 });
    expect(last(calls, "POST", "/start")).toBeTruthy();
    expect(errors).toEqual([]);
  });

  test("More: minutes per case, video, cancel says where the Case Files go", async ({ page }) => {
    const errors = watchConsole(page);
    const state = plannerState();
    const calls = await openPlanner(page, state);
    await page.getByTestId("plan-more-toggle").click();
    await page.locator("#plan-mins").fill("12");
    await page.getByTestId("save-minutes").click();
    await expect.poll(() => last(calls, "PUT", `/meetings/${MID}`)?.body).toEqual({ minutes_per_case: 12 });
    await page.getByRole("switch", { name: /Video for remote members/ }).click();
    await expect.poll(() => last(calls, "PUT", `/meetings/${MID}`)?.body).toEqual({ video: true });
    await snap(page, "more", { before: async (p) => { await p.getByTestId("plan-more").scrollIntoViewIfNeeded(); }, fullPage: false });
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("cancel-meeting").click();
    const dlg = page.getByRole("dialog", { name: "Cancel this meeting?" });
    const next = openMeetings().find((m) => m.id === "M-X")!;
    await expect(dlg.getByTestId("cancel-where")).toContainText(`Its 4 Case Files go to the next planned meeting, ${WEEKDAYS[weekdayOf(next.date)]} ${dmy(next.date)} at 11:00`);
    await expect(dlg.getByTestId("cancel-where")).toContainText("only this date is skipped");
    await dlg.getByRole("textbox").fill("Holiday declared (SYNTHETIC)");
    await snap(page, "cancel", { fullPage: false });
    await page.setViewportSize(SIZES[0]);
    await dlg.getByRole("button", { name: "Cancel the meeting" }).click();
    await expect.poll(() => last(calls, "POST", "/cancel")?.body).toEqual({ reason: "Holiday declared (SYNTHETIC)" });
    await expect(page.getByTestId("meeting-cancelled")).toContainText("Holiday declared");
    expect(errors).toEqual([]);
  });

  test("a member reads the agenda; the closed meeting gives the record PDF", async ({ page }) => {
    const errors = watchConsole(page);
    const state = plannerState({ can: { manage: false, record: false, ask: false }, code: null, me: { user: "rao@vxh.example", status: "present", department: "breast_surgery" } });
    await prepare(page, { role: "treating" });
    await routeMeetings(page, { state });
    await routePlanner(page, state);
    await login(page);
    await page.goto(`/tb-nik/meetings/${MID}`);
    await expect(page.getByTestId("meeting-page")).toHaveAttribute("data-planner", "read");
    await expect(page.getByTestId("plan-series")).toContainText("Every week on");
    await expect(page.getByTestId("change-series")).toHaveCount(0);
    await expect(page.getByTestId("row-actions")).toHaveCount(0);
    await expect(page.getByTestId("send-agenda")).toHaveCount(0);
    await expect(page.getByTestId("meeting-pdf")).toContainText("Download the agenda (PDF)");
    await snap(page, "member");
    Object.assign(state.meeting, { status: "closed", date: istDay(-1) });
    state.status = "closed";
    await page.reload();
    await expect(page.getByTestId("meeting-closed")).toBeVisible();
    await expect(page.getByTestId("meeting-pdf")).toContainText("Download the meeting record (PDF)");
    await snap(page, "closed", { sizes: LAPTOP, fullPage: false });
    expect(errors).toEqual([]);
  });

  test("the Case File: Board record (PDF) in the More menu, no slides", async ({ page }) => {
    const errors = watchConsole(page);
    await prepare(page, { role: "treating" });
    await routeCaseFile(page, { caseFile: caseFileAfterBoard(), steps: stepsAfterBoard() });
    await login(page);
    await page.goto(`/tb-nik/cases/${CID}`);
    await page.getByTestId("casefile-page").waitFor({ timeout: 20_000 });
    await page.getByTestId("more-menu").first().click();
    await expect(page.getByTestId("more-board-pdf")).toHaveAttribute("href", `/api/tb/cases/${CID}/board-pdf`);
    await expect(page.getByRole("menuitem", { name: /slides/i })).toHaveCount(0);
    await snap(page, "casefile-menu", { sizes: LAPTOP, fullPage: false });
    expect(errors).toEqual([]);
  });

  test("the Case File before the board: Board record (PDF) waits", async ({ page }) => {
    const errors = watchConsole(page);
    const unsent = caseFileUnsent() as { case: Record<string, unknown>; state: Record<string, unknown> };
    unsent.state.board_records = [];
    unsent.case.board_record = null;
    await prepare(page, { role: "treating" });
    await routeCaseFile(page, { caseFile: unsent });
    await login(page);
    await page.goto(`/tb-nik/cases/${CID}`);
    await page.getByTestId("casefile-page").waitFor({ timeout: 20_000 });
    await page.getByTestId("more-menu").first().click();
    await expect(page.getByTestId("more-board-pdf")).toHaveAttribute("aria-disabled", "true");
    await expect(page.getByTestId("more-board-pdf")).toContainText("after the board");
    expect(errors).toEqual([]);
  });
});

