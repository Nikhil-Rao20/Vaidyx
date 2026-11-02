// Phase 6 real-screen check (night-v3 6.5): the Case File's "Specialty agents" area on the running app with a demo login (read in
// code, never printed) on a synthetic Case File: the Overview card with the six agent chips and their badges, the Summary card with an
// agent opened (its brief, thread and question box) and the list. Laptop 1366 x 768 and phone 390 x 844 in light and dark. Shots go to
// /data/vaidyx/night-v3/shots/phase6/ as real-casefile-<state>-<theme>-<width>.png; page errors, console errors, failed API calls and
// sideways scroll go to findings.txt there. The meeting screens of the phase are checked by the live two-person spec
// (web/tb-nik/e2e/live/video.spec.ts) and the mocked specs. Run alone (the app on :7000 must be running):
//   node docs/night-v3/tools/phase6_real_check.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium, request } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";

const BASE = process.env.TBNIK_BASE_URL || "http://127.0.0.1:7000";
const OUT = "/data/vaidyx/night-v3/shots/phase6";
const CASE = process.env.TBNIK_CASE || "TB-2026-0002";
const SYNTHETIC = /^TB-2026-\d{4}$/;
const USER = process.env.TBNIK_USER || "tb-breast-doc";
const H = { "X-Requested-With": "tb-nik" };
if (!SYNTHETIC.test(CASE)) throw new Error("a synthetic Case File only");
fs.mkdirSync(OUT, { recursive: true });
const logins = Object.fromEntries(fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")
  .filter((l) => l.includes("\t") && !l.startsWith("#")).map((l) => l.split("\t")).map((c) => [c[0].trim(), c[1]]));
if (!logins[USER]) throw new Error(`no demo login ${USER}`);
const findings = [];
const shots = [];
const note = (t) => { findings.push(t); console.log(t); };
const VIEWS = [[{ width: 1366, height: 768 }, "light"], [{ width: 1366, height: 768 }, "dark"], [{ width: 390, height: 844 }, "light"], [{ width: 390, height: 844 }, "dark"]];

const browser = await chromium.launch({ headless: true });
const api = await request.newContext({ baseURL: BASE, extraHTTPHeaders: H });
const r = await api.post("/api/auth/login", { data: { username: USER, password: logins[USER], remember: true } });
if (!r.ok()) throw new Error(`sign-in ${USER}: HTTP ${r.status()}`);
const state = await api.storageState();

async function open(vp, scheme, label) {
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
  const name = `real-casefile-${stateName}-${scheme}-${width}`;
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: false });
  shots.push(name);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  if (wide) note(`${name}: sideways scroll (${await page.evaluate(() => document.documentElement.scrollWidth)} px)`);
}
async function step(label, fn) { try { await fn(); } catch (e) { note(`${label}: ${String(e.message || e).split("\n")[0].slice(0, 220)}`); } }

for (const [vp, scheme] of VIEWS) {
  const { page, close } = await open(vp, scheme, "casefile");
  const w = vp.width;
  await step(`overview ${scheme}-${w}`, async () => {
    await page.goto(`/tb-nik/cases/${CASE}`);
    await page.getByTestId("overview-agents").waitFor({ timeout: 20_000 });
    const chips = await page.locator('[data-testid^="agent-chip-"]').count();
    if (chips !== 6) note(`overview ${scheme}-${w}: ${chips} agent chips, expected 6`);
    const words = await page.getByTestId("overview-agents").innerText();
    if (!/AI agents, support only/.test(words)) note(`overview ${scheme}-${w}: the support-only line is missing`);
    await page.getByTestId("overview-agents").scrollIntoViewIfNeeded();
    await shot(page, "overview", scheme, w);
  });
  await step(`agent ${scheme}-${w}`, async () => {
    const chip = page.locator('[data-testid="agent-chip-pathology"] button').first();
    await chip.click();
    await page.getByTestId("summary-briefs").waitFor({ timeout: 15_000 });
    await page.waitForTimeout(600);
    const text = await page.getByTestId("summary-briefs").innerText();
    if (!/Pathology, AI agent/.test(text)) note(`agent ${scheme}-${w}: the Pathology agent did not open (text: ${text.slice(0, 80)})`);
    if (!/AI agent, support only/.test(text)) note(`agent ${scheme}-${w}: the support-only label is missing`);
    await page.getByTestId("summary-briefs").scrollIntoViewIfNeeded();
    await shot(page, "agent", scheme, w);
  });
  await step(`list ${scheme}-${w}`, async () => {
    const back = page.getByRole("button", { name: /All agents/ }).first();
    if (await back.isVisible().catch(() => false)) await back.click();
    await page.waitForTimeout(400);
    const text = await page.getByTestId("summary-briefs").innerText();
    const n = (text.match(/, AI agent/g) || []).length;
    if (n < 6) note(`list ${scheme}-${w}: ${n} agent rows, expected 6`);
    await shot(page, "list", scheme, w);
  });
  await close();
}
await browser.close();
fs.writeFileSync(path.join(OUT, "findings.txt"), (findings.length ? findings : ["no findings"]).join("\n") + "\n");
console.log(`${shots.length} shots in ${OUT}; findings: ${findings.length}`);
