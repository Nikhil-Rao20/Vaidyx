// Real-app check of items 1.4 (send dialog), 1.7 (pick a value), 1.11 (join buttons, filter, time input). Passwords read in code, never printed.
import fs from "node:fs"; import os from "node:os"; import path from "node:path";
import { chromium } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";
const BASE = "http://127.0.0.1:7000"; const OUT = process.env.OUT; fs.mkdirSync(OUT, { recursive: true });
function password(user) { for (const line of fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")) { if (!line || line.startsWith("#")) continue; const [u, p] = line.split("\t"); if (u === user && p) return p; } throw new Error("no login " + user); }
const SIZES = [{ width: 1366, height: 768 }, { width: 390, height: 844 }];
const problems = []; const notes = []; const H = { "X-Requested-With": "tb-nik" };
async function session(user) {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: SIZES[0] }); const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push(`${user}: pageerror ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && !/40[134]/.test(m.text())) problems.push(`${user}: console ${m.text().slice(0, 160)}`); });
  const r = await page.request.post(BASE + "/api/auth/login", { data: { username: user, password: password(user), remember: false }, headers: H });
  if (!r.ok()) throw new Error(`login ${user} HTTP ${r.status()}`);
  return { browser, page };
}
async function settle(page) { await page.waitForLoadState("networkidle", { timeout: 4000 }).catch(() => {}); await page.waitForTimeout(400); }
async function shots(page, name, opts = {}) {
  for (const size of SIZES) { await page.setViewportSize(size); for (const theme of ["light", "dark"]) {
    await page.evaluate((t) => { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("tbnik.theme", t); } catch {} }, theme); await settle(page);
    const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    if (wide) problems.push(`${name} ${theme} ${size.width}: sideways scroll`);
    await page.screenshot({ path: path.join(OUT, `${name}-${theme}-${size.width}.png`), fullPage: opts.fullPage ?? true });
  } }
  await page.setViewportSize(SIZES[0]); await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
}
const T = (s) => s.replace(/\n/g, " | ").slice(0, 500);
// A. Home: the two Join buttons, and the filter popover (tb-breast-doc)
{
  const { browser, page } = await session("tb-breast-doc");
  await page.goto(`${BASE}/tb-nik/cases`); await settle(page);
  const jc = await page.getByRole("button", { name: /Join a Case File/ }).count(); const jm = await page.getByRole("button", { name: /Join a meeting/ }).count();
  notes.push(`A1 join buttons: case=${jc} meeting=${jm}`); if (!jc || !jm) problems.push("A1: join buttons missing");
  await shots(page, "home-join-breastdoc", { fullPage: false });
  await page.getByRole("button", { name: /^Filters?/ }).first().click().catch(() => problems.push("A2: no Filter button")); await settle(page);
  notes.push(`A2 filter panel: ` + T(await page.getByRole("dialog").first().innerText().catch(async () => (await page.locator('[role="dialog"], [data-state="open"]').first().innerText().catch(() => "MISSING")))));
  await page.screenshot({ path: path.join(OUT, "home-filter-breastdoc-light-1366.png") });
  await page.setViewportSize(SIZES[1]); await settle(page); await page.screenshot({ path: path.join(OUT, "home-filter-breastdoc-light-390.png") });
  await page.keyboard.press("Escape"); await page.setViewportSize(SIZES[0]);
  // B. the Check step of TB-DEMO-P18B: pick a value, then undo
  await page.goto(`${BASE}/tb-nik/cases/TB-DEMO-P18B/check`); await settle(page);
  const problemRows = page.locator('[data-testid="problem-row"]'); notes.push(`B1 problem rows: ${await problemRows.count()}`);
  const useBtn = page.getByRole("button", { name: /Use this value for the board/ });
  if (!(await useBtn.count())) { await problemRows.first().click().catch(() => {}); await settle(page); }
  notes.push(`B2 use-this-value buttons: ${await useBtn.count()}`);
  if (await useBtn.count()) {
    await shots(page, "check-pick-before-breastdoc");
    await useBtn.first().click(); await settle(page); await page.waitForTimeout(1500);
    const picked = await page.getByText(/The board uses/).first().innerText().catch(() => "MISSING"); notes.push(`B3 picked: ${T(picked)}`); if (picked === "MISSING") problems.push("B3: no picked line after the pick");
    await shots(page, "check-pick-after-breastdoc");
    const undo = page.getByRole("button", { name: /^Undo/ }).first();
    if (await undo.count()) { await undo.click(); await settle(page); await page.waitForTimeout(1200); notes.push(`B4 after undo, use buttons: ${await useBtn.count()}, picked lines: ${await page.getByText(/The board uses/).count()}`); }
    else problems.push("B4: no Undo button after the pick");
  } else problems.push("B2: no Use this value button (no discordance on P18B?)");
  // C. the multi-step send dialog on TB-DEMO-P18B (never pressed Send)
  await page.goto(`${BASE}/tb-nik/cases/TB-DEMO-P18B`); await settle(page);
  await page.getByTestId("send-to-board").click().catch(() => problems.push("C1: no send-to-board button")); await settle(page);
  const dlg = page.getByTestId("mark-ready-dialog");
  notes.push(`C1 step 1: ` + T(await dlg.innerText().catch(() => "MISSING")));
  await shots(page, "send-step1-breastdoc", { fullPage: false });
  for (let i = 0; i < 3; i++) { const n = dlg.getByTestId("send-next"); if (await n.count() && await n.isEnabled()) { await n.click(); await settle(page); } }
  notes.push(`C2 step 4: ` + T(await dlg.innerText().catch(() => "MISSING")));
  await shots(page, "send-step4-breastdoc", { fullPage: false });
  await page.keyboard.press("Escape"); await settle(page);
  // E. settings: the digest time input
  await page.goto(`${BASE}/tb-nik/settings`); await settle(page);
  notes.push(`E1 native time inputs on settings: ${await page.locator('input[type="time"]').count()}`);
  await browser.close();
}
// D. the coordinator's meetings page and an agenda
{
  const { browser, page } = await session("tb-mdt");
  await page.goto(`${BASE}/tb-nik/meetings`); await settle(page);
  await shots(page, "meetings-mdt", { fullPage: false });
  const first = page.locator('a[href*="/meetings/"]').first();
  if (await first.count()) { await first.click(); await settle(page); notes.push(`D1 agenda url: ${page.url()}`); await shots(page, "agenda-mdt"); }
  await browser.close();
}
fs.writeFileSync(path.join(OUT, "notes3.txt"), notes.join("\n") + "\n\nPROBLEMS:\n" + problems.join("\n") + "\n");
console.log(notes.join("\n")); console.log("\nPROBLEMS (" + problems.length + "):\n" + problems.join("\n"));
