// Item 1.2 of docs/meetings-v2/PLAN.md: an API check of every Tumour Board meeting route against the running app (:7000), by role and by
// meeting state, on throw-away synthetic meetings. Synthetic patients only: Rekha Sharma TB-2026-0011 and Mohammed Arif TB-2026-0010 (the
// spare test files) and a fresh Case File for Parvathi Murugan (VXH/26/004209, made once by the coordinator, reused on a rerun). Never the
// real case. Passwords are read in lib.mjs and never printed; the meeting join code is never printed or written.
//
// Run (the WebSocket is out of scope):
//   export PATH=/data/vaidyx/tools/node/current/bin:$PATH LD_LIBRARY_PATH=/data/vaidyx/venv/pdf/lib
//   node docs/meetings-v2/tools/api_check.mjs
// Prints one line per check and a summary; writes /data/vaidyx/meetings-v2/api_check.json. Every meeting it makes is titled
// "... (synthetic)" and is ended (in session) or cancelled (planned) in a finally block, even after an error.
import fs from "node:fs";
import { open, BASE, H, j } from "./lib.mjs";

const OUTFILE = "/data/vaidyx/meetings-v2/api_check.json";
const STATEFILE = "/data/vaidyx/meetings-v2/api_check_state.json";  // the fresh Case File id, so a rerun reuses it
const U = { C: "tb-mdt", G: "tb-gynonc-doc", R: "tb-rad-doc", M: "tb-medonc-doc", B: "tb-breast-doc", A: "tb-root" };
const TAG = { C: "coordinator", G: "presenter (owner doctor)", R: "member doctor", M: "other doctor", B: "doctor not in the meeting", A: "root admin" };
const REKHA = "TB-2026-0011", ARIF = "TB-2026-0010";
const NOCASE = "TB-2026-9999";

const pad = (n) => String(n).padStart(2, "0");
const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const NOW = new Date();
const TODAY = isoDate(NOW);
const plus = (n) => { const d = new Date(NOW); d.setDate(d.getDate() + n); return isoDate(d); };
const NOWHM = `${pad(NOW.getHours())}:${pad(NOW.getMinutes())}`;
const LATE = "23:59";  // planned meeting A: today, after the meeting of today, so a "not discussed" Case File moves there and nowhere else
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const S = {};            // login key -> {browser, ctx, page, rq}
let browser = null;
const made = {};         // name -> meeting id (every meeting this run made)
const rows = [];
const notices = [];      // {step, login, items: [{kind, title}]}
const facts = {};        // small things worth keeping in the JSON (no secrets)
let codeValue = "";      // the join code: used in calls only, never printed or written

// ---- calls and rows ------------------------------------------------------------------------------------------------------------------

async function call(k, method, path, body, { timeout = 120000 } = {}) {
  if (!S[k]) return { s: 0, b: null, ct: "", len: 0, text: "", skipped: true };
  const opts = { method, headers: { ...H }, timeout, failOnStatusCode: false };
  if (body !== undefined) {
    if (typeof body === "string") { opts.data = body; opts.headers["Content-Type"] = "application/json"; } else opts.data = body;
  }
  let r;
  try {
    r = await S[k].rq.fetch(BASE + path, opts);
  } catch (e) {
    return { s: -1, b: null, ct: "", len: 0, text: "", err: e.message.slice(0, 120) };
  }
  const ct = r.headers()["content-type"] || "";
  const disp = r.headers()["content-disposition"] || "";
  if (ct.includes("json")) return { s: r.status(), b: await j(r), ct, disp, len: 0, text: "" };
  const buf = await r.body().catch(() => Buffer.alloc(0));
  return { s: r.status(), b: null, ct, disp, len: buf.length, text: ct.includes("text") ? buf.toString("utf8") : "" };
}

function reason(r) {
  if (r.skipped) return "skipped (no login)";
  if (r.err) return "request error " + r.err;
  const d = r.b && typeof r.b === "object" ? r.b.detail : null;
  if (d && typeof d === "object" && !Array.isArray(d)) return `${d.code || ""}: ${String(d.message || "").slice(0, 120)}`;
  if (typeof d === "string") return d.slice(0, 130);
  if (Array.isArray(d)) return "validation " + JSON.stringify(d).slice(0, 110);
  return "";
}

