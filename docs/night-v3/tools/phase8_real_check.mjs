// Phase 8 real-screen and live check (night-v3 8.4 and 8.5): Messages on the running app with demo logins read in code (never printed).
// Part 1, screens: the Messages page and the finder for one login at laptop 1366 x 768 and phone 390 x 844, light and dark.
// Part 2, live (laptop, light): A (a Breast Surgery doctor) writes to B (a Radiology doctor) with a synthetic Case File attached; B's
// top bar badge and bell show it at once; B opens it and A sees "Seen"; B types and A sees "is typing"; B answers and resolves, A sees
// both; A writes to the Radiology department; B (a member) sees and answers it; a Pathology login's list has no such conversation; the
// chip on B's side shows the label only if B may open the file, else "A Case File you cannot open" and the Case File route refuses.
// Shots go to /data/vaidyx/night-v3/shots/phase8/ as real-messages-<state>-<theme>-<width>.png; page errors, console errors, HTTP
// errors of 500 and up, sideways scroll and failed steps go to findings.txt there. Run alone (the app on :7000 with the Phase 8 routes):
//   node docs/night-v3/tools/phase8_real_check.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium, request } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";

const BASE = process.env.TBNIK_BASE_URL || "http://127.0.0.1:7000";
const OUT = "/data/vaidyx/night-v3/shots/phase8";
const CASE = process.env.TBNIK_CASE || "TB-2026-0001";
const SYNTHETIC = /^(TB-2026-\d{4}|HIST-\d{2}|TB-DEMO-P\d+)$/;
const A = process.env.TBNIK_USER_A || "tb-breast-doc";
const B = process.env.TBNIK_USER_B || "tb-rad-doc";
const C = process.env.TBNIK_USER_C || "tb-path-head";
const DEPT = process.env.TBNIK_DEPT || "Radiology";
const H = { "X-Requested-With": "tb-nik" };
const STAMP = new Date().toISOString().slice(11, 19);
if (!SYNTHETIC.test(CASE)) throw new Error("a synthetic Case File only");
fs.mkdirSync(OUT, { recursive: true });
const logins = Object.fromEntries(fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")
  .filter((l) => l.includes("\t") && !l.startsWith("#")).map((l) => l.split("\t")).map((c) => [c[0].trim(), c[1]]));
for (const u of [A, B, C]) if (!logins[u]) throw new Error(`no demo login ${u}`);
const findings = [];
const shots = [];
const note = (t) => { findings.push(t); console.log(t); };
const VIEWS = [[{ width: 1366, height: 768 }, "light"], [{ width: 1366, height: 768 }, "dark"], [{ width: 390, height: 844 }, "light"], [{ width: 390, height: 844 }, "dark"]];

const browser = await chromium.launch({ headless: true });
async function signIn(user) {
  const api = await request.newContext({ baseURL: BASE, extraHTTPHeaders: H });
  const r = await api.post("/api/auth/login", { data: { username: user, password: logins[user], remember: true } });
  if (!r.ok()) throw new Error(`sign-in ${user}: HTTP ${r.status()}`);
  return { api, state: await api.storageState() };
}
const sa = await signIn(A), sb = await signIn(B), sc = await signIn(C);
const nameOf = async (s) => ((await (await s.api.get("/api/tb/me")).json()).display_name || "");
const NAME_A = await nameOf(sa), NAME_B = await nameOf(sb);

