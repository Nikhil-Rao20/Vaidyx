// Real-app check of item 3.1 (night-v3 Phase 3): the MDT Coordinator opens a meeting in session on a synthetic Case File, fills the
// six-step decision form (screens of every step, laptop and phone, light and dark), saves it, and the record carries the new fields;
// a correction through the API on the meeting day makes version 2. Passwords read in code, never printed. Never the real case.
// Usage: OUT=/data/vaidyx/night-v3/shots/phase3 node docs/night-v3/tools/phase3_real_check.mjs [case_id]
import fs from "node:fs"; import os from "node:os"; import path from "node:path";
import { chromium } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";
const BASE = "http://127.0.0.1:7000"; const WEB = process.env.WEB || BASE + "/tb-nik"; const OUT = process.env.OUT || "/data/vaidyx/night-v3/shots/phase3"; fs.mkdirSync(OUT, { recursive: true });
const CASE = process.argv[2] || "TB-2026-0005";
if (/bharath/i.test(CASE)) throw new Error("never the real case");
function password(user) {
  for (const line of fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")) {
    if (!line || line.startsWith("#") || !line.includes("\t")) continue; const [u, p] = line.split("\t"); if (u === user) return p;
  }
  throw new Error("no login " + user);
}
const SIZES = [{ width: 1366, height: 768 }, { width: 390, height: 844 }];
const H = { "X-Requested-With": "tb-nik" }; const problems = []; const notes = [];
const j = async (r) => { try { return await r.json(); } catch { return null; } };
async function session(user) {
  const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: SIZES[0] }); const page = await ctx.newPage();
  page.on("pageerror", (e) => problems.push(`${user}: pageerror ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error" && !/403|401|WebSocket|ws:/.test(m.text())) problems.push(`${user}: console ${m.text().slice(0, 160)}`); });
  const r = await page.request.post(BASE + "/api/auth/login", { data: { username: user, password: password(user), remember: false }, headers: H });
  if (!r.ok()) throw new Error(`login ${user} HTTP ${r.status()}`);
  return { browser, page };
}
async function settle(page) { await page.waitForLoadState("networkidle", { timeout: 6000 }).catch(() => {}); await page.waitForTimeout(400); }
async function shots(page, name, before) {
  for (const size of SIZES) { await page.setViewportSize(size); for (const theme of ["light", "dark"]) {
    await page.evaluate((t) => { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("tbnik.theme", t); } catch {} }, theme); await settle(page);
    if (before) await before();
    const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    if (wide) problems.push(`${name} ${theme} ${size.width}: sideways scroll`);
    await page.screenshot({ path: path.join(OUT, `${name}-${theme}-${size.width}.png`), fullPage: true });
  } }
  await page.setViewportSize(SIZES[0]);
}
const today = new Date(); const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
const { browser, page } = await session("tb-mdt"); const rq = page.request;
// a meeting in session that has this Case File, else a planned one of today, else a new one
let list = (await j(await rq.get(`${BASE}/api/tb/meetings`, { headers: H })))?.meetings || [];
notes.push(`meetings: ${list.length}; shape ${JSON.stringify(list[0] || {}).slice(0, 300)}`);
let m = list.find((x) => x.status === "in_session") || list.find((x) => x.status === "planned" && String(x.date || "").startsWith(iso));
if (!m) {
  const r = await rq.post(`${BASE}/api/tb/meetings`, { headers: H, data: { date: iso, time: "14:00", title: "Phase 3 check (synthetic)", video: false } });
  const b = await j(r); if (!r.ok()) throw new Error(`create meeting HTTP ${r.status()} ${JSON.stringify(b).slice(0, 300)}`);
  m = b.meeting; notes.push(`created meeting ${m.id} ${m.date}`);
}
const mid = m.id || m.meeting_id; notes.push(`meeting ${mid} status ${m.status}`);
let view = await j(await rq.get(`${BASE}/api/tb/meetings/${mid}`, { headers: H })); notes.push(`view keys: ${Object.keys(view || {}).join(",")}`);
const onAgenda = (v) => JSON.stringify(v || {}).includes(`"${CASE}"`);
if (!onAgenda(view)) {
  const r = await rq.post(`${BASE}/api/tb/meetings/${mid}/agenda/add`, { headers: H, data: { case_id: CASE, list: "discussion", reason: "Phase 3 decision record check (synthetic)" } });
  const b = await j(r); notes.push(`agenda add ${CASE}: HTTP ${r.status()} ${JSON.stringify(b?.message || b?.detail || "").slice(0, 200)}`);
  if (!r.ok()) problems.push(`agenda add failed HTTP ${r.status()} ${JSON.stringify(b).slice(0, 300)}`);
}
if (m.status !== "in_session") {
  const r = await rq.post(`${BASE}/api/tb/meetings/${mid}/start`, { headers: H, data: {} });
  const b = await j(r); notes.push(`start: HTTP ${r.status()} ${JSON.stringify(b).slice(0, 200)}`);
  if (!r.ok()) problems.push(`start failed HTTP ${r.status()}`);
}
{ const r = await rq.post(`${BASE}/api/tb/meetings/${mid}/current`, { headers: H, data: { case_id: CASE } }); notes.push(`current ${CASE}: HTTP ${r.status()}`); }
await page.goto(`${WEB}/meetings/${mid}`); await settle(page);
await page.getByTestId("control-view").waitFor({ timeout: 15000 }).catch(() => problems.push("no control view"));
await page.getByRole("tab", { name: "Decision" }).click().catch(() => problems.push("no Decision tab"));
await page.getByTestId("decision-form").waitFor({ timeout: 10000 }).catch(() => problems.push("no decision form"));
const form = page.getByTestId("decision-form");
await shots(page, "decision-step1", () => form.scrollIntoViewIfNeeded());
await page.getByTestId("decision-step-2").click();
await page.locator("#d-text").fill("Neoadjuvant chemotherapy (carboplatin and paclitaxel, three cycles), then interval cytoreductive surgery; the board noted the ascitic cytology and the CA-125 of 1,246 U/mL as recorded");
await page.getByRole("radio", { name: "Curative" }).click();
await page.getByRole("button", { name: "Chemotherapy", exact: true }).click(); await page.getByRole("button", { name: "Surgery", exact: true }).click();
await page.locator("#d-sequence").fill("Chemotherapy then surgery, as the board stated it");
await shots(page, "decision-step2", () => page.getByTestId("decision-step-2").scrollIntoViewIfNeeded());
await page.getByTestId("decision-step-3").click();
await page.getByRole("radio", { name: "Yes", exact: true }).first().click().catch(() => {});
await shots(page, "decision-step3", () => page.getByTestId("decision-panel-3").scrollIntoViewIfNeeded());
await page.getByTestId("decision-step-4").click();
await page.getByTestId("add-investigation").click();
await page.getByLabel("Investigation 1", { exact: true }).fill("Germline BRCA testing");
await page.getByLabel("Department for investigation 1").fill("Medical Genetics");
await page.getByTestId("add-referral").click();
await page.getByLabel("Kind of referral 1").selectOption("nutrition");
await page.getByLabel("Department for referral 1").fill("Nutrition");
await shots(page, "decision-step4", () => page.getByTestId("decision-panel-4").scrollIntoViewIfNeeded());
await page.getByTestId("decision-step-5").click();
notes.push(`responsible clinician pre-filled: ${JSON.stringify(await page.locator("#d-responsible_doctor").inputValue().catch(() => null))}`);
if (!(await page.locator("#d-responsible_doctor").inputValue().catch(() => ""))) await page.locator("#d-responsible_doctor").fill("Dr Meena Iyer (Gynaecologic Oncology)");
await shots(page, "decision-step5", () => page.getByTestId("decision-panel-5").scrollIntoViewIfNeeded());
await page.getByTestId("decision-step-6").click();
await shots(page, "decision-step6", () => page.getByTestId("decision-panel-6").scrollIntoViewIfNeeded());
const posted = page.waitForResponse((r) => r.request().method() === "POST" && r.url().includes(`/cases/${encodeURIComponent(CASE)}/decision`), { timeout: 20000 });
await page.getByTestId("save-decision").click();
const resp = await posted.catch(() => null);
const saved = resp ? await j(resp) : null;
notes.push(`save: HTTP ${resp?.status()} record ${saved?.record?.id} outcome_type ${saved?.record?.outcome_type} intent ${saved?.record?.intent} modalities ${JSON.stringify(saved?.record?.modalities)} informed_by ${saved?.record?.informed_by} inform_by ${saved?.record?.inform_by_date} actions ${JSON.stringify((saved?.record?.actions || []).map((a) => [a.task, a.department, a.kind]))}`);
if (!resp || !resp.ok()) problems.push(`save failed: ${JSON.stringify(saved).slice(0, 400)}`);
await page.waitForTimeout(800);
await shots(page, "decision-saved", () => form.scrollIntoViewIfNeeded());
if (saved?.record?.id) {
  // the coordinator corrects the key worker on the meeting day (no reason needed), then the decision text (a reason needed)
  const rid = saved.record.id;
  let r = await rq.post(`${BASE}/api/tb/cases/${encodeURIComponent(CASE)}/board-records/${rid}/correct`, { headers: H, data: { changes: { key_worker: "Sister Anitha, oncology nurse, extension 2210" }, reason: "" } });
  let b = await j(r); notes.push(`correct key_worker: HTTP ${r.status()} version ${b?.record?.version} corrected ${JSON.stringify(b?.record?.corrected || b).slice(0, 200)}`);
  r = await rq.post(`${BASE}/api/tb/cases/${encodeURIComponent(CASE)}/board-records/${rid}/correct`, { headers: H, data: { changes: { decision_text: saved.record.decision_text + " (typing slip corrected)" }, reason: "" } });
  b = await j(r); notes.push(`correct decision without reason: HTTP ${r.status()} ${JSON.stringify(b?.detail || b).slice(0, 160)}`);
  if (r.status() !== 400) problems.push("a decision text correction without a reason was not refused");
  r = await rq.post(`${BASE}/api/tb/cases/${encodeURIComponent(CASE)}/board-records/${rid}/correct`, { headers: H, data: { changes: { decision_text: saved.record.decision_text + " (typing slip corrected)" }, reason: "Typing slip in the read-back" } });
  b = await j(r); notes.push(`correct decision with reason: HTTP ${r.status()} version ${b?.record?.version} versions ${(b?.record?.versions || []).length}`);
  const st = await j(await rq.get(`${BASE}/api/tb/cases/${encodeURIComponent(CASE)}`, { headers: H }));
  const acts = (st?.state?.actions || []).filter((a) => a.board_record === rid);
  notes.push(`case actions of the record: ${JSON.stringify(acts.map((a) => [a.label, a.department, a.kind, a.status, a.due]))}`);
  const mins = await rq.get(`${BASE}/api/tb/sessions/${mid}/minutes`, { headers: H }).catch(() => null);
  notes.push(`minutes: HTTP ${mins?.status()}`);
  if (mins?.ok()) { const mm = await j(mins); const dec = (mm?.cases || []).find((c) => c.case_id === CASE)?.decision; notes.push(`minutes decision fields: ${String(JSON.stringify(dec?.fields || dec || null)).slice(0, 600)}`); }
}
await browser.close();
fs.writeFileSync(path.join(OUT, "phase3_real_check_notes.txt"), notes.concat(["", "PROBLEMS:", ...problems]).join("\n") + "\n");
console.log(notes.join("\n")); console.log("PROBLEMS:", problems.length ? problems.join("\n") : "none");