function plain(r) {
  const d = r.b && typeof r.b === "object" ? r.b.detail : null;
  const m = d && typeof d === "object" && !Array.isArray(d) ? d.message : d;
  return typeof m === "string" && m.length >= 6 && !/Traceback|\{'|object at 0x|NoneType/.test(m);
}

function who(k, as) { return `${as || TAG[k]} (${U[k]})`; }

function rec(route, role, state, expected, got, verdict, why = "") {
  rows.push({ n: rows.length + 1, route, role, state, expected: String(expected), got, verdict, why });
  console.log(`${verdict.padEnd(4)} ${route} | ${role} | ${state} | exp ${expected} | got ${got}${why ? " | " + why : ""}`);
}

const gotOf = (r) => `${r.s}${reason(r) ? " " + reason(r) : ""}`;

// One call, one row: PASS when the status is one of `expect`; a 5xx is always FAIL; a refusal with no plain message is a NOTE.
// opts.note: the row is a NOTE whatever the status (an expectation that is a design question), with `why`.
async function ck(route, k, state, method, path, body, expect, why = "", opts = {}) {
  const r = await call(k, method, path, body, opts);
  if (r.skipped) { rec(route, who(k, opts.as), state, [].concat(expect).join("/"), "not run (login missing)", "NOTE", why); return r; }
  const exp = [].concat(expect);
  let v = exp.includes(r.s) ? "PASS" : (opts.failAs || "FAIL");
  if (r.s >= 500 || r.s < 0) v = "FAIL";
  if (opts.note && r.s < 500 && r.s >= 0) v = "NOTE";
  let w = why;
  if (r.s >= 400 && r.s < 500 && v === "PASS" && !plain(r)) { v = "NOTE"; w = (w ? w + "; " : "") + "refusal without a plain message"; }
  rec(route, who(k, opts.as), state, exp.join("/"), gotOf(r), v, w);
  return r;
}

// A content check (no call): PASS when cond, else FAIL (or opts.failAs).
function is(route, role, state, expected, got, cond, why = "", failAs = "FAIL") {
  rec(route, role, state, expected, got, cond ? "PASS" : failAs, why);
  return cond;
}

// ---- reads ---------------------------------------------------------------------------------------------------------------------------

async function view(mid, k = "C") { return (await call(k, "GET", `/api/tb/meetings/${mid}`)).b || {}; }
async function ids(mid, list = "discussion") { const v = await view(mid); return ((v.agenda || {})[list] || []).map((x) => x.case_id); }
async function onAny(mid, cid) { const v = await view(mid); return ["discussion", "noting", "not_ready"].some((l) => ((v.agenda || {})[l] || []).some((x) => x.case_id === cid)); }
async function caseOf(cid) {
  const b = (await call("C", "GET", `/api/tb/cases/${cid}`)).b || {};
  const c = b.case || {};
  return { meeting_id: c.meeting_id || "", board_date: c.board_date || "", board_send: c.board_send || null, ready: !!(c.board_ready && c.board_ready.at),
           records: ((b.state || {}).board_records || []), documents: b.documents || [] };
}
async function noticeIds(k) {
  const r = await call(k, "GET", "/api/tb/notifications?limit=300");
  return new Set(((r.b || {}).notifications || []).map((n) => n.id));
}
async function noticeNew(step, k, before) {
  const r = await call(k, "GET", "/api/tb/notifications?limit=300");
  const items = ((r.b || {}).notifications || []).filter((n) => !before.has(n.id)).map((n) => ({ kind: n.kind, title: String(n.title || "").slice(0, 100) }));
  notices.push({ step, login: U[k], items });
  console.log(`     notices after ${step} for ${U[k]}: ${items.length ? items.map((x) => x.kind + ": " + x.title).join(" ; ") : "none"}`);
  return items;
}
async function snap(keys) { const o = {}; for (const k of keys) if (S[k]) o[k] = await noticeIds(k); return o; }

// ---- set-up --------------------------------------------------------------------------------------------------------------------------

async function signIn() {
  for (const k of Object.keys(U)) {
    try {
      const o = await open(U[k], { browser });
      browser = o.browser; S[k] = o;
    } catch (e) {
      console.log(`login ${U[k]}: not available (${e.message.slice(0, 60)})`);
      facts["login_missing_" + k] = U[k];
    }
  }
}

async function freshCase() {
  let st = {};
  try { st = JSON.parse(fs.readFileSync(STATEFILE, "utf8")); } catch { st = {}; }
  const body = { identifier: "VXH/26/004209", protocol: "cervix", setting: "locally_advanced", department: "Gynaecologic Oncology", hospital_level: "essential", urgency: 3 };
  const r = await call("C", "POST", "/api/tb/cases/from-his", body, { timeout: 240000 });
  let cid = "", job = "";
  if (r.s === 200) {
    cid = ((r.b || {}).case || {}).case_id || ""; job = (r.b || {}).job || "";
    rec("POST /cases/from-his (set-up)", who("C"), "-", "200", `${r.s} created ${cid}`, "PASS", "fresh synthetic Case File Parvathi Murugan for the decision checks");
    facts.created_case = cid;
  } else if (r.s === 409) {
    cid = ((r.b || {}).existing || {}).case_id || st.fresh_case || "";
    rec("POST /cases/from-his (set-up)", who("C"), "-", "200/409", `${r.s} exists ${cid}`, "PASS", "one Case File per patient and cancer: reused");
  } else {
    rec("POST /cases/from-his (set-up)", who("C"), "-", "200", gotOf(r), "FAIL", "the fresh Case File could not be made; decision checks fall back to TB-2026-0011");
    return "";
  }
  if (job) {
    const t0 = Date.now(); let jj = {};
    while (Date.now() - t0 < 20 * 60 * 1000) {
      jj = (await call("C", "GET", `/api/tb/jobs/${job}`)).b || {};
      if (["finished", "failed"].includes(jj.state)) break;
      await sleep(10000);
    }
    rec("GET /jobs/{job} (set-up)", who("C"), "-", "finished", `${jj.state} ${jj.done}/${jj.total} in ${Math.round((Date.now() - t0) / 1000)} s`, jj.state === "finished" ? "PASS" : "NOTE");
  }
  fs.writeFileSync(STATEFILE, JSON.stringify({ fresh_case: cid }, null, 1));
  return cid;
}

async function mk(name, date, time, extra = {}) {
  const r = await ck("POST /meetings", "C", "-", "POST", "/api/tb/meetings",
    { date, time, title: `API check ${name} (synthetic)`, video: false, ...extra }, 200, `create ${name}`);
  const id = ((r.b || {}).meeting || {}).id;
  if (id) made[name] = id;
  return id;
}

// ---- the checks ----------------------------------------------------------------------------------------------------------------------

async function noMeetingRoutes() {
  let r = await ck("GET /meetings", "C", "-", "GET", "/api/tb/meetings", undefined, 200);
  is("GET /meetings", who("C"), "-", "can_manage true", String((r.b || {}).can_manage), (r.b || {}).can_manage === true);
  r = await ck("GET /meetings", "G", "-", "GET", "/api/tb/meetings", undefined, 200);
  is("GET /meetings", who("G"), "-", "can_manage false", String((r.b || {}).can_manage), (r.b || {}).can_manage === false);
  await ck("GET /meetings", "A", "-", "GET", "/api/tb/meetings", undefined, 403, "root admin is not placed");
  await ck("GET /meetings/open", "G", "-", "GET", "/api/tb/meetings/open", undefined, 200);
  await ck("GET /meetings/open", "A", "-", "GET", "/api/tb/meetings/open", undefined, 403);
  r = await ck("GET /meetings/decision-fields", "C", "-", "GET", "/api/tb/meetings/decision-fields", undefined, 200);
  is("GET /meetings/decision-fields", who("C"), "-", "5 outcomes, fields", `${((r.b || {}).outcomes || []).length} outcomes, ${((r.b || {}).fields || []).length} fields`,
    ((r.b || {}).outcomes || []).length === 5 && ((r.b || {}).fields || []).length > 10);
  await ck("GET /meetings/decision-fields", "A", "-", "GET", "/api/tb/meetings/decision-fields", undefined, 403);
  await ck("GET /scheduler/status", "A", "-", "GET", "/api/tb/scheduler/status", undefined, 200);
  await ck("GET /scheduler/status", "C", "-", "GET", "/api/tb/scheduler/status", undefined, 403);
  await ck("GET /meetings/{mid}", "C", "-", "GET", "/api/tb/meetings/S20990101-zzzz", undefined, 404, "no such meeting");
  await ck("POST /meetings/{mid}/start", "C", "-", "POST", "/api/tb/meetings/S20990101-zzzz/start", {}, 404, "no such meeting");

  // create: bad input and refusals
  await ck("POST /meetings", "C", "-", "POST", "/api/tb/meetings", {}, 400, "no date");
  await ck("POST /meetings", "C", "-", "POST", "/api/tb/meetings", { date: "2026-13-45" }, 400, "impossible date");
  await ck("POST /meetings", "C", "-", "POST", "/api/tb/meetings", { date: plus(30), time: "25:00" }, 400, "bad time");
  await ck("POST /meetings", "C", "-", "POST", "/api/tb/meetings", { date: plus(30), minutes_per_case: 0 }, 400, "minutes 0");
  await ck("POST /meetings", "C", "-", "POST", "/api/tb/meetings", { date: plus(30), title: "x".repeat(400) }, 400, "title too long");
  await ck("POST /meetings", "C", "-", "POST", "/api/tb/meetings", "this is not json", 400, "body not JSON");
  await ck("POST /meetings", "G", "-", "POST", "/api/tb/meetings", { date: plus(30), title: "API check refused (synthetic)" }, 403);
  await ck("POST /meetings", "B", "-", "POST", "/api/tb/meetings", { date: plus(30), title: "API check refused (synthetic)" }, 403);
  await ck("POST /meetings", "A", "-", "POST", "/api/tb/meetings", { date: plus(30), title: "API check refused (synthetic)" }, 403);
  const past = await ck("POST /meetings", "C", "-", "POST", "/api/tb/meetings", { date: "2020-01-06", time: "10:00", title: "API check past date (synthetic)" }, 400,
    "a meeting dated in the past", { failAs: "NOTE" });
  const pid = ((past.b || {}).meeting || {}).id;
  if (pid) { made.past = pid; await ck("POST /meetings/{mid}/cancel", "C", "planned (past date)", "POST", `/api/tb/meetings/${pid}/cancel`, { reason: "API check cleanup (synthetic)" }, 200); }
}

async function planned(fresh) {
  const T = made.today, P1 = made.plannedA, P2 = made.plannedB, P3 = made.plannedC;
  let v = await view(P2);
  is("POST /meetings (defaults)", who("C"), "planned", "room and minutes from the hospital defaults", `room "${(v.meeting || {}).room}", ${(v.meeting || {}).minutes_per_case} min`,
    !!(v.meeting || {}).room && !!(v.meeting || {}).minutes_per_case);

  // Rekha starts on a CLOSED meeting (S20261102-6708, decided there): finding 3 (decided case)
  let c = await caseOf(REKHA);
  facts.rekha_before = { meeting_id: c.meeting_id, board_date: c.board_date, ready: c.ready };
  await ck("POST /cases/{id}/meeting/move", "G", "case on a closed meeting (decided there)", "POST", `/api/tb/cases/${REKHA}/meeting/move`, { meeting_id: P1, reason: "API check (synthetic)" }, 200,
    "finding 3: a Case File whose meeting closed cannot be moved; here it was decided there, so a refusal is defensible", { failAs: "NOTE" });

  // agenda/add on a planned meeting
  await ck("POST /meetings/{mid}/agenda/add", "C", "planned", "POST", `/api/tb/meetings/${P1}/agenda/add`, {}, 400, "no case_id");
  await ck("POST /meetings/{mid}/agenda/add", "C", "planned", "POST", `/api/tb/meetings/${P1}/agenda/add`, { case_id: NOCASE }, 400, "Case File does not exist");
  await ck("POST /meetings/{mid}/agenda/add", "C", "planned", "POST", `/api/tb/meetings/${P1}/agenda/add`, { case_id: "TB 2026/../x" }, 400, "bad id");
  await ck("POST /meetings/{mid}/agenda/add", "C", "planned", "POST", `/api/tb/meetings/${P1}/agenda/add`, { case_id: REKHA, list: "later" }, 400, "unknown list");
  await ck("POST /meetings/{mid}/agenda/add", "C", "planned", "POST", `/api/tb/meetings/${P1}/agenda/add`, { case_id: REKHA, list: "not_ready" }, 400, "not ready without a reason");
  await ck("POST /meetings/{mid}/agenda/add", "G", "planned", "POST", `/api/tb/meetings/${P1}/agenda/add`, { case_id: REKHA }, 403);
  await ck("POST /meetings/{mid}/agenda/add", "R", "planned", "POST", `/api/tb/meetings/${P1}/agenda/add`, { case_id: REKHA }, 403);
  await ck("POST /meetings/{mid}/agenda/add", "C", "planned", "POST", `/api/tb/meetings/${P1}/agenda/add`, { case_id: REKHA, list: "discussion" }, 200);
  c = await caseOf(REKHA);
  is("POST /meetings/{mid}/agenda/add (link)", who("C"), "planned", `meeting_id ${P1}, board_date ${TODAY}`, `meeting_id ${c.meeting_id}, board_date ${c.board_date}`,
    c.meeting_id === P1 && c.board_date === TODAY);

  // PUT /meetings/{mid}: bad input, refusals, the reschedule (finding 10)
  await ck("PUT /meetings/{mid}", "G", "planned", "PUT", `/api/tb/meetings/${P1}`, { title: "API check refused (synthetic)" }, 403);
  await ck("PUT /meetings/{mid}", "C", "planned", "PUT", `/api/tb/meetings/${P1}`, { date: "2026-02-30" }, 400, "impossible date");
  await ck("PUT /meetings/{mid}", "C", "planned", "PUT", `/api/tb/meetings/${P1}`, { time: "7pm" }, 400, "bad time");
  await ck("PUT /meetings/{mid}", "C", "planned", "PUT", `/api/tb/meetings/${P1}`, { minutes_per_case: 500 }, 400, "minutes 500");
  await ck("PUT /meetings/{mid}", "C", "-", "PUT", `/api/tb/meetings/S20990101-zzzz`, { title: "x" }, 404, "no such meeting");
  await ck("POST /meetings/{mid}/send-agenda", "C", "planned", "POST", `/api/tb/meetings/${P1}/send-agenda`, {}, 200, "meeting A's agenda goes out before it is moved");
  const before = await snap(["G", "C"]);
  const resched = await ck("PUT /meetings/{mid}", "C", "planned", "PUT", `/api/tb/meetings/${P1}`, { date: plus(14) }, 200, "reschedule the date");
  is("PUT /meetings/{mid} (reschedule)", who("C"), "planned", `meeting date ${plus(14)}`, String(((resched.b || {}).meeting || {}).date), ((resched.b || {}).meeting || {}).date === plus(14));
  c = await caseOf(REKHA);
  is("PUT /meetings/{mid} (reschedule: Case File)", who("C"), "planned", `Rekha board_date ${plus(14)}`, `board_date ${c.board_date}, meeting_id ${c.meeting_id}`,
    c.board_date === plus(14), "finding 10: the agenda Case Files keep the old board date");
  const gn = await noticeNew("reschedule", "G", before.G);
  is("PUT /meetings/{mid} (reschedule: notice)", "owner doctor (tb-gynonc-doc)", "planned (agenda sent)", "a notice of the new date", `${gn.length} new notices`,
    gn.some((x) => x.kind === "agenda" && (/moved/i.test(x.title) || x.title.includes(plus(14).split("-").reverse().join("/")))),
    "finding 10: nobody is told of a new date or time", "FAIL");
  await ck("PUT /meetings/{mid}", "C", "planned", "PUT", `/api/tb/meetings/${P1}`, { date: TODAY, time: LATE }, 200, "date back to today");

  // finding 2: a code made days before a meeting must still work at the meeting
  const c2 = await ck("POST /meetings/{mid}/code", "C", "planned (in 7 days)", "POST", `/api/tb/meetings/${P2}/code`, {}, 200, "a code made a week before the meeting");
  const p2start = new Date(`${plus(7)}T10:00:00`).getTime();
  const exp2 = new Date((c2.b || {}).expires_at).getTime();
  is("POST /meetings/{mid}/code (expiry, finding 2)", who("C"), "planned (in 7 days)", "still valid when the meeting starts",
    `expires ${String((c2.b || {}).expires_at)}, meeting ${plus(7)} 10:00`, exp2 > p2start, "finding 2: the code lasts 12 h from when it is made");

  // move: refusals, bad input, the happy path
  for (const k of ["B", "R", "M"]) await ck("POST /cases/{id}/meeting/move", k, "planned", "POST", `/api/tb/cases/${REKHA}/meeting/move`, { meeting_id: P2 }, 403);
  await ck("POST /cases/{id}/meeting/move", "A", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/move`, { meeting_id: P2 }, 403);
  await ck("POST /cases/{id}/meeting/move", "G", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/move`, {}, 400, "no meeting_id");
  await ck("POST /cases/{id}/meeting/move", "G", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/move`, { meeting_id: P1 }, 400, "the meeting it is on");
  await ck("POST /cases/{id}/meeting/move", "G", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/move`, { meeting_id: "S20990101-zzzz" }, [400, 404], "no such meeting");
  await ck("POST /cases/{id}/meeting/move", "G", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/move`, { meeting_id: "S20261102-6708" }, 400, "target meeting closed");
  await ck("POST /cases/{id}/meeting/move", "G", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/move`, "nope", 400, "body not JSON");
  await ck("POST /cases/{id}/meeting/move", "C", "planned", "POST", `/api/tb/cases/${ARIF}/meeting/move`, { meeting_id: P2 }, 400, "never sent to the board (no ready mark)");
  await ck("POST /cases/{id}/meeting/move", "C", "-", "POST", `/api/tb/cases/${NOCASE}/meeting/move`, { meeting_id: P2 }, 404, "no such Case File");
  const bC = await snap(["C"]);
  await ck("POST /cases/{id}/meeting/move", "G", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/move`, { meeting_id: P2, reason: "API check move (synthetic)" }, 200);
  c = await caseOf(REKHA);
  is("POST /cases/{id}/meeting/move (Case File)", who("G"), "planned", `meeting_id ${P2}, board_date ${plus(7)}, board_send.meeting_id ${P2}`,
    `meeting_id ${c.meeting_id}, board_date ${c.board_date}, board_send.meeting_id ${(c.board_send || {}).meeting_id}`,
    c.meeting_id === P2 && c.board_date === plus(7) && (c.board_send || {}).meeting_id === P2);
  const off1 = await onAny(P1, REKHA), on2 = await onAny(P2, REKHA);
  is("POST /cases/{id}/meeting/move (agendas)", who("G"), "planned", "off meeting A, on meeting B", `on A ${off1}, on B ${on2}`, !off1 && on2);
  const cn = await noticeNew("move", "C", bC.C);
  is("POST /cases/{id}/meeting/move (notice)", who("C"), "planned", "the coordinator is told (agenda)", `${cn.length} new`, cn.some((x) => x.kind === "agenda"));

  // withdraw
  await ck("POST /cases/{id}/meeting/withdraw", "G", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/withdraw`, {}, 400, "no reason");
  await ck("POST /cases/{id}/meeting/withdraw", "G", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/withdraw`, { reason: "ab" }, 400, "reason too short");
  await ck("POST /cases/{id}/meeting/withdraw", "G", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/withdraw`, { reason: "x".repeat(501) }, 400, "reason too long");
  await ck("POST /cases/{id}/meeting/withdraw", "B", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/withdraw`, { reason: "API check (synthetic)" }, 403);
  await ck("POST /cases/{id}/meeting/withdraw", "R", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/withdraw`, { reason: "API check (synthetic)" }, 403);
  await ck("POST /cases/{id}/meeting/withdraw", "G", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/withdraw`, { reason: "API check withdraw (synthetic)" }, 200);
  c = await caseOf(REKHA);
  is("POST /cases/{id}/meeting/withdraw (Case File)", who("G"), "planned", "meeting_id empty, withdrawn recorded, off meeting B",
    `meeting_id "${c.meeting_id}", withdrawn ${!!(c.board_send || {}).withdrawn}, on B ${await onAny(P2, REKHA)}`,
    !c.meeting_id && !!(c.board_send || {}).withdrawn && !(await onAny(P2, REKHA)));
  await ck("POST /cases/{id}/meeting/withdraw", "G", "withdrawn", "POST", `/api/tb/cases/${REKHA}/meeting/withdraw`, { reason: "API check again (synthetic)" }, 400, "not on any agenda");
  await ck("POST /cases/{id}/meeting/move", "G", "withdrawn", "POST", `/api/tb/cases/${REKHA}/meeting/move`, { meeting_id: P1, reason: "API check put back (synthetic)" }, 200, "a withdrawn Case File is put back by a move");
  c = await caseOf(REKHA);
  is("POST /cases/{id}/meeting/move (put back)", who("G"), "planned", `meeting_id ${P1}, withdraw cleared`, `meeting_id ${c.meeting_id}, withdrawn ${!!(c.board_send || {}).withdrawn}`,
    c.meeting_id === P1 && !(c.board_send || {}).withdrawn);

  // cancel (meeting B) and the cancelled state
  await ck("POST /meetings/{mid}/cancel", "G", "planned", "POST", `/api/tb/meetings/${P2}/cancel`, {}, 403);
  await ck("POST /meetings/{mid}/cancel", "C", "planned", "POST", `/api/tb/meetings/${P2}/cancel`, { reason: "API check (synthetic)" }, 200);
  await ck("POST /meetings/{mid}/cancel", "C", "cancelled", "POST", `/api/tb/meetings/${P2}/cancel`, {}, 409, "already cancelled");
  await ck("POST /meetings/{mid}/start", "C", "cancelled", "POST", `/api/tb/meetings/${P2}/start`, {}, 409);
  await ck("PUT /meetings/{mid}", "C", "cancelled", "PUT", `/api/tb/meetings/${P2}`, { title: "API check edit (synthetic)" }, 409);
  await ck("POST /meetings/{mid}/agenda/add", "C", "cancelled", "POST", `/api/tb/meetings/${P2}/agenda/add`, { case_id: ARIF }, 409);
  await ck("POST /meetings/{mid}/code", "C", "cancelled", "POST", `/api/tb/meetings/${P2}/code`, {}, 409);
  await ck("POST /meetings/{mid}/end", "C", "cancelled", "POST", `/api/tb/meetings/${P2}/end`, {}, 409);
  await ck("POST /cases/{id}/meeting/move", "G", "planned", "POST", `/api/tb/cases/${REKHA}/meeting/move`, { meeting_id: P2 }, 400, "target meeting cancelled");

  // end a planned meeting that never started (meeting C)
  await ck("POST /meetings/{mid}/end", "C", "planned (never started)", "POST", `/api/tb/meetings/${P3}/end`, {}, 409,
    "ending a meeting that never started closes it as if it was held (cancel is the planned path)", { failAs: "NOTE" });
  const s3 = (await view(P3)).status;
  if (s3 === "closed") {
    await ck("POST /meetings/{mid}/cancel", "C", "closed", "POST", `/api/tb/meetings/${P3}/cancel`, {}, 409);
    await ck("POST /meetings/{mid}/start", "C", "closed", "POST", `/api/tb/meetings/${P3}/start`, {}, 409);
  }

  // the meeting of today, still planned: agenda (reorder), send-agenda, remind, code, join, waiting list, admit, present
  const DEC = fresh || ARIF;
  await ck("PUT /meetings/{mid}/agenda", "G", "planned", "PUT", `/api/tb/meetings/${T}/agenda`, { discussion: [REKHA] }, 403);
  await ck("PUT /meetings/{mid}/agenda", "C", "planned", "PUT", `/api/tb/meetings/${T}/agenda`, { discussion: [NOCASE] }, 400, "Case File does not exist");
  await ck("PUT /meetings/{mid}/agenda", "C", "planned", "PUT", `/api/tb/meetings/${T}/agenda`, "[1,2]", 400, "body not an object");
  const disc = fresh ? [REKHA, fresh] : [REKHA];
  await ck("PUT /meetings/{mid}/agenda", "C", "planned", "PUT", `/api/tb/meetings/${T}/agenda`, { discussion: disc, noting: [] }, 200);
  if (fresh) {
    await ck("PUT /meetings/{mid}/agenda", "C", "planned", "PUT", `/api/tb/meetings/${T}/agenda`, { discussion: [fresh, REKHA], noting: [] }, 200, "reorder");
    let order = await ids(T);
    is("PUT /meetings/{mid}/agenda (order)", who("C"), "planned", `${fresh}, ${REKHA}`, order.join(", "), order[0] === fresh && order[1] === REKHA);
    await ck("PUT /meetings/{mid}/agenda", "C", "planned", "PUT", `/api/tb/meetings/${T}/agenda`, { discussion: [REKHA, fresh], noting: [] }, 200, "reorder back");
    order = await ids(T);
    is("PUT /meetings/{mid}/agenda (order)", who("C"), "planned", `${REKHA}, ${fresh}`, order.join(", "), order[0] === REKHA && order[1] === fresh);
  }
  c = await caseOf(REKHA);
  const onA = await onAny(P1, REKHA);
  is("PUT /meetings/{mid}/agenda (one agenda)", who("C"), "planned", `Rekha meeting_id ${T}, off meeting A`, `meeting_id ${c.meeting_id}, on A ${onA}`, c.meeting_id === T && !onA);

  const nb = await snap(["G", "R", "M", "B"]);
  await ck("POST /meetings/{mid}/send-agenda", "G", "planned", "POST", `/api/tb/meetings/${T}/send-agenda`, {}, 403);
  const sa = await ck("POST /meetings/{mid}/send-agenda", "C", "planned", "POST", `/api/tb/meetings/${T}/send-agenda`, {}, 200);
  facts.agenda_sent_to = (sa.b || {}).sent_to;
  is("POST /meetings/{mid}/send-agenda (result)", who("C"), "planned", `cases ${disc.length}, sent to departments`, `cases ${(sa.b || {}).cases}, to ${((sa.b || {}).sent_to || []).join(" ")}`,
    (sa.b || {}).cases === disc.length && ((sa.b || {}).sent_to || []).length > 0);
  for (const k of ["G", "R", "M", "B"]) if (nb[k]) await noticeNew("send-agenda", k, nb[k]);
  const gAg = notices.find((x) => x.step === "send-agenda" && x.login === U.G);
  is("POST /meetings/{mid}/send-agenda (notice)", "owner doctor (tb-gynonc-doc)", "planned", "an agenda notice", `${(gAg || { items: [] }).items.filter((x) => x.kind === "agenda").length} agenda notices`,
    !!gAg && gAg.items.some((x) => x.kind === "agenda"));

  await ck("POST /meetings/{mid}/remind", "C", "planned", "POST", `/api/tb/meetings/${T}/remind`, {}, 400, "no case_id");
  await ck("POST /meetings/{mid}/remind", "C", "planned", "POST", `/api/tb/meetings/${T}/remind`, { case_id: ARIF }, 404, "not on the lists");
  await ck("POST /meetings/{mid}/remind", "R", "planned", "POST", `/api/tb/meetings/${T}/remind`, { case_id: REKHA }, 403, "radiology is not the owner");
  await ck("POST /meetings/{mid}/remind", "B", "planned", "POST", `/api/tb/meetings/${T}/remind`, { case_id: REKHA }, 403, "another treating department");
  const rm = await ck("POST /meetings/{mid}/remind", "C", "planned", "POST", `/api/tb/meetings/${T}/remind`, { case_id: REKHA }, [200, 409, 429], "the coordinator reminds the owner (a repeat limit may answer 409/429)");
  facts.remind_ok = rm.s === 200;
  await ck("POST /meetings/{mid}/remind", "G", "planned", "POST", `/api/tb/meetings/${T}/remind`, { case_id: REKHA }, [200, 409, 429], "the owner's doctor");

  await ck("POST /meetings/{mid}/code", "G", "planned", "POST", `/api/tb/meetings/${T}/code`, {}, 403);
  const code = await ck("POST /meetings/{mid}/code", "C", "planned", "POST", `/api/tb/meetings/${T}/code`, {}, 200);
  codeValue = String((code.b || {}).value || "");
  const hrs = ((new Date((code.b || {}).expires_at)).getTime() - Date.now()) / 3600000;
  is("POST /meetings/{mid}/code (shape)", who("C"), "planned", "6 digits", `${/^\d{6}$/.test(codeValue) ? "6 digits" : "not 6 digits"}`, /^\d{6}$/.test(codeValue));
  rec("POST /meetings/{mid}/code (expiry)", who("C"), "planned", "valid until the meeting is over", `expires in ${hrs.toFixed(1)} h from now, whatever the meeting time`, "NOTE",
    "finding 2: 12 h from when it is made, not from the meeting date and time; a code made the evening before expires before a morning meeting");
  v = await view(T, "C");
  is("GET /meetings/{mid} (code shown)", who("C"), "planned", "code shown to the coordinator", v.code ? "shown" : "not shown", !!v.code);
  v = await view(T, "R");
  is("GET /meetings/{mid} (code hidden)", who("R", "member doctor, not joined"), "planned", "no code", v.code ? "shown" : "null", !v.code);

  await ck("POST /meetings/join", "R", "planned", "POST", "/api/tb/meetings/join", { code: "12" }, 404, "not 6 digits (refused before it counts as a try)", { as: "doctor, not joined" });
  let wrong = "000000"; if (wrong === codeValue) wrong = "000001";
  await ck("POST /meetings/join", "R", "planned", "POST", "/api/tb/meetings/join", { code: wrong }, 404, "wrong code", { as: "doctor, not joined" });
  await ck("POST /meetings/join", "A", "planned", "POST", "/api/tb/meetings/join", { code: codeValue }, 403, "root admin is not placed");
  let jr = await ck("POST /meetings/join", "R", "planned", "POST", "/api/tb/meetings/join", { code: codeValue }, 200, "right code", { as: "doctor, not joined" });
  is("POST /meetings/join (status)", who("R"), "planned", "waiting", String((jr.b || {}).status), (jr.b || {}).status === "waiting");
  jr = await ck("POST /meetings/join", "G", "planned", "POST", "/api/tb/meetings/join", { code: codeValue }, 200, "", { as: "doctor, not joined" });
  jr = await ck("POST /meetings/join", "M", "planned", "POST", "/api/tb/meetings/join", { code: codeValue }, 200, "", { as: "doctor, not joined" });
  jr = await ck("POST /meetings/join", "C", "planned", "POST", "/api/tb/meetings/join", { code: codeValue }, 200);
  is("POST /meetings/join (coordinator)", who("C"), "planned", "admitted at once", String((jr.b || {}).status), (jr.b || {}).status === "admitted");
  v = await view(T, "C");
  const waiting = (v.attendance || []).filter((x) => x.status === "waiting").map((x) => x.user).sort();
  is("GET /meetings/{mid} (waiting list)", who("C"), "planned", "R, G, M waiting", waiting.join(" "), [U.R, U.G, U.M].every((u) => waiting.includes(u)));
  v = await view(T, "R");
  is("GET /meetings/{mid} (a waiting doctor)", who("R", "waiting doctor"), "planned", "me waiting, not a member, no chat or questions",
    `me ${(v.me || {}).status}, member ${(v.can || {}).member}, chat ${(v.chat || []).length}, questions ${(v.questions || []).length}`,
    (v.me || {}).status === "waiting" && (v.can || {}).member === false && !(v.chat || []).length && !(v.questions || []).length);
  await ck("GET /meetings/{mid}", "B", "planned", "GET", `/api/tb/meetings/${T}`, undefined, [200, 403],
    "Breast Surgery is neither on the agenda nor joined; 200 only if it is on the hospital's attendance list", { note: true });
  await ck("GET /meetings/{mid}", "A", "planned", "GET", `/api/tb/meetings/${T}`, undefined, 403);

  await ck("POST /meetings/{mid}/admit", "G", "planned", "POST", `/api/tb/meetings/${T}/admit`, { user: U.R }, 403, "", { as: "waiting doctor" });
  await ck("POST /meetings/{mid}/admit", "C", "planned", "POST", `/api/tb/meetings/${T}/admit`, { user: "nobody-here" }, 404, "has not joined");
  await ck("POST /meetings/{mid}/admit", "C", "planned", "POST", `/api/tb/meetings/${T}/admit`, {}, [400, 404], "no user");
  const an = await snap(["R", "G"]);
  await ck("POST /meetings/{mid}/admit", "C", "planned", "POST", `/api/tb/meetings/${T}/admit`, { user: U.R }, 200);
  await ck("POST /meetings/{mid}/admit", "C", "planned", "POST", `/api/tb/meetings/${T}/admit`, { user: U.G.toUpperCase() }, 200, "the login in another case");
  for (const k of ["R", "G"]) await noticeNew("admit", k, an[k]);
  v = await view(T, "R");
  is("GET /meetings/{mid} (admitted)", who("R"), "planned", "member true, status remote", `member ${(v.can || {}).member}, status ${(v.me || {}).status}`,
    (v.can || {}).member === true && (v.me || {}).status === "remote");

  await ck("POST /meetings/{mid}/present", "R", "planned", "POST", `/api/tb/meetings/${T}/present`, { mode: "tv" }, 400, "bad mode");
  await ck("POST /meetings/{mid}/present", "B", "planned", "POST", `/api/tb/meetings/${T}/present`, { mode: "remote" }, 404, "has not joined");
  await ck("POST /meetings/{mid}/present", "R", "planned", "POST", `/api/tb/meetings/${T}/present`, { mode: "room" }, 200);
  await ck("POST /meetings/{mid}/present", "G", "planned", "POST", `/api/tb/meetings/${T}/present`, { mode: "remote" }, 200);

  // live routes before the start
  await ck("POST /meetings/{mid}/chat", "R", "planned", "POST", `/api/tb/meetings/${T}/chat`, { text: "API check: a line before the start (synthetic)" }, 200, "chat is open while planned");
  await ck("POST /meetings/{mid}/chat", "M", "planned", "POST", `/api/tb/meetings/${T}/chat`, { text: "API check (synthetic)" }, 403, "", { as: "waiting doctor" });
  await ck("POST /meetings/{mid}/hand", "R", "planned", "POST", `/api/tb/meetings/${T}/hand`, { raised: true }, 409);
  await ck("POST /meetings/{mid}/reaction", "R", "planned", "POST", `/api/tb/meetings/${T}/reaction`, { kind: "agree" }, 409);
  await ck("POST /meetings/{mid}/questions", "R", "planned", "POST", `/api/tb/meetings/${T}/questions`, { text: "API check (synthetic)" }, 409);
  await ck("PUT /meetings/{mid}/decision-live", "C", "planned", "PUT", `/api/tb/meetings/${T}/decision-live`, { text: "x" }, 409);
  await ck("POST /meetings/{mid}/timer", "C", "planned", "POST", `/api/tb/meetings/${T}/timer`, { action: "start" }, 409);
  await ck("POST /meetings/{mid}/current", "C", "planned", "POST", `/api/tb/meetings/${T}/current`, { case_id: REKHA }, 409);
  await ck("POST /meetings/{mid}/open", "C", "planned", "POST", `/api/tb/meetings/${T}/open`, { kind: "none" }, 409);
  await ck("POST /meetings/{mid}/agents", "C", "planned", "POST", `/api/tb/meetings/${T}/agents`, { role: "nuclear_medicine", on: true }, 409);
  await ck("POST /meetings/{mid}/spotlight", "C", "planned", "POST", `/api/tb/meetings/${T}/spotlight`, { users: [U.R] }, 409);
  await ck("POST /meetings/{mid}/presenting", "R", "planned", "POST", `/api/tb/meetings/${T}/presenting`, { on: true }, 409);
  await ck("POST /meetings/{mid}/cases/{cid}/end", "C", "planned", "POST", `/api/tb/meetings/${T}/cases/${REKHA}/end`, {}, 409);
  await ck("POST /meetings/{mid}/present-allow", "C", "planned", "POST", `/api/tb/meetings/${T}/present-allow`, { user: U.R, allowed: true }, 200, "allowed before the start");
  await ck("POST /meetings/{mid}/cases/{cid}/card", "R", "planned", "POST", `/api/tb/meetings/${T}/cases/${REKHA}/card`, { agree: true }, 409,
    "a card before the meeting has started", { failAs: "NOTE" });
  await ck("POST /meetings/{mid}/cases/{cid}/decision", "C", "planned", "POST", `/api/tb/meetings/${T}/cases/${DEC}/decision`, { outcome: "decision" }, 409,
    "an incomplete body: a 400 means the route does not check that the meeting has started", { failAs: "NOTE" });
}

async function inSession(fresh) {
  const T = made.today, P1 = made.plannedA;
  const DEC = fresh || REKHA;
  await ck("POST /meetings/{mid}/start", "G", "planned", "POST", `/api/tb/meetings/${T}/start`, {}, 403);
  const st = await ck("POST /meetings/{mid}/start", "C", "planned", "POST", `/api/tb/meetings/${T}/start`, {}, 200);
  is("POST /meetings/{mid}/start (floor)", who("C"), "in session", `${REKHA} on the floor`, String(((st.b || {}).current || {}).case_id), ((st.b || {}).current || {}).case_id === REKHA);
  await ck("POST /meetings/{mid}/start", "C", "in session", "POST", `/api/tb/meetings/${T}/start`, {}, 409, "start twice");
  await ck("POST /meetings/{mid}/cancel", "C", "in session", "POST", `/api/tb/meetings/${T}/cancel`, {}, 409, "cancel a running meeting");
  await ck("PUT /meetings/{mid}", "C", "in session", "PUT", `/api/tb/meetings/${T}`, { date: plus(1) }, 409, "date of a running meeting");
  await ck("PUT /meetings/{mid}", "C", "in session", "PUT", `/api/tb/meetings/${T}`, { room: "API check room 2 (synthetic)" }, 200, "room may change");

  // move / withdraw while its meeting is in session (finding 3 B)
  await ck("POST /cases/{id}/meeting/move", "G", "in session", "POST", `/api/tb/cases/${REKHA}/meeting/move`, { meeting_id: P1 }, 400,
    "refused while the meeting runs (sound); finding 3 B: also refused for ever when a meeting is left in session");
  await ck("POST /cases/{id}/meeting/withdraw", "G", "in session", "POST", `/api/tb/cases/${REKHA}/meeting/withdraw`, { reason: "API check (synthetic)" }, 400, "refused while the meeting runs");

  // current
  await ck("POST /meetings/{mid}/current", "G", "in session", "POST", `/api/tb/meetings/${T}/current`, { case_id: REKHA }, 403);
  await ck("POST /meetings/{mid}/current", "C", "in session", "POST", `/api/tb/meetings/${T}/current`, { case_id: NOCASE }, [400, 404], "not on the agenda");
  await ck("POST /meetings/{mid}/current", "C", "in session", "POST", `/api/tb/meetings/${T}/current`, { slide: "x" }, 400, "slide not a number");
  if (fresh) {
    const cr = await ck("POST /meetings/{mid}/current", "C", "in session", "POST", `/api/tb/meetings/${T}/current`, { case_id: fresh }, 200);
    is("POST /meetings/{mid}/current (floor)", who("C"), "in session", fresh, String((cr.b || {}).case_id), (cr.b || {}).case_id === fresh);
    await ck("POST /meetings/{mid}/current", "C", "in session", "POST", `/api/tb/meetings/${T}/current`, { case_id: REKHA }, 200, "back to Rekha");
  }

  // open (Rekha on the floor; tb-gynonc-doc is her presenter)
  const docs = (await caseOf(REKHA)).documents;
  const doc = (docs[0] || {}).doc_id || "";
  const img = (docs.find((d) => JSON.stringify(d.his || {}).includes("imaging_study_ref")) || {}).doc_id || "";
  facts.open_doc = doc; facts.images_doc = img;
  await ck("POST /meetings/{mid}/open", "C", "in session", "POST", `/api/tb/meetings/${T}/open`, { kind: "video" }, 400, "bad kind");
  await ck("POST /meetings/{mid}/open", "C", "in session", "POST", `/api/tb/meetings/${T}/open`, { kind: "record", doc_id: "Dnope0000" }, 404, "no such record");
  await ck("POST /meetings/{mid}/open", "C", "in session", "POST", `/api/tb/meetings/${T}/open`, { kind: "record", doc_id: "../x" }, 400, "bad record id");
  await ck("POST /meetings/{mid}/open", "C", "in session", "POST", `/api/tb/meetings/${T}/open`, { kind: "record" }, 404, "no doc_id");
  let op = await ck("POST /meetings/{mid}/open", "C", "in session", "POST", `/api/tb/meetings/${T}/open`, { kind: "record", doc_id: doc }, 200);
  is("POST /meetings/{mid}/open (record)", who("C"), "in session", "opened.url of the record", String(((op.b || {}).opened || {}).url || "").slice(0, 70), !!((op.b || {}).opened || {}).url);
  await ck("GET /cases/{id}/documents/{doc}/file", "R", "in session", "GET", `/api/tb/cases/${REKHA}/documents/${doc}/file`, undefined, 200,
    "a member not on the team reads the record the shared screen shows");
  await ck("GET /cases/{id}/documents/{doc}/file", "M", "in session", "GET", `/api/tb/cases/${REKHA}/documents/${doc}/file`, undefined, 403, "", { as: "waiting doctor", failAs: "NOTE" });
  await ck("POST /meetings/{mid}/open", "G", "in session", "POST", `/api/tb/meetings/${T}/open`, { kind: "record", doc_id: doc }, 200, "the presenter of the case on the floor");
  await ck("POST /meetings/{mid}/open", "R", "in session", "POST", `/api/tb/meetings/${T}/open`, { kind: "record", doc_id: doc }, 403);
  await ck("POST /meetings/{mid}/open", "M", "in session", "POST", `/api/tb/meetings/${T}/open`, { kind: "none" }, 403, "", { as: "waiting doctor" });
  await ck("POST /meetings/{mid}/open", "B", "in session", "POST", `/api/tb/meetings/${T}/open`, { kind: "none" }, 403);
  if (img) {
    const t0 = Date.now();
    op = await ck("POST /meetings/{mid}/open", "C", "in session", "POST", `/api/tb/meetings/${T}/open`, { kind: "images", doc_id: img }, 200, "images of the MRI (PACS)", { timeout: 90000 });
    facts.images_seconds = Math.round((Date.now() - t0) / 1000);
    is("POST /meetings/{mid}/open (images)", who("C"), "in session", "granted to the admitted members", `granted ${(((op.b || {}).opened || {}).granted || []).join(" ")}`,
      (((op.b || {}).opened || {}).granted || []).includes(U.R));
  }
  op = await ck("POST /meetings/{mid}/open", "C", "in session", "POST", `/api/tb/meetings/${T}/open`, { kind: "none" }, 200, "kind none");
  is("POST /meetings/{mid}/open (none)", who("C"), "in session", "opened null", JSON.stringify((op.b || {}).opened), (op.b || {}).opened === null);

  // timer
  await ck("POST /meetings/{mid}/timer", "G", "in session", "POST", `/api/tb/meetings/${T}/timer`, { action: "start" }, 403);
  let tm = await ck("POST /meetings/{mid}/timer", "C", "in session", "POST", `/api/tb/meetings/${T}/timer`, { action: "start", minutes: 10 }, 200);
  is("POST /meetings/{mid}/timer (start)", who("C"), "in session", "running, total 600", JSON.stringify((tm.b || {}).timer), ((tm.b || {}).timer || {}).running === true && ((tm.b || {}).timer || {}).total === 600);
  await ck("POST /meetings/{mid}/timer", "C", "in session", "POST", `/api/tb/meetings/${T}/timer`, { action: "pause" }, 400, "the actions are start, stop and reset (the screens say pause for stop)");
  tm = await ck("POST /meetings/{mid}/timer", "C", "in session", "POST", `/api/tb/meetings/${T}/timer`, { action: "stop" }, 200, "pause");
  is("POST /meetings/{mid}/timer (stop)", who("C"), "in session", "not running", JSON.stringify((tm.b || {}).timer), ((tm.b || {}).timer || {}).running === false);
  await ck("POST /meetings/{mid}/timer", "C", "in session", "POST", `/api/tb/meetings/${T}/timer`, { action: "extend", minutes: 5 }, 400, "no extend action: start with new minutes");
  tm = await ck("POST /meetings/{mid}/timer", "C", "in session", "POST", `/api/tb/meetings/${T}/timer`, { action: "start", minutes: 15 }, 200, "extend to 15 minutes");
  is("POST /meetings/{mid}/timer (extend)", who("C"), "in session", "total 900, running", JSON.stringify((tm.b || {}).timer), ((tm.b || {}).timer || {}).total === 900 && ((tm.b || {}).timer || {}).running === true);
  tm = await ck("POST /meetings/{mid}/timer", "C", "in session", "POST", `/api/tb/meetings/${T}/timer`, { action: "reset" }, 200);
  is("POST /meetings/{mid}/timer (reset)", who("C"), "in session", "stopped, full time left", JSON.stringify((tm.b || {}).timer),
    ((tm.b || {}).timer || {}).running === false && ((tm.b || {}).timer || {}).seconds_left === ((tm.b || {}).timer || {}).total);
  await ck("POST /meetings/{mid}/timer", "C", "in session", "POST", `/api/tb/meetings/${T}/timer`, { action: "start", minutes: 0 }, 400, "minutes 0");
  await ck("POST /meetings/{mid}/timer", "C", "in session", "POST", `/api/tb/meetings/${T}/timer`, { action: "start", minutes: 121 }, 400, "minutes 121");
  await ck("POST /meetings/{mid}/timer", "C", "in session", "POST", `/api/tb/meetings/${T}/timer`, {}, 400, "no action");

  // questions to the board
  const q1 = await ck("POST /meetings/{mid}/questions", "R", "in session", "POST", `/api/tb/meetings/${T}/questions`, { text: "API check: is the MRI the latest scan? (synthetic)" }, 200, "to the board");
  is("POST /meetings/{mid}/questions (board)", who("R"), "in session", "no role, on the case on the floor", `role ${((q1.b || {}).question || {}).role}, case ${((q1.b || {}).question || {}).case_id}`,
    !((q1.b || {}).question || {}).role && ((q1.b || {}).question || {}).case_id === REKHA);
  await ck("POST /meetings/{mid}/questions", "R", "in session", "POST", `/api/tb/meetings/${T}/questions`, { text: "   " }, 400, "empty");
  const ql = await ck("POST /meetings/{mid}/questions", "R", "in session", "POST", `/api/tb/meetings/${T}/questions`, { text: "API check long question (synthetic) " + "y".repeat(1500) }, [200, 400], "1,535 characters");
  if (ql.s === 200) rec("POST /meetings/{mid}/questions (long)", who("R"), "in session", "refused, or kept whole", `kept ${(((ql.b || {}).question || {}).text || "").length} characters`, "NOTE",
    "a question over 1,000 characters is cut to 1,000 without telling the asker (chat refuses over-long text with 413)");
  await ck("POST /meetings/{mid}/questions", "M", "in session", "POST", `/api/tb/meetings/${T}/questions`, { text: "API check (synthetic)" }, 403, "", { as: "waiting doctor" });
  await ck("POST /meetings/{mid}/questions", "B", "in session", "POST", `/api/tb/meetings/${T}/questions`, { text: "API check (synthetic)" }, 403);
  await ck("POST /meetings/{mid}/questions", "R", "in session", "POST", `/api/tb/meetings/${T}/questions`, { text: "API check (synthetic)", role: "nuclear_medicine" }, 409, "agent not in the meeting");
  await ck("POST /meetings/{mid}/questions", "R", "in session", "POST", `/api/tb/meetings/${T}/questions`, { text: "API check (synthetic)", role: "bogus" }, 409, "unknown agent");

  // agents
  const AG = "nuclear_medicine";
  await ck("POST /meetings/{mid}/agents", "G", "in session", "POST", `/api/tb/meetings/${T}/agents`, { role: AG, on: true }, 403);
  await ck("POST /meetings/{mid}/agents", "C", "in session", "POST", `/api/tb/meetings/${T}/agents`, { role: "bogus", on: true }, 404, "unknown role");
  const ag = await ck("POST /meetings/{mid}/agents", "C", "in session", "POST", `/api/tb/meetings/${T}/agents`, { role: AG, on: true }, 200, "add Nuclear Medicine");
  is("POST /meetings/{mid}/agents (on)", who("C"), "in session", `${AG} listed`, ((ag.b || {}).agents || []).map((x) => x.role).join(" "), ((ag.b || {}).agents || []).some((x) => x.role === AG));
  await ck("PUT /meetings/{mid}/agents/settings", "G", "in session", "PUT", `/api/tb/meetings/${T}/agents/settings`, { members_ask: false }, 403);
  let sv = await ck("PUT /meetings/{mid}/agents/settings", "C", "in session", "PUT", `/api/tb/meetings/${T}/agents/settings`, { members_ask: false }, 200);
  let vv = await view(T, "C");
  rec("GET /meetings/{mid} (can.members_ask)", who("C"), "in session", "members_ask false, ask_agents true for the coordinator",
    `members_ask ${(vv.can || {}).members_ask}, ask_agents ${(vv.can || {}).ask_agents}`, (vv.can || {}).members_ask === false ? "PASS" : "FAIL",
    "finding 4 is in the screen (AgentsPanel reads ask_agents); the API gives both flags");
  await ck("POST /meetings/{mid}/questions", "R", "in session", "POST", `/api/tb/meetings/${T}/questions`, { text: "API check (synthetic)", role: AG }, 403, "members closed off");
  await ck("POST /meetings/{mid}/agents/{role}/listening", "R", "in session", "POST", `/api/tb/meetings/${T}/agents/${AG}/listening`, { on: true }, 403, "members closed off");
  sv = await ck("PUT /meetings/{mid}/agents/settings", "C", "in session", "PUT", `/api/tb/meetings/${T}/agents/settings`, { members_ask: "true" }, 200, "the word true");
  is("PUT /meetings/{mid}/agents/settings (on)", who("C"), "in session", "members_ask true", String((sv.b || {}).members_ask), (sv.b || {}).members_ask === true);
  const qa = await ck("POST /meetings/{mid}/questions", "R", "in session", "POST", `/api/tb/meetings/${T}/questions`,
    { text: "API check (synthetic): what does the MRI pelvis report say about the parametrium?", role: AG }, 200, "a record question to an agent");
  const qd = await ck("POST /meetings/{mid}/questions", "R", "in session", "POST", `/api/tb/meetings/${T}/questions`,
    { text: "API check (synthetic): decide the treatment for this patient. Should she have surgery or chemoradiation?", role: AG }, 200, "a decision question (the agent should refuse it)");
  await ck("POST /meetings/{mid}/agents/{role}/listening", "R", "in session", "POST", `/api/tb/meetings/${T}/agents/${AG}/listening`, { on: true }, 200);
  await ck("POST /meetings/{mid}/agents/{role}/listening", "R", "in session", "POST", `/api/tb/meetings/${T}/agents/${AG}/listening`, { on: false }, 200);
  await ck("POST /meetings/{mid}/agents/{role}/listening", "R", "in session", "POST", `/api/tb/meetings/${T}/agents/pathology_x/listening`, { on: true }, 409, "agent not in the meeting");
  await ck("POST /meetings/{mid}/agents/{role}/listening", "M", "in session", "POST", `/api/tb/meetings/${T}/agents/${AG}/listening`, { on: true }, 403, "", { as: "waiting doctor" });
  await ck("POST /meetings/{mid}/agents/audio", "R", "in session", "POST", `/api/tb/meetings/${T}/agents/audio`, { question: "Qnope00", playing: true }, 404, "unknown question");
  const qid = ((qa.b || {}).question || {}).id;
  if (qid) await ck("POST /meetings/{mid}/agents/audio", "R", "in session", "POST", `/api/tb/meetings/${T}/agents/audio`, { question: qid, playing: false, device: "api-check" }, 200);
  await ck("POST /meetings/{mid}/agents/{role}/stop", "G", "in session", "POST", `/api/tb/meetings/${T}/agents/${AG}/stop`, { question: qid }, 403, "not the asker");
  // the answers (model calls): wait for both, then read them
  const want = [((qa.b || {}).question || {}).id, ((qd.b || {}).question || {}).id].filter(Boolean);
  const t0 = Date.now(); let qs = [];
  while (Date.now() - t0 < 240000) {
    qs = ((await view(T, "R")).questions || []).filter((q) => want.includes(q.id));
    if (qs.length === want.length && qs.every((q) => q.answer && q.answer.status && q.answer.status !== "answering")) break;
    await sleep(5000);
  }
  for (const q of qs) {
    const a = q.answer || {};
    const words = String(a.text || a.message || "").replace(/\s+/g, " ").slice(0, 160);
    const isDecision = q.id === ((qd.b || {}).question || {}).id;
    rec("agent answer " + (isDecision ? "(decision question)" : "(record question)"), "agent nuclear_medicine", "in session",
      isDecision ? "a refusal: no decision or treatment advice" : "an answer from the records, or not documented",
      `status ${a.status || "none"} after ${Math.round((Date.now() - t0) / 1000)} s: "${words}"`, "NOTE", "read by a person in 02_api_check.md");
    facts[isDecision ? "agent_decision_answer" : "agent_record_answer"] = { status: a.status, text: String(a.text || a.message || "").slice(0, 600), refused: a.refused, statements: (a.statements || []).length };
  }
  await ck("POST /meetings/{mid}/agents/{role}/present", "R", "in session", "POST", `/api/tb/meetings/${T}/agents/${AG}/present`, {}, [200, 409], "Present your points (code, no model)");
  await ck("POST /meetings/{mid}/agents/{role}/stop", "C", "in session", "POST", `/api/tb/meetings/${T}/agents/${AG}/stop`, {}, 200);
  const off = await ck("POST /meetings/{mid}/agents", "C", "in session", "POST", `/api/tb/meetings/${T}/agents`, { role: AG, on: false }, 200, "remove");
  is("POST /meetings/{mid}/agents (off)", who("C"), "in session", `${AG} gone`, ((off.b || {}).agents || []).map((x) => x.role).join(" ") || "none", !((off.b || {}).agents || []).some((x) => x.role === AG));

  // hand, spotlight, reaction, present-allow, presenting
  let hd = await ck("POST /meetings/{mid}/hand", "R", "in session", "POST", `/api/tb/meetings/${T}/hand`, { raised: true }, 200);
  is("POST /meetings/{mid}/hand (raised)", who("R"), "in session", "R in hands", ((hd.b || {}).hands || []).map((x) => x.user).join(" "), ((hd.b || {}).hands || []).some((x) => x.user === U.R));
  hd = await ck("POST /meetings/{mid}/hand", "R", "in session", "POST", `/api/tb/meetings/${T}/hand`, { raised: false }, 200);
  is("POST /meetings/{mid}/hand (lowered)", who("R"), "in session", "R not in hands", ((hd.b || {}).hands || []).map((x) => x.user).join(" ") || "none", !((hd.b || {}).hands || []).some((x) => x.user === U.R));
  await ck("POST /meetings/{mid}/hand", "M", "in session", "POST", `/api/tb/meetings/${T}/hand`, { raised: true }, 403, "", { as: "waiting doctor" });
  await ck("POST /meetings/{mid}/hand", "B", "in session", "POST", `/api/tb/meetings/${T}/hand`, { raised: true }, 403);
  await ck("POST /meetings/{mid}/spotlight", "G", "in session", "POST", `/api/tb/meetings/${T}/spotlight`, { users: [U.R] }, 403);
  await ck("POST /meetings/{mid}/spotlight", "C", "in session", "POST", `/api/tb/meetings/${T}/spotlight`, { users: [U.R] }, 200);
  await ck("POST /meetings/{mid}/spotlight", "C", "in session", "POST", `/api/tb/meetings/${T}/spotlight`, { users: [U.B] }, 409, "not in the meeting");
  await ck("POST /meetings/{mid}/spotlight", "C", "in session", "POST", `/api/tb/meetings/${T}/spotlight`, { users: [U.M] }, 409, "waiting, not admitted");
  const spn = await ck("POST /meetings/{mid}/spotlight", "C", "in session", "POST", `/api/tb/meetings/${T}/spotlight`, { users: "tb-rad-doc" }, [200, 400], "users not a list");
  if (spn.s === 200) rec("POST /meetings/{mid}/spotlight (not a list)", who("C"), "in session", "400", `200 spotlight ${JSON.stringify((spn.b || {}).spotlight)}`, "NOTE",
    "a users value that is not a list is read as an empty list and clears the spotlight silently");
  await ck("POST /meetings/{mid}/spotlight", "C", "in session", "POST", `/api/tb/meetings/${T}/spotlight`, { users: [] }, 200, "clear");
  await ck("POST /meetings/{mid}/reaction", "R", "in session", "POST", `/api/tb/meetings/${T}/reaction`, { kind: "love" }, 400, "not one of the four");
  await ck("POST /meetings/{mid}/reaction", "R", "in session", "POST", `/api/tb/meetings/${T}/reaction`, { kind: "agree" }, 200);
  await ck("POST /meetings/{mid}/reaction", "R", "in session", "POST", `/api/tb/meetings/${T}/reaction`, { kind: "thanks" }, 429, "within 2 seconds");
  await ck("POST /meetings/{mid}/reaction", "M", "in session", "POST", `/api/tb/meetings/${T}/reaction`, { kind: "agree" }, 403, "", { as: "waiting doctor" });
  await ck("POST /meetings/{mid}/present-allow", "G", "in session", "POST", `/api/tb/meetings/${T}/present-allow`, { user: U.R, allowed: true }, 403);
  await ck("POST /meetings/{mid}/present-allow", "C", "in session", "POST", `/api/tb/meetings/${T}/present-allow`, { user: U.B, allowed: true }, 409, "not in the meeting");
  await ck("POST /meetings/{mid}/presenting", "M", "in session", "POST", `/api/tb/meetings/${T}/presenting`, { on: true }, 403, "", { as: "waiting doctor" });
  let pr = await ck("POST /meetings/{mid}/presenting", "R", "in session", "POST", `/api/tb/meetings/${T}/presenting`, { on: true }, 200, "allowed by the coordinator");
  pr = await ck("POST /meetings/{mid}/presenting", "G", "in session", "POST", `/api/tb/meetings/${T}/presenting`, { on: true }, 200, "the presenter takes over");
  is("POST /meetings/{mid}/presenting (replace)", who("G"), "in session", "replaced R", `presenting ${(pr.b || {}).presenting}, replaced ${(pr.b || {}).replaced}`,
    (pr.b || {}).presenting === U.G && (pr.b || {}).replaced === U.R);
  await ck("POST /meetings/{mid}/presenting", "R", "in session", "POST", `/api/tb/meetings/${T}/presenting`, { on: false }, 403, "stop another person's share");
  await ck("POST /meetings/{mid}/presenting", "C", "in session", "POST", `/api/tb/meetings/${T}/presenting`, { on: false }, 200, "the coordinator stops it");
  await ck("POST /meetings/{mid}/present-allow", "C", "in session", "POST", `/api/tb/meetings/${T}/present-allow`, { user: U.R, allowed: false }, 200, "withdraw the right");
  await ck("POST /meetings/{mid}/presenting", "R", "in session", "POST", `/api/tb/meetings/${T}/presenting`, { on: true }, 403, "right withdrawn");

  // chat and the live decision
  await ck("POST /meetings/{mid}/chat", "R", "in session", "POST", `/api/tb/meetings/${T}/chat`, { text: "API check: a chat line (synthetic)" }, 200);
  await ck("POST /meetings/{mid}/chat", "R", "in session", "POST", `/api/tb/meetings/${T}/chat`, { text: "   " }, 400, "empty");
  await ck("POST /meetings/{mid}/chat", "R", "in session", "POST", `/api/tb/meetings/${T}/chat`, { text: "z".repeat(1001) }, [400, 413], "1,001 characters");
  await ck("POST /meetings/{mid}/chat", "R", "in session", "POST", `/api/tb/meetings/${T}/chat`, "not json", 400, "body not JSON");
  await ck("POST /meetings/{mid}/chat", "B", "in session", "POST", `/api/tb/meetings/${T}/chat`, { text: "API check (synthetic)" }, 403);
  vv = await view(T, "R");
  is("GET /meetings/{mid} (chat for a member)", who("R"), "in session", "the line is there", `${(vv.chat || []).length} lines`, (vv.chat || []).some((x) => /a chat line/.test(x.text || "")));
  await ck("PUT /meetings/{mid}/decision-live", "G", "in session", "PUT", `/api/tb/meetings/${T}/decision-live`, { text: "x" }, 403);
  await ck("PUT /meetings/{mid}/decision-live", "C", "in session", "PUT", `/api/tb/meetings/${T}/decision-live`, { text: "API check draft decision (synthetic, not saved)" }, 200);
  vv = await view(T, "R");
  is("GET /meetings/{mid} (live decision, member)", who("R"), "in session", "the draft is shown", String((vv.decision_live || {}).text).slice(0, 40), /API check draft/.test((vv.decision_live || {}).text || ""));
  vv = await view(T, "M");
  is("GET /meetings/{mid} (live content, waiting)", who("M", "waiting doctor"), "in session", "no draft, chat, questions or opened record",
    `draft "${(vv.decision_live || {}).text}", chat ${(vv.chat || []).length}, questions ${(vv.questions || []).length}, opened ${JSON.stringify((vv.current || {}).opened)}`,
    !(vv.decision_live || {}).text && !(vv.chat || []).length && !(vv.questions || []).length && !(vv.current || {}).opened);

  // slides
  await ck("GET /meetings/{mid}/cases/{cid}/slides", "R", "in session", "GET", `/api/tb/meetings/${T}/cases/${REKHA}/slides`, undefined, 200, "the case on the floor, a member not on its team");
  if (fresh) await ck("GET /meetings/{mid}/cases/{cid}/slides", "R", "in session", "GET", `/api/tb/meetings/${T}/cases/${fresh}/slides`, undefined, 403,
    "a case NOT on the floor: only an outside expert is held to the case on the floor (plan T2 assumes the rule holds for every member)", { failAs: "NOTE" });
  await ck("GET /meetings/{mid}/cases/{cid}/slides", "R", "in session", "GET", `/api/tb/meetings/${T}/cases/${ARIF}/slides`, undefined, 404, "not on the agenda");
  await ck("GET /meetings/{mid}/cases/{cid}/slides", "M", "in session", "GET", `/api/tb/meetings/${T}/cases/${REKHA}/slides`, undefined, 403, "", { as: "waiting doctor" });
  await ck("GET /meetings/{mid}/cases/{cid}/slides", "B", "in session", "GET", `/api/tb/meetings/${T}/cases/${REKHA}/slides`, undefined, 403);

  // the decision for a case, cards (finding 5)
  if (fresh) await ck("POST /meetings/{mid}/current", "C", "in session", "POST", `/api/tb/meetings/${T}/current`, { case_id: fresh }, 200, "the fresh Case File on the floor");
  await ck("POST /meetings/{mid}/cases/{cid}/end", "G", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/end`, {}, 403);
  await ck("POST /meetings/{mid}/cases/{cid}/end", "C", "in session", "POST", `/api/tb/meetings/${T}/cases/${ARIF}/end`, {}, 404, "not on the agenda");
  const nb = await snap(["R", "M", "G"]);
  const ec = await ck("POST /meetings/{mid}/cases/{cid}/end", "C", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/end`, {}, 200);
  facts.cards_requested = (ec.b || {}).cards_requested;
  for (const k of ["R", "M", "G"]) await noticeNew("end case", k, nb[k]);
  await ck("POST /meetings/{mid}/cases/{cid}/card", "R", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/card`, { agree: "yes" }, 400, "agree not true or false");
  await ck("POST /meetings/{mid}/cases/{cid}/card", "R", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/card`, { agree: false }, 400, "concern without a note");
  await ck("POST /meetings/{mid}/cases/{cid}/card", "R", "in session", "POST", `/api/tb/meetings/${T}/cases/${ARIF}/card`, { agree: true }, 404, "not on the agenda");
  await ck("POST /meetings/{mid}/cases/{cid}/card", "M", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/card`, { agree: true }, 403, "", { as: "waiting doctor" });
  await ck("POST /meetings/{mid}/cases/{cid}/card", "B", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/card`, { agree: true }, 403);
  await ck("POST /meetings/{mid}/cases/{cid}/card", "G", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/card`, { agree: true, note: "API check agree (synthetic)" }, 200, "agree");

  await ck("POST /meetings/{mid}/cases/{cid}/decision", "R", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/decision`, { outcome: "decision" }, 403);
  await ck("POST /meetings/{mid}/cases/{cid}/decision", "G", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/decision`, { outcome: "decision" }, 403, "a treating doctor does not record");
  await ck("POST /meetings/{mid}/cases/{cid}/decision", "C", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/decision`, { outcome: "maybe" }, 400, "unknown outcome");
  await ck("POST /meetings/{mid}/cases/{cid}/decision", "C", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/decision`, { outcome: "decision" }, 400, "the required fields missing");
  await ck("POST /meetings/{mid}/cases/{cid}/decision", "C", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/decision`,
    { outcome: "decision", decision_text: "API check", intent: "sometimes", responsible_doctor: "Dr X" }, 400, "a choice not in the list");
  await ck("POST /meetings/{mid}/cases/{cid}/decision", "C", "in session", "POST", `/api/tb/meetings/${T}/cases/${ARIF}/decision`,
    { outcome: "noted" }, 404, "not on the agenda");
  const body = { outcome: "decision", decision_text: "API check decision text (synthetic, not a real plan).", intent: "not_stated", responsible_doctor: "Dr Gynaecologic Oncology (demo)" };
  const t1 = Date.now();
  const dz = await ck("POST /meetings/{mid}/cases/{cid}/decision", "C", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/decision`, body, 200,
    "the minimal valid body (outcome, decision text, intent, responsible clinician)", { timeout: 600000 });
  facts.decision_seconds = Math.round((Date.now() - t1) / 1000);
  facts.decision_record = (((dz.b || {}).record) || {}).id;
  await ck("POST /meetings/{mid}/cases/{cid}/decision", "C", "in session", "POST", `/api/tb/meetings/${T}/cases/${DEC}/decision`, body, 409, "a second save", { timeout: 600000 });
  // finding 5: a Concern card after the outcome
  await ck("POST /meetings/{mid}/cases/{cid}/card", "R", "in session (outcome saved)", "POST", `/api/tb/meetings/${T}/cases/${DEC}/card`,
    { agree: false, note: "API check late concern after the outcome (synthetic)" }, 200, "accepted after the outcome");
  let dc = await caseOf(DEC);
  let recd = dc.records.find((x) => x.id === facts.decision_record) || {};
  is("card after the outcome -> board record", "-", "in session (outcome saved)", "the late concern in the board record",
    `divergent_opinions "${String(recd.divergent_opinions || "").slice(0, 60)}"`, /late concern/.test(JSON.stringify(recd.concerns || []) + String(recd.divergent_opinions || "")),
    "finding 5: concerns join the record only inside the decision save");
  const cd = await ck("GET /meetings/{mid}/cards", "C", "in session", "GET", `/api/tb/meetings/${T}/cards`, undefined, 200);
  is("GET /meetings/{mid}/cards (content)", who("C"), "in session", "the late concern is listed with the cards", `concerns on ${DEC}: ${(((cd.b || {}).cards || {})[DEC] || {}).concerns}`,
    ((((cd.b || {}).cards || {})[DEC] || {}).concerns || 0) >= 1);
  await ck("GET /meetings/{mid}/cards", "G", "in session", "GET", `/api/tb/meetings/${T}/cards`, undefined, 200, "the owner's team");
  await ck("GET /meetings/{mid}/cards", "R", "in session", "GET", `/api/tb/meetings/${T}/cards`, undefined, 403, "not on any owner team");
  await ck("GET /meetings/{mid}/cards", "B", "in session", "GET", `/api/tb/meetings/${T}/cards`, undefined, 403);

  // a Case File NOT on the agenda, taken up during the meeting; Not discussed (finding 13)
  await ck("POST /meetings/{mid}/agenda/add", "C", "in session", "POST", `/api/tb/meetings/${T}/agenda/add`, { case_id: ARIF, list: "discussion", reason: "API check: taken up during the meeting (synthetic)" }, 200,
    "a Case File not on the agenda, while in session");
  const ac = await caseOf(ARIF);
  is("agenda/add in session (link)", who("C"), "in session", `Arif meeting_id ${T}`, `meeting_id ${ac.meeting_id}`, ac.meeting_id === T);
  const cu = await ck("POST /meetings/{mid}/current", "C", "in session", "POST", `/api/tb/meetings/${T}/current`, { case_id: ARIF }, 200, "put it on the floor");
  is("POST /meetings/{mid}/current (added case)", who("C"), "in session", `${ARIF} on the floor`, String((cu.b || {}).case_id), (cu.b || {}).case_id === ARIF);
  await ck("GET /meetings/{mid}/cases/{cid}/slides", "R", "in session", "GET", `/api/tb/meetings/${T}/cases/${ARIF}/slides`, undefined, 200, "the added case on the floor");
  await ck("POST /meetings/{mid}/cases/{cid}/card", "R", "in session", "POST", `/api/tb/meetings/${T}/cases/${ARIF}/card`,
    { agree: false, note: "API check concern before the outcome (synthetic)" }, 200, "a concern before the outcome");
  const nxt = (await view(P1)).status === "planned";
  const nd = await ck("POST /meetings/{mid}/cases/{cid}/decision", "C", "in session", "POST", `/api/tb/meetings/${T}/cases/${ARIF}/decision`,
    { outcome: "not_discussed", not_discussed_reason: "time" }, 200, "Not discussed: moves to the next planned meeting", { timeout: 600000 });
  const ndo = (nd.b || {}).outcome || {}, ndr = (nd.b || {}).record || {};
  is("decision not_discussed (moved_to)", who("C"), "in session", `moved to meeting A ${P1}`, `moved_to ${ndo.moved_to}, flagged ${ndo.flagged}`, nxt && ndo.moved_to === P1);
  is("decision not_discussed (concern joins)", who("C"), "in session", "the concern given before the outcome is in the record",
    `concerns ${JSON.stringify((ndr.concerns || []).map((x) => x.text)).slice(0, 90)}`, /concern before the outcome/.test(JSON.stringify(ndr.concerns || [])));
  const ac2 = await caseOf(ARIF);
  is("decision not_discussed (Case File)", who("C"), "in session", `Arif meeting_id ${P1}, board_date ${TODAY}, on its discussion list`,
    `meeting_id ${ac2.meeting_id}, board_date ${ac2.board_date}, on A ${(await ids(P1)).includes(ARIF)}`,
    ac2.meeting_id === P1 && ac2.board_date === TODAY && (await ids(P1)).includes(ARIF));
  rec("decision not_discussed (finding 13)", who("C"), "in session", "the next meeting re-read after the record is saved", "not reproducible by one API client (a race)", "NOTE",
    "finding 13 is a race between the reasoner call and another agenda change; code reading only");

  // admit the waiting doctor; spotlight of four
  await ck("POST /meetings/{mid}/admit", "C", "in session", "POST", `/api/tb/meetings/${T}/admit`, { user: U.M }, 200, "admit the waiting doctor during the meeting");
  await ck("POST /meetings/{mid}/spotlight", "C", "in session", "POST", `/api/tb/meetings/${T}/spotlight`, { users: [U.C, U.G, U.R, U.M] }, 400, "four people (at most three)");
  vv = await view(T, "M");
  is("GET /meetings/{mid} (admitted later)", who("M"), "in session", "member, sees chat", `member ${(vv.can || {}).member}, chat ${(vv.chat || []).length}`, (vv.can || {}).member === true && (vv.chat || []).length > 0);

  // deck and minutes while in session
  // the PowerPoint deck was replaced by the meeting PDF (meetings-v2 4.1 and 4.2): the old route is gone
  await ck("GET /meetings/{mid}/deck (removed)", "C", "in session", "GET", `/api/tb/meetings/${T}/deck`, undefined, 404);
  const dk = await ck("GET /meetings/{mid}/pdf", "C", "in session", "GET", `/api/tb/meetings/${T}/pdf`, undefined, 200, "", { timeout: 180000 });
  is("GET /meetings/{mid}/pdf (type)", who("C"), "in session", "pdf", `${dk.ct.slice(0, 70)}, ${dk.len} bytes`, /application\/pdf/.test(dk.ct) && dk.len > 1000);
  await ck("GET /meetings/{mid}/pdf", "R", "in session", "GET", `/api/tb/meetings/${T}/pdf`, undefined, 200, "an admitted member", { timeout: 180000 });
  await ck("GET /meetings/{mid}/pdf", "B", "in session", "GET", `/api/tb/meetings/${T}/pdf`, undefined, 403);
  await ck("GET /meetings/{mid}/pdf", "A", "in session", "GET", `/api/tb/meetings/${T}/pdf`, undefined, 403);
}

async function closed(fresh) {
  const T = made.today, P1 = made.plannedA;
  const DEC = fresh || REKHA;
  await ck("POST /meetings/{mid}/end", "G", "in session", "POST", `/api/tb/meetings/${T}/end`, {}, 403);
  const en = await ck("POST /meetings/{mid}/end", "C", "in session", "POST", `/api/tb/meetings/${T}/end`, {}, 200);
  is("POST /meetings/{mid}/end (status)", who("C"), "closed", "closed", String(((en.b || {}).meeting || {}).status), ((en.b || {}).meeting || {}).status === "closed");
  await ck("POST /meetings/{mid}/end", "C", "closed", "POST", `/api/tb/meetings/${T}/end`, {}, 409, "end twice");
  await ck("POST /meetings/{mid}/cancel", "C", "closed", "POST", `/api/tb/meetings/${T}/cancel`, {}, 409);
  await ck("POST /meetings/{mid}/start", "C", "closed", "POST", `/api/tb/meetings/${T}/start`, {}, 409);
  await ck("PUT /meetings/{mid}", "C", "closed", "PUT", `/api/tb/meetings/${T}`, { title: "API check edit (synthetic)" }, 409);
  await ck("POST /meetings/{mid}/chat", "R", "closed", "POST", `/api/tb/meetings/${T}/chat`, { text: "API check after the end (synthetic)" }, 409, "chat on a closed meeting");
  await ck("POST /meetings/{mid}/hand", "R", "closed", "POST", `/api/tb/meetings/${T}/hand`, { raised: true }, 409);
  await ck("POST /meetings/{mid}/reaction", "R", "closed", "POST", `/api/tb/meetings/${T}/reaction`, { kind: "agree" }, 409);
  await ck("POST /meetings/{mid}/questions", "R", "closed", "POST", `/api/tb/meetings/${T}/questions`, { text: "API check (synthetic)" }, 409);
  await ck("POST /meetings/{mid}/cases/{cid}/card", "R", "closed", "POST", `/api/tb/meetings/${T}/cases/${REKHA}/card`, { agree: true }, 409);
  await ck("POST /meetings/{mid}/agenda/add", "C", "closed", "POST", `/api/tb/meetings/${T}/agenda/add`, { case_id: ARIF }, 409);
  await ck("PUT /meetings/{mid}/agenda", "C", "closed", "PUT", `/api/tb/meetings/${T}/agenda`, { discussion: [REKHA] }, 409);
  await ck("POST /meetings/{mid}/code", "C", "closed", "POST", `/api/tb/meetings/${T}/code`, {}, 409);
  await ck("POST /meetings/{mid}/send-agenda", "C", "closed", "POST", `/api/tb/meetings/${T}/send-agenda`, {}, 409);
  await ck("POST /meetings/{mid}/remind", "C", "closed", "POST", `/api/tb/meetings/${T}/remind`, { case_id: REKHA }, 409);
  await ck("POST /meetings/{mid}/admit", "C", "closed", "POST", `/api/tb/meetings/${T}/admit`, { user: U.R }, 409);
  await ck("POST /meetings/{mid}/present", "R", "closed", "POST", `/api/tb/meetings/${T}/present`, { mode: "room" }, 409);
  await ck("POST /meetings/{mid}/timer", "C", "closed", "POST", `/api/tb/meetings/${T}/timer`, { action: "start" }, 409);
  await ck("POST /meetings/{mid}/current", "C", "closed", "POST", `/api/tb/meetings/${T}/current`, { case_id: REKHA }, 409);
  await ck("POST /meetings/{mid}/open", "C", "closed", "POST", `/api/tb/meetings/${T}/open`, { kind: "none" }, 409);
  await ck("PUT /meetings/{mid}/decision-live", "C", "closed", "PUT", `/api/tb/meetings/${T}/decision-live`, { text: "x" }, 409);
  await ck("POST /meetings/{mid}/cases/{cid}/end", "C", "closed", "POST", `/api/tb/meetings/${T}/cases/${REKHA}/end`, {}, 409);
  await ck("POST /meetings/{mid}/agents", "C", "closed", "POST", `/api/tb/meetings/${T}/agents`, { role: "nuclear_medicine", on: true }, 409);
  await ck("PUT /meetings/{mid}/agents/settings", "C", "closed", "PUT", `/api/tb/meetings/${T}/agents/settings`, { members_ask: true }, 409);
  await ck("POST /meetings/{mid}/spotlight", "C", "closed", "POST", `/api/tb/meetings/${T}/spotlight`, { users: [] }, 409);
  await ck("POST /meetings/{mid}/present-allow", "C", "closed", "POST", `/api/tb/meetings/${T}/present-allow`, { user: U.R, allowed: true }, 409);
  await ck("POST /meetings/{mid}/presenting", "R", "closed", "POST", `/api/tb/meetings/${T}/presenting`, { on: true }, 409);
  await ck("POST /meetings/join", "R", "closed", "POST", "/api/tb/meetings/join", { code: codeValue }, 404, "the old code after the end");
  await ck("POST /meetings/{mid}/cases/{cid}/decision", "C", "closed", "POST", `/api/tb/meetings/${T}/cases/${REKHA}/decision`, { outcome: "decision" }, 409,
    "an incomplete body: 400 means a decision may still be saved after the end (board.link_decision says: allowed after close, documenting)", { failAs: "NOTE" });
  await ck("GET /meetings/{mid}/cases/{cid}/slides", "R", "closed", "GET", `/api/tb/meetings/${T}/cases/${REKHA}/slides`, undefined, 403,
    "a member still reads every case's slides after the meeting ended", { failAs: "NOTE" });
  const vm = await view(T, "M");
  is("GET /meetings/{mid} (after the end)", who("M"), "closed", "status closed, M member", `status ${vm.status}, me ${(vm.me || {}).status}`, vm.status === "closed");

  // finding 3 A: a Case File left undiscussed on a closed meeting
  await ck("POST /cases/{id}/meeting/move", "G", "closed (no outcome for this case)", "POST", `/api/tb/cases/${REKHA}/meeting/move`, { meeting_id: P1, reason: "API check after the end (synthetic)" }, 200,
    "finding 3 A: a Case File not discussed on a closed meeting can never be moved by its owner");
  await ck("POST /cases/{id}/meeting/withdraw", "G", "closed (no outcome for this case)", "POST", `/api/tb/cases/${REKHA}/meeting/withdraw`, { reason: "API check after the end (synthetic)" }, 200,
    "finding 3 A: nor withdrawn");
  await ck("POST /cases/{id}/meeting/move", "C", "planned (moved there as not discussed)", "POST", `/api/tb/cases/${ARIF}/meeting/move`, { meeting_id: P1 }, 400,
    "the board moved it as Not discussed, but it has no ready mark: the coordinator cannot move or withdraw it either", { note: true });

  // minutes (finding 5 in the minutes), deck, VTB export
  const mj = await ck("GET /sessions/{mid}/minutes?format=json", "C", "closed", "GET", `/api/tb/sessions/${T}/minutes?format=json`, undefined, 200);
  const cases = ((mj.b || {}).cases || []);
  const pv = cases.find((x) => x.case_id === DEC) || {}, ar = cases.find((x) => x.case_id === ARIF) || {}, rk = cases.find((x) => x.case_id === REKHA) || {};
  is("minutes: decision", who("C"), "closed", "the decision text", String((pv.decision || {}).text || "").slice(0, 60), /API check decision text/.test((pv.decision || {}).text || ""));
  is("minutes: late concern (finding 5)", who("C"), "closed", "the Concern card given after the outcome", `divergent_opinions "${String((pv.decision || {}).divergent_opinions || "").slice(0, 60)}"`,
    /late concern/.test((pv.decision || {}).divergent_opinions || ""), "finding 5");
  is("minutes: concern before the outcome", who("C"), "closed", "the concern on the not-discussed case", `"${String((ar.decision || {}).divergent_opinions || "").slice(0, 70)}"`,
    /concern before the outcome/.test((ar.decision || {}).divergent_opinions || ""));
  is("minutes: undecided case", who("C"), "closed", "Rekha listed with no decision", `status ${rk.agenda_status}, decision ${rk.decision ? "yes" : "none"}`, !!rk.case_id && !rk.decision);
  const att = ((mj.b || {}).attendance || []).filter((d) => d.status === "present").map((d) => d.id);
  is("minutes: attendance", who("C"), "closed", "radiology, gynaecologic oncology and medical oncology present", att.join(" "),
    ["radiology", "gynaecologic_oncology", "medical_oncology"].every((x) => att.includes(x)));
  const mh = await ck("GET /sessions/{mid}/minutes", "C", "closed", "GET", `/api/tb/sessions/${T}/minutes`, undefined, 200);
  is("minutes html", who("C"), "closed", "text/html with the decision, no em dash", `${mh.ct.slice(0, 24)}, ${mh.len} bytes, em dash ${mh.text.includes("\u2014")}`,
    /html/.test(mh.ct) && /API check decision text/.test(mh.text) && !mh.text.includes("\u2014"));
  const mr = await ck("GET /sessions/{mid}/minutes?format=json", "R", "closed", "GET", `/api/tb/sessions/${T}/minutes?format=json`, undefined, 200, "a member not on any team");
  const rcs = ((mr.b || {}).cases || []);
  is("minutes for a member not on the team", who("R"), "closed", "every case restricted (no patient, no decision)", rcs.map((x) => `${x.case_id}:${x.restricted ? "restricted" : "FULL"}`).join(" "),
    rcs.length > 0 && rcs.every((x) => x.restricted && !x.decision && !x.patient));
  const mg = await ck("GET /sessions/{mid}/minutes?format=json", "G", "closed", "GET", `/api/tb/sessions/${T}/minutes?format=json`, undefined, 200, "the owner's doctor");
  is("minutes for the owner's doctor", who("G"), "closed", "own cases in full, Arif restricted", ((mg.b || {}).cases || []).map((x) => `${x.case_id}:${x.restricted ? "restricted" : "full"}`).join(" "),
    ((mg.b || {}).cases || []).some((x) => x.case_id === REKHA && !x.restricted) && ((mg.b || {}).cases || []).some((x) => x.case_id === ARIF && x.restricted));
  await ck("GET /sessions/{mid}/minutes", "B", "closed", "GET", `/api/tb/sessions/${T}/minutes`, undefined, 403, "Breast Surgery: not on the sheet, no case", { failAs: "NOTE" });
  await ck("GET /sessions/{mid}/minutes", "A", "closed", "GET", `/api/tb/sessions/${T}/minutes`, undefined, 403, "root admin");
  // the PowerPoint deck was replaced by the meeting PDF (meetings-v2 4.1 and 4.2)
  const dk = await ck("GET /meetings/{mid}/pdf", "C", "closed", "GET", `/api/tb/meetings/${T}/pdf`, undefined, 200, "", { timeout: 180000 });
  is("GET /meetings/{mid}/pdf (closed)", who("C"), "closed", "pdf attachment", `${dk.ct.slice(0, 60)}; ${dk.disp.slice(0, 60)}`, /application\/pdf/.test(dk.ct));
  await ck("GET /meetings/{mid}/pdf", "M", "closed", "GET", `/api/tb/meetings/${T}/pdf`, undefined, 200, "admitted during the meeting", { timeout: 180000 });
  const vt = await ck("GET /cases/{id}/export/vtb", "C", "-", "GET", `/api/tb/cases/${REKHA}/export/vtb`, undefined, [200, 409], "Rekha (a Case summary exists)", { timeout: 180000 });
  if (vt.s === 200) is("GET /cases/{id}/export/vtb (type)", who("C"), "-", "pptx", `${vt.ct.slice(0, 60)}, ${vt.len} bytes`, /presentationml/.test(vt.ct) && vt.len > 1000);
  if (fresh) await ck("GET /cases/{id}/export/vtb", "C", "-", "GET", `/api/tb/cases/${fresh}/export/vtb`, undefined, [200, 409], "the fresh Case File (no summary yet: 409)", { timeout: 180000 });
  await ck("GET /cases/{id}/export/vtb", "B", "-", "GET", `/api/tb/cases/${REKHA}/export/vtb`, undefined, 403, "another department");
  await ck("GET /cases/{id}/export/vtb", "R", "-", "GET", `/api/tb/cases/${REKHA}/export/vtb`, undefined, 403, "a member of the meeting, not on the team");
}

async function auditCheck() {
  const T = made.today;
  const since = (e) => String(e.ts || "") >= T0LOCAL;
  const kindsBy = {};
  for (const k of ["C", "R", "G"]) {
    const r = await call("C", "GET", `/api/tb/activity?user=${U[k]}&limit=2000`);
    const evs = ((r.b || {}).events || []).filter(since);
    kindsBy[k] = evs;
  }
  const all = [].concat(...Object.values(kindsBy));
  const kinds = new Set(all.map((e) => e.kind));
  facts.audit_kinds = [...kinds].sort();
  const want = ["created", "meeting_updated", "agenda_lists", "agenda_added_to_list", "agenda_sent", "code_issued", "joined", "admitted", "presence_mode", "meeting_started",
    "opened", "timer", "question", "agent_added", "agents_settings", "hand", "spotlight", "reaction", "present_allowed", "presenting", "chat", "slides_read", "case_ended", "card",
    "outcome", "meeting_ended", "meeting_cancelled", "agenda_moved", "agenda_withdrawn", "agenda_removed_by_owner"].concat(facts.remind_ok ? ["reminded"] : []);
  const missing = want.filter((k) => !kinds.has(k));
  is("audit (session events of this run)", "coordinator reads /activity", "-", "a line for every action", missing.length ? `missing ${missing.join(" ")}` : `${want.length} kinds present`,
    missing.length === 0, "kinds per action; the chat line is audited as characters only");
  const blob = JSON.stringify(all);
  is("audit: the join code", "-", "-", "never in the audit", codeValue && blob.includes(codeValue) ? "FOUND" : "absent", !(codeValue && blob.includes(codeValue)));
  is("audit: chat words", "-", "-", "chat words not in the audit", /a chat line \(synthetic\)/.test(blob) ? "FOUND" : "absent", !/a chat line \(synthetic\)/.test(blob));
}

// ---- clean-up and output -----------------------------------------------------------------------------------------------------------

async function cleanup() {
  const done = {};
  for (const [name, mid] of Object.entries(made)) {
    try {
      const st = (await view(mid)).status;
      if (st === "in_session") { const r = await call("C", "POST", `/api/tb/meetings/${mid}/end`, {}); done[name] = `ended (${r.s})`; }
      else if (st === "planned") { const r = await call("C", "POST", `/api/tb/meetings/${mid}/cancel`, { reason: "API check cleanup (synthetic)" }); done[name] = `cancelled (${r.s})`; }
      else done[name] = st;
      done[name] += " -> " + (await view(mid)).status;
    } catch (e) { done[name] = "cleanup error " + e.message.slice(0, 80); }
  }
  facts.cleanup = done;
  console.log("\nMeetings made and their end state:", JSON.stringify(Object.fromEntries(Object.entries(made).map(([n, m]) => [n, `${m}: ${done[n]}`])), null, 1));
  try {
    const a = await caseOf(ARIF), r = await caseOf(REKHA);
    facts.after = { [ARIF]: { meeting_id: a.meeting_id, board_date: a.board_date }, [REKHA]: { meeting_id: r.meeting_id, board_date: r.board_date } };
    if (made.plannedA && a.meeting_id === made.plannedA) rec("POST /meetings/{mid}/cancel (Case Files)", who("C"), "cancelled", "the agenda Case Files let go or told",
      `Arif still points at the cancelled meeting ${a.meeting_id}`, "NOTE", "cancel leaves meeting_id and board_date on the Case Files of its agenda");
  } catch { /* the Case Files are read for the report only */ }
}

const T0LOCAL = `${TODAY}T${pad(NOW.getHours())}:${pad(NOW.getMinutes())}:00`;
let fatal = null;
try {
  if (NOWHM >= "23:40") throw new Error("run before 23:40: meeting A is planned for 23:59 today");
  await signIn();
  if (!S.C || !S.G || !S.R) throw new Error("the coordinator, the presenter and the member logins are needed");
  await noMeetingRoutes();
  const fresh = await freshCase();
  await mk("today", TODAY, NOWHM, { minutes_per_case: 10 });
  await mk("plannedA", TODAY, LATE);
  await mk("plannedB", plus(7), "10:00");
  await mk("plannedC", plus(7), "11:00");
  if (!made.today || !made.plannedA || !made.plannedB || !made.plannedC) throw new Error("the meetings could not be made");
  await planned(fresh);
  await inSession(fresh);
  await closed(fresh);
  await auditCheck();
} catch (e) {
  fatal = e;
  console.log("ERROR " + (e.stack || e.message).slice(0, 800));
  rec("run", "-", "-", "no error", "error: " + e.message.slice(0, 160), "FAIL");
} finally {
  await cleanup();
  const totals = { PASS: 0, FAIL: 0, NOTE: 0 };
  for (const r of rows) totals[r.verdict] = (totals[r.verdict] || 0) + 1;
  fs.writeFileSync(OUTFILE, JSON.stringify({ run_at: T0LOCAL, base: BASE, meetings: made, facts, totals, rows, notices, error: fatal ? String(fatal.message) : null }, null, 1));
  console.log(`\nTOTAL ${rows.length} checks: ${totals.PASS} PASS, ${totals.FAIL} FAIL, ${totals.NOTE} NOTE -> ${OUTFILE}`);
  for (const r of rows.filter((x) => x.verdict !== "PASS")) console.log(`  ${r.verdict} #${r.n} ${r.route} | ${r.role} | ${r.state} | exp ${r.expected} | got ${r.got}${r.why ? " | " + r.why : ""}`);
  if (browser) await browser.close();
}
