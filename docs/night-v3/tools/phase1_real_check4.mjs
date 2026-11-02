// Real-app check of items 1.6 (More menu: move or take off) and 1.5 (agenda row fields). Passwords read in code, never printed.
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
const T = (s) => s.replace(/\n/g, " | ").slice(0, 400); const j = async (r) => { try { return await r.json(); } catch { return null; } };
{
  const { browser, page } = await session("tb-breast-doc"); const rq = page.request;
  let r = await rq.get(`${BASE}/api/tb/meetings/open`, { headers: H }); let b = await j(r); notes.push(`A0 open meetings: ${r.status()} n=${(b?.meetings || []).length}`);
  await page.goto(`${BASE}/tb-nik/cases/TB-2026-0001`); await settle(page);
  await page.getByTestId("more-menu").click().catch(() => problems.push("A1: no More menu")); await settle(page);
  const menu = await page.getByRole("menu").innerText().catch(() => "MISSING"); notes.push(`A1 More menu on a sent Case File: ${T(menu)}`);
  if (!/Move to another meeting/.test(menu)) problems.push("A1: no Move to another meeting item");
  for (const theme of ["light", "dark"]) { await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme); await page.waitForTimeout(250); await page.screenshot({ path: path.join(OUT, `more-menu-sent-${theme}-1366.png`) }); }
  await page.getByRole("menuitem", { name: /Move to another meeting/ }).click().catch(() => problems.push("A2: cannot open the move dialog")); await settle(page);
  notes.push(`A2 move dialog: ` + T(await page.getByRole("dialog").innerText().catch(() => "MISSING")));
  await page.screenshot({ path: path.join(OUT, "move-dialog-light-1366.png") });
  await page.setViewportSize(SIZES[1]); await page.waitForTimeout(300); await page.screenshot({ path: path.join(OUT, "move-dialog-light-390.png") });
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1); if (wide) problems.push("A2: sideways scroll on the phone with the move dialog");
  await page.keyboard.press("Escape"); await page.setViewportSize(SIZES[0]);
  r = await rq.get(`${BASE}/api/tb/cases/TB-2026-0001`, { headers: H }); b = await j(r); notes.push(`A3 board_send: ${JSON.stringify(b?.board_send || b?.case?.board_send || null).slice(0, 200)}`);
  await browser.close();
}
{
  const { browser, page } = await session("tb-mdt"); const rq = page.request;
  const r = await rq.get(`${BASE}/api/tb/meetings`, { headers: H }); const b = await j(r);
  const m = (b?.meetings || [])[0]; notes.push(`B0 meetings for the coordinator: ${(b?.meetings || []).length}, first ${m?.id} ${m?.status} ${m?.date}`);
  if (m) {
    const ar = await rq.get(`${BASE}/api/tb/meetings/${m.id}/agenda`, { headers: H }).catch(() => null);
    const ab = ar ? await j(ar) : null;
    const rows = [].concat(...Object.values(ab?.lists || ab?.agenda_lists || {}).filter(Array.isArray)).concat(ab?.rows || ab?.agenda || []);
    const first = rows.find((x) => x && typeof x === "object" && ("waiting_on" in x || "new_since_sent" in x || "presenter" in x));
    notes.push(`B1 agenda row fields: ${ar ? ar.status() : "n/a"} ${first ? JSON.stringify({ waiting_on: first.waiting_on, new_since_sent: first.new_since_sent, presenter: first.presenter }).slice(0, 200) : "no row with the fields (" + Object.keys(ab || {}).join(",") + ")"}`);
    await page.goto(`${BASE}/tb-nik/meetings/${m.id}`); await settle(page);
    await page.screenshot({ path: path.join(OUT, "agenda-mdt-light-1366.png"), fullPage: true });
  }
  await browser.close();
}
fs.writeFileSync(path.join(OUT, "notes4.txt"), notes.join("\n") + "\n\nPROBLEMS:\n" + problems.join("\n") + "\n");
console.log(notes.join("\n")); console.log("\nPROBLEMS (" + problems.length + "):\n" + problems.join("\n"));
