// Phone and room screen (night-v3 5.5, research/04 sections 6.4, 6.5 and 7): the member's phone (the controls fading after 4 s
// without a touch and coming back on a tap, never while a sheet is open; the decision strip on one line that opens on a tap;
// landscape with the strip at the right edge; Save data in the More sheet and the laptop More menu) and the room screen on a
// projector (1920 x 1080: large type, the compact agenda column, six remote tiles and "+3 more", nothing scrolling the page, the
// wake lock while it is open). The live channel is mocked (page.routeWebSocket).
// Run: cd web/tb-nik && npx vite build && TBNIK_MOCK=1 npx playwright test -c e2e/playwright.config.ts meetings-phone
// Files: docs/ui/build/shots/meetings-member-phone-landscape-*, meetings-member-save-data-*, meetings-room-large-dark-1920.png.
// Routes: e2e/support/f2.ts (SYNTHETIC).
import { expect, test, type Locator, type Page } from "@playwright/test";
import { SIZES, login, prepare, shoot, watchConsole } from "../support/helpers";
import { MID, meetingState, memberState, routeCaseFile, routeMeetings, type MeetingRouteOptions } from "../support/f2";
import type { Role } from "../support/fixtures";

const PHONE = { width: 390, height: 844 };
const LANDSCAPE = { width: 844, height: 390 };

/** helpers.shoot from the top of the page; a key press first so the phone's controls are shown in the picture. */
const snap: typeof shoot = (page, name, state, opts = {}) => shoot(page, name, state, { ...opts, before: async (p) => { await p.evaluate(() => window.scrollTo(0, 0)); await p.keyboard.press("Shift"); if (opts.before) await opts.before(p); } });

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

const box = async (l: Locator) => {
  const b = await l.boundingBox();
  if (!b) throw new Error("no box");
  return b;
};
const px = (l: Locator) => l.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
const noSidewaysScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

/** Seven more remote members (SYNTHETIC), so the room screen has nine remote attendees. */
const MORE_REMOTE = [
  ["meera@vxh.example", "Meera Iyer", "pathology", "Pathology"],
  ["suresh@vxh.example", "Suresh Kumar", "radiation_oncology", "Radiation Oncology"],
  ["anjali@vxh.example", "Anjali Desai", "nuclear_medicine", "Nuclear Medicine"],
  ["ravi@vxh.example", "Ravi Shankar", "surgical_oncology", "Surgical Oncology"],
  ["deepa@vxh.example", "Deepa Nair", "medical_oncology", "Medical Oncology"],
  ["arjun@vxh.example", "Arjun Reddy", "radiology", "Radiology"],
  ["kavya@vxh.example", "Kavya Menon", "palliative_care", "Palliative Care"],
].map(([user, name, department, department_name]) => ({ user, name, department, department_name, status: "remote", mode: "remote", online: true, head: false }));

