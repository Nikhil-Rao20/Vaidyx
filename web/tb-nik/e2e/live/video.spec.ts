// Two people in one meeting, live: the MDT Coordinator (tb-mdt) conducts, a doctor (tb-rad-doc) joins with the code, both arrive
// through the pre-join screen with Chromium's fake camera and microphone, and each sees the other's tile. Synthetic data only: a
// throw-away meeting with Kavitha's synthetic Case File on the noting list; cancelled at the end. Screenshots go to
// docs/ui/build/shots/live-*.png. Present a screen (night-v3 5.2): Chromium picks the screen itself (the flags in
// playwright.live.config.ts), the other person sees it on the stage; one presenter at a time.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

const SHOTS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../../docs/ui/build/shots");
const CASE = process.env.TBNIK_LIVE_CASE || "TB-2026-0001";

function logins(): Record<string, string> {
  const file = process.env.TBNIK_LOGINS || path.join(os.homedir(), "vaidyx", ".tb_v2_demo_logins");
  const out: Record<string, string> = {};
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    const [user, password] = line.split("\t");
    if (user && password) out[user.trim()] = password;
  }
  return out;
}

async function signedIn(browser: Browser, user: string, password: string): Promise<{ page: Page; api: APIRequestContext }> {
  const ctx = await browser.newContext({ permissions: ["camera", "microphone"] });
  const page = await ctx.newPage();
  const r = await page.request.post("/api/auth/login", { data: { username: user, password, remember: false }, headers: { "X-Requested-With": "tb-nik" } });
  if (!r.ok()) throw new Error(`Sign-in failed for ${user}: HTTP ${r.status()}`);
  return { page, api: page.request };
}

async function shot(page: Page, name: string) {
  fs.mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `live-${name}.png`), fullPage: false });
}

