// The meeting chat (night-v3 5.3): the Chat panel's "Meeting chat" tab of the member view, with the live channel mocked so chat
// lines can be pushed. Kept with the meeting record, apart from the questions to the agents; never on the room screen.
// Run: cd web/tb-nik && npx vite build && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts meetings-chat
// Files: docs/ui/build/shots/meetings-member-chat-<theme>-<width>.png. Routes: e2e/support/f2.ts (SYNTHETIC).
import { expect, test, type Page } from "@playwright/test";
import { SIZES, login, prepare, shoot, watchConsole } from "../support/helpers";
import { CID, MID, meetingState, memberState, routeCaseFile, routeMeetings, type MeetingRouteOptions } from "../support/f2";
import type { Role } from "../support/fixtures";

const DESKTOP_MOBILE = [SIZES[0], SIZES[2]];

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

type Line = { id: string; by: string; by_name: string; text: string; at: string; case_id?: string | null };
/** HH:MM as the browser shows it (the config runs the browser in Asia/Kolkata). */
const hhmm = (iso: string) => new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" }).format(new Date(iso));
const line = (id: string, text: string, by = "joseph@vxh.example", by_name = "Thomas Joseph", case_id: string | null = CID): Line => ({ id, by, by_name, text, at: new Date().toISOString(), case_id });
const chatTab = (page: Page) => page.getByRole("tab", { name: /Meeting chat/ });
async function showChatTab(page: Page) {
  if (!(await page.getByTestId("chat-panel").isVisible().catch(() => false))) await page.getByTestId("panel-chat").click();
  if ((await chatTab(page).getAttribute("aria-selected")) !== "true") await chatTab(page).click();
  await expect(page.getByTestId("chat-list")).toBeVisible();
}