test.describe("Phone and room screen", () => {
  test("phone member: the controls fade after 4 s, come back on a tap, stay while a sheet is open; the decision strip opens", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(PHONE);
    await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: memberState() });
    const frame = page.getByTestId("member-view");
    const stage = page.getByTestId("shared-screen");
    await expect(frame).toHaveAttribute("data-orientation", "portrait");
    await page.keyboard.press("Shift");
    await expect(frame).toHaveAttribute("data-controls", "shown");
    const before = await box(stage);
    // No touch for 4 s: the top bar and the bar fade; the stage keeps its place.
    await expect(frame).toHaveAttribute("data-controls", "hidden", { timeout: 8000 });
    await expect.poll(() => page.getByTestId("bar-controls").evaluate((el) => getComputedStyle(el).opacity)).toBe("0");
    await expect.poll(() => page.getByTestId("top-controls").evaluate((el) => getComputedStyle(el).opacity)).toBe("0");
    expect(await box(stage)).toEqual(before);
    // A tap on the stage brings them back.
    await page.mouse.click(before.x + before.width / 2, before.y + before.height / 2);
    await expect(frame).toHaveAttribute("data-controls", "shown");
    await expect.poll(() => page.getByTestId("bar-controls").evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
    // Not while a sheet is open: the More sheet, then the People sheet.
    await page.getByTestId("more").click();
    await expect(page.getByTestId("more-menu")).toBeVisible();
    await page.getByTestId("sheet-panel-people").click();
    await expect(page.getByTestId("people-panel")).toBeVisible();
    await page.waitForTimeout(5000);
    await expect(frame).toHaveAttribute("data-controls", "shown");
    await page.getByRole("button", { name: "Close the panel" }).click();
    await expect(page.getByTestId("people-panel")).toHaveCount(0);
    await expect(frame).toHaveAttribute("data-controls", "hidden", { timeout: 8000 });
    // The decision strip: one line; a tap opens the whole text, a second folds it.
    await page.keyboard.press("Shift");
    const strip = page.getByTestId("decision-strip-phone");
    const text = strip.getByTestId("decision-strip").locator("p");
    await expect(strip).toHaveAttribute("data-expanded", "false");
    expect(await text.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
    await page.getByTestId("decision-expand").click();
    await expect(strip).toHaveAttribute("data-expanded", "true");
    expect(await text.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    await expect(page.getByTestId("decision-expand")).toHaveAttribute("aria-expanded", "true");
    await page.getByTestId("decision-expand").click();
    await expect(strip).toHaveAttribute("data-expanded", "false");
    expect(await noSidewaysScroll(page)).toBe(true);
    expect(errors).toEqual([]);
  });

  test("phone member: landscape with the strip at the right; Save data in the More sheet and the laptop menu", async ({ page }) => {
    const errors = watchConsole(page);
    await page.setViewportSize(LANDSCAPE);
    await open(page, `/meetings/${MID}/member`, { role: "treating", wait: "member-view", state: memberState() });
    const frame = page.getByTestId("member-view");
    await expect(frame).toHaveAttribute("data-orientation", "landscape");
    const stage = await box(page.getByTestId("shared-screen"));
    const column = page.getByTestId("landscape-strip");
    await expect(column.getByTestId("tile-grid")).toHaveAttribute("data-orientation", "column");
    const strip = await box(column);
    expect(strip.x, "the strip sits right of the stage").toBeGreaterThanOrEqual(stage.x + stage.width);
    expect(strip.x + strip.width).toBeLessThanOrEqual(LANDSCAPE.width);
    expect(stage.height, "the stage is never taller than 16:10").toBeLessThanOrEqual(stage.width * 10 / 16 + 1);
    expect(stage.height).toBeGreaterThan(120);
    expect(await noSidewaysScroll(page)).toBe(true);
    expect(await frame.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true);
    await snap(page, "meetings", "member-phone-landscape", { sizes: [LANDSCAPE], fullPage: false });
    // Save data: camera off and the lower quality, remembered for this tab.
    await page.setViewportSize(PHONE);
    await page.getByTestId("more").click();
    const save = page.getByTestId("save-data");
    await expect(save).toHaveAttribute("aria-pressed", "false");
    await save.click();
    await expect(save).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("save-data-note")).toHaveText("Your camera stays off and the stage stays at the lower quality, to use less mobile data.");
    expect(await page.evaluate(() => sessionStorage.getItem("tbnik.call.savedata"))).toBe("on");
    await snap(page, "meetings", "member-save-data", { sizes: [PHONE], fullPage: false });
    await page.reload();
    await page.getByTestId("member-view").waitFor();
    await page.getByTestId("more").click();
    await expect(page.getByTestId("save-data")).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "Close", exact: true }).click();
    // The laptop More menu has it too.
    await page.setViewportSize(SIZES[0]);
    await page.getByTestId("more").click();
    await expect(page.getByTestId("save-data")).toHaveAttribute("aria-checked", "true");
    await page.getByTestId("save-data").click();
    await expect(page.getByTestId("save-data")).toHaveAttribute("aria-checked", "false");
    expect(await page.evaluate(() => sessionStorage.getItem("tbnik.call.savedata"))).toBeNull();
    // A laptop never fades its controls.
    await page.keyboard.press("Escape");
    await page.waitForTimeout(4500);
    await expect(frame).toHaveAttribute("data-controls", "shown");
    expect(errors).toEqual([]);
  });

  test("room screen on a projector: large type, the agenda column, six tiles and +2 more, no page scroll, the wake lock", async ({ page }) => {
    const errors = watchConsole(page);
    // The wake lock as the browser would give it, counted.
    await page.addInitScript(() => {
      const w = window as unknown as { __wake: { asked: string[]; released: number } };
      w.__wake = { asked: [], released: 0 };
      Object.defineProperty(navigator, "wakeLock", { configurable: true, value: { request: async (type: string) => { w.__wake.asked.push(type); return { release: async () => { w.__wake.released += 1; } }; } } });
    });
    await page.setViewportSize(SIZES[1]);
    const base = meetingState("in_session");
    const state = meetingState("in_session", { attendance: [...(base.attendance as object[]), ...MORE_REMOTE] });
    await open(page, `/meetings/${MID}/room`, { wait: "room-screen", state });
    const frame = page.getByTestId("room-screen");
    await expect(page.getByTestId("room-summary")).toBeVisible();
    // Nine remote members, one of them offline and out of the video (no tile, night-v3 5.6): six tiles and "+2 more" (never a
    // scroll); the agents apart.
    const people = page.getByTestId("room-people");
    await expect(people.getByTestId("tile")).toHaveCount(6);
    await expect(people.getByTestId("strip-more")).toHaveText("+2 more");
    await expect(people.getByRole("heading", { name: "Remote (8)" })).toBeVisible();
    await expect(people.getByTestId("agent-tile")).toHaveCount(2);
    expect(await people.evaluate((el) => el.scrollHeight <= el.clientHeight + 1), "the remote column fits without clipping").toBe(true);
    expect(await px(people.getByTestId("tile-name").first())).toBeGreaterThanOrEqual(20);
    // The agenda column: numbers, patient lines, Done or Now words, 20 px, no click; the current case is Now.
    const rail = page.getByTestId("agenda-rail");
    await expect(rail).toHaveAttribute("data-look", "room");
    await expect(rail).toHaveAttribute("data-open", "true");
    const now = rail.locator("li[data-state=now]");
    await expect(now).toContainText("Now");
    await expect(now).toContainText("Priya Venkatesan");
    expect(await px(now)).toBeGreaterThanOrEqual(20);
    await expect(rail.locator("button")).toHaveCount(0);
    // The decision strip at 28 px; the stage text at 28 px or more (the source chips apart).
    expect(await px(page.getByTestId("decision-strip").locator("p"))).toBeGreaterThanOrEqual(28);
    const stageSizes = await page.getByTestId("shared-screen").evaluate((el) => {
      const out: number[] = [];
      el.querySelectorAll(".stage-slide *").forEach((n) => {
        if (n.closest(".quote-chip")) return;
        const own = [...n.childNodes].some((c) => c.nodeType === Node.TEXT_NODE && (c.textContent ?? "").trim());
        if (own) out.push(parseFloat(getComputedStyle(n).fontSize));
      });
      return out;
    });
    expect(stageSizes.length).toBeGreaterThan(3);
    expect(Math.min(...stageSizes)).toBeGreaterThanOrEqual(28);
    // The hands by name; the agent voices chip.
    await expect(page.getByTestId("room-hands")).toContainText("Shanthi Raman");
    await expect(page.getByTestId("agent-voices")).toBeVisible();
    // Nothing scrolls the page.
    expect(await frame.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight)).toBe(true);
    // Contrast on the dark stage: the room's quieter words keep 7:1 or more.
    const ratios = await page.evaluate(() => {
      const cv = document.createElement("canvas").getContext("2d")!;
      const rgba = (c: string) => { cv.clearRect(0, 0, 1, 1); cv.fillStyle = "#000"; cv.fillStyle = c; cv.fillRect(0, 0, 1, 1); return [...cv.getImageData(0, 0, 1, 1).data]; };
      const bgOf = (el: Element): number[] => {
        for (let e: Element | null = el; e; e = e.parentElement) { const b = rgba(getComputedStyle(e).backgroundColor); if (b[3] > 0) return b; }
        return [11, 15, 20, 255];
      };
      const lum = (c: number[]) => { const f = (v: number) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
      const ratio = (el: Element) => {
        const bg = bgOf(el);
        cv.clearRect(0, 0, 1, 1); cv.fillStyle = `rgb(${bg[0]},${bg[1]},${bg[2]})`; cv.fillRect(0, 0, 1, 1); cv.fillStyle = getComputedStyle(el).color; cv.fillRect(0, 0, 1, 1);
        const fg = [...cv.getImageData(0, 0, 1, 1).data];
        const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
        return (a + 0.05) / (b + 0.05);
      };
      const hasText = (el: Element) => [...el.childNodes].some((c) => c.nodeType === Node.TEXT_NODE && (c.textContent ?? "").trim());
      return [...document.querySelectorAll("[data-testid=room-row-word], [data-testid=strip-more], [data-testid=room-count], [data-testid=agent-tile] span")].filter(hasText).map(ratio);
    });
    expect(ratios.length).toBeGreaterThan(3);
    expect(Math.min(...ratios)).toBeGreaterThanOrEqual(7);
    // The wake lock while the room screen is open.
    expect(await page.evaluate(() => (window as unknown as { __wake: { asked: string[] } }).__wake.asked)).toContain("screen");
    await snap(page, "meetings", "room-large", { sizes: [SIZES[1]], themes: ["dark"], fullPage: false });
    // Under 1600 px the agenda folds to the numbers.
    await page.setViewportSize(SIZES[0]);
    await expect(rail).toHaveAttribute("data-open", "false");
    expect(await frame.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true);
    // Closing the room screen releases the wake lock.
    await page.getByRole("link", { name: "Close the room screen" }).click();
    await expect(frame).toHaveCount(0);
    await expect.poll(() => page.evaluate(() => (window as unknown as { __wake: { released: number } }).__wake.released)).toBeGreaterThanOrEqual(1);
    expect(errors).toEqual([]);
  });
});
