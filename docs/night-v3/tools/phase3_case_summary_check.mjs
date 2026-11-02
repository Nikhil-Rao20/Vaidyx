// Real-model check of item 3.3: decisions recorded on synthetic Case Files (the lenient board-records route, as the old board tab),
// the Case summary built in the background after each, and on demand for a file decided earlier; the numbers per version are printed.
// Usage: OUT=/data/vaidyx/night-v3/shots/phase3 node docs/night-v3/tools/phase3_case_summary_check.mjs
import fs from "node:fs"; import os from "node:os"; import path from "node:path";
import { chromium } from "/home/bharath.tangella/vaidyx/Vaidyx/web/tb-nik/node_modules/playwright/index.mjs";
const BASE = "http://127.0.0.1:7000"; const OUT = process.env.OUT || "/data/vaidyx/night-v3/shots/phase3"; fs.mkdirSync(OUT, { recursive: true });
function password(user) { for (const line of fs.readFileSync(path.join(os.homedir(), "vaidyx/.tb_v2_demo_logins"), "utf8").split("\n")) { if (!line || line.startsWith("#") || !line.includes("\t")) continue; const [u, p] = line.split("\t"); if (u === user) return p; } throw new Error("no login " + user); }
const H = { "X-Requested-With": "tb-nik" }; const notes = []; const problems = []; const j = async (r) => { try { return await r.json(); } catch { return null; } };
const browser = await chromium.launch(); const ctx = await browser.newContext(); const page = await ctx.newPage();
const lg = await page.request.post(BASE + "/api/auth/login", { data: { username: "tb-mdt", password: password("tb-mdt"), remember: false }, headers: H });
if (!lg.ok()) throw new Error("login " + lg.status()); const rq = page.request;
const today = new Date().toISOString().slice(0, 10);
const RECORDS = {
  "TB-2026-0006": { outcome: "decision", decision_text: "External beam radiotherapy to the prostate and pelvis with androgen deprivation therapy, as discussed by the board; the PSA of 38.6 ng/mL and the Gleason 4+3=7 (ISUP 3) biopsy were noted as recorded.", intent: "curative", modalities: ["radiotherapy", "endocrine"], sequence: "Androgen deprivation first, radiotherapy to follow", responsible_doctor: "Dr Ramesh Pillai (Urology, demo)", trial_considered: "no", investigations: [{ item: "Bone scan", department: "Nuclear Medicine" }], next_review: "2027-01-15", board_date: today, recorded_by: "Meera Choudhary", participants: "Urology, Radiation Oncology, Medical Oncology, Radiology, Pathology" },
  "TB-2026-0007": { outcome: "deferred", awaited: "Endoscopic ultrasonography report", awaited_from: "Gastroenterology", decision_text: "Deferred until the endoscopic ultrasonography report is in the Case File.", board_date: today, recorded_by: "Meera Choudhary", participants: "Gastrointestinal Surgery, Medical Oncology, Radiology, Pathology" },
  "TB-2026-0008": { outcome: "decision", decision_text: "Chemotherapy as per the NCG regimen for classical Hodgkin lymphoma stage IIB, with an interim PET-CT after two cycles; the board noted the SUVmax of 14.2 and the B symptoms as recorded.", intent: "curative", modalities: ["chemotherapy"], responsible_doctor: "Dr Kavya Menon (Haematology, demo)", fitness_considered: "yes", patient_preference: "yes", patient_preference_note: "Wishes to continue work during treatment", referrals: [{ kind: "fertility", department: "Gynaecologic Oncology", note: "Fertility preservation counselling before chemotherapy" }], next_step: "Interim PET-CT after cycle 2", next_step_date: "2026-12-20", board_date: today, recorded_by: "Meera Choudhary", participants: "Haematology, Medical Oncology, Radiology, Pathology, Nuclear Medicine" },
};
for (const [cid, body] of Object.entries(RECORDS)) {
  const r = await rq.post(`${BASE}/api/tb/cases/${cid}/board-records`, { headers: H, data: body }); const b = await j(r);
  notes.push(`${cid}: board-records HTTP ${r.status()} record ${b?.id || b?.record?.id || JSON.stringify(b).slice(0, 200)} outcome ${b?.outcome_type || b?.record?.outcome_type}`);
  if (!r.ok()) problems.push(`${cid}: record failed`);
}
{ const r = await rq.post(`${BASE}/api/tb/cases/TB-2026-0005/case-summary`, { headers: H, data: {} }); const b = await j(r);
  notes.push(`TB-2026-0005: on-demand build HTTP ${r.status()} version ${b?.n} seconds ${b?.seconds} ${r.ok() ? "" : JSON.stringify(b).slice(0, 300)}`); }