test("two people in a meeting with video", async ({ browser }) => {
  const pw = logins();
  expect(pw["tb-mdt"], "tb-mdt login").toBeTruthy();
  expect(pw["tb-rad-doc"], "tb-rad-doc login").toBeTruthy();
  const mdt = await signedIn(browser, "tb-mdt", pw["tb-mdt"]);
  const doc = await signedIn(browser, "tb-rad-doc", pw["tb-rad-doc"]);
  const status = await (await mdt.api.get("/api/tb/video/status")).json();
  test.skip(!status.enabled, "video is not set up on this server");

  // a throw-away meeting, today, video on, the synthetic Case File for noting
  const today = new Date().toISOString().slice(0, 10);
  const created = await (await mdt.api.post("/api/tb/meetings", { data: { date: today, time: "23:45", room: "Live check (synthetic)", video: true, minutes_per_case: 5 } })).json();
  const mid: string = created.meeting?.id ?? created.id;
  expect(mid).toBeTruthy();
  try {
    const added = await mdt.api.post(`/api/tb/meetings/${mid}/agenda/add`, { data: { case_id: CASE, list: "noting" } });
    expect(added.ok(), await added.text()).toBeTruthy();
    const code = (await (await mdt.api.post(`/api/tb/meetings/${mid}/code`, { data: {} })).json()).value;
    const joined = await (await doc.api.post("/api/tb/meetings/join", { data: { code } })).json();
    expect(joined.status).toBe("waiting");
    expect((await mdt.api.post(`/api/tb/meetings/${mid}/admit`, { data: { user: "tb-rad-doc" } })).ok()).toBeTruthy();
    expect((await mdt.api.post(`/api/tb/meetings/${mid}/start`, { data: {} })).ok()).toBeTruthy();
    expect((await mdt.api.post(`/api/tb/meetings/${mid}/current`, { data: { case_id: CASE } })).ok()).toBeTruthy();

    // the coordinator: pre-join, then the conduct view with a camera
    await mdt.page.goto(`/tb-nik/meetings/${mid}`);
    await mdt.page.getByTestId("prejoin").waitFor({ timeout: 30_000 });
    await shot(mdt.page, "prejoin-coordinator");
    await mdt.page.getByTestId("prejoin-join").click();
    await mdt.page.getByTestId("control-view").waitFor({ timeout: 30_000 });

    // the doctor: pre-join, then the member view
    await doc.page.goto(`/tb-nik/meetings/${mid}/member`);
    await doc.page.getByTestId("prejoin").waitFor({ timeout: 30_000 });
    await doc.page.getByTestId("prejoin-join").click();
    await doc.page.getByTestId("member-view").waitFor({ timeout: 30_000 });
    await expect(doc.page.getByTestId("member-view")).toHaveAttribute("data-video-status", "connected", { timeout: 40_000 });

    // each sees the other's tile with a camera (a video element inside the tile)
    await expect(doc.page.locator('[data-testid="tile"][data-user="tb-mdt"] video:visible').first()).toBeVisible({ timeout: 40_000 });
    await expect(mdt.page.locator('[data-testid="tile"][data-user="tb-rad-doc"] video:visible').first()).toBeVisible({ timeout: 40_000 });
    await doc.page.waitForTimeout(1500);
    await shot(doc.page, "member-in-call");
    await shot(mdt.page, "conduct-in-call");

    // the doctor raises a hand; the coordinator sees it
    await doc.page.getByTestId("raise-hand").click();
    await expect(mdt.page.locator('[data-testid="tile"][data-user="tb-rad-doc"]')).toContainText("", { timeout: 10_000 });
    await mdt.page.getByTestId("panel-people").click();  // night-v3 5.1: the People panel opens from the bar
    await expect(mdt.page.getByTestId("person-row").filter({ hasText: "Dr Radiology" })).toBeVisible();
    await shot(mdt.page, "conduct-people");
    await mdt.page.getByTestId("panel-people").click();

    // Present a screen: the coordinator presents, the doctor sees the picture on the stage and may not present yet
    const docStage = doc.page.getByTestId("shared-screen");
    const mdtStage = mdt.page.getByTestId("shared-screen");
    const sharePicture = async (page: Page) => {
      await expect(page.getByTestId("shared-screen")).toHaveAttribute("data-stage", "share", { timeout: 40_000 });
      await expect.poll(async () => page.getByTestId("stage-share").locator("video").first().evaluate((v: HTMLVideoElement) => v.videoWidth).catch(() => 0), { timeout: 30_000 }).toBeGreaterThan(0);
    };
    const present = async (page: Page) => {
      await expect(page.getByTestId("present")).toBeEnabled({ timeout: 20_000 });
      await page.getByTestId("present").click();
      const ask = page.getByTestId("present-dialog");
      if (await ask.isVisible({ timeout: 3_000 }).catch(() => false)) await page.getByTestId("present-share").click();
      await expect(page.getByTestId("present")).toHaveAttribute("aria-pressed", "true", { timeout: 20_000 });
    };
    await expect(doc.page.getByTestId("present")).toBeDisabled();
    await present(mdt.page);
    await expect(mdt.page.getByTestId("presenting-bar")).toBeVisible();
    await expect(mdtStage).toHaveAttribute("data-stage", "share-self", { timeout: 20_000 });
    await sharePicture(doc.page);
    await expect(doc.page.getByTestId("share-badge")).toContainText("MDT Coordinator (demo) is presenting");
    await expect(doc.page.getByTestId("present")).toBeDisabled();
    await expect(doc.page.getByTestId("present")).toHaveAttribute("title", "Ask the MDT Coordinator to allow you to present");
    await doc.page.waitForTimeout(1000);
    await shot(doc.page, "member-sees-share");
    await shot(mdt.page, "conduct-presenting");

    // the coordinator allows the doctor, who presents: the coordinator's share stops and the stage names the doctor
    const allow = await mdt.api.post(`/api/tb/meetings/${mid}/present-allow`, { data: { user: "tb-rad-doc", allowed: true } });
    expect(allow.ok(), await allow.text()).toBeTruthy();
    await present(doc.page);
    await expect(mdt.page.getByTestId("present")).toHaveAttribute("aria-pressed", "false", { timeout: 20_000 });
    await expect(mdt.page.getByTestId("presenting-bar")).toHaveCount(0);
    await sharePicture(mdt.page);
    await expect(mdt.page.getByTestId("share-badge")).toContainText("Dr Radiology");
    await expect(mdt.page.getByTestId("share-stop")).toBeVisible();  // the coordinator may stop anyone's share
    await shot(mdt.page, "conduct-sees-share");

    // the doctor stops: both stages show the slide again
    await doc.page.getByTestId("stop-presenting").click();
    await expect(doc.page.getByTestId("present")).toHaveAttribute("aria-pressed", "false", { timeout: 20_000 });
    await expect(docStage).toHaveAttribute("data-stage", "slide", { timeout: 20_000 });
    await expect(mdtStage).toHaveAttribute("data-stage", "slide", { timeout: 20_000 });

    // the room screen joins under its own identity and shows the remote doctor
    const room = await mdt.page.context().newPage();
    await room.goto(`/tb-nik/meetings/${mid}/room`);
    await room.getByTestId("room-screen").waitFor({ timeout: 30_000 });
    await expect(room.locator('[data-testid="tile"][data-user="tb-rad-doc"]:visible').first()).toBeVisible({ timeout: 40_000 });
    await room.waitForTimeout(1500);
    await shot(room, "room-in-call");
    await room.close();
  } finally {
    await mdt.api.post(`/api/tb/meetings/${mid}/end`, { data: {} }).catch(() => undefined);
    await mdt.api.post(`/api/tb/meetings/${mid}/cancel`, { data: { reason: "live check (synthetic)" } }).catch(() => undefined);
    await mdt.page.context().close();
    await doc.page.context().close();
  }
});