test.describe("Meeting chat", () => {
  test("member view: the lines, the badge, Enter sends, a pushed line, the shots", async ({ page }) => {
    const errors = watchConsole(page);
    const state = memberState();
    const lines = (state as { chat: Line[] }).chat;
    const live = await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state });
    // The badge before the chat was opened: one unanswered question (Q2) plus the two lines of others (C1 is mine).
    await expect(page.getByTestId("panel-chat")).toHaveAccessibleName("Chat 3");
    await page.getByTestId("panel-chat").click();
    // A question is waiting, so the panel opens on the questions; the chat tab carries its own count.
    await expect(page.getByTestId("questions-panel")).toBeVisible();
    await expect(page.getByTestId("chat-tab-unread")).toHaveText(/2/);
    await chatTab(page).click();
    const rows = page.getByTestId("chat-line");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0)).toHaveAttribute("data-mine", "true");
    await expect(rows.nth(0)).toContainText("You");
    await expect(rows.nth(0)).toContainText(hhmm(lines[0].at));
    await expect(rows.nth(1)).toContainText("Shanthi Raman");
    await expect(rows.nth(1)).toContainText(hhmm(lines[1].at));
    await expect(rows.nth(2)).toContainText("Priya Nair");
    await expect(rows.nth(2)).toContainText(lines[2].text);
    await expect(page.getByTestId("chat-list").getByRole("heading", { name: "Today" })).toBeVisible();
    await expect(page.getByText("Kept with the meeting record; not sent as a notification.")).toBeVisible();
    // Seen: the badge is back to the unanswered question once the panel closes.
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("chat-panel")).toHaveCount(0);
    await expect(page.getByTestId("panel-chat")).toHaveAccessibleName("Chat 1");
    // A pushed line while the panel is closed: counted on the button.
    live.push({ type: "chat", message: line("C4", "I can join the next case in five minutes.") });
    await expect(page.getByTestId("panel-chat")).toHaveAccessibleName("Chat 2");
    await page.getByTestId("panel-chat").click();
    await showChatTab(page);
    await expect(rows).toHaveCount(4);
    await expect(rows.nth(3)).toContainText("Thomas Joseph");
    await expect(rows.nth(3)).toContainText("I can join the next case in five minutes.");
    // A line sent on another Case File carries a small chip with the patient's initials.
    live.push({ type: "chat", message: line("C5", "Fatima's MRI is ready for the next case.", "shanthi@vxh.example", "Shanthi Raman", "TB-2026-0030") });
    await expect(rows.nth(4)).toContainText("on FB");
    await expect(rows.nth(3)).not.toContainText("on ");
    // Shift+Enter breaks the line; Enter sends {text} to the meeting's chat route.
    const box = page.locator("#meeting-chat");
    await box.click();
    await box.pressSequentially("Agree with the plan.");
    await box.press("Shift+Enter");
    await box.pressSequentially("Please add the bone scan.");
    await expect(box).toHaveValue("Agree with the plan.\nPlease add the bone scan.");
    const posted = page.waitForRequest((r) => r.url().endsWith(`/api/tb/meetings/${MID}/chat`) && r.method() === "POST");
    await box.press("Enter");
    const req = await posted;
    expect(req.postDataJSON()).toEqual({ text: "Agree with the plan.\nPlease add the bone scan." });
    await expect(box).toHaveValue("");
    // The server's line comes back on the live channel: mine, with its line break kept (the mocked refresh after the send
    // returns the fixture's three lines, so the pushed line is the last one).
    live.push({ type: "chat", message: line("C6", "Agree with the plan.\nPlease add the bone scan.", "rao@vxh.example", "Lakshmi Rao") });
    await expect(rows.last()).toHaveAttribute("data-mine", "true");
    await expect(rows.last()).toContainText("Please add the bone scan.");
    expect(await rows.last().locator("p").nth(1).evaluate((el) => (el as HTMLElement).innerText)).toBe("Agree with the plan.\nPlease add the bone scan.");
    // The counter shows from 900 characters.
    await box.fill("x".repeat(950));
    await expect(page.getByText("950 / 1000")).toBeVisible();
    await box.fill("");
    await snap(page);
    expect(errors).toEqual([]);
  });

  test("the New messages pill when scrolled up", async ({ page }) => {
    const errors = watchConsole(page);
    const many = Array.from({ length: 24 }, (_, i) => ({ ...line(`L${i}`, `Line ${i + 1} of the long chat, kept with the meeting record.`), at: new Date(Date.now() - (30 - i) * 60_000).toISOString() }));
    const live = await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: memberState({ chat: many }) });
    await page.getByTestId("panel-chat").click();
    await showChatTab(page);
    const list = page.getByTestId("chat-list");
    // Opened at the newest line.
    await expect(page.getByTestId("chat-line").last()).toBeInViewport();
    await list.evaluate((el) => { el.scrollTop = 0; el.dispatchEvent(new Event("scroll")); });
    live.push({ type: "chat", message: line("L99", "A new line while I read the older ones.") });
    await expect(page.getByTestId("chat-new-pill")).toBeVisible();
    await page.getByTestId("chat-new-pill").click();
    await expect(page.getByTestId("chat-new-pill")).toHaveCount(0);
    await expect(page.getByTestId("chat-line").last()).toBeInViewport();
    // At the bottom, the next line is followed without a pill.
    live.push({ type: "chat", message: line("L100", "And one more.") });
    await expect(page.getByTestId("chat-line").last()).toContainText("And one more.");
    await expect(page.getByTestId("chat-line").last()).toBeInViewport();
    await expect(page.getByTestId("chat-new-pill")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("the chat tab opens by itself when no question waits", async ({ page }) => {
    const errors = watchConsole(page);
    const base = memberState() as { questions: Array<{ answer: unknown }>; can: Record<string, boolean> };
    const answered = base.questions.filter((q) => q.answer);
    const live = await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: memberState({ questions: answered }) });
    await expect(page.getByTestId("panel-chat")).toHaveAccessibleName("Chat 2");
    await page.getByTestId("panel-chat").click();
    await expect(chatTab(page)).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("chat-line")).toHaveCount(3);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("panel-chat")).toHaveAccessibleName("Chat");
    // Seen lines stay seen after a reload (sessionStorage), and a new one counts again.
    await page.reload();
    await page.getByTestId("member-view").waitFor();
    await expect(page.getByTestId("panel-chat")).toHaveAccessibleName("Chat");
    live.push({ type: "chat", message: line("C4", "One more thing on this case.") });
    await expect(page.getByTestId("panel-chat")).toHaveAccessibleName("Chat 1");
    expect(errors).toEqual([]);
  });

  test("no lines yet, and a member who may not chat", async ({ page }) => {
    const errors = watchConsole(page);
    const base = memberState() as { questions: Array<{ answer: unknown }>; can: Record<string, boolean> };
    const answered = base.questions.filter((q) => q.answer);
    await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: memberState({ chat: [], questions: answered, can: { ...base.can, chat: false } }) });
    await page.getByTestId("panel-chat").click();
    await showChatTab(page);
    await expect(page.getByText("No messages yet. Meeting chat is kept with the meeting record.")).toBeVisible();
    await expect(page.getByText("Only members admitted to the meeting can chat.")).toBeVisible();
    await expect(page.getByTestId("send-chat")).toBeDisabled();
    await expect(page.locator("#meeting-chat")).toBeDisabled();
    expect(errors).toEqual([]);
  });

  test("a refused line shows the server's message", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: memberState() });
    await page.route(`**/api/tb/meetings/${MID}/chat`, (r) => r.fulfill({ status: 429, contentType: "application/json", body: JSON.stringify({ detail: { message: "Too many messages: wait a minute and send again.", code: "chat_rate" } }) }));
    await page.getByTestId("panel-chat").click();
    await showChatTab(page);
    await page.locator("#meeting-chat").fill("Is the PET-CT booked?");
    await page.getByTestId("send-chat").click();
    await expect(page.getByTestId("chat-error")).toHaveText("Too many messages: wait a minute and send again.");
    await expect(page.locator("#meeting-chat")).toHaveAttribute("aria-invalid", "true");
    await expect(page.locator("#meeting-chat")).toHaveValue("Is the PET-CT booked?");
    expect(errors).toEqual([]);
  });

  test("the room screen shows no meeting chat", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, `/meetings/${MID}/room`, { wait: "room-screen", state: meetingState("in_session") });
    await expect(page.getByRole("tab", { name: /Meeting chat/ })).toHaveCount(0);
    await expect(page.getByText("The final histopathology came in this morning")).toHaveCount(0);
    await page.keyboard.press("Control+Alt+C");
    await expect(page.getByTestId("chat-list")).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});

/** The shots of the chat tab at a laptop and a phone, light and dark (the tab is chosen again after the phone's sheet opens). */
async function snap(page: Page) {
  await shoot(page, "meetings", "member-chat", { sizes: DESKTOP_MOBILE, fullPage: false, before: async (p) => { await showChatTab(p); await p.getByTestId("chat-line").last().scrollIntoViewIfNeeded(); } });
}