async function open(state, vp, scheme, label) {
  const ctx = await browser.newContext({ viewport: vp, colorScheme: scheme, locale: "en-IN", timezoneId: "Asia/Kolkata", reducedMotion: "reduce", storageState: state, baseURL: BASE });
  await ctx.addInitScript((t) => { try { localStorage.setItem("tbnik.theme", t); } catch { /* no storage */ } }, scheme);
  ctx.setDefaultTimeout(10_000);
  const page = await ctx.newPage();
  const tag = `${label} ${scheme}-${vp.width}`;
  page.on("pageerror", (e) => note(`${tag}: page error ${e.message.split("\n")[0].slice(0, 200)}`));
  page.on("console", (m) => { if (m.type() === "error" && !/favicon|net::ERR_ABORTED|Failed to load resource/.test(m.text())) note(`${tag}: console ${m.text().slice(0, 200)}`); });
  page.on("response", (x) => { if (x.url().includes("/api/") && x.status() >= 500) note(`${tag}: HTTP ${x.status()} ${x.url().replace(BASE, "")}`); });
  return { page, close: () => ctx.close() };
}
async function shot(page, stateName, scheme, width) {
  await page.evaluate((t) => { if (document.documentElement.getAttribute("data-theme") !== t) document.documentElement.setAttribute("data-theme", t); }, scheme);
  await page.waitForTimeout(350);
  const name = `real-messages-${stateName}-${scheme}-${width}`;
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: false });
  shots.push(name);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  if (wide) note(`${name}: sideways scroll (${await page.evaluate(() => document.documentElement.scrollWidth)} px)`);
}
async function step(label, fn) { try { await fn(); } catch (e) { note(`${label}: ${String(e.message || e).split("\n")[0].slice(0, 220)}`); } }
async function until(fn, ms = 8000, every = 250) { const end = Date.now() + ms; let last; while (Date.now() < end) { last = await fn(); if (last) return last; await new Promise((r) => setTimeout(r, every)); } return last; }

// ---- Part 1: screens for A -----------------------------------------------------------------------------------------------------------
for (const [vp, scheme] of VIEWS) {
  const { page, close } = await open(sa.state, vp, scheme, "screens");
  const w = vp.width, tag = `${scheme}-${w}`;
  await step(`list ${tag}`, async () => {
    await page.goto("/tb-nik/messages");
    await page.getByTestId("messages-page").waitFor({ timeout: 20_000 });
    await page.waitForTimeout(800);
    if (!(await page.getByTestId("messages-nav").count())) note(`list ${tag}: no Messages icon in the top bar`);
    await shot(page, "list", scheme, w);
  });
  await step(`finder ${tag}`, async () => {
    await page.getByTestId("new-message").first().click();
    await page.getByTestId("directory-picker").waitFor();
    await page.waitForTimeout(500);
    const people = await page.getByTestId("directory-person").count();
    const depts = await page.getByTestId("directory-department").count();
    if (!people) note(`finder ${tag}: no person listed`);
    if (!depts) note(`finder ${tag}: no department listed`);
    const text = await page.getByTestId("directory-picker").innerText();
    if (/TNMC|registration|@/.test(text)) note(`finder ${tag}: a registration number or e-mail is on the finder`);
    await shot(page, "finder", scheme, w);
    await page.keyboard.press("Escape");
  });
  await close();
}

