// Real-app check of item 3.4: the Case summaries of the decided synthetic Case Files are built again on demand (the real model), then the
// Summary section, the Overview, the header line and the list row of one of them are shot (laptop and phone, light and dark) as the
// MDT Coordinator, and the list search finds a word of the summary line. Passwords read in code, never printed. Never the real case.
// Usage: OUT=/data/vaidyx/night-v3/shots/phase3 node docs/night-v3/tools/phase3_summary_check.mjs
import fs from "node:fs"; import os from "node:os"; import path from "node:path";
import { chromium } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";
const BASE = "http://127.0.0.1:7000"; const OUT = process.env.OUT || "/data/vaidyx/night-v3/shots/phase3"; fs.mkdirSync(OUT, { recursive: true });
function password(user) { for (const line of fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")) { if (!line || line.startsWith("#") || !line.includes("\t")) continue; const [u, p] = line.split("\t"); if (u === user) return p; } throw new Error("no login " + user); }
const SIZES = [{ width: 1366, height: 768 }, { width: 390, height: 844 }]; const H = { "X-Requested-With": "tb-nik" }; const notes = []; const problems = [];
const j = async (r) => { try { return await r.json(); } catch { return null; } };
const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: SIZES[0] }); const page = await ctx.newPage();
page.on("pageerror", (e) => problems.push(`pageerror ${e.message}`));
page.on("console", (m) => { if (m.type() === "error" && !/403|401|WebSocket|ws:/.test(m.text())) problems.push(`console ${m.text().slice(0, 160)}`); });
const lg = await page.request.post(BASE + "/api/auth/login", { data: { username: "tb-mdt", password: password("tb-mdt"), remember: false }, headers: H });
if (!lg.ok()) throw new Error("login " + lg.status()); const rq = page.request;
for (const cid of process.env.SKIP_REBUILD ? [] : ["TB-2026-0005", "TB-2026-0006", "TB-2026-0007", "TB-2026-0008"]) {
  const r = await rq.post(`${BASE}/api/tb/cases/${cid}/case-summary`, { headers: H, data: {} }); const b = await j(r);
  const v = b?.version || b; const rem = {}; for (const x of v?.removed || []) rem[x.reason] = (rem[x.reason] || 0) + 1;
  const iso = JSON.stringify(v?.sections || []).match(/\b20\d\d-\d\d-\d\d\b/g) || [];
  notes.push(`${cid}: rebuild HTTP ${r.status()} version ${v?.n} seconds ${v?.seconds} removed ${JSON.stringify(rem)} iso dates in sentences ${iso.length} ${r.ok() ? "" : JSON.stringify(b).slice(0, 200)}`);
  if (!r.ok()) problems.push(`${cid}: rebuild failed`);
}
const cf = await j(await rq.get(`${BASE}/api/tb/cases/TB-2026-0005`, { headers: H }));
notes.push(`summary_line: ${JSON.stringify(cf?.case?.summary_line)}`);
notes.push(`state.artefacts.case_summary keys: ${Object.keys(cf?.state?.artefacts?.case_summary || {}).join(",")}; versions listed ${(cf?.state?.artefacts?.case_summary?.versions || []).length}`);
const settle = async () => { await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {}); await page.waitForTimeout(500); };
async function shots(name, url, ready) {
  for (const size of SIZES) { await page.setViewportSize(size); for (const theme of ["light", "dark"]) {
    await page.goto(url); await settle();
    await page.evaluate((t) => { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("tbnik.theme", t); } catch {} }, theme); await settle();
    if (ready) { const ok = await page.getByTestId(ready).first().isVisible().catch(() => false); if (!ok) problems.push(`${name} ${theme} ${size.width}: ${ready} not visible`); }
    const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    if (wide) problems.push(`${name} ${theme} ${size.width}: sideways scroll`);
    await page.screenshot({ path: path.join(OUT, `${name}-${theme}-${size.width}.png`), fullPage: true });
  } }
  await page.setViewportSize(SIZES[0]);
}
await shots("case-summary-section", `${BASE}/tb-nik/cases/TB-2026-0005/summary`, "section-summary");
notes.push(`summary section text: ${(await page.getByTestId("section-summary").innerText().catch(() => "")).replace(/\s+/g, " ").slice(0, 700)}`);
await shots("case-summary-overview", `${BASE}/tb-nik/cases/TB-2026-0005`, null);
await shots("caselist-summary-line", `${BASE}/tb-nik/cases`, null);
const word = String(cf?.case?.summary_line?.text || "").split(/[\s,;:]+/).find((w) => w.length > 6 && /^[a-z]+$/i.test(w)) || "";
if (word) {
  await page.goto(`${BASE}/tb-nik/cases`); await settle();
  const box = page.getByPlaceholder(/Search a patient/).first();
  await box.fill(word).catch(() => problems.push("no search box")); await page.waitForTimeout(800);
  const rows = await page.getByText("Lalitha Subramanian").count();
  notes.push(`list search for "${word}": rows with TB-2026-0005 = ${rows}`);
  await page.screenshot({ path: path.join(OUT, `caselist-search-summary-line-light-1366.png`), fullPage: true });
}
await browser.close();
fs.writeFileSync(path.join(OUT, "phase3_summary_check_notes.txt"), notes.concat(["", "PROBLEMS:", ...problems]).join("\n") + "\n");
console.log(notes.join("\n")); console.log("PROBLEMS:", problems.length ? problems.join("\n") : "none");
