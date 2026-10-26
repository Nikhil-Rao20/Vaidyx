// Real-app check of items 1.3 (linked rows), 1.8 (resident sign-off buttons) and 1.9 (doctor break-glass). Passwords read in code, never printed.
import fs from "node:fs"; import os from "node:os"; import path from "node:path";
import { chromium } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";
const BASE = "http://127.0.0.1:7000"; const OUT = process.env.OUT; fs.mkdirSync(OUT, { recursive: true });
function password(user) {
  const res = fs.readFileSync("/data/vaidyx/night-v3/.resident_login", "utf8").trim().split(/\s+/);
  if (res[0] === user) return res[1];
  for (const line of fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")) { if (!line || line.startsWith("#")) continue; const [u, p] = line.split("\t"); if (u === user && p) return p; }
  throw new Error("no login " + user);
}
const RESIDENT = fs.readFileSync("/data/vaidyx/night-v3/.resident_login", "utf8").trim().split(/\s+/)[0];
const SIZES = [{ width: 1366, height: 768 }, { width: 390, height: 844 }];
const problems = []; const notes = []; const H = { "X-Requested-With": "tb-nik" };
async function session(user) {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: SIZES[0] }); const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push(`${user}: pageerror ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && !/403|401/.test(m.text())) problems.push(`${user}: console ${m.text().slice(0, 160)}`); });
  const r = await page.request.post(BASE + "/api/auth/login", { data: { username: user, password: password(user), remember: false }, headers: H });
  if (!r.ok()) throw new Error(`login ${user} HTTP ${r.status()}`);
  return { browser, page };
}
async function settle(page) { await page.waitForLoadState("networkidle", { timeout: 4000 }).catch(() => {}); await page.waitForTimeout(400); }
async function shots(page, name) {
  for (const size of SIZES) { await page.setViewportSize(size); for (const theme of ["light", "dark"]) {
    await page.evaluate((t) => { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("tbnik.theme", t); } catch {} }, theme); await settle(page);
    const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    if (wide) problems.push(`${name} ${theme} ${size.width}: sideways scroll`);
    await page.screenshot({ path: path.join(OUT, `${name}-${theme}-${size.width}.png`), fullPage: true });
  } }
  await page.setViewportSize(SIZES[0]);
}
const j = async (r) => { try { return await r.json(); } catch { return null; } };
// A. break-glass API flow as tb-medonc-doc on TB-DEMO-P19
{
  const { browser, page } = await session("tb-medonc-doc"); const rq = page.request;
  let r = await rq.get(`${BASE}/api/tb/cases/TB-DEMO-P19`, { headers: H }); let b = await j(r);
  notes.push(`A1 GET case before: ${r.status()} ${JSON.stringify(b?.detail).slice(0, 200)}`);
  if (!(r.status() === 403 && b?.detail?.break_glass === true)) problems.push("A1: expected 403 with break_glass true");
  r = await rq.post(`${BASE}/api/tb/break-glass`, { headers: H, data: { case_id: "TB-DEMO-P19", reason: "Night-v3 check of the read-only window (synthetic)" } }); b = await j(r);
  notes.push(`A2 open: ${r.status()} ${JSON.stringify(b).slice(0, 200)}`); if (r.status() !== 200) problems.push("A2: open failed");
  r = await rq.get(`${BASE}/api/tb/cases/TB-DEMO-P19`, { headers: H }); notes.push(`A3 GET case in window: ${r.status()}`); if (r.status() !== 200) problems.push("A3: case not readable in window");
  r = await rq.get(`${BASE}/api/tb/cases/TB-DEMO-P19/steps`, { headers: H }); b = await j(r); notes.push(`A4 steps: ${r.status()} role=${b?.role} mode=${b?.mode}`);
  r = await rq.put(`${BASE}/api/tb/cases/TB-DEMO-P19/reason`, { headers: H, data: { value: "new_diagnosis" } }); b = await j(r);
  notes.push(`A5 PUT reason in window: ${r.status()} ${JSON.stringify(b?.detail).slice(0, 160)}`); if (!(r.status() === 403 && b?.detail?.code === "break_glass_read_only")) problems.push("A5: write not refused as break_glass_read_only");
  r = await rq.get(`${BASE}/api/tb/case-list`, { headers: H }); b = await j(r); const listed = (b?.cases || []).some((c) => c.case_id === "TB-DEMO-P19"); notes.push(`A6 listed in case-list: ${listed}`); if (listed) problems.push("A6: windowed case listed");
  r = await rq.get(`${BASE}/api/tb/me`, { headers: H }); b = await j(r); notes.push(`A7 me.break_glass: ${JSON.stringify(b?.break_glass).slice(0, 200)}`);
  // UI: the Case File opens read-only with the banner
  await page.goto(`${BASE}/tb-nik/cases/TB-DEMO-P19`); await settle(page);
  const banner = await page.getByText(/Read-only until/).first().innerText().catch(() => "MISSING"); notes.push(`A8 banner: ${banner}`); if (banner === "MISSING") problems.push("A8: no read-only banner");
  await shots(page, "breakglass-open-medonc");
  r = await rq.delete(`${BASE}/api/tb/break-glass`, { headers: H, data: { case_id: "TB-DEMO-P19" } }); b = await j(r); notes.push(`A9 close: ${r.status()} ${JSON.stringify(b).slice(0, 120)}`);
  r = await rq.get(`${BASE}/api/tb/cases/TB-DEMO-P19`, { headers: H }); notes.push(`A10 GET after close: ${r.status()}`); if (r.status() !== 403) problems.push("A10: still open after close");
  await browser.close();
}
// B. UI 403 page with "Open with a reason" as tb-rad-doc on TB-005 (no owner: creator only)
{
  const { browser, page } = await session("tb-rad-doc"); const rq = page.request;
  let r = await rq.get(`${BASE}/api/tb/cases/TB-005`, { headers: H }); const b = await j(r); notes.push(`B0 rad-doc GET TB-005: ${r.status()} break_glass=${b?.detail?.break_glass}`);
  await page.goto(`${BASE}/tb-nik/cases/TB-005`); await settle(page);
  notes.push(`B1 url: ${page.url()} error-state: ${await page.locator('[data-testid="casefile-error"]').count()}`);
  const btn = page.getByRole("button", { name: /Open with a reason/ }).first();
  if (await btn.count()) {
    await shots(page, "breakglass-403-raddoc");
    await btn.click(); await settle(page);
    notes.push(`B2 dialog: ` + (await page.getByRole("dialog").innerText().catch(() => "MISSING")).replace(/\n/g, " | ").slice(0, 400));
    await page.screenshot({ path: path.join(OUT, "breakglass-dialog-raddoc-light-1366.png") });
    await page.getByRole("dialog").getByRole("textbox").first().fill("Night-v3 check of the 403 page (synthetic)");
    await page.getByRole("dialog").getByRole("button", { name: /Open/ }).last().click(); await settle(page); await page.waitForTimeout(1500);
    const banner = await page.getByText(/Read-only until/).first().innerText().catch(() => "MISSING"); notes.push(`B3 after open: url=${page.url()} banner=${banner}`); if (banner === "MISSING") problems.push("B3: no banner after opening from the 403 page");
    await shots(page, "breakglass-opened-raddoc");
    r = await rq.delete(`${BASE}/api/tb/break-glass`, { headers: H, data: { case_id: "TB-005" } }); notes.push(`B4 close: ${r.status()}`);
  } else { problems.push("B1: no Open with a reason button"); await page.screenshot({ path: path.join(OUT, "breakglass-403-raddoc-missing.png") }); }
  await browser.close();
}
// C. the list as tb-breast-doc: linked rows under their heading
{
  const { browser, page } = await session("tb-breast-doc");
  await page.goto(`${BASE}/tb-nik/cases`); await settle(page);
  const heading = await page.getByText(/Linked Case Files of other departments/).first().innerText().catch(() => "MISSING"); notes.push(`C1 heading: ${heading}`); if (heading === "MISSING") problems.push("C1: no linked heading");
  const chip = await page.getByText(/Owned by .*read-only/).first().innerText().catch(() => "MISSING"); notes.push(`C2 chip: ${chip}`);
  const views = await page.locator('[data-testid="views-bar"], nav[aria-label*="iew"]').first().innerText().catch(() => "n/a"); notes.push(`C3 views: ${views.replace(/\n/g, " | ").slice(0, 200)}`);
  await shots(page, "list-linked-breastdoc");
  await browser.close();
}
// D. the resident's Check step on TB-DEMO-P19: "Send to Dr X for sign-off"
{
  const { browser, page } = await session(RESIDENT);
  await page.goto(`${BASE}/tb-nik/cases/TB-DEMO-P19/check`); await settle(page);
  const n = await page.getByRole("button", { name: /Send to Dr .* for sign-off/ }).count(); notes.push(`D1 resident sign-off buttons on Check: ${n}`); if (!n) problems.push("D1: no resident sign-off button on the Check step");
  await shots(page, "resident-check-signoff");
  await page.goto(`${BASE}/tb-nik/cases/TB-DEMO-P19`); await settle(page);
  const st = await page.locator('[data-testid="staging-card"]').innerText().catch(() => "none"); notes.push(`D2 resident staging card: ${st.replace(/\n/g, " | ").slice(0, 300)}`);
  await browser.close();
}
fs.writeFileSync(path.join(OUT, "notes2.txt"), notes.join("\n") + "\n\nPROBLEMS:\n" + problems.join("\n") + "\n");
console.log(notes.join("\n")); console.log("\nPROBLEMS (" + problems.length + "):\n" + problems.join("\n"));
