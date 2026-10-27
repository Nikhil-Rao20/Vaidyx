// Phase 5 real-screen check (night-v3 5.6): the meeting call on the running app with the demo logins (read in code, never printed)
// and Chromium's fake camera and microphone, in a throw-away synthetic meeting (TB-2026-0001 and one more synthetic Case File; never a
// real one): the member tb-rad-doc, the MDT Coordinator tb-mdt, a third login waiting to be admitted, and the room screen. Laptop
// 1366 x 768 and phone 390 x 844 in light and dark, the room at 1920 x 1080 dark. Shots go to /data/vaidyx/night-v3/shots/phase5/ as
// real-<role>-call-<state>-<theme>-<width>.png; page errors and sideways scroll go to findings.txt there. The meeting is cancelled (or
// ended) at the end. The join route allows 5 tries per 15 minutes per login, and this script uses one for tb-rad-doc and one for the
// third login. Run alone (LiveKit on :7880 and the app on :7000 must be running):
//   node docs/night-v3/tools/phase5_real_check.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium, request } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";

const BASE = process.env.TBNIK_BASE_URL || "http://127.0.0.1:7000";
const OUT = "/data/vaidyx/night-v3/shots/phase5";
const CASE = "TB-2026-0001";
const SYNTHETIC = /^TB-2026-\d{4}$/;  // the synthetic Case Files of the demo; the real case never matches
const MEMBER = "tb-rad-doc";
const MDT = "tb-mdt";
const THIRD_CHOICES = ["tb-path-doc", "tb-path-head", "tb-medonc-doc", "tb-breast-doc"];
const H = { "X-Requested-With": "tb-nik" };
fs.mkdirSync(OUT, { recursive: true });
const logins = Object.fromEntries(fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")
  .filter((l) => l.includes("\t") && !l.startsWith("#")).map((l) => l.split("\t")).map((c) => [c[0].trim(), c[1]]));
const THIRD = THIRD_CHOICES.find((u) => logins[u]);
const findings = [];
const shots = [];
const note = (t) => { findings.push(t); console.log(t); };

const LAPTOP = { width: 1366, height: 768 };
const PHONE = { width: 390, height: 844 };
const ROOM = { width: 1920, height: 1080 };
const VIEWS = [[LAPTOP, "light"], [LAPTOP, "dark"], [PHONE, "light"], [PHONE, "dark"]];

const browser = await chromium.launch({
  headless: true,
  args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"],
});

/** A signed-in API client for a login (the cookies are reused by every page of that login). */
async function apiFor(user) {
  const api = await request.newContext({ baseURL: BASE, extraHTTPHeaders: H });
  const r = await api.post("/api/auth/login", { data: { username: user, password: logins[user], remember: true } });
  if (!r.ok()) throw new Error(`sign-in ${user}: HTTP ${r.status()}`);
  return { api, state: await api.storageState() };
}

/** A page for a login at a size and theme; page errors, console errors and failed API calls are noted. */
async function open(who, vp, scheme, label) {
  const ctx = await browser.newContext({ viewport: vp, colorScheme: scheme, locale: "en-IN", timezoneId: "Asia/Kolkata", reducedMotion: "reduce",
    storageState: who.state, permissions: ["camera", "microphone"], baseURL: BASE });
  // the app keeps the theme in localStorage (lib/appearance.ts), not in the browser's colour scheme
  await ctx.addInitScript((t) => { try { localStorage.setItem("tbnik.theme", t); } catch { /* no storage */ } }, scheme);
  ctx.setDefaultTimeout(10_000);  // the app answers in under a second; a missing element fails the step, never the whole run
  const page = await ctx.newPage();
  const tag = `${label} ${scheme}-${vp.width}`;
  page.on("pageerror", (e) => note(`${tag}: page error ${e.message.split("\n")[0].slice(0, 200)}`));
  page.on("console", (m) => { if (m.type() === "error" && !/favicon|net::ERR_ABORTED|Failed to load resource/.test(m.text())) note(`${tag}: console ${m.text().slice(0, 200)}`); });
  page.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 500) note(`${tag}: HTTP ${r.status()} ${r.url().replace(BASE, "")}`); });
  return { ctx, page, close: () => ctx.close() };
}