// ---- Part 2: live between A and B (laptop, light) -------------------------------------------------------------------------------------
const live = { conv: "", deptConv: "", chip: "" };
const pa = await open(sa.state, VIEWS[0][0], "light", "A");
const pb = await open(sb.state, VIEWS[0][0], "light", "B");
await step("B home", async () => { await pb.page.goto("/tb-nik/cases"); await pb.page.getByTestId("messages-nav").waitFor({ timeout: 20_000 }); });
const badgeB = async () => (await pb.page.getByTestId("messages-nav").innerText()).trim();
const badge0 = await badgeB();
await step("A writes to B", async () => {
  await pa.page.goto("/tb-nik/messages");
  await pa.page.getByTestId("messages-page").waitFor({ timeout: 20_000 });
  await pa.page.getByTestId("new-message").first().click();
  await pa.page.getByTestId("directory-picker").waitFor();
  await pa.page.locator(`[data-testid="directory-person"][data-user="${B}"]`).first().click();
  await pa.page.getByTestId("composer-input").waitFor({ timeout: 15_000 });
  await pa.page.getByTestId("add-case-file").click();
  await pa.page.getByTestId("link-picker").waitFor();
  await until(async () => (await pa.page.getByTestId("link-option").count()) > 0, 10_000);
  const opt = pa.page.getByTestId("link-option").filter({ hasText: CASE });
  if (await opt.count()) await opt.first().click(); else { note(`A writes: the Case File ${CASE} is not in the picker`); await pa.page.keyboard.press("Escape"); }
  await pa.page.getByTestId("composer-input").fill(`Please look at the CT of this synthetic file when you can (${STAMP}).`);
  await pa.page.getByTestId("send").click();
  await pa.page.locator('[data-testid="message"][data-mine="true"]').first().waitFor({ timeout: 15_000 });
  await until(() => /\/messages\/C[0-9a-f]+/.test(pa.page.url()), 8000);
  live.conv = (pa.page.url().match(/\/messages\/(C[0-9a-f]+)/) || [])[1] || "";
  if (!live.conv) note("A writes: the page did not move to the conversation");
  await shot(pa.page, "thread-a", "light", 1366);
});
await step("B badge and bell", async () => {
  const b = await until(async () => { const t = await badgeB(); return t !== badge0 && /\d/.test(t) ? t : ""; }, 6000);
  if (!b) note(`B badge: the top bar count did not change within 6 s (was "${badge0}")`);
  await pb.page.getByRole("button", { name: /notifications/i }).first().click();
  const item = pb.page.getByText(`New message from ${NAME_A}`).first();
  const ok = await until(() => item.isVisible().catch(() => false), 6000);
  if (!ok) note(`B bell: no "New message from ${NAME_A}" item within 6 s`);
  const bell = await pb.page.getByRole("dialog").or(pb.page.locator("[role=menu]")).first().innerText().catch(() => "");
  if (/CT of this synthetic/.test(bell)) note("B bell: the message text is in the bell");
  await shot(pb.page, "bell-b", "light", 1366);
  await pb.page.keyboard.press("Escape");
});
await step("B opens, A sees Seen", async () => {
  await pb.page.goto(`/tb-nik/messages/${live.conv}`);
  await pb.page.getByTestId("thread").or(pb.page.getByTestId("message-list")).first().waitFor({ timeout: 20_000 });
  await pb.page.waitForTimeout(800);
  const chips = pb.page.getByTestId("chip");
  if (await chips.count()) { live.chip = (await chips.first().innerText()).trim(); } else note("B opens: no chip on the message");
  const text = await pb.page.getByTestId("message-list").innerText().catch(() => "");
  if (/[A-Z]{2,}\/\d|UHID|MRN/.test(live.chip)) note(`B opens: the chip shows an identifier: ${live.chip}`);
  if (!text.includes("CT of this synthetic")) note("B opens: the message text is missing on B's screen");
  await shot(pb.page, "thread-b", "light", 1366);
  const seen = await until(() => pa.page.getByTestId("seen").isVisible().catch(() => false), 8000);
  if (!seen) note('A: no "Seen" within 8 s of B opening');
});
await step("B types and answers, A sees both", async () => {
  await pb.page.getByTestId("composer-input").fill("On it,");
  const typing = await until(() => pa.page.getByTestId("typing").isVisible().catch(() => false), 6000);
  if (!typing) note('A: no "is typing" within 6 s');
  await pb.page.getByTestId("composer-input").fill(`On it, the CT report goes in the Case File today (${STAMP}).`);
  await pb.page.getByTestId("send").click();
  const got = await until(async () => (await pa.page.locator('[data-testid="message"][data-mine="false"]').count()) > 0, 8000);
  if (!got) note("A: B's answer did not arrive within 8 s");
});
await step("B resolves, A sees Resolved", async () => {
  await pb.page.getByTestId("resolve").click();
  const ok = await until(() => pa.page.getByText("Resolved").first().isVisible().catch(() => false), 8000);
  if (!ok) note('A: no "Resolved" within 8 s');
  await shot(pa.page, "resolved-a", "light", 1366);
});
await step("A writes to the department", async () => {
  await pa.page.getByTestId("new-message").first().click();
  await pa.page.getByTestId("directory-picker").waitFor();
  await pa.page.getByTestId("directory-department").filter({ hasText: DEPT }).first().click();
  await pa.page.getByTestId("composer-input").waitFor({ timeout: 15_000 });
  await pa.page.getByTestId("composer-input").fill(`${DEPT}, the synthetic PET report is awaited for the board (${STAMP}).`);
  await pa.page.getByTestId("send").click();
  await until(() => /\/messages\/C[0-9a-f]+/.test(pa.page.url()) && !pa.page.url().includes(live.conv), 8000);
  live.deptConv = (pa.page.url().match(/\/messages\/(C[0-9a-f]+)/) || [])[1] || "";
  await pb.page.goto("/tb-nik/messages");
  const row = pb.page.locator(`[data-testid="conversation-row"][data-id="${live.deptConv}"]`);
  const seen = await until(() => row.first().isVisible().catch(() => false), 8000);
  if (!seen) note(`B: the ${DEPT} conversation is not in B's list`);
  await row.first().click();
  await pb.page.getByTestId("composer-input").waitFor({ timeout: 15_000 });
  const head = await pb.page.getByTestId("thread").innerText().catch(() => "");
  if (!/Reaches \d+/.test(head) && !head.includes(`From ${NAME_A}`)) note(`B: the department thread header reads: ${head.slice(0, 120)}`);
  await pb.page.getByTestId("composer-input").fill(`We will report it tomorrow (${STAMP}).`);
  await pb.page.getByTestId("send").click();
  const got = await until(async () => (await pa.page.locator('[data-testid="message"][data-mine="false"]').count()) > 0, 8000);
  if (!got) note("A: the department answer did not arrive within 8 s");
  await shot(pa.page, "department-a", "light", 1366);
  await shot(pb.page, "department-b", "light", 1366);
});
await step("C sees nothing of it", async () => {
  const r = await sc.api.get("/api/tb/messages/conversations");
  if (r.status() === 403) { note(`C: ${C} may not use Messages (403): the department check used the API only for A and B`); return; }
  const ids = ((await r.json()).conversations || []).map((c) => c.id);
  if (ids.includes(live.deptConv) || ids.includes(live.conv)) note("C: a Pathology login sees a Radiology or direct conversation it is not in");
  const r2 = await sc.api.get(`/api/tb/messages/conversations/${live.deptConv}`);
  if (r2.status() !== 404) note(`C: opening the ${DEPT} conversation gave HTTP ${r2.status()}, not 404`);
});
await step("the chip grants nothing", async () => {
  const r = await sb.api.get(`/api/tb/cases/${CASE}`);
  const may = r.status() === 200;
  if (may && /cannot open/.test(live.chip)) note(`chip: B may open ${CASE} (HTTP 200) but the chip said cannot open`);
  if (!may && !/cannot open/.test(live.chip)) note(`chip: B gets HTTP ${r.status()} on ${CASE} but the chip read "${live.chip}"`);
  note(`info: B's chip read "${live.chip}"; the Case File route gives B HTTP ${r.status()}`);
});
await step("phone thread for B", async () => {
  for (const scheme of ["light", "dark"]) {
    const { page, close } = await open(sb.state, { width: 390, height: 844 }, scheme, "B-phone");
    await page.goto(`/tb-nik/messages/${live.conv}`);
    await page.getByTestId("composer-input").waitFor({ timeout: 20_000 });
    await page.waitForTimeout(600);
    await shot(page, "phone-thread", scheme, 390);
    await close();
  }
});
await pa.close(); await pb.close();
await browser.close();
fs.writeFileSync(path.join(OUT, "findings.txt"), `${new Date().toISOString()} A=${A} B=${B} C=${C} case=${CASE}\nconv=${live.conv} dept=${live.deptConv}\nshots: ${shots.join(", ")}\n${findings.length ? findings.join("\n") : "no findings"}\n`);
console.log(`${shots.length} shots, ${findings.length} findings -> ${OUT}/findings.txt`);
