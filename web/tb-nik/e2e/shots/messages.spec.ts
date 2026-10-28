// Messages (night-v3 item 8.4): the list and a thread, the first-use notice, the New message finder, the composer with a Case
// File chip and the soft patient-number warning, edit / react / delete, @ mentions, the phone layout and the not-placed page.
// Mock mode only (the routes and the socket come from e2e/support/messages_mock.ts, SYNTHETIC).
// Run: cd web/tb-nik && npx tsc -b --noEmit && npx vite build && LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib TBNIK_MOCK=1 \
//   TBNIK_SHOTS=/data/vaidyx/night-v3/shots/phase8_mock npx playwright test -c e2e/playwright.config.ts messages
// Files: messages-<state>-<theme>-<width>.png (states: list, thread, notice, finder, composer).
import { expect, test, type Page } from "@playwright/test";
import { MOCK, SIZES, login, prepare, shoot, watchConsole } from "../support/helpers";
import { C_DEPT_MINE, C_DIRECT, routeMessages, type MessagesMockOptions } from "../support/messages_mock";
import type { Role } from "../support/fixtures";

const DM = [SIZES[0], SIZES[2]];
const PHONE = SIZES[2];

test.skip(!MOCK, "Messages screens are checked against the mock (TBNIK_MOCK=1)");