async function shot(page, role, state, scheme, width) {
  // the signed-in profile's theme wins over localStorage after the page loads: put the asked theme back before the picture
  await page.evaluate((t) => { if (document.documentElement.getAttribute("data-theme") !== t) document.documentElement.setAttribute("data-theme", t); }, scheme);
  await page.waitForTimeout(350);
  const name = `real-${role}-call-${state}-${scheme}-${width}`;
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: false });
  shots.push(name);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  if (wide) note(`${name}: sideways scroll (${await page.evaluate(() => document.documentElement.scrollWidth)} px)`);
}

/** Try a step; a failure is noted and the run goes on. */
async function step(label, fn) {
  try { await fn(); } catch (e) { note(`${label}: ${String(e.message || e).split("\n")[0].slice(0, 220)}`); }
}

const visible = (loc, timeout = 3000) => loc.first().waitFor({ state: "visible", timeout }).then(() => true, () => false);

/** The member page: through the pre-join when it shows, then the call; waits for the video (up to 20 s). */
async function memberIn(page, mid) {
  await page.goto(`/tb-nik/meetings/${mid}/member`);
  const first = await Promise.race([
    page.getByTestId("prejoin").waitFor({ timeout: 15_000 }).then(() => "prejoin"),
    page.getByTestId("member-view").waitFor({ timeout: 15_000 }).then(() => "view"),
  ]);
  if (first === "prejoin") await page.getByTestId("prejoin-join").click();
  await page.getByTestId("member-view").waitFor({ timeout: 15_000 });
  await page.locator('[data-testid="member-view"][data-video-status="connected"]').waitFor({ timeout: 20_000 }).catch(() => note("member: the video did not connect in 20 s"));
}

async function coordinatorIn(page, mid) {
  await page.goto(`/tb-nik/meetings/${mid}`);
  const first = await Promise.race([
    page.getByTestId("prejoin").waitFor({ timeout: 15_000 }).then(() => "prejoin"),
    page.getByTestId("control-view").waitFor({ timeout: 15_000 }).then(() => "view"),
  ]);
  if (first === "prejoin") await page.getByTestId("prejoin-join").click();
  await page.getByTestId("control-view").waitFor({ timeout: 15_000 });
  await page.getByTestId("video-chip").and(page.locator('[data-video-status="connected"]')).waitFor({ timeout: 20_000 }).catch(() => undefined);
}

/** Opens a side panel: the bar button on a laptop, the More sheet's entry on a phone. Returns false when there is no way to it. */
async function openPanel(page, kind, phone) {
  const bar = page.getByTestId(`panel-${kind}`);
  if (await bar.count()) { await bar.first().click(); return true; }
  if (!phone) return false;
  await page.getByTestId("more").click();
  const sheet = page.getByTestId("more-menu");
  await sheet.waitFor({ timeout: 3000 });
  const words = { people: /^People/, agenda: /^Agenda/, case: /^Case/, agents: /^Agents/, chat: /^Chat/ };
  const item = sheet.getByRole("button", { name: words[kind] }).or(sheet.getByRole("menuitem", { name: words[kind] }));
  if (!(await item.count())) { await page.keyboard.press("Escape"); return false; }
  await item.first().click();
  return true;
}

async function closePanels(page) {
  await page.keyboard.press("Escape");
  await page.waitForTimeout(250);
}

const mdt = await apiFor(MDT);
const mem = await apiFor(MEMBER);
const third = THIRD ? await apiFor(THIRD) : null;
if (!THIRD) note("no third login in the logins file: the admit toast is shot with the member waiting");
let mid = "";

