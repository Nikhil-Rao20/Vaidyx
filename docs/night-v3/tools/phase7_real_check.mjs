// Phase 7 real-screen check (night-v3 7.3 and 7.4): the Similar Case Files area on the running app with a demo doctor login (read in
// code, never printed) on a synthetic Case File (Kavitha's TB-2026-0001 by default): the Overview card, the Summary card with the label,
// a real search (the reasoner orders the synthetic history, up to a minute), the result cards, and opening the first result (at once,
// or through the "Open with a reason" dialog with the reason written in) and the banner on the past file. Laptop 1366 x 768 and phone
// 390 x 844 in light and dark. Shots go to /data/vaidyx/night-v3/shots/phase7/ as real-similar-<state>-<theme>-<width>.png; page
// errors, console errors, failed API calls, numbers that could read as a score, advice words and sideways scroll go to findings.txt
// there. Run alone (the app on :7000 with the similar routes must be running; a login may search ten times in ten minutes):
//   node docs/night-v3/tools/phase7_real_check.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium, request } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";

const BASE = process.env.TBNIK_BASE_URL || "http://127.0.0.1:7000";
const OUT = "/data/vaidyx/night-v3/shots/phase7";
const CASE = process.env.TBNIK_CASE || "TB-2026-0001";
const SYNTHETIC = /^(TB-2026-\d{4}|HIST-\d{2}|TB-DEMO-P\d+)$/;
const USER = process.env.TBNIK_USER || "tb-breast-doc";
const WORDS = process.env.TBNIK_WORDS || "";
const H = { "X-Requested-With": "tb-nik" };
const LABEL = "Past Case File, not advice for this patient";
const NOT_SAID = ["recommend", "consider", "suggest", "do the same", "treat as", "best match"];
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
  const name = `real-similar-${stateName}-${scheme}-${width}`;
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: false });
  shots.push(name);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  if (wide) note(`${name}: sideways scroll (${await page.evaluate(() => document.documentElement.scrollWidth)} px)`);
}
async function step(label, fn) { try { await fn(); } catch (e) { note(`${label}: ${String(e.message || e).split("\n")[0].slice(0, 220)}`); } }

const seen = { results: 0, opened: "" };
for (const [vp, scheme] of VIEWS) {
  const { page, close } = await open(vp, scheme, "similar");
  const w = vp.width;
  const tag = `${scheme}-${w}`;
  await step(`overview ${tag}`, async () => {
    await page.goto(`/tb-nik/cases/${CASE}`);
    await page.getByTestId("overview-similar").waitFor({ timeout: 20_000 });
    const words = await page.getByTestId("overview-similar").innerText();
    if (!words.includes(LABEL)) note(`overview ${tag}: the label is missing on the Overview card`);
    await page.getByTestId("overview-similar").scrollIntoViewIfNeeded();
    await shot(page, "overview", scheme, w);
    await page.getByTestId("overview-similar-open").click();
    await page.getByTestId("summary-similar").waitFor({ timeout: 15_000 });
  });
  await step(`card ${tag}`, async () => {
    await page.waitForTimeout(600);
    const card = page.getByTestId("summary-similar");
    const text = await card.innerText();
    if (!text.includes(LABEL)) note(`card ${tag}: the label is missing on the Summary card`);
    if (!/Gemma-4-31B/.test(text)) note(`card ${tag}: the model line is missing`);
    if (!/The search is logged/.test(text)) note(`card ${tag}: the logging note is missing`);
    if (await page.getByTestId("similar-unavailable").count()) note(`card ${tag}: not available: ${text.slice(0, 160)}`);
    await card.scrollIntoViewIfNeeded();
    await shot(page, "card", scheme, w);
  });
  await step(`search ${tag}`, async () => {
    if (WORDS) await page.locator("#similar-words").fill(WORDS);
    await page.getByTestId("similar-search").click();
    await page.getByTestId("similar-results").waitFor({ timeout: 90_000 });
    await page.waitForTimeout(500);
    const items = page.getByTestId("similar-item");
    const n = await items.count();
    seen.results = n;
    if (!n) note(`search ${tag}: no result card (text: ${(await page.getByTestId("similar-results").innerText()).slice(0, 160)})`);
    const text = await page.getByTestId("summary-similar").innerText();
    for (const x of NOT_SAID) if (text.toLowerCase().includes(x)) note(`search ${tag}: the word "${x}" is on the screen`);
    if (/\d{1,3}\s?% (similar|match|likeness)/i.test(text) || /\b(similarity )?score\b/i.test(text.replace(/Allred score|Nottingham score|IHC score/g, "")) || /\brank(ed)?\b/i.test(text)) note(`search ${tag}: a score, rank or similarity percent is on the screen`);
    for (let i = 0; i < n; i++) {
      const t = await items.nth(i).innerText();
      if (!t.includes(LABEL)) note(`search ${tag}: card ${i + 1} has no label`);
      if (/\b\d{1,2}\/\d{1,2}\/\d{4}\b/.test(t.replace(/This file, [^:]*\d{2}\/\d{2}\/\d{4}/g, ""))) note(`search ${tag}: card ${i + 1} shows a day-level date of the past file`);
    }
    await page.getByTestId("similar-results").scrollIntoViewIfNeeded();
    await shot(page, "results", scheme, w);
    if (n) { await items.first().scrollIntoViewIfNeeded(); await shot(page, "first", scheme, w); }
  });
  if (scheme === "light" && w === 1366) await step(`open ${tag}`, async () => {
    const items = page.getByTestId("similar-item");
    if (!(await items.count())) return;
    const past = await items.first().getAttribute("data-case");
    await items.first().getByTestId("similar-open").click();
    const dialog = page.getByRole("dialog");
    const landed = () => /from=similar/.test(page.url());
    for (let i = 0; i < 20 && !landed() && !(await dialog.isVisible().catch(() => false)); i++) await page.waitForTimeout(300);
    if (!landed() && await dialog.isVisible().catch(() => false)) {
      seen.opened = "with_reason";
      const reason = await page.locator("#open-reason").inputValue();
      if (!reason.startsWith("similar to Case File ")) note(`open ${tag}: the reason is "${reason}"`);
      await shot(page, "dialog", scheme, w);
      await dialog.locator('button[type="submit"]').click();
      await page.waitForURL(/from=similar/, { timeout: 30_000 });
    } else seen.opened = "normal";
    await page.getByTestId("similar-from-banner").waitFor({ timeout: 20_000 });
    const banner = await page.getByTestId("similar-from-banner").innerText();
    if (!banner.includes(`Similar Case Files of ${CASE}`) || !banner.includes(LABEL)) note(`open ${tag}: the banner reads "${banner}"`);
    if (!page.url().includes(`/cases/${past}/`)) note(`open ${tag}: landed on ${page.url()} not ${past}`);
    await shot(page, "opened", scheme, w);
  });
  await close();
}
await browser.close();
fs.writeFileSync(path.join(OUT, "findings.txt"), (findings.length ? findings : ["no findings"]).join("\n") + "\n");
console.log(`${shots.length} shots in ${OUT}; result cards on the last search: ${seen.results}; first result opened: ${seen.opened || "not tried"}; findings: ${findings.length}`);