async function open(page: Page, to: string, o: MessagesMockOptions & { role?: Role; wait?: string } = {}) {
  await prepare(page, { role: o.role ?? "treating" });
  const live = await routeMessages(page, o);
  await login(page);
  await page.goto(`/tb-nik${to}`);
  if (o.wait) await page.getByTestId(o.wait).first().waitFor({ timeout: 20_000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  return live;
}

/** After a route change: the shell fades the old page out while its Outlet already shows the new route, so wait for the new
 *  copy before clicking (a click on the fading copy is lost with it). */
async function settled(page: Page) {
  await page.waitForTimeout(600);
}

async function noSideways(page: Page) {
  const extra = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(extra).toBeLessThanOrEqual(1);
}

const typingEvent = { type: "typing", conversation_id: C_DIRECT, by: "ravi@vxh.example", by_name: "Dr Ravi Kumar" };

test.describe("Messages", () => {
  test("the list, the filters and a thread", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, "/messages", { wait: "conversation-list" });
    const rows = page.getByTestId("conversation-row");
    await expect(rows).toHaveCount(4);
    await expect(rows.nth(0)).toHaveAttribute("data-unread", "true");
    await expect(rows.nth(0)).toContainText("Dr Ravi Kumar");
    await expect(rows.nth(0).getByLabel("2 unread")).toHaveText("2");
    await expect(rows.nth(1)).toContainText("Dr Meena Iyer");
    await expect(rows.nth(1)).toContainText("Resolved");
    await expect(rows.nth(2)).toContainText("Radiology");
    await expect(rows.nth(2)).toContainText("Reaches 6 people");
    await expect(rows.nth(3)).toContainText("Breast Surgery");
    await expect(rows.nth(3)).toContainText("From Dr Anil Verma");
    await expect(rows.nth(3).getByLabel("Muted")).toBeVisible();
    await expect(page.getByTestId("no-conversation")).toContainText("Choose a conversation");

    await page.getByTestId("filter-unread").click();
    await expect(rows).toHaveCount(1);
    await page.getByTestId("filter-resolved").click();
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText("Dr Meena Iyer");
    await page.getByTestId("filter-all").click();
    await expect(rows).toHaveCount(4);

    // A word search: the list narrows and the hits in the messages show below.
    await page.getByRole("searchbox", { name: "Find a person, a department or a word" }).fill("mammogram");
    await expect(page.getByTestId("search-hits")).toContainText("Radiology");
    await page.getByRole("searchbox", { name: "Find a person, a department or a word" }).fill("");
    await expect(rows).toHaveCount(4);

    await shoot(page, "messages", "list", { sizes: DM, fullPage: false });
    await page.setViewportSize(SIZES[0]);

    await rows.first().getByRole("link").click();
    await expect(page).toHaveURL(new RegExp(`/messages/${C_DIRECT}$`));
    await settled(page);
    const thread = page.getByTestId("thread");
    await expect(thread).toBeVisible();
    const msgs = thread.getByTestId("message");
    await expect(msgs).toHaveCount(6);
    await expect(msgs.nth(0)).toHaveAttribute("data-mine", "true");
    await expect(msgs.nth(1)).toHaveAttribute("data-mine", "false");
    await expect(msgs.nth(1)).toContainText("edited");
    await expect(msgs.nth(2)).toContainText("This message was deleted");
    await expect(msgs.nth(0).getByTestId("chip")).toHaveText(/Case File: TB-2026-0031, Breast cancer/);
    await expect(msgs.nth(0).getByTestId("chip")).toHaveAttribute("href", "/tb-nik/cases/TB-2026-0031");
    await expect(msgs.nth(4).getByTestId("chip")).toContainText("A Case File you cannot open");
    await expect(msgs.nth(4).getByTestId("chip-offer")).toHaveAttribute("href", "/tb-nik/cases/TB-2026-0027");
    await expect(msgs.nth(3).getByTestId("seen")).toHaveText("Seen");
    await expect(msgs.nth(0).getByTestId("reactions")).toBeVisible();
    await expect(thread).toContainText("Online");
    await expect(page.getByTestId("resolve")).toHaveText(/Mark as resolved/);
    await expect(page.getByTestId("mute")).toHaveText(/Mute/);
    await expect(page.getByTestId("composer")).toContainText("Do not type patient names or numbers here. Attach the Case File. Decisions go in the Case File.");

    // Read up to the last message once the thread is open; the row loses its unread mark.
    await expect.poll(() => live.sent().some((s) => s.path === `/api/tb/messages/conversations/${C_DIRECT}/read` && (s.body as { seq?: number }).seq === 6)).toBe(true);
    await expect(page.getByTestId("conversation-row").first()).toHaveAttribute("data-unread", "false");
    await expect(page.getByTestId("conversation-row").first()).toHaveAttribute("data-active", "true");

    // "is typing" from the socket, gone after 4 seconds.
    live.push(typingEvent);
    await expect(page.getByTestId("typing")).toHaveText("Dr Ravi Kumar is typing");
    await expect(page.getByTestId("typing")).toHaveCount(0, { timeout: 6000 });

    // Resolve and reopen; mute and unmute.
    await page.getByTestId("resolve").click();
    await expect(page.getByTestId("resolve")).toHaveText(/Reopen/);
    await page.getByTestId("resolve").click();
    await expect(page.getByTestId("resolve")).toHaveText(/Mark as resolved/);
    await page.getByTestId("mute").click();
    await expect(page.getByTestId("mute")).toHaveText(/Unmute/);
    await page.getByTestId("mute").click();
    await expect(page.getByTestId("mute")).toHaveText(/^Mute$/);

    await shoot(page, "messages", "thread", { sizes: DM, fullPage: false, before: async (p) => { live.push(typingEvent); await p.getByTestId("typing").waitFor(); } });
    await noSideways(page);
    expect(errors).toEqual([]);
  });

  test("the first-use notice", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, `/messages/${C_DIRECT}`, { wait: "thread", noticeSeen: false });
    const notice = page.getByTestId("notice");
    await expect(notice).toContainText("Messages are for work between the staff of this hospital.");
    await expect(notice).toContainText("kept for 365 days after the last message");
    await expect(notice).toContainText("Ask the MDT Coordinator to have a message removed.");
    await shoot(page, "messages", "notice", { sizes: DM, fullPage: false });
    await page.setViewportSize(SIZES[0]);
    await notice.getByRole("button", { name: "Got it" }).click();
    await expect(notice).toHaveCount(0);
    expect(live.sent().some((s) => s.path === "/api/tb/messages/notice")).toBe(true);
    expect(errors).toEqual([]);
  });

  test("the New message finder", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, "/messages", { wait: "conversation-list" });
    await page.getByTestId("new-message").click();
    const finder = page.getByTestId("directory-picker");
    await expect(finder).toBeVisible();
    await expect(finder.getByTestId("directory-coordinator")).toContainText("MDT Coordinator");
    await expect(finder.getByTestId("directory-person")).toHaveCount(6);  // me left out
    await expect(finder.getByTestId("directory-department")).toHaveCount(4);
    await expect(finder.getByTestId("directory-department").filter({ hasText: "Radiology" })).toHaveText(/Radiology, 6 people/);
    await shoot(page, "messages", "finder", { sizes: DM, fullPage: false });
    await page.setViewportSize(SIZES[0]);
    await finder.getByRole("searchbox").fill("rad");
    await expect(finder.getByTestId("directory-person")).toHaveCount(2);
    await expect(finder.getByTestId("directory-department")).toHaveCount(1);
    // A person I already write to: straight to that conversation.
    await finder.getByTestId("directory-person").filter({ hasText: "Dr Ravi Kumar" }).click();
    await expect(page).toHaveURL(new RegExp(`/messages/${C_DIRECT}$`));
    await expect(page.getByTestId("thread")).toBeVisible();
    await settled(page);
    // A person with no conversation yet: the composer against them.
    await page.getByTestId("new-message").click();
    await page.getByTestId("directory-picker").getByTestId("directory-person").filter({ hasText: "Dr Anil Verma" }).click();
    await expect(page).toHaveURL(/\/messages\/new\?to=verma%40vxh\.example$/);
    await expect(page.getByTestId("thread")).toContainText("Dr Anil Verma");
    await expect(page.getByTestId("composer")).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("the composer: a Case File chip, the soft warning, send, edit, react, delete", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, "/messages/new?to=verma%40vxh.example&case=TB-2026-0031", { wait: "composer" });
    await expect(page.getByTestId("composer-chip")).toHaveText(/Case File: TB-2026-0031, Breast cancer/);
    const box = page.getByTestId("composer-input");
    await box.fill("Please see VXH/2026/000123 before Thursday.");
    await box.press("Enter");
    await expect(page.getByTestId("number-warning")).toContainText("This looks like a patient number. Attach the Case File instead?");
    expect(live.sent().filter((s) => s.method === "POST" && s.path === "/api/tb/messages/conversations")).toHaveLength(0);
    await shoot(page, "messages", "composer", { sizes: DM, fullPage: false });
    await page.setViewportSize(SIZES[0]);
    // The Case File picker lists only what I may attach.
    await page.getByTestId("add-case-file").click();
    await expect(page.getByTestId("link-picker").getByTestId("link-option")).toHaveCount(5);
    await page.keyboard.press("Escape");
    await page.getByTestId("send-anyway").click();
    await expect(page).toHaveURL(/\/messages\/C0000000005$/);
    await settled(page);
    const start = live.sent().find((s) => s.path === "/api/tb/messages/conversations");
    expect(start?.body).toMatchObject({ to: { user: "verma@vxh.example" }, link: { type: "case", id: "TB-2026-0031" } });
    const mine = page.getByTestId("message").last();
    await expect(mine).toHaveAttribute("data-mine", "true");
    await expect(mine.getByTestId("chip")).toHaveText(/Case File: TB-2026-0031/);

    // Edit within the 10 minutes.
    await mine.hover();
    await mine.getByTestId("message-menu").click();
    await expect(page.getByText(/You can edit for (9|10) more minutes/)).toBeVisible();
    await page.getByTestId("edit-message").click();
    await mine.getByTestId("edit-input").fill("Please see the Case File before Thursday.");
    await mine.getByTestId("edit-save").click();
    await expect(mine).toContainText("edited");
    await expect(mine).toContainText("Please see the Case File before Thursday.");
    // React, then take it back.
    await mine.hover();
    await mine.getByTestId("message-menu").click();
    await page.getByTestId("react-will_do").click();
    await expect(mine.getByTestId("reactions")).toContainText("Will do");
    await mine.getByTestId("reactions").getByRole("button").click();
    await expect(mine.getByTestId("reactions")).toHaveCount(0);
    // Delete.
    await mine.hover();
    await mine.getByTestId("message-menu").click();
    await page.getByTestId("delete-message").click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
    await expect(mine).toContainText("This message was deleted");
    expect(errors).toEqual([]);
  });

  test("@ mentions of the readers", async ({ page }) => {
    const errors = watchConsole(page);
    const live = await open(page, `/messages/${C_DEPT_MINE}`, { wait: "composer" });
    const box = page.getByTestId("composer-input");
    await box.pressSequentially("Thanks @Sur");
    await expect(page.getByTestId("mention-list")).toContainText("Dr Suresh Menon");
    await box.press("Enter");
    await expect(box).toHaveValue("Thanks @Dr Suresh Menon ");
    await box.pressSequentially("noted.");
    await box.press("Enter");
    await expect(page.getByTestId("message").last()).toContainText("Thanks @Dr Suresh Menon noted.");
    const sent = live.sent().find((s) => s.path === `/api/tb/messages/conversations/${C_DEPT_MINE}/messages`);
    expect(sent?.body).toMatchObject({ mentions: ["menon@vxh.example"] });
    expect(errors).toEqual([]);
  });

  test("too many messages: the server's words", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, `/messages/${C_DIRECT}`, { wait: "composer", rateLimited: true });
    await page.getByTestId("composer-input").fill("Hello");
    await page.getByTestId("send").click();
    await expect(page.getByText("Too many messages. Please wait a moment.").first()).toBeVisible();
    await expect(page.getByTestId("composer-input")).toHaveValue("Hello");
    expect(errors).toEqual([]);
  });

  test("phone: the list, then the thread full screen above the Dock", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(PHONE);
    await open(page, "/messages", { wait: "conversation-list" });
    await expect(page.getByTestId("thread")).toHaveCount(0);
    await noSideways(page);
    await page.getByTestId("conversation-row").first().getByRole("link").click();
    await expect(page.getByTestId("thread")).toBeVisible();
    await expect(page.getByTestId("conversation-list")).toHaveCount(0);
    await settled(page);
    const send = await page.getByTestId("send").boundingBox();
    expect(send).not.toBeNull();
    // The composer sits above the Dock (about 72 px high at the bottom).
    expect((send?.y ?? 0) + (send?.height ?? 0)).toBeLessThan(PHONE.height - 72);
    await noSideways(page);
    await page.getByTestId("thread").getByRole("link", { name: "Messages" }).click();
    await expect(page.getByTestId("conversation-list")).toBeVisible();
    await settled(page);
    // The finder is a full-height sheet on a phone.
    await page.getByTestId("new-message").click();
    const box = await page.getByTestId("directory-picker").boundingBox();
    expect(box?.height ?? 0).toBeGreaterThan(PHONE.height - 4);
    expect(errors).toEqual([]);
  });

  test("no Messages icon or socket for a root admin", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, "/cases", { role: "root_admin" });
    await page.waitForTimeout(500);
    await expect(page.getByTestId("messages-nav")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("a message that looks like HTML shows as text", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, `/messages/${C_DIRECT}`, { wait: "composer-input" });
    await page.getByTestId("composer-input").fill("<b>not bold</b> <img src=x onerror=alert(1)>");
    await page.getByTestId("send").click();
    const mine = page.locator('[data-testid="message"][data-mine="true"]').last();
    await expect(mine).toContainText("<b>not bold</b>");
    await expect(mine.locator("b, img")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("not placed: the page says so", async ({ page }) => {
    const errors = watchConsole(page);
    await open(page, "/messages", { role: "root_admin", wait: "messages-page" });
    await expect(page.getByTestId("messages-page")).toContainText("Messages are for placed hospital staff.");
    await expect(page.getByTestId("conversation-list")).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});