try {
  // ---- the throw-away meeting -------------------------------------------------------------------------------------------------------
  const today = new Date().toISOString().slice(0, 10);
  const created = await (await mdt.api.post("/api/tb/meetings", { data: { date: today, time: "23:50", room: "Real check (synthetic)", video: true, minutes_per_case: 5 } })).json();
  mid = created.meeting?.id ?? created.id;
  if (!mid) throw new Error(`no meeting: ${JSON.stringify(created).slice(0, 200)}`);
  note(`meeting ${mid}`);
  const a1 = await mdt.api.post(`/api/tb/meetings/${mid}/agenda/add`, { data: { case_id: CASE, list: "noting" } });
  if (!a1.ok()) throw new Error(`agenda ${CASE}: HTTP ${a1.status()}`);
  const list = await (await mdt.api.get("/api/tb/case-list")).json();
  const ids = (list.rows || list.cases || []).map((r) => r.case_id || r.id || "");
  let case2 = "";
  for (const id of ["TB-2026-0002", ...ids].filter((x, i, a) => SYNTHETIC.test(x) && x !== CASE && ids.includes(x) && a.indexOf(x) === i)) {
    if ((await mdt.api.post(`/api/tb/meetings/${mid}/agenda/add`, { data: { case_id: id, list: "noting" } })).ok()) { case2 = id; break; }
  }
  note(`second Case File: ${case2 || "none added"}`);
  const code = (await (await mdt.api.post(`/api/tb/meetings/${mid}/code`, { data: {} })).json()).value;

  // ---- the join page, the waiting room, the pre-join (the member) ---------------------------------------------------------------------
  for (const [vp, scheme] of VIEWS) {
    const v = await open(mem, vp, scheme, "member");
    await step(`join page ${scheme}-${vp.width}`, async () => {
      await v.page.goto("/tb-nik/meetings/join");
      await v.page.getByTestId("join-page").waitFor({ timeout: 10_000 });
      await shot(v.page, "member", "join", scheme, vp.width);
    });
    await v.close();
  }
  const joined = await (await mem.api.post("/api/tb/meetings/join", { data: { code } })).json().catch(() => ({}));
  if (joined.status !== "waiting") throw new Error(`member join refused: ${JSON.stringify(joined).slice(0, 200)}`);
  for (const [vp, scheme] of VIEWS) {
    const v = await open(mem, vp, scheme, "member");
    await step(`waiting ${scheme}-${vp.width}`, async () => {
      await v.page.goto(`/tb-nik/meetings/${mid}/member`);
      await v.page.getByTestId("waiting-room").waitFor({ timeout: 10_000 });
      await shot(v.page, "member", "waiting", scheme, vp.width);
    });
    await v.close();
  }
  await mdt.api.post(`/api/tb/meetings/${mid}/admit`, { data: { user: MEMBER } });
  for (const [vp, scheme] of VIEWS) {
    const v = await open(mem, vp, scheme, "member");
    await step(`pre-join ${scheme}-${vp.width}`, async () => {
      await v.page.goto(`/tb-nik/meetings/${mid}/member`);
      await v.page.getByTestId("prejoin").waitFor({ timeout: 10_000 });
      await v.page.waitForTimeout(800);  // the fake camera's picture
      await shot(v.page, "member", "prejoin", scheme, vp.width);
    });
    await v.close();
  }

  // ---- before the start, nothing on the floor yet: the grid and the empty room screen ---------------------------------------------------
  for (const [vp, scheme] of VIEWS) {
    const v = await open(mem, vp, scheme, "member");
    await step(`grid ${scheme}-${vp.width}`, async () => {
      await memberIn(v.page, mid);
      await v.page.waitForTimeout(800);
      const stage = await v.page.getByTestId("shared-screen").getAttribute("data-stage").catch(() => null);
      if (stage !== "grid" && stage !== "floor") note(`member grid ${scheme}-${vp.width}: the stage shows ${stage} before the start`);
      await shot(v.page, "member", "grid", scheme, vp.width);
    });
    await v.close();
  }
  const room = await open(mdt, ROOM, "dark", "room");
  await step("room empty", async () => {
    await room.page.goto(`/tb-nik/meetings/${mid}/room`);
    await room.page.getByTestId("room-screen").waitFor({ timeout: 15_000 });
    await room.page.waitForTimeout(1200);
    await shot(room.page, "room", "empty", "dark", 1920);
  });

  // the start puts the first Case File on the floor (board.start); the coordinator stays in the call while the member is shot
  await mdt.api.post(`/api/tb/meetings/${mid}/start`, { data: {} });
  let anchor = await open(mdt, LAPTOP, "light", "coordinator anchor");
  await step("coordinator anchor", () => coordinatorIn(anchor.page, mid));

  // ---- the first case on the floor: the member's call ---------------------------------------------------------------------------------
  await mdt.api.post(`/api/tb/meetings/${mid}/current`, { data: { case_id: CASE } });
  await mem.api.post(`/api/tb/meetings/${mid}/chat`, { data: { text: "Real check line: the PET-CT report is on the Case File (synthetic)." } });
  await mdt.api.post(`/api/tb/meetings/${mid}/chat`, { data: { text: "Thank you, next we look at the pathology (synthetic)." } });
  for (const [vp, scheme] of VIEWS) {
    const phone = vp.width < 1024;
    const v = await open(mem, vp, scheme, "member");
    const p = v.page;
    const w = vp.width;
    await step(`member call ${scheme}-${w}`, async () => {
      await memberIn(p, mid);
      await p.locator('[data-testid="tile"][data-user="tb-mdt"] video').first().waitFor({ timeout: 15_000 }).catch(() => note(`member ${scheme}-${w}: no coordinator video tile`));
      await p.waitForTimeout(800);
      await shot(p, "member", "stage", scheme, w);
    });
    for (const kind of ["people", "chat", "agenda", "case", "agents"]) {
      await step(`member panel ${kind} ${scheme}-${w}`, async () => {
        if (!(await openPanel(p, kind, phone))) { note(`member ${scheme}-${w}: no way to the ${kind} panel`); return; }
        await p.waitForTimeout(500);
        await shot(p, "member", `panel-${kind}`, scheme, w);
        if (kind === "chat") {
          const tab = p.getByRole("tab", { name: /Meeting chat/ });
          if (await tab.count()) { await tab.first().click(); await p.waitForTimeout(400); await shot(p, "member", "panel-chat-meeting", scheme, w); }
        }
        await closePanels(p);
      });
    }
    await step(`member more ${scheme}-${w}`, async () => {
      await p.getByTestId("more").first().click();
      await p.getByTestId("more-menu").waitFor({ timeout: 3000 });
      await shot(p, "member", phone ? "sheet-more" : "more", scheme, w);
      await closePanels(p);
    });
    if (phone) {
      await step(`member chat sheet ${scheme}-${w}`, async () => {
        await p.getByTestId("panel-chat").first().click();
        await p.waitForTimeout(500);
        await shot(p, "member", "sheet-chat", scheme, w);
        await closePanels(p);
      });
    }
    await step(`member devices ${scheme}-${w}`, async () => {
      const arrow = p.getByTestId("mic-devices");
      if (!(await arrow.count())) return;  // phone: the devices are in the More sheet
      await arrow.first().click();
      await p.getByTestId("device-settings").first().waitFor({ timeout: 3000 });
      await shot(p, "member", "devices", scheme, w);
      await closePanels(p);
    });
    await step(`member stepped away ${scheme}-${w}`, async () => {
      const away = p.getByTestId("step-away");
      if (!(await visible(away, 2000))) { note(`member ${scheme}-${w}: no Step away button`); return; }
      await away.first().click();
      await p.getByTestId("back-to-shared").first().waitFor({ timeout: 3000 });
      await shot(p, "member", "stepped-away", scheme, w);
      await p.getByTestId("back-to-shared").first().click();
    });
    await v.close();
  }
  await anchor.close();

  // ---- the coordinator: the admit toast with a third login waiting, then the layout, Decision, the tile menu, End meeting ---------------
  const memberAnchor = await open(mem, LAPTOP, "light", "member anchor");
  await step("member anchor", () => memberIn(memberAnchor.page, mid));
  if (third) {
    const j = await (await third.api.post("/api/tb/meetings/join", { data: { code } })).json().catch(() => ({}));
    if (j.status !== "waiting") note(`${THIRD} join: ${JSON.stringify(j).slice(0, 200)}`);
  }
  for (const [vp, scheme] of VIEWS) {
    const v = await open(mdt, vp, scheme, "coordinator");
    await step(`coordinator admit toast ${scheme}-${vp.width}`, async () => {
      await coordinatorIn(v.page, mid);
      const toast = v.page.getByTestId("waiting-banner");
      if (!(await visible(toast, 8000))) note(`coordinator ${scheme}-${vp.width}: no admit toast`);
      await v.page.waitForTimeout(600);
      await shot(v.page, "coordinator", "admit-toast", scheme, vp.width);
    });
    await v.close();
  }
  if (third) await mdt.api.post(`/api/tb/meetings/${mid}/admit`, { data: { user: THIRD } });
  for (const [vp, scheme] of VIEWS) {
    const phone = vp.width < 1024;
    const v = await open(mdt, vp, scheme, "coordinator");
    const p = v.page;
    const w = vp.width;
    await step(`coordinator layout ${scheme}-${w}`, async () => {
      await coordinatorIn(p, mid);
      await p.locator(`[data-testid="tile"][data-user="${MEMBER}"] video`).first().waitFor({ timeout: 15_000 }).catch(() => note(`coordinator ${scheme}-${w}: no member video tile`));
      await p.waitForTimeout(800);
      await shot(p, "coordinator", "layout", scheme, w);
    });
    if (!phone) {
      await step(`coordinator decision ${scheme}-${w}`, async () => {
        await p.getByTestId("panel-decision").click();
        await p.getByTestId("decision-form").first().waitFor({ timeout: 5000 });
        await shot(p, "coordinator", "panel-decision", scheme, w);
        await closePanels(p);
      });
      await step(`coordinator tile menu ${scheme}-${w}`, async () => {
        await p.locator(`[data-testid="tile"][data-user="${MEMBER}"]`).first().hover();
        await p.locator(`[data-testid="tile"][data-user="${MEMBER}"] [data-testid="tile-menu"]`).first().click();
        await p.getByTestId("tile-pin").first().waitFor({ timeout: 3000 });
        await shot(p, "coordinator", "tile-menu", scheme, w);
        await closePanels(p);
      });
      await step(`coordinator end dialog ${scheme}-${w}`, async () => {
        await p.getByTestId("end-meeting").first().click();
        await p.getByTestId("end-meeting-dialog").waitFor({ timeout: 3000 });
        await shot(p, "coordinator", "end-dialog", scheme, w);
        await closePanels(p);
        await p.getByTestId("end-meeting-dialog").waitFor({ state: "hidden", timeout: 3000 });
      });
    } else {
      await step(`coordinator sheet ${scheme}-${w}`, async () => {
        await p.getByTestId("coordinator-sheet").click();
        await p.getByTestId("coordinator-menu").waitFor({ timeout: 3000 });
        await shot(p, "coordinator", "sheet", scheme, w);
        await closePanels(p);
      });
      await step(`coordinator phone decision ${scheme}-${w}`, async () => {
        await p.getByTestId("coordinator-sheet").click();
        const menu = p.getByTestId("coordinator-menu");
        await menu.waitFor({ timeout: 3000 });
        const item = menu.getByRole("button", { name: /^Decision/ });
        if (!(await item.count())) { note(`coordinator ${scheme}-${w}: no Decision in the coordinator sheet`); await closePanels(p); return; }
        await item.first().click();
        await p.getByTestId("decision-form").first().waitFor({ timeout: 5000 });
        await shot(p, "coordinator", "panel-decision", scheme, w);
        await closePanels(p);
      });
    }
    await v.close();
  }

  // ---- the room screen: summary and stage, the agents standing in, questions and hands, the typed decision -----------------------------
  await step("room summary", async () => {
    await room.page.locator(`[data-testid="tile"][data-user="${MEMBER}"]`).first().waitFor({ timeout: 15_000 }).catch(() => note("room: no member tile"));
    await room.page.waitForTimeout(1000);
    await shot(room.page, "room", "summary", "dark", 1920);
  });
  await step("room agents", async () => {
    const agents = await room.page.getByTestId("agent-tile").count();
    note(`room: ${agents} agent tiles`);
    const toggle = room.page.getByTestId("summary-toggle");
    if (await toggle.count()) { await toggle.click({ force: true }); await room.page.waitForTimeout(500); }
    await shot(room.page, "room", "agents", "dark", 1920);
    if (await toggle.count()) await toggle.click({ force: true });
  });
  await step("room questions and hands", async () => {
    await mem.api.post(`/api/tb/meetings/${mid}/hand`, { data: { raised: true } });
    const q = await mem.api.post(`/api/tb/meetings/${mid}/questions`, { data: { text: "Is the staging work-up complete for the board? (synthetic real check)" } });
    if (!q.ok()) note(`question: HTTP ${q.status()}`);
    await room.page.waitForTimeout(1500);
    await shot(room.page, "room", "questions-hands", "dark", 1920);
  });
  await step("room typed decision", async () => {
    const r = await mdt.api.put(`/api/tb/meetings/${mid}/decision-live`, { data: { text: "The board notes the case; the staging work-up to be completed before the next board (synthetic)." } });
    if (!r.ok()) note(`decision-live: HTTP ${r.status()}`);
    await room.page.waitForTimeout(1200);
    await shot(room.page, "room", "decision", "dark", 1920);
  });
  await room.close();
  await memberAnchor.close();
} catch (e) {
  note(`run stopped: ${String(e.message || e).split("\n")[0]}`);
} finally {
  if (mid) {
    const c = await mdt.api.post(`/api/tb/meetings/${mid}/cancel`, { data: { reason: "real check (synthetic)" } });
    if (!c.ok()) { const e = await mdt.api.post(`/api/tb/meetings/${mid}/end`, { data: {} }); note(`meeting ${mid}: cancel HTTP ${c.status()}, end HTTP ${e.status()}`); }
    else note(`meeting ${mid}: cancelled`);
  }
  await browser.close();
  for (const x of [mdt, mem, third]) await x?.api.dispose();
  note(`${shots.length} shots in ${OUT}`);
  fs.writeFileSync(path.join(OUT, "findings.txt"), findings.join("\n") + "\n");
}
