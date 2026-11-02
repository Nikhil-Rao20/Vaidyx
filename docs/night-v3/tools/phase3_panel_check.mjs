// Real-app check of item 3.2: the Board decisions panel of a synthetic Case File with recorded rounds (laptop and phone, light and dark).
// Usage: OUT=/data/vaidyx/night-v3/shots/phase3 node docs/night-v3/tools/phase3_panel_check.mjs [case_id] [user]
import fs from "node:fs"; import os from "node:os"; import path from "node:path";
import { chromium } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";
const BASE = "http://127.0.0.1:7000"; const OUT = process.env.OUT || "/data/vaidyx/night-v3/shots/phase3"; fs.mkdirSync(OUT, { recursive: true });
const CASE = process.argv[2] || "TB-2026-0005"; const USER = process.argv[3] || "tb-mdt";
if (/bharath/i.test(CASE)) throw new Error("never the real case");
function password(user) { for (const line of fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")) { if (!line || line.startsWith("#") || !line.includes("\t")) continue; const [u, p] = line.split("\t"); if (u === user) return p; } throw new Error("no login " + user); }
const SIZES = [{ width: 1366, height: 768 }, { width: 390, height: 844 }]; const H = { "X-Requested-With": "tb-nik" }; const problems = []; const notes = [];
const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: SIZES[0] }); const page = await ctx.newPage();
page.on("pageerror", (e) => problems.push(`pageerror ${e.message}`));
page.on("console", (m) => { if (m.type() === "error" && !/403|401|WebSocket|ws:/.test(m.text())) problems.push(`console ${m.text().slice(0, 160)}`); });
const r = await page.request.post(BASE + "/api/auth/login", { data: { username: USER, password: password(USER), remember: false }, headers: H });
if (!r.ok()) throw new Error(`login HTTP ${r.status()}`);
const settle = async () => { await page.waitForLoadState("networkidle", { timeout: 6000 }).catch(() => {}); await page.waitForTimeout(400); };
for (const size of SIZES) { await page.setViewportSize(size); for (const theme of ["light", "dark"]) {
  await page.goto(`${BASE}/tb-nik/cases/${encodeURIComponent(CASE)}/board`); await settle();
  await page.evaluate((t) => { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("tbnik.theme", t); } catch {} }, theme); await settle();
  const panel = page.getByTestId("board-form");
  const seen = await panel.isVisible().catch(() => false);
  if (!seen) problems.push(`${theme} ${size.width}: panel not visible`);
  else { await panel.scrollIntoViewIfNeeded(); notes.push(`${theme} ${size.width}: rounds ${await page.locator("[data-testid^=board-round-]").count()}; text starts: ${(await panel.innerText()).replace(/\s+/g, " ").slice(0, 300)}`); }
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  if (wide) problems.push(`${theme} ${size.width}: sideways scroll`);
  await page.screenshot({ path: path.join(OUT, `board-decisions-${theme}-${size.width}.png`), fullPage: true });
} }
await browser.close();
fs.writeFileSync(path.join(OUT, "phase3_panel_check_notes.txt"), notes.concat(["", "PROBLEMS:", ...problems]).join("\n") + "\n");
console.log(notes.join("\n")); console.log("PROBLEMS:", problems.length ? problems.join("\n") : "none");
