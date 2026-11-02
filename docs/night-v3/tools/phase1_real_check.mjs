// Real-app check of the night-v3 Phase 1 screens (1.1 New Case File, Overview, 1.12 staging card). Passwords read from the demo logins file, never printed.
import fs from "node:fs"; import os from "node:os"; import path from "node:path";
import { chromium } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";
const BASE = "http://127.0.0.1:7000"; const OUT = process.env.OUT; fs.mkdirSync(OUT, { recursive: true });
const NEWCASE = process.env.NEWCASE_PATH || "/tb-nik/new";
function password(user) { for (const line of fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")) { if (!line || line.startsWith("#")) continue; const [u, p] = line.split("\t"); if (u === user && p) return p; } throw new Error("no login " + user); }
const SIZES = [{ width: 1366, height: 768 }, { width: 390, height: 844 }];
const problems = [];
async function session(user) {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: SIZES[0] }); const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push(`${user}: pageerror ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") problems.push(`${user}: console ${m.text().slice(0, 160)}`); });
  const r = await page.request.post(BASE + "/api/auth/login", { data: { username: user, password: password(user), remember: false }, headers: { "X-Requested-With": "tb-nik" } });
  if (!r.ok()) throw new Error(`login ${user} HTTP ${r.status()}`);
  return { browser, page };
}
async function settle(page) { await page.waitForLoadState("networkidle", { timeout: 4000 }).catch(() => {}); await page.waitForTimeout(400); }
async function shots(page, name, before) {
  for (const size of SIZES) { await page.setViewportSize(size); for (const theme of ["light", "dark"]) {
    await page.evaluate((t) => { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("tbnik.theme", t); } catch {} }, theme);
    if (before) await before(page); await settle(page);
    const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    if (wide) problems.push(`${name} ${theme} ${size.width}: sideways scroll`);
    await page.screenshot({ path: path.join(OUT, `${name}-${theme}-${size.width}.png`), fullPage: true });
  } }
}
const notes = [];
// 1. tb-breast-doc: New Case File for VXH/26/004218 (two live files: colorectal P18A, breast P18B)
{
  const { browser, page } = await session("tb-breast-doc");
  await page.goto(`${BASE}${NEWCASE}?identifier=${encodeURIComponent("VXH/26/004218")}`); await settle(page);
  await page.waitForSelector('[data-testid="patient-case-files"]', { timeout: 15000 }).catch(() => problems.push("breast-doc: no patient-case-files card"));
  notes.push("patient card: " + (await page.locator('[data-testid="patient-case-files"]').innerText().catch(() => "MISSING")).replace(/\n/g, " | "));
  await shots(page, "newcase-patient-breastdoc");
  await page.setViewportSize(SIZES[0]);
  await page.getByRole("button", { name: /^Continue$/ }).first().click().catch(() => problems.push("breast-doc: no Continue on Patient step"));
  await settle(page);
  // pick Breast at the Cancer step
  const breast = page.getByRole("radio", { name: /breast/i }).first();
  if (await breast.count()) await breast.click(); else { const b = page.getByText(/^Breast/).first(); if (await b.count()) await b.click(); else problems.push("breast-doc: no Breast choice found"); }
  await settle(page);
  await page.waitForSelector('[data-testid="duplicate-case-file"]', { timeout: 10000 }).catch(() => problems.push("breast-doc: no duplicate notice at the Cancer step"));
  notes.push("duplicate notice: " + (await page.locator('[data-testid="duplicate-case-file"]').innerText().catch(() => "MISSING")).replace(/\n/g, " | "));
  const cont = page.getByRole("button", { name: /^Continue$/ }).first();
  notes.push("Continue disabled at Cancer step: " + (await cont.isDisabled().catch(() => "n/a")));
  await shots(page, "newcase-cancer-dup-breastdoc");
  // Overview of P18B: "Other Case Files of this patient" and the staging card
  await page.setViewportSize(SIZES[0]);
  await page.goto(`${BASE}/tb-nik/cases/TB-DEMO-P18B`); await settle(page);
  await page.waitForSelector('[data-testid="other-case-files"]', { timeout: 15000 }).catch(() => problems.push("breast-doc: no other-case-files on P18B Overview"));
  notes.push("other files: " + (await page.locator('[data-testid="other-case-files"]').innerText().catch(() => "MISSING")).replace(/\n/g, " | "));
  notes.push("staging card present: " + (await page.locator('[data-testid="staging-card"], [data-testid^="staging"]').count()));
  const work = page.getByRole("button", { name: /work out/i }).first();
  if (await work.count()) { await work.click(); await page.waitForTimeout(1500); await page.waitForLoadState("networkidle", { timeout: 90000 }).catch(() => {}); notes.push("worked out the draft stage"); }
  await settle(page);
  notes.push("prognostic section present: " + (await page.locator('[data-testid="prognostic-section"]').count()));
  notes.push("prognostic result: " + (await page.locator('[data-testid="prognostic-result"]').innerText().catch(() => "none")).replace(/\n/g, " | ").slice(0, 600));
  await shots(page, "overview-p18b-breastdoc");
  await browser.close();
}
// 2. tb-medonc-doc (Medical Oncology): the same patient, "Ask to join"
{
  const { browser, page } = await session("tb-medonc-doc");
  await page.goto(`${BASE}${NEWCASE}?identifier=${encodeURIComponent("VXH/26/004218")}`); await settle(page);
  await page.waitForSelector('[data-testid="patient-case-files"]', { timeout: 15000 }).catch(() => problems.push("medonc-doc: no patient-case-files card"));
  notes.push("medonc card: " + (await page.locator('[data-testid="patient-case-files"]').innerText().catch(() => "MISSING")).replace(/\n/g, " | "));
  const ask = page.getByRole("button", { name: /Ask to join/ }).first();
  if (await ask.count()) { await ask.click(); await settle(page); await page.screenshot({ path: path.join(OUT, "newcase-ask-dialog-medonc-light-1366.png") }); notes.push("ask dialog: " + (await page.getByRole("dialog").innerText().catch(() => "MISSING")).replace(/\n/g, " | ").slice(0, 400)); await page.keyboard.press("Escape"); }
  else problems.push("medonc-doc: no Ask to join button");
  await shots(page, "newcase-patient-medonc");
  await browser.close();
}
fs.writeFileSync(path.join(OUT, "notes.txt"), notes.join("\n") + "\n\nPROBLEMS:\n" + problems.join("\n") + "\n");
console.log(notes.join("\n")); console.log("\nPROBLEMS (" + problems.length + "):\n" + problems.join("\n"));