const t0 = Date.now(); const want = ["TB-2026-0005", "TB-2026-0006", "TB-2026-0007", "TB-2026-0008"]; const seen = {};
while (Object.keys(seen).length < want.length && Date.now() - t0 < 15 * 60 * 1000) {
  for (const cid of want) {
    if (seen[cid]) continue;
    const r = await rq.get(`${BASE}/api/tb/cases/${cid}/case-summary`, { headers: H }); const b = await j(r);
    if (r.ok() && b?.version?.n) {
      seen[cid] = b;
      const v = b.version; const secs = (v.sections || []).map((s) => `${s.id}:${s.sentences ? s.sentences.length : (s.blocks || []).reduce((n, x) => n + (x.sentences || []).length, 0)}${s.built_by === "model" ? "(model)" : ""}`).join(" ");
      const rem = {}; for (const x of v.removed || []) rem[x.reason] = (rem[x.reason] || 0) + 1;
      notes.push(`${cid}: version ${v.n} trigger ${v.trigger?.kind} seconds ${v.seconds} sections ${secs} removed ${JSON.stringify(rem)} model_error ${JSON.stringify(v.model_error || null)} status ${JSON.stringify(b.status)}`);
      const uncited = []; for (const s of v.sections || []) for (const x of (s.sentences || []).concat(...(s.blocks || []).map((bk) => bk.sentences || []))) if (!(x.citations || []).length && !x.code && !x.fixed && !x.from_fields) uncited.push(x.text.slice(0, 80));
      if (uncited.length) problems.push(`${cid}: uncited sentences ${JSON.stringify(uncited)}`);
      const firstModel = (v.sections || []).find((s) => s.id === "presentation")?.sentences?.slice(0, 2).map((x) => x.text + " [" + (x.citations || []).map((c) => c.doc_title || c.kind).join("; ") + "]");
      notes.push(`${cid}: presentation starts: ${JSON.stringify(firstModel)}`);
      const rounds = (v.sections || []).find((s) => s.id === "rounds"); notes.push(`${cid}: rounds blocks ${(rounds?.blocks || []).length}; first block sentences: ${JSON.stringify((rounds?.blocks?.[0]?.sentences || []).slice(0, 3).map((x) => x.text.slice(0, 120)))}`);
      const status = (v.sections || []).find((s) => s.id === "status"); notes.push(`${cid}: status: ${JSON.stringify((status?.sentences || []).map((x) => x.text.slice(0, 100)))}`);
    }
  }
  if (Object.keys(seen).length < want.length) await new Promise((res) => setTimeout(res, 10000));
}
for (const cid of want) if (!seen[cid]) problems.push(`${cid}: no Case summary after ${Math.round((Date.now() - t0) / 1000)} s`);
await browser.close();
fs.writeFileSync(path.join(OUT, "phase3_case_summary_check_notes.txt"), notes.concat(["", "PROBLEMS:", ...problems]).join("\n") + "\n");
console.log(notes.join("\n")); console.log("PROBLEMS:", problems.length ? problems.join("\n") : "none");
