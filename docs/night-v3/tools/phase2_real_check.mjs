// Real-app check of item 2.11: the four Phase 2 synthetic patients of the demo HIS (ovary, prostate, stomach, Hodgkin lymphoma) become
// Case Files as the MDT Coordinator, their reports are read by the real models, and the checklist gaps and the glance values are listed;
// screenshots of each Case File (laptop and phone, light and dark). Passwords read in code, never printed.
// Usage: OUT=/data/vaidyx/night-v3/shots/phase2 node docs/night-v3/tools/phase2_real_check.mjs
import fs from "node:fs"; import os from "node:os"; import path from "node:path";
import { chromium } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";
const BASE = "http://127.0.0.1:7000"; const OUT = process.env.OUT || "/data/vaidyx/night-v3/shots/phase2"; fs.mkdirSync(OUT, { recursive: true });
function password(user) {
  for (const line of fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")) {
    if (!line || line.startsWith("#") || !line.includes("\t")) continue; const [u, p] = line.split("\t"); if (u === user) return p;
  }
  throw new Error("no login " + user);
}
const SIZES = [{ width: 1366, height: 768 }, { width: 390, height: 844 }];
const H = { "X-Requested-With": "tb-nik" }; const problems = []; const notes = [];
const PATIENTS = [
  { tag: "ovary", identifier: "VXH/26/004220", protocol: "ovary", setting: "advanced", department: "Gynaecologic Oncology" },
  { tag: "prostate", identifier: "VXH/26/004221", protocol: "prostate", setting: "locally_extensive", department: "Urology" },
  { tag: "stomach", identifier: "VXH/26/004222", protocol: "stomach", setting: "locally_advanced", department: "Gastrointestinal Surgery" },
  { tag: "lymphoma", identifier: "VXH/26/004223", protocol: "lymphoma", setting: "adult_hodgkin", department: "Haematology" },
];
const j = async (r) => { try { return await r.json(); } catch { return null; } };
async function session(user) {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: SIZES[0] }); const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push(`${user}: pageerror ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && !/403|401/.test(m.text())) problems.push(`${user}: console ${m.text().slice(0, 160)}`); });
  const r = await page.request.post(BASE + "/api/auth/login", { data: { username: user, password: password(user), remember: false }, headers: H });
  if (!r.ok()) throw new Error(`login ${user} HTTP ${r.status()}`);
  return { browser, page };
}
async function settle(page) { await page.waitForLoadState("networkidle", { timeout: 6000 }).catch(() => {}); await page.waitForTimeout(500); }
async function shots(page, name) {
  for (const size of SIZES) { await page.setViewportSize(size); for (const theme of ["light", "dark"]) {
    await page.evaluate((t) => { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("tbnik.theme", t); } catch {} }, theme); await settle(page);
    const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    if (wide) problems.push(`${name} ${theme} ${size.width}: sideways scroll`);
    await page.screenshot({ path: path.join(OUT, `${name}-${theme}-${size.width}.png`), fullPage: true });
  } }
  await page.setViewportSize(SIZES[0]);
}
// a job is finished only when its state says so (done == total still runs the summary and the briefs)
const finished = (job) => !!job && /done|finished|complete|failed|error/.test(String(job.state || job.status || ""));
const { browser, page } = await session("tb-mdt"); const rq = page.request;
const made = [];
for (const p of PATIENTS) {
  const r = await rq.post(`${BASE}/api/tb/cases/from-his`, { headers: H, data: { identifier: p.identifier, protocol: p.protocol, setting: p.setting, department: p.department, hospital_level: "optimal" } });
  const b = await j(r);
  if (r.status() === 409 && b?.existing?.case_id) { notes.push(`${p.tag}: exists already as ${b.existing.case_id}`); made.push({ ...p, case_id: b.existing.case_id, job: null }); continue; }
  if (!r.ok()) { problems.push(`${p.tag}: create HTTP ${r.status()} ${JSON.stringify(b).slice(0, 300)}`); continue; }
  notes.push(`${p.tag}: created ${b.case?.case_id} job ${b.job} total ${b.total} his ${JSON.stringify(b.his).slice(0, 200)}`);
  made.push({ ...p, case_id: b.case?.case_id, job: b.job, total: b.total });
}
// wait for the model jobs (the reader and the reasoner): up to 40 minutes in all
const t0 = Date.now(); let first = true;
for (const m of made) {
  if (!m.job) continue;
  while (Date.now() - t0 < 40 * 60 * 1000) {
    const r = await rq.get(`${BASE}/api/tb/jobs/${m.job}`, { headers: H }); const job = await j(r);
    if (first) { notes.push(`job shape: ${JSON.stringify(job).slice(0, 400)}`); first = false; }
    if (finished(job)) { notes.push(`${m.tag}: job finished ${JSON.stringify({ status: job.status, state: job.state, done: job.done, total: job.total, errors: job.errors }).slice(0, 300)} after ${Math.round((Date.now() - t0) / 1000)} s`); break; }
    await new Promise((res) => setTimeout(res, 10000));
  }
}
for (const m of made) {
  if (!m.case_id) continue;
  const r = await rq.get(`${BASE}/api/tb/cases/${m.case_id}/steps`, { headers: H }); const s = await j(r);
  if (!r.ok()) { problems.push(`${m.tag}: steps HTTP ${r.status()}`); continue; }
  const reqs = (s?.pre_authorization?.groups || []).flatMap((g) => g.items || g.rows || []);
  const by = {}; for (const q of reqs) by[q.status || q.state] = (by[q.status || q.state] || 0) + 1;
  const open = reqs.filter((q) => !["satisfied", "present", "ok", "not_applicable", "done"].includes(q.status || q.state)).map((q) => `${q.id || q.record_id}:${q.status || q.state}`);
  const docs = (s?.documents || []).map((d) => `${d.doc_type}${d.state && d.state !== "ready" ? "(" + d.state + ")" : ""}`);
  const glance = (s?.glance || []).flatMap((g) => (g.rows || []).map((f) => `${f.label}=${String(f.value || "").slice(0, 40)}`));
  const warnings = (s?.warnings || []).map((w) => `${w.kind}: ${String(w.text).slice(0, 120)}`);
  notes.push(`${m.tag} ${m.case_id}: requirements ${JSON.stringify(by)}; open ${open.join(", ") || "none"}`);
  notes.push(`${m.tag} documents (${docs.length}): ${docs.join(", ")}`);
  notes.push(`${m.tag} glance (${glance.length}): ${glance.join(" | ").slice(0, 1200)}`);
  notes.push(`${m.tag} warnings: ${warnings.join(" || ") || "none"}`);
  notes.push(`${m.tag} todo: ${JSON.stringify((s?.todo || s?.to_do || []).slice(0, 6)).slice(0, 600)}`);
  await page.goto(`${BASE}/tb-nik/cases/${m.case_id}`); await settle(page);
  const chip = await page.getByText(/Checklist built \(draft\)/).first().innerText().catch(() => "MISSING"); notes.push(`${m.tag} header draft chip: ${chip}`);
  if (chip === "MISSING") problems.push(`${m.tag}: no draft chip in the header`);
  await shots(page, `casefile-${m.tag}`);
  await page.goto(`${BASE}/tb-nik/cases/${m.case_id}?step=check`).catch(() => {}); await settle(page);
  const checkLink = page.getByRole("link", { name: /^Check/ }).first(); if (await checkLink.count()) { await checkLink.click().catch(() => {}); await settle(page); }
  await shots(page, `casefile-${m.tag}-check`);
}
await page.goto(`${BASE}/tb-nik/cases`); await settle(page); await shots(page, "caselist-coordinator");
await browser.close();
fs.writeFileSync(path.join(OUT, "phase2_real_check_notes.txt"), notes.concat(["", "PROBLEMS:", ...problems]).join("\n") + "\n");
console.log(notes.join("\n")); console.log("\nPROBLEMS:\n" + (problems.join("\n") || "none"));
process.exit(problems.length ? 1 : 0);
