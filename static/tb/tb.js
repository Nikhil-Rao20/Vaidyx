// Vaidyx-TB frontend. Vanilla JS, same-origin only (CSP). All document-derived text is escaped before rendering.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { caseId: null, data: null, tab: "ready", cards: null, roles: null, protocols: null, chat: [], briefs: {}, me: null, org: null };
// permissions: the server decides (org.can on every route); the UI only hides what the current user may not do (V1 item 2.1)
const can = (k, id) => { const v = (S.data?.permissions || {})[k]; return v === true || !!(v && typeof v === "object" && id && v[id]); };
const MAIN_SECTIONS = ["welcome", "case", "intake", "inbox", "sessions", "dashboard", "orgpage", "deptpage"];  // one main section shows at a time
const meCan = (k) => !!S.me && (S.me.admin || !!(S.org?.can || {})[k]);  // the server says what this user may do (V2 item 2.2)

async function api(path, opts = {}) {
  const o = { credentials: "same-origin", ...opts };
  if (o.json !== undefined) { o.method = o.method || "POST"; o.headers = { "Content-Type": "application/json" }; o.body = JSON.stringify(o.json); delete o.json; }
  const r = await fetch("/api/tb" + path, o);
  if (r.status === 401) { location.href = "/login"; throw new Error("not logged in"); }
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  return r.json();
}
function toast(msg, ms = 3500) { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), ms); }
// Document dates (V1 item 3.1): event date (clinical order) with the report date standing in when only one was found; unconfirmed = none found.
const docDates = (c) => { c = c || {}; const r = c.report_date_iso || "", e = c.event_date_iso || "";
  return { report: r || e, event: e || r, reportAssumed: !!c.report_date_assumed || (!r && !!e), eventAssumed: !!c.event_date_assumed || (!e && !!r), unconfirmed: c.date_unconfirmed != null ? !!c.date_unconfirmed : !(r || e), flags: c.date_flags || [] }; };
const fmtDate = (d) => { if (!d) return "?"; const x = new Date(d + (d.length === 10 ? "T00:00:00" : "")); return isNaN(x) ? d : x.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }); };
const DT = { clinical_note: "Clinical note", referral: "Referral", discharge_summary: "Discharge summary", ct: "CT", mri: "MRI", xray: "X-ray", ultrasound: "Ultrasound",
  mammogram: "Mammogram", pet_ct: "PET/CT", bone_scan: "Bone scan", histopathology: "Histopathology", cytology: "Cytology", ihc: "IHC", molecular: "Molecular",
  lab: "Laboratory", endoscopy: "Endoscopy", operative_note: "Operative note", treatment_summary: "Treatment summary", tumour_board_record: "Tumour Board record",
  pulmonary_function: "PFT", other: "Other" };

// ------------------------------------------------------------------ models
async function loadModels() {
  try {
    const h = (await api("/health")).models;
    const tag = (m) => (m.origin ? `<span class="chip ${/chin/i.test(m.origin) ? "c-cn" : "c-mute"}">${esc(m.origin)}</span>` : "") +
      (m.medical === false ? `<span class="chip c-nm">Non-medical</span>` : m.medical ? `<span class="chip c-info">Medical</span>` : "");
    $("#models").innerHTML = Object.entries(h).filter(([k]) => k !== "extractor" || (h.extractor.base_url !== h.reader.base_url && h.extractor.base_url !== h.reasoner.base_url))
      .map(([k, m]) => `<span class="mpill" title="${esc(m.base_url)}"><span class="dot ${m.online ? "on" : "off"}"></span><b>${k === "reader" ? (h.extractor?.base_url === h.reader.base_url ? "Reader + extractor" : "Document reader") : k === "reasoner" ? "Reasoning" : "Extractor"}</b> ${esc(m.label || m.model)} ${tag(m)}</span>`).join("");
  } catch (e) { $("#models").innerHTML = `<span class="mpill"><span class="dot off"></span>models unavailable</span>`; }
}

// ------------------------------------------------------------------ cases
async function loadCases() {
  const d = await api("/cases"); S.demoList = d.demo; S.cases = d.cases;  // listed board dates feed the agenda panel (12 Oct)
  const awaiting = d.cases.filter((c) => c.listing?.status === "awaiting_listing");
  $("#case-list").innerHTML = (awaiting.length ? `<div class="small muted" style="margin:2px 0 6px">${awaiting.length} awaiting listing</div>` : "") + (d.cases.length ? d.cases.slice().sort((a, b) => (b.listing?.status === "awaiting_listing") - (a.listing?.status === "awaiting_listing")).map((c) => `
    <div class="citem ${c.case_id === S.caseId ? "on" : ""}" data-case="${esc(c.case_id)}">
      <div class="t"><span>${esc(c.patient?.name || c.case_id)}</span>${c.gate_passed ? '<span class="chip c-ok">Ready</span>' : c.readiness != null ? `<span class="chip c-warn">${c.readiness}%</span>` : c.listing?.status === "awaiting_listing" ? '<span class="chip c-mute">Awaiting listing</span>' : ""}</div>
      <div class="s">${esc(c.case_id)} · ${esc(c.protocol || "no protocol yet")} · ${c.documents} documents${c.open_actions ? ` · ${c.open_actions} open actions` : ""}</div>
      ${caseRowOwner(c)}
      ${c.his ? `<div class="s"><span class="mono" title="${esc(`Created from ${c.his.label || "the hospital system"}; ${c.his.window_label || ""}`)}">HIS ${esc(c.his.uhid || "")}</span>${c.his.unlinked ? ` <span class="chip c-warn">${plural(c.his.unlinked, "registration")} to link</span>` : ""}</div>` : ""}
    </div>`).join("") : `<div class="muted small">No Case Files yet.</div>`);
  $$(".citem").forEach((el) => (el.onclick = () => openCase(el.dataset.case)));
  $("#demo-list").innerHTML = d.demo.map((c) => `<div class="demo"><b>${esc(c.case_id)}</b> ${esc(c.patient?.name)}<br><span class="muted">${esc(c.protocol)} · ${c.files} files${c.has_arrivals ? " · has later arrivals" : ""}</span><br>
      ${meCan("create_case") ? `<button class="ghost sm" data-demo="${esc(c.case_id)}" style="margin-top:6px">Load as new Case File</button>` : ""}</div>`).join("") || `<div class="muted small">No demo corpus found.</div>`;
  $$("[data-demo]").forEach((b) => (b.onclick = async () => {
    if (!confirm(`Load synthetic case ${b.dataset.demo}? Any existing Case File with this id is replaced.`)) return;
    const j = await api("/demo/" + b.dataset.demo, { method: "POST" });
    S.caseId = b.dataset.demo; await openCase(S.caseId); watchJob(j.job);
  }));
}

async function openCase(id, keepTab) {
  if (id !== S.caseId) { S.tab = "ready"; }
  if (id !== S.chatCase) { S.chat = []; S.chatCase = id; }  // questions and answers never follow into another patient's Case File (Phase 6 review)
  S.caseId = id; S.data = await api("/cases/" + encodeURIComponent(id));
  MAIN_SECTIONS.forEach((x) => $("#" + x).classList.toggle("hidden", x !== "case")); stopRoomPoll();
  const c = S.data.case, p = c.patient || {};
  $("#c-protocol").textContent = (S.protocols?.find((x) => x.id === c.protocol)?.label || c.protocol) + " · Tumour Board Case File";
  $("#c-title").textContent = p.name || c.case_id;
  const setLabel = S.protocols?.find((x) => x.id === c.protocol)?.settings?.find((x) => x.id === c.setting)?.label;
  $("#c-meta").textContent = [c.case_id, p.mrn && "UHID / MRN " + p.mrn, p.agesex, c.listing?.status === "awaiting_listing" ? (c.listing?.reason === "referred" ? "Awaiting listing: no Pre-Authorization check until the cancer protocol is chosen" : "Awaiting listing: no Pre-Authorization check until the coordinator lists it") : "", setLabel && "NCG setting: " + setLabel,
    c.hospital_level && "Hospital level: " + c.hospital_level, c.board_date && "Board " + fmtDate(c.board_date)].filter(Boolean).join(" · ");
  const unlisted = c.listing?.status === "awaiting_listing", referred = unlisted && c.listing?.reason === "referred";  // referred: the new owner picks the protocol (V2 item 5.2)
  const listBtn = can("list_case") ? `<button class="${unlisted ? "primary" : "ghost"} sm" id="btn-list">${unlisted ? "List for the board" : "Change listing"}</button>` : "";
  $("#c-actions").innerHTML = ownerLineHTML() + (referred ? `<div class="banner warn small refbanner"><b>Referred here by ${esc(referredFrom())}: choose the cancer protocol for the new work-up</b>${listBtn}</div>` : listBtn) + readyLineHTML();
  if ($("#btn-list")) $("#btn-list").onclick = listCase;
  bindReadyLine();
  bindOwnerLine($("#c-actions"));
  renderReadiness();
  const hide = isLimited() ? ["ask", "roles", "summary", "board", "audit"] : unlisted ? ["roles", "summary", "board"] : [];  // a department that was only asked: its requests and records (V2 item 5.1)
  $$("#tabs button").forEach((b) => b.classList.toggle("hidden", hide.includes(b.dataset.tab)));
  if (hide.includes(S.tab)) S.tab = "ready";
  if (!keepTab) S.tab = S.tab || "ready";
  showTab(S.tab);
  loadCases();
}

function renderReadiness() {
  if (isLimited()) { $("#c-ready").innerHTML = ""; return; }  // a department that was only asked never sees the gate (V2 item 5.1)
  const g = S.data.state.gate;
  if (!g) { $("#c-ready").innerHTML = S.data.case.listing?.status === "awaiting_listing" ? `<div class="rtext"><b>Not listed yet</b><span>Records are kept; the Pre-Authorization check starts when the Case File is listed</span></div>` : ""; return; }
  const pct = g.readiness, r = 26, C = 2 * Math.PI * r, col = g.passed ? "#1e6b45" : pct >= 60 ? "#8a5300" : "#b23a2f";
  $("#c-ready").innerHTML = `<svg class="ring" viewBox="0 0 64 64"><circle cx="32" cy="32" r="${r}" fill="none" stroke="#d9e2ec" stroke-width="7"/>
    <circle cx="32" cy="32" r="${r}" fill="none" stroke="${col}" stroke-width="7" stroke-linecap="round" stroke-dasharray="${C * pct / 100} ${C}" transform="rotate(-90 32 32)"/>
    <text x="32" y="37" text-anchor="middle" font-size="15" font-weight="600" fill="#1f2933">${pct}%</text></svg>
    <div class="rtext"><b>${g.passed ? "Readiness criteria met" : "Pre-Authorization pending"}</b><span>${g.satisfied} of ${g.total} mandatory records satisfied</span></div>`;
}

function showTab(t) {
  S.tab = t;
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === t));
  $$(".tab").forEach((el) => el.classList.toggle("hidden", el.id !== "tab-" + t));
  ({ ready: renderReady, docs: renderDocs, ask: renderAsk, roles: renderRoles, summary: renderSummary, board: renderBoard, audit: renderAudit })[t]();
}

// ------------------------------------------------------------------ citations / evidence
const flagHTML = (x) => (x.flags || []).map((f) => `<span class="chip c-warn" title="${/approximate/.test(f) ? "The quote matches the source only approximately (a character or word differs). Open the source and check it before relying on this item. Left out of the print view until an expert reviews it." : "The cited source contains a negation (no / not / negative / absent) that this sentence does not; read the source before relying on it."}">${esc(f)}</span>`).join("");
const modelLabel = (m) => (!m ? "" : /non-medical/i.test(m) ? m : `${m} (non-medical)`);
// an item kept on an approximate source match (V1 item 6.5) is left out of the print view until an expert has reviewed the artefact
const approxCls = (x, rv) => (x.approximate && (rv || {}).status !== "reviewed" ? "noprint approx" : "");
// V1 item 6.4: what the model wrote but verification or the scope guardrail took out, kept with the reason for reviewers
const WHERE = { presentation: "Presenting complaints", treatment_history: "Treatment history", investigations: "Investigations", imaging: "Imaging", fitness: "Fitness for treatment",
  questions: "Questions for the board", points_for_review: "Points for review", not_documented: "Not documented", answer: "Answer" };
function removedHTML(list) {
  if (!list || !list.length) return "";
  return `<details class="removed noprint"><summary class="small">${list.length} removed item${list.length === 1 ? "" : "s"} (failed verification, not facts)</summary>
    <div class="small muted">What the model wrote that was taken out before display, with the reason. Not facts: never rely on them.</div>
    <ul>${list.map((x) => `<li class="small"><span class="chip c-mute">${esc(x.reason_label || x.reason)}</span> <s>${esc(x.text)}</s>${x.detail ? ` <span class="muted">(${esc(x.detail)})</span>` : ""}${x.where ? ` <span class="muted">· ${esc(WHERE[x.where] || x.where)}</span>` : ""}</li>`).join("")}</ul></details>`;
}
// V1 item 8.1: a quote on a scanned page was checked against the vision reader's transcription, not against the image
const SCAN_TITLE = "Read from a scanned page by the vision reader (Qwen3.5-4B, Chinese, non-medical). The quote was checked against that transcription, not against the image: open the source and compare with the scan.";
const scanPage = (id, page) => page !== undefined && page !== null && page !== "" && !!(S.data?.documents || []).find((d) => d.doc_id === id)?.scan_pages?.includes(+page);
const isScan = (c) => !!c && (c.source_method ? c.source_method === "vision-transcription" : scanPage(c.doc_id, c.page));
const scanChip = (c) => (isScan(c) ? ` <span class="chip c-scan" title="${SCAN_TITLE}">from scan (OCR)</span>` : "");
// V1 item 8.2: a critical value (biomarkers, stage as recorded) read from a scan counts for the gate only once a clinician confirmed it on the image
const scanNeeds = () => [...(S.data?.state?.gate?.requirements || []), ...(S.data?.state?.gate?.shown || [])].flatMap((r) => (r.needs || []).filter((n) => n.type === "confirm_value"));
const critChip = (fid, f, docId) => (f && f.verification === "verified" && scanNeeds().some((n) => n.fact === fid && n.doc_id === (docId || f.doc_id)) ? ` <span class="chip c-warn" title="Critical value read from a scan: the Pre-Authorization asks a clinician to confirm it against the image">confirm on the scan</span>` : "");
function citeHTML(c) {
  const label = `${c.doc_title || c.doc_id}${c.date ? " · " + fmtDate(c.date) : ""}`;
  return `<span class="cite" data-doc="${esc(c.doc_id)}" data-page="${c.page ?? ""}" data-start="${c.start ?? ""}" data-end="${c.end ?? ""}" title="&quot;${esc(c.quote)}&quot;${isScan(c) ? " (" + SCAN_TITLE + ")" : ""}">${esc(label)}${isScan(c) ? '<span class="scan-tag">from scan (OCR)</span>' : ""}</span>`;
}
document.addEventListener("click", (e) => {
  const c = e.target.closest(".cite");
  const roomCase = c && c.closest("#sessions") ? S.roomCase : null;  // a citation in the Board room opens the room's Case File
  if (c) openDoc(c.dataset.doc, c.dataset.page !== undefined && c.dataset.page !== "" ? { page: +c.dataset.page, start: +c.dataset.start, end: +c.dataset.end } : null,
    roomCase ? `/cases/${encodeURIComponent(roomCase)}/documents/${encodeURIComponent(c.dataset.doc)}` : undefined);
  if (e.target.id === "drawer" || e.target.closest("[data-close]")) $("#drawer").classList.add("hidden");
  if (e.target.id === "modal" || e.target.closest("[data-closemodal]")) $("#modal").classList.add("hidden");
  if (e.target.closest("[data-rmrow]")) e.target.closest(".arow").remove();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { $("#drawer").classList.add("hidden"); $("#modal").classList.add("hidden"); } });

const STATUS = {
  satisfied: ["c-ok", "Satisfied", "i-ok", "✓"], missing_record: ["c-bad", "Record missing", "i-bad", "×"], not_final: ["c-bad", "Not final / signed", "i-bad", "!"],
  missing_field: ["c-warn", "Field missing or pending", "i-warn", "!"], needs_review: ["c-rev", "Needs expert review", "i-rev", "?"], not_applicable: ["c-mute", "Not applicable", "i-na", "–"],
  needs_confirmation: ["c-warn", "Needs your confirmation", "i-warn", "?"], waived: ["c-mute", "Waived for this Case File", "i-na", "–"],
};
const FINALISH = (c) => ["FINAL", "AMENDED", "CORRECTED"].includes(c.status) && c.signed !== "no";
const statusChip = (c) => { if (!c || !c.status) return ""; const ok = FINALISH(c); const un = c.status === "UNSTATED" && c.signed !== "no";
  return `<span class="chip ${ok || (un && c.signed === "yes") ? "c-ok" : un ? "c-warn" : "c-bad"}" title="${esc((c.status_notes || []).join("; "))}">${un ? (c.signed === "yes" ? "Signed, status not stated" : "Status not stated") : esc(c.status)}${c.signed === "no" ? " · unsigned" : c.signed === "yes" && !un ? " · signed" : ""}</span>`; };

// ------------------------------------------------------------------ tab: Pre-Authorization
const TIER = { a: ["c-ok", "NCG Essential"], b: ["c-info", "NCG Optimal"], c: ["c-mute", "NCG Optional"], none: ["c-mute", "Not applicable"] };
const LEVEL = { 1: ["Level 1 · Case File", "The record is missing, not final or not this patient"], 2: ["Level 2 · Records", "A required value is missing, pending or not verified in the record"] };
function ncgLine(r) {
  // the NCG line each record rests on (V1 item 4.1): guideline, page and verbatim quote; then the basis / caveat texts
  const src = r.sources && r.sources.length ? r.sources : r.source ? [r.source] : [];
  const cites = src.map((x) => `${esc(x.guideline || "NCG")}${x.page !== undefined && x.page !== "n/a" ? ", p. " + esc(x.page) : x.where ? ", " + esc(x.where) : ""}: "${esc(x.quote || "")}"`).join("; ");
  const extra = [r.tier_basis, r.note, r.setting_note].filter(Boolean).map(esc).join(" · ");
  return cites || extra ? `<div class="ncg muted">${cites}${extra ? `<div>${extra}</div>` : ""}</div>` : "";
}
function reqRow(r, shown) {
  const s = STATUS[r.status] || STATUS.needs_review;
  const ev = r.evidence.filter((e) => e.doc_id).map((e) => {
    const d = S.data.documents.find((x) => x.doc_id === e.doc_id); const cl = d?.classification || {};
    return `<span class="cite" data-doc="${esc(e.doc_id)}" title="${esc(e.quote || "")}${e.value && isScan(e) ? " (" + SCAN_TITLE + ")" : ""}">${esc(e.value ? `${S.facts?.[e.fact]?.label || e.fact}: ${e.value}` : (cl.title || e.doc_id))}${docDates(cl).event ? " · " + fmtDate(docDates(cl).event) : ""}${e.value && isScan(e) ? '<span class="scan-tag">from scan (OCR)</span>' : ""}</span>`;
  }).join("");
  const needs = r.needs || (r.status === "needs_confirmation" && r.evidence[0]?.doc_id ? [{ type: "attest_final", doc_id: r.evidence[0].doc_id }] : []);
  const attest = needs.filter((n) => can("confirm", n.doc_id)).map((n) => n.type === "attest_final" ? `<button class="ghost sm" data-attest="${esc(n.doc_id)}">Attest: final, signed</button>`
    : n.type === "confirm_dates" ? `<button class="ghost sm" data-confdate="${esc(n.doc_id)}">Confirm date</button>`
    : n.type === "confirm_doc_type" ? `<button class="ghost sm" data-conftype="${esc(n.doc_id)}">Confirm document type</button>`
    : n.type === "confirm_value" ? `<button class="ghost sm" data-confval="${esc(JSON.stringify(n))}" title="Read the value on the scan image and record it (V1 8.2)">Confirm ${esc(S.facts?.[n.fact]?.label || n.fact)} on the scan</button>`
    : n.type === "confirm_match" ? `<button class="ghost sm" data-confmatch="${esc(n.doc_id)}" title="An outside report matched by name only: check the patient on the report and confirm">Confirm patient</button>` : "").join("");
  const waive = shown || !can("waive", r.id) ? "" : r.status === "waived" ? `<button class="ghost sm" data-unwaive="${esc(r.id)}">Remove waiver</button>` : (r.status !== "satisfied" && r.status !== "not_applicable") ? `<button class="ghost sm" data-waive="${esc(r.id)}" title="Clinical decision that this record is not required for this Case File (audited)">Waive</button>` : "";
  // a record NCG tiers under a condition the system never judges: NCG's own tier, marked conditional, never counted
  const tier = r.ncg_tier ? ["c-mute", (TIER[r.ncg_tier] || TIER.c)[1] + " (conditional)"] : TIER[r.tier] || TIER.a;
  const lvl = r.level && !shown ? ` <span class="chip c-lvl" title="${esc(LEVEL[r.level][1])}">${LEVEL[r.level][0]}</span>` : "";
  const chip = shown && r.status !== "satisfied" && r.status !== "not_applicable" ? `<span class="chip c-mute" title="Shown for information: not counted at this hospital level or in this setting">${esc(s[1])} (not counted)</span>` : `<span class="chip ${s[0]}">${s[1]}</span>`;
  const po = r.pending_order;  // V2 item 3.3: the HIS order behind the gap and its stage; the accession / Lab No. of the record
  const his = (r.accession ? ` <span class="chip c-mono" title="Accession / Lab No. in the hospital system">${esc(r.accession)}</span>` : "")
    + (po ? ` <span class="chip ${po.stage === "cancelled" ? "c-bad" : "c-info"}" title="${esc([po.test, po.performer_department && "performed by " + po.performer_department, po.encounter_number].filter(Boolean).join(" · "))}">Ordered in the HIS: ${esc(stageText(po))}</span>` : "");
  return `<div class="req ${shown ? "shown" : ""}"><div class="icon ${s[2]}">${s[3]}</div><div style="flex:1">
    <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap"><span class="lbl">${esc(r.label)} <span class="chip ${tier[0]}" title="${esc(r.tier_note || r.tier_label || "")}">${tier[1]}</span>${lvl}${his}</span><span style="display:flex;gap:4px;align-items:center;flex-wrap:wrap">${attest}${waive}${chip}</span></div>
    <div class="dept">Responsible Department: ${esc(r.department)}${r.tier_note ? " · " + esc(r.tier_note) : ""}</div>
    ${r.problems.map((p) => `<div class="prob">${esc(p)}</div>`).join("")}${(r.notes || []).map((p) => `<div class="prob muted">${esc(p)}</div>`).join("")}${ncgLine(r)}<div class="ev">${ev}</div></div></div>`;
}
function renderReady() {
  if (isLimited()) return renderLimited();  // V2 item 5.1: the reduced view of a department that was only asked
  const { state } = S.data, g = state.gate;
  const group = (title, sub, list, shown) => list.length ? `<div class="lvlhead"><b>${title}</b><span class="small muted">${sub}</span></div>${list.map((r) => reqRow(r, shown)).join("")}` : "";
  let reqs;
  if (g) {
    const l1 = g.requirements.filter((r) => r.level === 1), l2 = g.requirements.filter((r) => r.level === 2), met = g.requirements.filter((r) => !r.level);
    reqs = group(`Level 1 · Case File <span class="chip c-lvl">${l1.length} open</span>`, "each required record present, final and signed, right patient", l1)
      + group(`Level 2 · Records <span class="chip c-lvl">${l2.length} open</span>`, "required values present, verified, not pending", l2)
      + group("Met, waived or not applicable", `${met.filter((r) => r.status === "satisfied").length} of ${g.total} counted records met`, met)
      + group("Shown, not counted", "NCG Optimal records at an Essential hospital, Optional records, and records not applicable in this setting", g.shown || [], true);
    if (!g.requirements.length && !(g.shown || []).length) reqs = `<div class="muted">This protocol lists no records.</div>`;
  } else reqs = S.data.case.listing?.status === "awaiting_listing" ? `<div class="muted">Not listed: the Pre-Authorization check starts when the Case File is listed under a cancer protocol.</div>` : `<div class="muted">Not evaluated yet. Add documents to start.</div>`;
  const blockers = g?.blockers?.length ? `<div class="banner bad"><b>${g.blockers.length} document${g.blockers.length > 1 ? "s" : ""} failed to read</b> and block the Pre-Authorization until re-processed or dismissed (a dismissal needs a reason and is audited; the Case File can then pass without that document).
    ${g.blockers.map((b) => `<div class="row"><span>${esc(b.filename)}: <span class="muted">${esc(b.error)}</span></span>${can("reprocess") ? `<button class="ghost sm" data-reproc-doc="${esc(b.doc_id)}">Re-process</button>` : ""}${can("confirm", b.doc_id) ? `<button class="ghost sm" data-dismiss="${esc(b.doc_id)}">Dismiss</button>` : ""}</div>`).join("")}</div>` : "";
  const opt = g ? g.optional.map((o) => `<span class="chip ${o.available ? "c-info" : "c-mute"}" style="margin:2px">${o.available ? "✓ " : ""}${esc(o.label)}</span>`).join("") : "";
  const acts = (state.actions || []).filter((a) => a.source === "pre_authorization");
  const RQORD = { suggested: 0, overdue: 1, pending: 2, completed: 3 };  // what still needs the doctor first, closed last
  const actHTML = acts.length ? acts.sort((a, b) => (RQORD[a.status] ?? 2) - (RQORD[b.status] ?? 2)).map(actionHTML).join("") : `<div class="muted small">No requests.</div>`;
  const rq = S.data.requests || { suggested: acts.filter((a) => a.status === "suggested").length, sent: acts.filter((a) => a.status === "pending" || a.status === "overdue").length, closed: acts.filter((a) => a.status === "completed").length };
  const docs = g?.documents || {};
  const setting = g ? `NCG setting: <b>${esc(g.setting_label || "not recorded (the strictest tier of each record applies until the coordinator records it)")}</b> · Hospital level: <b>${esc(g.hospital_level || "essential")}</b> · Protocol ${esc(g.protocol)} v${esc(g.protocol_version || "")}` : "";
  const hisCase = !!S.data.his;
  $("#tab-ready").innerHTML = `<div class="grid2"><div>
    ${hisCardHTML()}
    ${ownershipCardHTML()}
    <div class="card"><h3>Pre-Authorization check <span class="btns">${hisCase && can("refetch") ? `<button class="ghost sm" id="btn-refetch" data-refetch title="Fetch from the hospital system only the records new or changed since the last fetch; the Pre-Authorization then re-checks">Re-fetch from the HIS</button>` : ""}<button class="ghost sm" id="btn-recheck">Re-check now</button></span></h3>
      <div class="muted small" style="margin-bottom:6px">Required records from the NCG Essential / Optimal / Optional tiers for this cancer and setting (clinical review before real use). A record counts only when it is the final, signed version and its required primary fields are found with a verified source quote. Document exists ≠ Document is ready.</div>
      ${setting ? `<div class="small" style="margin-bottom:4px">${setting}</div>` : ""}${g?.tiers_note ? `<div class="muted small" style="margin-bottom:6px">${esc(g.tiers_note)}</div>` : ""}
      ${blockers}${orphanHTML(g)}${reqs}${gateHistoryHTML()}</div>
    ${hisFlagsHTML()}
    ${g?.core_data?.length ? `<div class="card"><h3>MDT minimum core data <span class="muted small">${g.core_data.filter((c) => c.present).length} of ${g.core_data.length} documented</span></h3>
      <div class="muted small" style="margin-bottom:6px">Informational checklist (not part of the gate). Source: ${esc(g.core_data_source || "")}.</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">${g.core_data.map((c) => c.present ? `<span class="cite" data-doc="${esc(c.evidence[0]?.doc_id || "")}" title="${esc((c.evidence[0]?.value || "") + " | " + (c.evidence[0]?.quote || ""))}">✓ ${esc(c.label)}</span>` : `<span class="chip c-mute">– ${esc(c.label)}</span>`).join("")}</div></div>` : ""}
    <div class="card"><h3>Optional records available</h3><div>${opt || '<span class="muted small">None</span>'}</div></div>
    ${discordHTML()}
    ${confirmationsHTML()}
    ${g?.policy_basis ? `<div class="card"><h3>Why a Pre-Authorization gate</h3><div class="small" style="color:#475569">${esc(g.policy_basis)}</div>${g.pmjay_note ? `<div class="small muted" style="margin-top:6px">${esc(g.pmjay_note)}</div>` : ""}</div>` : ""}
  </div><div>
    <div class="card" id="req-card"><h3>Requests to departments <span class="muted small">${rq.suggested || 0} suggested · ${rq.sent || 0} sent${rq.done ? ` (${rq.done} done)` : ""} · ${rq.closed || 0} closed</span>${can("create_request") ? `<span class="btns"><button class="ghost sm" data-newreq title="A request no protocol record covers, for example a pre-anaesthetic check-up">Notify a department</button></span>` : ""}</h3>
      <div class="muted small" style="margin-bottom:8px">Every gap becomes a suggested request to the Responsible Department (a Level 1 gap to the department that owns the record, a Level 2 gap to the department that uploaded it). Nothing is sent until the treating doctor sends it: Notify opens the draft to edit and send in-app, or to open in your own mail program. A sent request closes by itself when the record arrives (re-fetch from the HIS, or an upload); the department acknowledges it and sends "done" back from its inbox. The agent routes the gap; it does not perform the missing clinical task.</div>${actHTML}</div>
    <div class="card"><h3>${can("upload") ? (hisCase ? "Outside reports" : "Add documents") : "Documents"}</h3>
      ${can("upload") ? `<div class="drop" id="drop">${hisCase ? "Upload an outside report (another hospital, a private laboratory): it is read, matched to the patient and checked like every record" : "Drop files or a whole folder here"}<br><span class="small">PDF, scanned images (PNG / JPG / TIFF), text and Office files</span><br>
      <button class="ghost sm" id="pick-files" style="margin-top:8px">Choose files</button> <button class="ghost sm" id="pick-folder">Choose folder</button></div>
      <input type="file" id="f-files" multiple class="hidden"><input type="file" id="f-folder" webkitdirectory multiple class="hidden">` : `<div class="muted small">Department users upload through "Upload for my department" in the side panel; records are matched to the patient and filed here.</div>`}
      <div id="job"></div>
      ${can("upload") && (S.demoList || []).some((x) => x.case_id === S.caseId && x.has_arrivals) ? `<button class="ghost sm" id="btn-arrivals" style="margin-top:10px">Demo: new reports arrive from departments</button>` : ""}
      <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">${can("reprocess") && docs.errors ? `<button class="ghost sm" id="btn-reproc-err">Re-process ${docs.errors} failed</button>` : ""}${can("reprocess") ? `<button class="ghost sm" id="btn-reproc-all" title="Re-read, re-classify and re-extract every document (after a protocol or model change)">Re-process all documents</button>` : ""}<a class="ghost sm" href="/api/tb/cases/${esc(S.caseId)}/export">Export Case File record</a><a class="ghost sm" href="/api/tb/cases/${esc(S.caseId)}/export/fhir" title="FHIR R4 document bundle (mCODE-informed, ABDM-ready shape; values as recorded; codes not assigned)">FHIR bundle</a><a class="ghost sm" href="/api/tb/cases/${esc(S.caseId)}/export/registry?format=csv" title="HBCR (ICMR-NCDIR 2025) registry items as the records state them, with sources">Registry abstract</a></div>
      <div class="muted small" style="margin-top:10px">${docs.total || 0} documents · ${docs.ready || 0} processed${docs.processing ? ` · ${docs.processing} processing` : ""}${docs.errors ? ` · ${docs.errors} failed to read${docs.dismissed?.length ? ` (${docs.dismissed.length} dismissed)` : ""}` : ""}${docs.identity_flags?.length ? ` · <b style="color:#b23a2f">${docs.identity_flags.length} identity flags</b>` : ""}${docs.superseded?.length ? ` · ${plural(docs.superseded.length, "earlier version")} kept as history` : ""}${docs.outside_unconfirmed?.length ? ` · <b style="color:#8a5300">${plural(docs.outside_unconfirmed.length, "outside report")} awaiting the patient confirmation</b>` : ""}</div>
    </div>
    <div id="hs-card"></div></div></div>`;
  renderHospitalSystems();
  $("#btn-recheck").onclick = async () => { const st = await api(`/cases/${S.caseId}/recheck`, { method: "POST" }); await openCase(S.caseId, true); const r = st.recheck || {};
    toast(`Re-checked ${r.documents_checked} processed document(s) against the protocol: ${r.satisfied}/${r.total} satisfied${r.level1_open ? `, ${r.level1_open} Level 1 gap(s)` : ""}${r.level2_open ? `, ${r.level2_open} Level 2 gap(s)` : ""}${r.processing ? `, ${r.processing} still processing` : ""}${r.blockers ? `, ${r.blockers} failed document(s) block the gate` : ""}. ${r.changed?.length ? "Changed: " + r.changed.join(", ") + "." : "No change."} Documents are not re-read by a re-check; use Re-process for that.`, 9000); };
  const reproc = async (which) => { const j = await api(`/cases/${S.caseId}/reprocess`, { json: { which } }); watchJob(j.job); };
  if ($("#btn-reproc-err")) $("#btn-reproc-err").onclick = () => reproc("errors");
  if ($("#btn-reproc-all")) $("#btn-reproc-all").onclick = () => { if (confirm("Re-read, re-classify and re-extract every document in this Case File?")) reproc("all"); };
  $$("[data-reproc-doc]", $("#tab-ready")).forEach((b) => (b.onclick = () => reproc([b.dataset.reprocDoc])));
  $$("[data-dismiss]", $("#tab-ready")).forEach((b) => (b.onclick = () => dismissDoc(b.dataset.dismiss)));
  $$("[data-waive]", $("#tab-ready")).forEach((b) => (b.onclick = () => waiveReq(b.dataset.waive)));
  $$("[data-unwaive]", $("#tab-ready")).forEach((b) => (b.onclick = async () => { await api(`/cases/${S.caseId}/overrides`, { json: { kind: "requirements", key: b.dataset.unwaive, value: null } }); await openCase(S.caseId, true); toast("Waiver removed"); }));
  bindConfirmations($("#tab-ready"));
  $$("[data-confdate]", $("#tab-ready")).forEach((b) => (b.onclick = () => confirmDates(b.dataset.confdate)));
  $$("[data-conftype]", $("#tab-ready")).forEach((b) => (b.onclick = () => confirmDocType(b.dataset.conftype)));
  $$("[data-confval]", $("#tab-ready")).forEach((b) => (b.onclick = () => confirmValue(JSON.parse(b.dataset.confval))));
  $$("[data-attest]", $("#tab-ready")).forEach((b) => (b.onclick = () => attestDoc(b.dataset.attest)));
  bindHIS($("#tab-ready"));
  bindOwnership($("#tab-ready"));
  if ($("#drop")) bindUpload();
  const arr = $("#btn-arrivals");
  if (arr) arr.onclick = async () => { try { const j = await api(`/cases/${S.caseId}/demo-arrivals`, { method: "POST" }); watchJob(j.job); } catch (e) { toast(e.message); } };
  bindActions($("#tab-ready"));
  bindDiscord($("#tab-ready"));
}

// ------------------------------------------------------------------ quality dashboard and agenda readiness (12 Oct)
const FORECAST = { ready: ["✓", "Ready"], on_track: ["→", "On track"], at_risk: ["!", "At risk"], blocked: ["×", "Blocked"], not_listed: ["…", "Awaiting listing"] };
const fcChip = (f) => `<span class="chip fc-${esc(f)}">${esc((FORECAST[f] || ["", f])[0])} ${esc((FORECAST[f] || ["", f])[1])}</span>`;
const tile = (label, value, unit = "", sub = "") => `<div class="tile"><div class="lbl">${esc(label)}</div><div class="val">${value == null ? '<span class="muted">n/a</span>' : esc(String(value))}${unit && value != null ? `<small>${esc(unit)}</small>` : ""}</div>${sub ? `<div class="sub">${esc(sub)}</div>` : ""}</div>`;
const barRow = (label, value, max, text, target = null, muted = false) => `<div class="barrow"><div>${esc(label)}</div><div class="bar"><i class="${muted ? "muted" : ""}" style="width:${max ? Math.max(value ? 2 : 0, Math.round(100 * (value || 0) / max)) : 0}%"></i>${target != null && max ? `<b style="left:${Math.round(100 * target / max)}%" title="target ${target}"></b>` : ""}</div><div class="num">${esc(text)}</div></div>`;

function readinessHTML(a, remind = false) {  // remind: the MDT Coordinator / admin chases from here (V2 item 6.1)
  if (!a || !a.cases.length) return `<div class="muted small">No Case File is listed for this board date.</div>`;
  const rem = (n) => n ? ` <span class="muted">${plural(n, "reminder")}</span>` : "";
  const c = a.counts;
  return `<div class="tiles">${tile("Days to the board", a.days_to_board, "", a.board_date ? fmtDate(a.board_date) : "")}${tile("Ready", c.ready, "", `of ${a.cases.length} Case Files`)}${tile("On track", c.on_track)}${tile("At risk", c.at_risk, "", "requests due after the board or overdue")}${tile("Blocked", c.blocked, "", "documents failed to read")}${tile("Open requests", a.requests_open, "", `${a.requests_overdue} overdue`)}</div>
    <table class="t" style="margin-top:8px"><thead><tr><th>Case File</th><th>Forecast</th><th>Readiness</th><th>Open gaps</th><th>Summary</th></tr></thead><tbody>
    ${a.cases.map((r) => `<tr class="click" data-open="${esc(r.case_id)}"><td><b>${esc(r.patient)}</b><div class="small muted">${esc(r.case_id)} · ${esc(r.protocol || "not listed")}</div>${r.owner_name ? `<div class="small muted">Owner: ${esc(r.owner_name)}</div>` : ""}<div class="small">${r.ready ? `<span class="chip c-ok" title="${esc(r.ready.note || "")}">Ready (by ${esc(r.ready.by)})</span>` : `<span class="chip c-mute">Not marked ready</span>`}${rem(r.reminders)}</div>${remind && r.owner ? `<button class="ghost sm" data-remowner="${esc(r.case_id)}" data-patient="${esc(r.patient)}" title="One in-app reminder to ${esc(r.owner_name || "the owning department")}: requests not sent, overdue ones, the summary and the ready mark (audited)">Remind owner</button>` : ""}</td><td>${fcChip(r.forecast)}<div class="small muted">${esc(r.why)}</div></td>
      <td><div class="bar" style="min-width:90px"><i style="width:${r.readiness || 0}%"></i></div><div class="small">${r.satisfied ?? 0} of ${r.total ?? 0}${r.level1_open ? ` · L1 ${r.level1_open}` : ""}${r.level2_open ? ` · L2 ${r.level2_open}` : ""}</div></td>
      <td class="small">${r.gaps.slice(0, 4).map((g) => `${esc(g.label)} <span class="muted">(${esc(g.department)})</span>`).join("<br>")}${r.gaps.length > 4 ? `<br><span class="muted">+${r.gaps.length - 4} more</span>` : ""}${r.discordances_open ? `<br><span class="chip c-rev">${r.discordances_open} report(s) disagree</span>` : ""}</td>
      <td class="small">${r.summary === "ready" ? '<span class="chip c-ok">ready</span>' : r.summary === "stale" ? '<span class="chip c-warn">stale</span>' : '<span class="chip c-mute">none</span>'}${Object.keys(r.briefs).length ? `<div class="muted">${Object.keys(r.briefs).length} brief(s)</div>` : ""}</td></tr>`).join("")}</tbody></table>
    <h4 style="margin:14px 0 4px">Chase list: what to ask which department before the board</h4>
    ${a.chase.length ? a.chase.map((g) => `<div style="margin:6px 0"><b>${esc(g.department)}</b> <span class="muted small">${g.items.length} request(s)${g.overdue ? `, ${g.overdue} overdue` : ""}</span>
      <table class="t"><tbody>${g.items.map((x) => `<tr><td class="small" style="width:160px"><b>${esc(x.patient)}</b><div class="muted">${esc(x.case_id)}</div></td><td class="small">${esc(x.label)}${x.what ? `<div class="muted">${esc(x.what).slice(0, 160)}</div>` : ""}</td>
        <td class="small" style="width:150px">${x.due ? fmtDate(x.due) : "no due date"}<div>${x.overdue ? '<span class="chip c-bad">overdue</span>' : x.after_board ? '<span class="chip c-warn">due after the board</span>' : x.days_left != null ? `<span class="muted">${x.days_left} day(s) left</span>` : ""}${x.unsent ? ' <span class="chip c-mute">not sent</span>' : ""}${rem(x.reminders)}</div>
        ${remind && x.action_id ? `<button class="ghost sm" data-remreq="${esc(x.action_id)}" data-case="${esc(x.case_id)}" data-sug="${x.unsent ? "1" : ""}" data-label="${esc(x.label || "")}" title="${x.unsent ? "Not sent yet: the reminder goes to the owning department, asking it to send the request" : `Remind ${esc(g.department)} about this request`} (in-app, audited)">Remind</button>` : ""}</td></tr>`).join("")}</tbody></table></div>`).join("") : '<div class="muted small">Nothing to chase.</div>'}`;
}

async function showDashboard(start = "", end = "") {
  stopRoomPoll(); S.roomId = null; showOnly("dashboard");
  $("#dashboard").innerHTML = `<div class="card"><h3>Tumour Board quality dashboard</h3><div class="muted small"><span class="spin"></span> Counting...</div></div>`;
  let d;
  try { d = await api(`/metrics/dashboard?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`); } catch (e) { $("#dashboard").innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
  const b = d.kpis.before, du = d.kpis.during, af = d.kpis.after;
  const att = Object.values(du.attendance || {});
  const outcomes = Object.entries(af.outcomes || {});
  const flags = Object.entries(af.flags_by_kind || {});
  const maxOpen = Math.max(1, ...b.by_department.map((x) => x.open + x.closed));
  $("#dashboard").innerHTML = `<div class="card"><h3>Tumour Board quality dashboard <span class="muted small">counts of what the records and the system's events show · no clinical judgement</span></h3>
    <div class="dash-filters"><div><label>From</label><input type="date" id="dash-from" value="${esc(start)}"></div><div><label>To</label><input type="date" id="dash-to" value="${esc(end)}"></div>
      <button class="ghost sm" id="dash-apply">Apply</button><button class="ghost sm" id="dash-clear">All time</button><a class="ghost sm" href="/api/tb/metrics/dashboard?format=csv&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}">Export CSV</a></div>
    <div class="hero">${b.ready_now_pct == null ? "n/a" : b.ready_now_pct + "%"}</div><div class="muted small" style="margin-bottom:8px">of listed Case Files are ready now (Pre-Authorization met): ${b.ready_now} of ${b.listed}</div></div>

    <div class="card"><h3>Before the board</h3>
    <div class="tiles">${tile("Case Files", b.cases, "", `${b.listed} listed, ${b.awaiting_listing} awaiting listing`)}${tile("Readiness (median)", b.readiness_median, "%")}${tile("Ready before the board date", b.ready_before_board_pct, "%", `${b.ready_before_board_n} of ${b.ready_before_board_d} past boards · target 80% (Victorian 4.4)`)}${tile("Days listed to ready (median)", b.days_listed_to_ready_median)}${tile("Documents", b.documents, "", `${b.final_signed_pct ?? 0}% final and signed · ${b.scanned_pct ?? 0}% from scans`)}${tile("Reports that disagree", b.discordances_open, "", "open for review")}${tile("Identity flags", b.identity_flags, "", "documents needing a patient check")}${tile("Requests open", b.requests_open, "", `${b.requests_overdue} overdue · ${b.requests_closed} closed · median ${b.hours_to_close_median ?? "n/a"} h to close`)}</div>
    <h4 style="margin:12px 0 4px">Requests by department</h4><div class="muted small" style="margin-bottom:4px">Bar = open requests; number = open (overdue) · closed · median hours to close.</div>
    ${b.by_department.length ? b.by_department.map((x) => barRow(x.department, x.open, maxOpen, `${x.open}${x.overdue ? ` (${x.overdue})` : ""} · ${x.closed} · ${x.hours_to_close_median ?? "n/a"} h`)).join("") : '<div class="muted small">No requests yet.</div>'}</div>

    <div class="card"><h3>During the board</h3>
    <div class="tiles">${tile("Board sessions", du.sessions, "", `${du.closed} closed`)}${tile("Cases discussed", du.cases_discussed)}${tile("Quorate sessions", du.quorate_pct, "%", `${du.quorate_n} of ${du.closed} · surgical, radiation and medical oncologist present (PM-JAY) · target 95% (NHS 2020)`)}${tile("Minutes per case (median)", du.minutes_per_case_median, "", du.minutes_per_case_max != null ? `max ${du.minutes_per_case_max}` : "")}${tile("AI briefs for absent specialties", du.agent_briefs)}${tile("Questions to AI support", du.agent_questions)}</div>
    <h4 style="margin:12px 0 4px">Attendance per specialty <span class="muted small">closed sessions · target line 90% (Victorian 3.3)</span></h4>
    ${att.length && du.closed ? att.map((x) => barRow(x.department, x.rate ?? 0, 100, x.rate == null ? "not marked" : `${x.rate}% · ${x.present} of ${x.sessions}`, 90, x.rate == null)).join("") : '<div class="muted small">No closed session yet.</div>'}</div>

    <div class="card"><h3>After the board</h3>
    <div class="tiles">${tile("Decisions recorded", af.decisions, "", outcomes.map(([k, v]) => `${k} ${v}`).join(" · "))}${tile("Records final (every flag resolved)", af.final_pct, "%", `${af.final} of ${af.decisions}`)}${tile("Flags open / resolved", `${af.flags_open} / ${af.flags_resolved}`)}${tile("PM-JAY composition complete", af.composition_complete_pct, "%", `${af.composition_checked} records checked`)}${tile("Recorded on the board day", af.decision_recorded_same_day_pct, "%", "target 80% (Victorian 8.4, within 24 h)")}${tile("Patient informed within 7 days", af.patient_informed_7d_pct, "%", `${af.patient_informed_7d_n} of ${af.patient_informed_7d_d} · target 80% (Victorian 8.4 / 8.5)`)}${tile("Follow-up actions open", af.board_actions_open, "", `${af.board_actions_overdue} overdue · ${af.board_actions_closed} closed · median ${af.days_to_close_action_median ?? "n/a"} days`)}${tile("Decisions with a changed value", af.decision_watch_open, "", "a later report changed a value the decision cited")}</div>
    ${flags.length ? `<h4 style="margin:12px 0 4px">Adjudication flags by kind</h4><table class="t"><thead><tr><th>Kind</th><th>Open</th><th>Resolved</th><th>Information only</th></tr></thead><tbody>${flags.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v.open}</td><td>${v.resolved}</td><td>${v.info}</td></tr>`).join("")}</tbody></table>` : ""}</div>

    <div class="card"><h3>Against the published standards</h3><div class="muted small" style="margin-bottom:4px">Each line names its source; a target is a reference, not a judgement of the hospital.</div>
    ${d.references.map((r) => `<div class="refrow"><div class="m"><b>${esc(r.label)}</b></div><div class="num"><b>${r.value == null ? "n/a" : r.value + r.unit}</b> <span class="muted">target ${r.target}${esc(r.unit)}</span></div>
      <div>${r.met == null ? '<span class="chip c-mute">… no data</span>' : r.met ? '<span class="chip c-ok">✓ met</span>' : '<span class="chip c-warn">! below target</span>'}</div><div class="src">${esc(r.source)}</div></div>`).join("")}
    <div class="muted small" style="margin-top:8px">${esc(d.note)} Generated ${esc((d.generated || "").replace("T", " ").slice(0, 16))}.</div></div>`;
  $("#dash-apply").onclick = () => showDashboard($("#dash-from").value, $("#dash-to").value);
  $("#dash-clear").onclick = () => showDashboard();
}

// ------------------------------------------------------------------ discordances between reports, decision watch (12 Oct)
function discordItemHTML(it) {
  const sev = it.noted ? "c-mute" : it.severity === "review" ? "c-rev" : "c-info";
  return `<div class="flag ${it.severity === "review" ? "review" : "info"}${it.noted ? " resolved" : ""}"><div class="k">${esc(it.kind_label)} <span class="chip ${sev}">${it.noted ? "noted" : it.severity === "review" ? "review" : "information"}</span></div>
    <div>${esc(it.text)}</div><div style="margin-top:4px">${it.citations.map(citeHTML).join(" ")}</div>
    ${it.noted ? `<div class="small muted">Noted by ${esc(it.noted.by)} on ${esc((it.noted.at || "").slice(0, 10))}${it.noted.note ? `: ${esc(it.noted.note)}` : ""}${it.noted.confirmation && can("list_case") ? ` <button class="ghost sm" data-undonote="${esc(it.noted.confirmation)}">Undo</button>` : ""}</div>`
      : (can("list_case") ? `<div style="margin-top:6px"><button class="ghost sm" data-notedisc="${esc(it.key)}">Mark as noted</button></div>` : "")}</div>`;
}
function discordHTML() {
  const d = S.data.discordances;
  if (!d || !d.items.length) return "";
  const open = d.items.filter((x) => !x.noted), noted = d.items.filter((x) => x.noted);
  return `<div class="card"><h3>Reports that disagree <span class="muted small">${d.open_review} for review · ${d.info} informational${noted.length ? ` · ${noted.length} noted` : ""}</span></h3>
    <div class="muted small" style="margin-bottom:6px">The same primary field verified in two reports with different values, both quoted. The system never chooses which is right: the board does. A value that changed between reports of different dates is information (the newest counts); the same field differing between two final reports, an amendment, or a draft that disagrees with the final report is for review.</div>
    ${open.map(discordItemHTML).join("")}${noted.length ? `<details class="small"><summary>${noted.length} noted</summary>${noted.map(discordItemHTML).join("")}</details>` : ""}</div>`;
}
function bindDiscord(root) {
  $$("[data-notedisc]", root).forEach((b) => (b.onclick = async () => {
    const note = prompt("Mark this discordance as noted (optional note, for example 'discussed at the board'):", "");
    if (note === null) return;
    try { await api(`/cases/${S.caseId}/confirmations`, { json: { type: "note_discordance", key: b.dataset.notedisc, reason: note } }); toast("Noted (audited; can be undone)"); await openCase(S.caseId, true); }
    catch (e) { toast(e.message, 7000); }
  }));
  $$("[data-undonote]", root).forEach((b) => (b.onclick = async () => {
    try { await api(`/cases/${S.caseId}/confirmations/${b.dataset.undonote}/undo`, { json: {} }); toast("Undone"); await openCase(S.caseId, true); } catch (e) { toast(e.message, 7000); }
  }));
}
function trendsHTML() {
  const t = S.data.trends || [];
  if (!t.length) return "";
  return `<div class="card"><h3>Values over time <span class="muted small">${t.length} field(s)</span></h3>
    <div class="muted small" style="margin-bottom:6px">Every verified value of a numeric field, oldest first, with its report. A table of what the records say; the board reads the trend.</div>
    ${t.map((f) => `<div style="margin:8px 0 10px"><b>${esc(f.label)}</b><table class="t" style="margin-top:4px"><tbody>${f.rows.map((r) => `<tr><td class="small" style="width:92px">${esc(r.date ? fmtDate(r.date) : "date not stated")}</td>
      <td style="width:40%"><div style="display:flex;align-items:center;gap:6px"><div style="height:8px;border-radius:4px;background:${r.final ? "var(--accent)" : "var(--line-2)"};width:${f.max && r.number != null ? Math.max(4, Math.round(100 * r.number / f.max)) : 0}%"></div><span class="small">${esc(r.value)}</span></div></td>
      <td class="small">${citeHTML(r)}${r.final ? "" : ' <span class="chip c-warn">non-final</span>'}</td></tr>`).join("")}</tbody></table></div>`).join("")}</div>`;
}
function outcomeHTML(b) {
  const oc = b.outcome_type || "decision", label = (S.data.outcomes || {})[oc] || oc;
  return `<div class="small" style="margin:6px 0"><span class="chip ${oc === "decision" ? "c-ok" : oc === "not_discussed" ? "c-bad" : "c-warn"}">${esc(label)}</span>${b.deferred_reason ? ` ${esc(b.deferred_reason)}` : ""}${b.referred_to ? ` to ${esc(b.referred_to)}` : ""}</div>`;
}
function communicationHTML(b) {
  if ((b.outcome_type || "decision") !== "decision") return "";
  const kv = [["Patient informed", b.patient_informed_date ? `${fmtDate(b.patient_informed_date)}${b.informed_by ? ` by ${esc(b.informed_by)}` : ""}` : '<span class="chip c-warn">not yet recorded</span>'],
    ["Key worker", b.key_worker ? esc(b.key_worker) : '<span class="muted">not recorded</span>'], ["Intention to treat (as recorded)", b.intent_as_recorded ? esc(b.intent_as_recorded) : '<span class="muted">not stated</span>'],
    ["Clinical trial considered", b.trial_considered ? esc(b.trial_considered) : '<span class="muted">not recorded</span>'], ["Consent recorded", b.consent_recorded ? esc(b.consent_recorded) : '<span class="muted">not recorded</span>']];
  const form = can("board_record") ? `<details class="small" style="margin-top:6px"><summary>Record communication with the patient</summary><div class="form">
      <div class="grid2"><div><label>Date the patient was informed</label><input type="date" class="cm-date" value="${esc(b.patient_informed_date || "")}"></div><div><label>Informed by</label><input class="cm-by" value="${esc(b.informed_by || "")}" placeholder="lead clinician"></div></div>
      <div class="grid2"><div><label>Key worker</label><input class="cm-kw" value="${esc(b.key_worker || "")}"></div><div><label>Intention to treat (as recorded)</label><select class="cm-intent"><option value="" ${!b.intent_as_recorded ? "selected" : ""}>Not stated</option><option value="curative" ${b.intent_as_recorded === "curative" ? "selected" : ""}>Curative / radical</option><option value="palliative" ${b.intent_as_recorded === "palliative" ? "selected" : ""}>Palliative</option></select></div></div>
      <div class="grid2"><div><label>Clinical trial considered</label><select class="cm-trial"><option value="" ${!b.trial_considered ? "selected" : ""}>Not recorded</option><option value="yes" ${b.trial_considered === "yes" ? "selected" : ""}>Yes</option><option value="no" ${b.trial_considered === "no" ? "selected" : ""}>No</option></select></div><div><label>Consent recorded</label><select class="cm-consent"><option value="" ${!b.consent_recorded ? "selected" : ""}>Not recorded</option><option value="yes" ${b.consent_recorded === "yes" ? "selected" : ""}>Yes</option><option value="no" ${b.consent_recorded === "no" ? "selected" : ""}>No</option></select></div></div>
      <div style="margin-top:8px"><button class="ghost sm" data-cmsave="${esc(b.id)}">Save (audited, no new version)</button></div></div></details>` : "";
  return `<div class="stagebox" style="margin-top:8px"><b>Patient and communication</b><div class="kv small" style="margin-top:4px">${kv.map(([k, v]) => `<div>${k}</div><div>${v}</div>`).join("")}</div>${form}</div>`;
}
function decisionWatchHTML(b) {
  const d = S.data.discordances;
  const mine = (d?.items || []).filter((x) => x.kind === "decision_watch" && x.record === b.id);
  return mine.length ? `<div style="margin-top:8px">${mine.map(discordItemHTML).join("")}</div>` : "";
}

// ------------------------------------------------------------------ MCP connectors: records held by hospital systems (12 Oct)
async function renderHospitalSystems() {
  const box = $("#hs-card"); if (!box) return;
  if (!S.connectors) { try { S.connectors = await api("/connectors"); } catch (e) { S.connectors = { connectors: [] }; } }
  const cs = (S.connectors.connectors || []).filter((c) => c.enabled);
  if (!cs.length || !S.connectors.can_fetch) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="card"><h3>Hospital systems <span class="muted small">MCP connectors</span></h3>
    <div class="muted small" style="margin-bottom:8px">Records the hospital's systems hold for this patient that are not in the Case File. Fetched files go through the normal intake pipeline (reading, identity matching, verification); nothing is written back to the hospital system.</div>
    ${cs.map((c) => `<div class="hsrow" data-conn="${esc(c.id)}"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap"><span><b>${esc(c.label)}</b> <span class="muted small">uploads as ${esc(deptName(c.department))}</span></span>
      <button class="ghost sm" data-hs-check="${esc(c.id)}">Check for new records</button></div><div class="hs-result small" style="margin-top:6px"></div></div>`).join("")}</div>`;
  $$("[data-hs-check]", box).forEach((b) => (b.onclick = async () => {
    const row = b.closest(".hsrow"), out = $(".hs-result", row); b.disabled = true; out.innerHTML = `<span class="spin"></span> Asking the hospital system...`;
    try {
      const r = await api(`/cases/${S.caseId}/connectors/${b.dataset.hsCheck}/records`);
      if (!r.patient) { out.innerHTML = `<span class="muted">${esc(r.note || "No matching patient in the hospital system.")}</span>`; b.disabled = false; return; }
      const fresh = r.records.filter((x) => !x.in_case_file);
      out.innerHTML = `<div class="muted">Patient <b>${esc(r.patient.name)}</b> (${esc(r.patient.patient_id)}, matched on ${esc(r.matched_on)}): ${r.records.length} record(s), ${fresh.length} not in the Case File.</div>
        ${r.records.length ? `<table class="t" style="margin-top:6px"><thead><tr><th></th><th>Record</th><th>Type</th><th>Date</th><th>Department</th><th>In Case File</th></tr></thead><tbody>
        ${r.records.map((x) => `<tr><td>${x.in_case_file ? "" : `<input type="checkbox" data-rec="${esc(x.record_id)}" checked aria-label="fetch ${esc(x.filename)}">`}</td><td>${esc(x.filename)}</td><td>${esc(x.record_type || "")}</td><td>${esc(x.record_date ? fmtDate(x.record_date) : "")}</td><td>${esc(x.department || "")}</td><td>${x.in_case_file ? '<span class="chip c-ok">yes</span>' : '<span class="chip c-warn">no</span>'}</td></tr>`).join("")}</tbody></table>` : ""}
        ${fresh.length ? `<div style="margin-top:8px"><button class="primary sm" data-hs-fetch="${esc(b.dataset.hsCheck)}">Fetch selected into the intake pipeline</button></div>` : ""}`;
      const fb = $("[data-hs-fetch]", row);
      if (fb) fb.onclick = async () => {
        const ids = $$("input[data-rec]:checked", row).map((x) => x.dataset.rec);
        if (!ids.length) { toast("Select at least one record"); return; }
        fb.disabled = true; fb.innerHTML = `<span class="spin"></span> Fetching...`;
        try {
          const f = await api(`/cases/${S.caseId}/connectors/${fb.dataset.hsFetch}/fetch`, { json: { record_ids: ids } });
          toast(`${f.fetched.length} record(s) fetched as ${f.department}${f.errors.length ? `, ${f.errors.length} failed` : ""}; now being read and matched to the patient`);
          if (f.job) watchJob(f.job);
        } catch (e) { toast(e.message, 7000); fb.disabled = false; fb.textContent = "Fetch selected into the intake pipeline"; }
      };
    } catch (e) { out.innerHTML = `<span class="chip c-bad">not available</span> ${esc(e.message)}`; }
    b.disabled = false;
  }));
}

// ------------------------------------------------------------------ admin: connectors and the read-only MCP server (12 Oct)
async function showConnectors() {
  const [r, m] = await Promise.all([api("/connectors"), api("/mcp-server")]);
  const row = (c) => `<tr class="crow" data-id="${esc(c.id || "")}"><td><input class="c-id" value="${esc(c.id || "")}" placeholder="his_main" ${c.id ? "readonly" : ""}></td><td><input class="c-label" value="${esc(c.label || "")}" placeholder="Hospital information system"></td>
    <td><input class="c-url" value="${esc(c.url || "")}" placeholder="http://127.0.0.1:7111/mcp"></td><td><input class="c-token" type="password" value="" placeholder="${c.has_token ? "(kept)" : "bearer token"}"></td>
    <td><select class="c-dept">${(S.org?.departments || []).map((d) => `<option value="${esc(d.id)}" ${d.id === c.department ? "selected" : ""}>${esc(d.name)}</option>`).join("")}</select></td>
    <td><input type="checkbox" class="c-on" ${c.enabled !== false ? "checked" : ""}></td><td>${c.id ? `<button class="ghost sm" data-probe="${esc(c.id)}">Test</button>` : ""} <button class="ghost sm" data-rmconn>×</button><div class="c-probe small"></div></td></tr>`;
  $("#modal-body").innerHTML = `<h2 style="color:#1f2933;margin-top:0">Connectors and the MCP server</h2>
    <h3 style="margin:10px 0 4px">Hospital systems (MCP connectors)</h3>
    <div class="muted small" style="margin-bottom:6px">An outside MCP server that holds records (HIS, LIS, RIS, archive). It must offer the records protocol (${r.protocol.tools.join(", ")}) with every tool annotated read-only; "Test" checks that. Fetched files are uploaded as the department chosen here and go through patient matching. Tokens are stored on the server and never shown again.</div>
    <table class="t"><thead><tr><th>Id</th><th>Label</th><th>MCP URL</th><th>Token</th><th>Uploads as</th><th>On</th><th></th></tr></thead><tbody id="c-rows">${(r.connectors || []).map(row).join("")}</tbody></table>
    <button class="ghost sm" id="c-add" style="margin-top:6px">+ Connector</button>
    <h3 style="margin:16px 0 4px">This Case File store as an MCP server (read-only)</h3>
    <div class="kv small">
      <div>Status</div><div>${m.running ? '<span class="chip c-ok">running</span>' : '<span class="chip c-mute">not running</span>'} start: <code>${esc(m.start)}</code></div>
      <div>URL</div><div><code>${esc(m.url)}</code> · header <code>${esc(m.header)}</code></div>
      <div>Token</div><div>${m.token ? `<code id="mcp-tok" class="hidden">${esc(m.token)}</code><button class="ghost sm" id="mcp-show">Show</button> <button class="ghost sm" id="mcp-regen">Regenerate</button>` : '<span class="muted">admins only</span>'}</div>
      <div>Tools</div><div>${(m.tools || []).map((t) => `<span class="chip c-mute">${esc(t)}</span>`).join(" ")}</div>
      <div>stdio</div><div><code>${esc((m.stdio_command || []).join(" "))}</code></div>
      <div>Protocol</div><div>${esc(m.protocol)} · real Case Files hidden: ${m.include_protected ? "no (TB_MCP_INCLUDE_PROTECTED set)" : "yes"}</div>
    </div>
    <div class="muted small" style="margin-top:8px">${esc(m.scope)}</div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px"><button class="ghost" data-closemodal>Close</button>${r.can_manage ? `<button class="primary" id="c-save">Save connectors</button>` : ""}</div>`;
  $("#modal").classList.remove("hidden");
  const bind = () => {
    $$("[data-rmconn]", $("#c-rows")).forEach((x) => (x.onclick = () => x.closest("tr").remove()));
    $$("[data-probe]", $("#c-rows")).forEach((x) => (x.onclick = async () => { const out = $(".c-probe", x.closest("td")); out.innerHTML = `<span class="spin"></span>`;
      try { const p = await api(`/connectors/${x.dataset.probe}/probe`, { method: "POST" }); out.innerHTML = p.ok ? `<span class="chip ${p.usable ? "c-ok" : "c-bad"}">${p.usable ? "usable" : "not usable"}</span> ${esc(p.reason || "")} ${p.tools.map((t) => `<span class="chip ${t.read_only ? "c-mute" : "c-bad"}">${esc(t.name)}</span>`).join(" ")}` : `<span class="chip c-bad">unreachable</span> ${esc(p.error || "")}`; }
      catch (e) { out.textContent = e.message; } }));
  };
  bind();
  $("#c-add").onclick = () => { $("#c-rows").insertAdjacentHTML("beforeend", row({})); bind(); };
  if ($("#mcp-show")) $("#mcp-show").onclick = () => $("#mcp-tok").classList.toggle("hidden");
  if ($("#mcp-regen")) $("#mcp-regen").onclick = async () => { if (!confirm("Regenerate the MCP server token? Connected clients must be given the new one and the server restarted.")) return; const t = await api("/mcp-server/regenerate-token", { json: {} }); toast(t.note, 8000); showConnectors(); };
  if ($("#c-save")) $("#c-save").onclick = async () => {
    const connectors = $$("#c-rows tr.crow").map((tr) => ({ id: $(".c-id", tr).value.trim(), label: $(".c-label", tr).value.trim(), url: $(".c-url", tr).value.trim(), token: $(".c-token", tr).value, keep_token: !$(".c-token", tr).value, department: $(".c-dept", tr).value, enabled: $(".c-on", tr).checked }));
    try { await api("/connectors", { method: "PUT", json: { connectors } }); toast("Connectors saved"); S.connectors = null; showConnectors(); if (S.caseId) renderHospitalSystems(); }
    catch (e) { toast(e.message, 7000); }
  };
}

function orphanHTML(g) {
  // waivers recorded for a record this protocol version no longer lists (renamed or removed): shown, never silently lost (review M4)
  const o = g?.orphaned_waivers || [];
  return o.length ? `<div class="banner warn"><b>${o.length} waiver${o.length > 1 ? "s" : ""} no longer match${o.length > 1 ? "" : "es"} a record</b> of protocol ${esc(g.protocol)} v${esc(g.protocol_version || "")} (the record was renamed or removed). Review whether the decision applies to the current records and waive again if so.
    ${o.map((w) => `<div class="row"><span><b>${esc(w.requirement)}</b>: waived by ${esc(w.by || "clinician")}${w.reason ? ` (${esc(w.reason)})` : ""}</span></div>`).join("")}</div>` : "";
}
async function dismissDoc(docId) {
  // V1 item 4.3: a document that failed to read blocks the gate until it is re-processed or dismissed with a reason (audited, undoable)
  const d = S.data.documents.find((x) => x.doc_id === docId);
  const v = await confirmDialog({ title: "Dismiss a document that failed to read", intro: `"${d?.rel_path || d?.filename || docId}" could not be read (${d?.error || "unknown error"}). Dismissing it records that the Pre-Authorization may pass without it. Give the reason, for example: a duplicate of a report already filed, or an unreadable copy with the original requested from the department.`,
    fields: [{ id: "reason", label: "Reason", type: "textarea", required: true }], submit: "Dismiss" });
  if (!v) return;
  await recordConfirmation("dismiss_failed", docId, {}, v.reason);
}


// ------------------------------------------------------------------ clinician confirmations (one reusable dialog) · V1 item 2.2
const CONF_LABEL = { attest_final: "Attested final, signed", waive: "Requirement waived", confirm_dates: "Dates confirmed", confirm_doc_type: "Document type confirmed",
  confirm_match: "Patient match confirmed", dismiss_failed: "Failed document dismissed", confirm_value: "Value confirmed", resolve_flag: "Flag resolved" };
const confLabel = (c) => c.type === "confirm_match" ? (c.fields?.case_id ? (c.by === "system:matching" ? "Filed by the matcher (exact identifier)" : "Patient match confirmed") : "Not this patient") : CONF_LABEL[c.type] || c.type;
function confirmDialog({ title, intro, html = "", fields = [], submit = "Record", note = "Recorded with your name and the time in the audit log. It can be undone; the record of both stays." }) {
  // Returns a promise of {field: value} or null. Every field: {id, label, type: text|textarea|select|date, options: [[value, label]], required, value, placeholder}
  return new Promise((resolve) => {
    const f = (x) => x.type === "textarea" ? `<textarea id="cd-${x.id}" placeholder="${esc(x.placeholder || "")}">${esc(x.value || "")}</textarea>`
      : x.type === "select" ? `<select id="cd-${x.id}">${(x.options || []).map(([v, l]) => `<option value="${esc(v)}" ${v === x.value ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`
      : `<input id="cd-${x.id}" type="${x.type === "date" ? "date" : "text"}" value="${esc(x.value || "")}" placeholder="${esc(x.placeholder || "")}">`;
    $("#modal-body").innerHTML = `<h3 style="color:#1f2933;margin-top:0">${esc(title)}</h3>${intro ? `<div class="small muted">${esc(intro)}</div>` : ""}${html}
      <div class="form">${fields.map((x) => `<label>${esc(x.label)}${x.required ? "" : ' <span class="muted" style="font-weight:400">(optional)</span>'}</label>${f(x)}`).join("")}</div>
      <div class="small muted" style="margin-top:10px">${esc(note)}</div>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px"><button class="ghost" id="cd-cancel">Cancel</button><button class="primary" id="cd-ok">${esc(submit)}</button></div>`;
    $("#modal").classList.remove("hidden");
    const done = (v) => { $("#modal").classList.add("hidden"); resolve(v); };
    $("#cd-cancel").onclick = () => done(null);
    if ($("#cd-protocol") && $("#cd-setting")) $("#cd-protocol").onchange = () => { const p = (S.protocols || []).find((x) => x.id === $("#cd-protocol").value); $("#cd-setting").innerHTML = `<option value="">Not chosen yet</option>` + (p?.settings || []).map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join(""); };
    $("#cd-ok").onclick = () => { const out = {}; for (const x of fields) { const v = $("#cd-" + x.id).value.trim(); if (x.required && !v) { toast(`${x.label} is required`); return; } out[x.id] = v; } done(out); };
    const first = fields[0] && $("#cd-" + fields[0].id); if (first) first.focus();
  });
}
async function recordConfirmation(type, key, fields, reason) {
  try { const r = await api(`/cases/${S.caseId}/confirmations`, { json: { type, key, fields: fields || {}, reason: reason || "" } }); await openCase(S.caseId, true); toast(`${CONF_LABEL[type] || "Confirmation"} recorded in the audit log${r.job ? "; the fields are being extracted again under the confirmed type" : ""}`); if (r.job) watchJob(r.job); return r; }
  catch (e) { toast(e.message, 7000); return null; }
}
function confirmationsHTML() {
  const list = (S.data.state.confirmations || []).filter((c) => !c.undone);
  if (!list.length) return "";
  const what = (c) => c.type === "confirm_value" ? `${esc(c.key.split(":")[1] || "")}: "${esc(c.fields?.value || "")}"` : c.type === "confirm_doc_type" ? esc(DT[c.fields?.doc_type] || c.fields?.doc_type || "")
    : c.type === "confirm_dates" ? [c.fields?.report_date && "report " + fmtDate(c.fields.report_date), c.fields?.event_date && "event " + fmtDate(c.fields.event_date)].filter(Boolean).join(", ")
    : c.type === "waive" ? esc(S.data.state.gate?.requirements?.find((r) => r.id === c.key)?.label || c.key) : esc(S.data.documents.find((d) => d.doc_id === c.key)?.classification?.title || c.key);
  return `<div class="card"><h3>Clinician confirmations <span class="muted small">${list.length}</span></h3>
    <div class="muted small" style="margin-bottom:6px">Human decisions recorded against the Case File. They are applied after the model, so they win and survive a re-process.</div>
    ${list.map((c) => `<div class="conf"><span class="chip ${c.type === "confirm_match" && !c.fields?.case_id ? "c-mute" : "c-ok"}">${esc(confLabel(c))}</span> ${what(c)}${c.reason ? ` <span class="muted">(${esc(c.reason)})</span>` : ""}
      <span class="small muted">by ${esc(c.by)} ${esc((c.at || "").slice(0, 16).replace("T", " "))}</span> ${can("undo_confirmation", c.id) ? (() => { const intake = c.type === "confirm_match" && c.fields?.case_id && !(S.data.documents.find((d) => d.doc_id === c.key) || {}).outside && !(S.data.documents.find((d) => d.doc_id === c.key) || {}).his;
        return `<button class="ghost sm" data-undo="${esc(c.id)}" title="${intake ? "The document goes back to the Needs matching queue" : c.type === "confirm_match" ? "The confirmation is undone; the record stays and asks for the patient again" : "Undo this confirmation"}">${intake ? "Undo: back to matching" : "Undo"}</button>`; })() : ""}</div>`).join("")}</div>`;
}
function bindConfirmations(root) {
  $$("[data-undo]", root).forEach((b) => (b.onclick = async () => { if (!confirm("Undo this confirmation? Both the confirmation and the undo stay in the audit log.")) return;
    try { const r = await api(`/cases/${S.caseId}/confirmations/${b.dataset.undo}/undo`, { method: "POST" }); await openCase(S.caseId, true); toast(r.unfiled ? "Match undone: the document is back in the Needs matching queue" : "Confirmation undone" + (r.job ? "; the fields are being extracted again" : "")); if (r.job) watchJob(r.job); refreshQueueCount(); } catch (e) { toast(e.message, 7000); } }));
}

async function attestDoc(docId) {
  const d = S.data.documents.find((x) => x.doc_id === docId);
  const v = await confirmDialog({ title: "Attest: final, signed version", intro: `You confirm that "${d?.classification?.title || d?.filename || docId}" is the final, signed version of the report, as checked in the source.`,
    fields: [{ id: "reason", label: "Note", type: "textarea", placeholder: "e.g. verified with the department" }], submit: "Attest" });
  if (!v) return;
  await recordConfirmation("attest_final", docId, {}, v.reason);
}
function datesKV(c) {
  const dd = docDates(c);
  const one = (k, label) => { const iso = c[k + "_date_iso"], ass = dd[k === "report" ? "reportAssumed" : "eventAssumed"];
    const txt = dd.unconfirmed ? "not found in the text: confirm it from the source" : ass ? `${fmtDate(dd[k])} (stands in: only the ${k === "report" ? "event" : "report"} date was found)` : iso ? `${fmtDate(iso)}${c[k + "_date_label"] ? " · " + esc(c[k + "_date_label"]) : ""}${c[k + "_date_quote"] ? ` · "${esc(c[k + "_date_quote"])}"` : ""}` : "not stated";
    return `<div>${label}</div><div>${txt}</div>`; };
  const seen = (c.dates || []).filter((x) => x.kind !== "report" && x.kind !== "event").map((x) => `${fmtDate(x.iso)} (${esc(x.label || dateKindLabel[x.kind] || x.kind)}${x.kind === "ignore" ? ", ignored" : ""})`).join("; ");
  return one("report", "Report date") + one("event", "Event date") + (dd.flags.length ? `<div>Date check</div><div><span class="chip c-warn">${esc(dd.flags.join("; "))}</span></div>` : "")
    + (seen ? `<div>Other dates seen</div><div class="small muted">${seen}</div>` : "") + (c.dates_confirmed_by ? `<div>Dates confirmed by</div><div>${esc(c.dates_confirmed_by)}</div>` : "");
}
// Document dates (V1 item 3.1): event date shown; "(report date)" when it stands in; "date not found" asks for confirmation; sanity flags.
function dateCell(c) {
  const dd = docDates(c);
  if (dd.unconfirmed) return `<span class="chip c-warn" title="No labelled report or event date was found in the text. Confirm it from the source document.">date not found</span>`;
  const flags = dd.flags.map((f) => `<span class="chip c-warn" title="${esc(f)}">check date</span>`).join(" ");
  const by = c.dates_confirmed_by ? ` <span class="chip c-ok" title="Confirmed by ${esc(c.dates_confirmed_by)}">confirmed</span>` : "";
  return `${fmtDate(dd.event)}${dd.eventAssumed ? ` <span class="muted small" title="Only the report date was found; it stands in for the event date">(report date)</span>` : dd.report && dd.report !== dd.event ? ` <span class="muted small" title="Report date">(reported ${fmtDate(dd.report)})</span>` : ""}${by}${flags ? " " + flags : ""}`;
}
const dmy = (iso) => (iso && /^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : iso || "");  // Indian day-first form for the dialog
const dateKindLabel = { report: "report date", event: "event date", event_low: "received / registered (used only when no event date)", ignore: "ignored", unlabelled: "no label (not used)" };
async function confirmDates(docId) {
  const d = S.data.documents.find((x) => x.doc_id === docId); const c = d?.classification || {};
  const seen = (c.dates || []).map((x) => `${fmtDate(x.iso)} = ${x.label || dateKindLabel[x.kind] || x.kind}${x.kind === "ignore" ? " (ignored)" : ""}`).join("; ");
  const intro = `Read the dates in the source document "${c.title || d?.filename || docId}" and type them as printed. Report date = when the report was signed out; event date = when the study, sample, procedure or visit happened. Leave a field empty if the document does not state it.`
    + (seen ? ` Dates seen in the text: ${seen}.` : " No date was found in the text.") + (c.date_suggestion ? ` The filename suggests ${fmtDate(c.date_suggestion)} (a suggestion only).` : "") + ((c.date_flags || []).length ? ` Flags: ${c.date_flags.join("; ")}.` : "");
  const v = await confirmDialog({ title: "Confirm the document dates", intro,
    fields: [{ id: "report_date", label: "Report date (DD/MM/YYYY)", type: "text", value: c.report_date_assumed ? "" : dmy(c.report_date_iso), placeholder: dmy(c.date_suggestion) || "DD/MM/YYYY" },
             { id: "event_date", label: "Event date (DD/MM/YYYY)", type: "text", value: c.event_date_assumed ? "" : dmy(c.event_date_iso), placeholder: "DD/MM/YYYY" },
             { id: "reason", label: "Note", type: "text", placeholder: "e.g. date read from the signature line of the scan" }], submit: "Confirm dates" });
  if (!v) return;
  await recordConfirmation("confirm_dates", docId, { report_date: v.report_date, event_date: v.event_date }, v.reason);
}
async function confirmDocType(docId) {
  const d = S.data.documents.find((x) => x.doc_id === docId); const c = d?.classification || {}; const dis = c.doc_type_disagreement;
  const intro = `The reader model (Qwen3.5-4B, Chinese, non-medical) called "${c.title || d?.filename || docId}" ${DT[c.model_doc_type || c.doc_type] || c.doc_type}` + (dis ? `; the title keywords say ${DT[dis.keyword_type] || dis.keyword_type} (${dis.note || "keyword match"})` : "") + ". Choose the type as the document itself states it. The fields are extracted again from the stored text.";
  const opts = Object.entries(DT).map(([k, l]) => [k, l]);
  const v = await confirmDialog({ title: "Confirm the document type", intro, fields: [{ id: "doc_type", label: "Document type", type: "select", options: opts, value: dis?.keyword_type || c.doc_type }, { id: "reason", label: "Note", type: "text" }], submit: "Confirm type" });
  if (!v) return;
  await recordConfirmation("confirm_doc_type", docId, { doc_type: v.doc_type }, v.reason);
}
// V1 item 8.2: a critical value read from a scan counts only after a clinician has read it on the image
const IMG_EXT = [".png", ".jpg", ".jpeg", ".webp", ".bmp"], PAGED_EXT = [".pdf", ".tif", ".tiff"];  // PDF pages and TIFF frames are rendered by the server
function scanImageURL(caseId, d, page) {
  const base = `/api/tb/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(d.doc_id)}/file`;
  return PAGED_EXT.includes(d.ext) ? `${base}?render=1&page=${+page || 0}` : IMG_EXT.includes(d.ext) ? base : "";
}
async function confirmValue(n) {
  const d = S.data.documents.find((x) => x.doc_id === n.doc_id) || { doc_id: n.doc_id }; const c = d.classification || {};
  const label = S.facts?.[n.fact]?.label || n.fact, title = c.title || d.filename || n.doc_id, page = (+n.page || 0) + 1;
  const img = scanImageURL(S.caseId, d, n.page);
  const v = await confirmDialog({ title: `Confirm ${label} against the scan`,
    intro: `"${n.value}" was read from page ${page} of ${title}, a scanned page, by the vision reader (Qwen3.5-4B, Chinese, non-medical). Read ${label} on the image and record it exactly as written there; correct it if the transcription is wrong. It counts for the Pre-Authorization once you confirm it.`,
    html: img ? `<div class="confscan"><div class="scanwrap"><img src="${esc(img)}" alt="${esc(`Page ${page} of ${title}`)}">${(n.boxes || []).map((r) => boxDiv(r, "focus", `${label} as read`)).join("")}</div></div>${(n.boxes || []).length ? '<div class="small muted">Highlighted: where the value was read on the image (independent OCR engine word positions).</div>' : ""}` : `<div class="small muted">No image preview for this format: open the original from the Documents tab.</div>`,
    fields: [{ id: "match", label: "What the image shows", type: "select", required: true, value: "",
      options: [["", "Choose after reading the image"], ["same", `The same as transcribed: "${n.value}"`], ["differs", "Something else: I type it below"]] },
      { id: "value", label: `${label} as written on the image (only if it differs)`, type: "text", required: false, value: "" }], submit: "Confirm value" });
  if (!v) return;
  if (v.match === "differs" && !v.value) { toast("Type the value as written on the image"); return; }
  await recordConfirmation("confirm_value", `${n.doc_id}:${n.fact}`, { value: v.match === "same" ? n.value : v.value });
}
async function waiveReq(reqId) {
  const r = S.data.state.gate?.requirements?.find((x) => x.id === reqId);
  const v = await confirmDialog({ title: "Waive a requirement for this Case File", intro: `Clinical decision that "${r?.label || reqId}" is not required for this Case File. It leaves the Pre-Authorization check for this Case File only.`,
    fields: [{ id: "reason", label: "Reason", type: "textarea", required: true, placeholder: "e.g. CT done at the referring hospital, report in the file" }], submit: "Waive" });
  if (!v) return;
  await recordConfirmation("waive", reqId, {}, v.reason);
}
// a new document may answer a Tumour Board action (V1 item 7.4): suggested, a person closes it or says it does not
const suggestionHTML = (a, inbox) => !a.suggested_close || a.status === "completed" ? "" : `<div class="stagebox small" style="margin-top:6px"><span class="chip c-ok">May be complete</span> ${esc(a.suggested_close.reason)}.
  ${!inbox && can("update_action", a.id) ? ` <button class="ghost sm" data-sugclose="${esc(a.id)}" data-doc="${esc(a.suggested_close.doc_id)}">Close with this document</button> <button class="ghost sm" data-sugdismiss="${esc(a.id)}">Not this document</button>` : inbox ? ` <span class="muted">Open the Case File to close it.</span>` : ""}</div>`;
function actionHTML(a) {
  if (a.source === "pre_authorization") return requestHTML(a);  // V2 items 4.2 / 4.3: a request to a department, sent by the treating doctor
  const today = localToday();
  if (a.status === "pending" && a.due && a.due < today) a = { ...a, status: "overdue" };  // worked out on display, like the inbox
  return `<div class="action ${a.status}"><div class="h"><span>${a.source === "board" ? `<span class="chip c-info" title="From the Tumour Board record ${esc(a.board_record || "")}">Tumour Board action</span> ` : ""}${esc(a.label)}${a.level ? ` <span class="chip c-lvl" title="${esc((LEVEL[a.level] || [])[1] || "")}">${esc(a.level_label || (LEVEL[a.level] || [])[0] || "")}</span>` : ""}${a.accession ? ` <span class="chip c-mono" title="Accession / Lab No. in the hospital system">${esc(a.accession)}</span>` : ""}${a.pending_order ? ` <span class="chip c-info">Ordered in the HIS: ${esc(stageText(a.pending_order))}</span>` : ""}</span><span class="chip ${a.status === "completed" ? "c-ok" : a.status === "overdue" ? "c-bad" : "c-warn"}">${a.status === "completed" ? "Completed" : a.status === "overdue" ? "Overdue" : "Pending"}</span></div>
    <div class="w">${esc(a.what)}</div>${suggestionHTML(a)}
    <div class="f"><span>Responsible Department: <b>${esc(a.department)}</b> · due ${fmtDate(a.due)}</span>
    ${a.status !== "completed" ? `<span><button class="ghost sm" data-req="${a.id}">Request message</button> ${can("update_action", a.id) ? `<button class="ghost sm" data-act="${a.id}" data-st="completed">Mark completed</button>` : ""}</span>` : `<span>${a.completed ? "closed " + esc(a.completed.slice(0, 16).replace("T", " ")) : ""}</span>`}</div>
    ${a.history?.length > 1 ? `<details class="small muted"><summary>History</summary>${a.history.map((h) => `<div>${esc(h.ts.slice(0, 16).replace("T", " "))} ${esc(h.event)}</div>`).join("")}</details>` : ""}</div>`;
}
function requestText(a) {
  // the V1 message of a Tumour Board action (a Pre-Authorization request takes its draft from the server: V2 item 4.2)
  const c = S.data.case, p = c.patient || {};
  return `Tumour Board Case File ${c.case_id}: ${p.name || ""}${p.mrn ? ", UHID " + p.mrn : ""}${p.agesex ? ", " + p.agesex : ""}
To: ${a.department}
Required before the Tumour Board${c.board_date ? " on " + fmtDate(c.board_date) : ""}: ${a.label}${a.level_label ? " (" + a.level_label + ")" : ""}
Details: ${a.what}
Please upload the final, signed report to the Case File by ${fmtDate(a.due)}. The Case File is re-checked automatically when it arrives.
(Generated by Vaidyx Tumour Board assistant, action ${a.id})`;
}

// ---- requests to departments (V2 items 4.2 / 4.3): the gate suggests, the treating doctor sends, the department answers
const localToday = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const daysLate = (due) => { if (!due) return 0; const n = Math.round((new Date(localToday() + "T00:00:00") - new Date(String(due).slice(0, 10) + "T00:00:00")) / 86400000); return n > 0 ? n : 0; };
const isFreeReq = (a) => !!a.free || a.origin === "doctor" || !a.requirement;
function reqStatus(a) {
  // one chip per request: Suggested (not sent) / Sent DD/MM/YYYY / Acknowledged / Done, awaiting the record / Overdue n d / Closed
  if (a.status === "completed") return ["c-ok", "Closed"];
  if (a.status === "suggested") return ["c-mute", "Suggested (not sent)"];
  if (a.done) return ["c-info", "Done, awaiting the record"];
  const late = a.days_overdue || daysLate(a.due);
  if (late) return ["c-bad", `Overdue ${late} d`];
  if (a.acknowledged) return ["c-info", "Acknowledged"];
  return ["c-warn", a.sent ? `Sent ${esc(dmyd(a.sent.at))}` : "Pending"];  // "Pending": a V1 request, sent automatically before V2 recorded the sending
}
const encText = (e) => [e?.ip_no && "IP No. " + e.ip_no, e?.op_no && "OP No. " + e.op_no].filter(Boolean).join(" · ");
const encHTML = (e) => [["ip_no", "IP No."], ["op_no", "OP No."]].filter(([k]) => e?.[k]).map(([k, l]) => `<div class="small">${l} <span class="mono">${esc(e[k])}</span></div>`).join("");
function reqTrail(a) {
  // who did what: sent, acknowledged, done (with the note), closed; earlier sendings when the request moved to another department
  const s = a.sent, k = a.acknowledged, d = a.done, out = [];
  (a.earlier || []).forEach((e) => out.push(e.sent ? `<span class="muted">Sent earlier to ${esc(e.sent.to_name || e.department || "")} by ${esc(e.sent.by || "")} on ${esc(dmyt(e.sent.at))}; the request moved since, so it is sent afresh</span>`
    : `<span class="muted">Sent automatically to ${esc(e.department || "")} before V2 (no sending record); the request moved since, so it is sent afresh</span>`));
  if (s) out.push(`Sent to ${esc(s.to_name || a.department)} by <b>${esc(s.by)}</b> on ${esc(dmyt(s.at))}${s.count > 1 ? ` (${s.count} times)` : ""}`);
  if (k && !k.implied) out.push(`Acknowledged by <b>${esc(k.by)}</b> on ${esc(dmyt(k.at))}`);
  if (d) out.push(`Done, sent back by <b>${esc(d.by)}</b> on ${esc(dmyt(d.at))}${d.note ? `: "${esc(d.note)}"` : ""}`);
  if (a.status === "completed") out.push(a.closed_by ? `Closed by <b>${esc(a.closed_by)}</b>${a.completed ? " on " + esc(dmyt(a.completed)) : ""}` : `Closed by itself${a.completed ? " on " + esc(dmyt(a.completed)) : ""}: the record reached the Case File`);
  return out.length ? `<div class="reqtrail small">${out.map((x) => `<div>${x}</div>`).join("")}</div>` : "";
}
function requestHTML(a, answer) {
  const [cls, txt] = reqStatus(a), open = a.status !== "completed", sent = a.status !== "suggested", free = isFreeReq(a);
  const dept = a.department || deptName(a.department_id) || "the department";
  const btns = [];
  if (open && can("send_request")) btns.push(sent ? `<button class="ghost sm" data-notify="${esc(a.id)}" title="Send the request again as a reminder (audited)">Send again</button>`
    : `<button class="primary sm" data-notify="${esc(a.id)}" title="Read the draft, edit it and send it in-app or open it in your own mail program">Notify ${esc(dept)}</button>`);
  if (a.sent) btns.push(`<button class="ghost sm" data-reqmsg="${esc(a.id)}">Request message</button>`);
  if (open && can("remind")) btns.push(`<button class="ghost sm" data-remind="${esc(a.id)}" data-sug="${sent ? "" : "1"}" title="${sent ? `Remind ${esc(dept)} about this request (in-app, audited)` : "Not sent yet: the reminder goes to the owning department, asking it to send the request (in-app, audited)"}">Remind</button>`);  // V2 item 6.1
  if (open && free && sent && can("close_request")) btns.push(`<button class="ghost sm" data-closereq="${esc(a.id)}" title="Close a request with no protocol record behind it (audited)">Close</button>`);
  if (answer && open && sent && can("answer_request", a.id)) {  // the department asked answers on the Case File as in its inbox (V2 items 4.3 / 5.1)
    if (!a.acknowledged) btns.push(`<button class="ghost sm" data-ack="${esc(a.id)}">Acknowledge</button>`);
    if (!a.done) btns.push(`<button class="primary sm" data-done="${esc(a.id)}" title="The report is signed in your own system: send &quot;done&quot; back with an optional note">Done</button>`);
  }
  const po = a.pending_order;
  return `<div class="action reqcard ${open ? (cls === "c-bad" ? "overdue" : sent ? "" : "suggested") : "completed"}" data-aid="${esc(a.id)}"><div class="h"><span>${free ? `<span class="chip c-info" title="Written by the treating doctor; no protocol record behind it">Free request</span> ` : ""}${esc(a.label)}${a.level ? ` <span class="chip c-lvl" title="${esc((LEVEL[a.level] || [])[1] || "")}">${esc(a.level_label || (LEVEL[a.level] || [])[0] || "")}</span>` : ""}${a.accession ? ` <span class="chip c-mono" title="Accession / Lab No. in the hospital system">${esc(a.accession)}</span>` : ""}${po ? ` <span class="chip ${po.stage === "cancelled" ? "c-bad" : "c-info"}">Ordered in the HIS: ${esc(stageText(po))}</span>` : ""}</span><span class="chip ${cls} reqst">${esc(txt)}</span></div>
    ${a.what ? `<div class="w">${esc(a.what)}</div>` : ""}${reqTrail(a)}${remindersHTML(a.reminders)}
    <div class="f"><span>Responsible Department: <b>${esc(dept)}</b>${sent && a.due ? ` · due ${esc(dmyd(a.due))}` : open ? " · not sent yet" : ""}</span>${btns.length ? `<span>${btns.join("")}</span>` : ""}</div>
    ${a.history?.length > 1 ? `<details class="small muted"><summary>History</summary>${a.history.map((h) => `<div>${esc(dmyt(h.ts))} ${esc(h.event)}</div>`).join("")}</details>` : ""}</div>`;
}
const crlf = (s) => String(s || "").replace(/\r?\n/g, "\r\n");  // RFC 6068: line breaks in a mailto: body are CRLF
async function copyText(text, el) { try { await navigator.clipboard.writeText(text); toast("Copied"); } catch (e) { if (el) { el.focus(); el.select(); } toast("Select and copy the text"); } }
async function notifyDialog(aid) {
  // V2 item 4.2: the draft comes from the server (patient, UHID, IP / OP No., the record, what is missing, accession No., due date);
  // the doctor edits it and sends it in-app, or opens it in their own mail program. The server sends no e-mail.
  let d;
  try { d = await api(`/cases/${encodeURIComponent(S.caseId)}/requests/${encodeURIComponent(aid)}/draft`); } catch (e) { toast(e.message, 7000); return; }
  const to = d.to || {}, again = !!d.sent && d.status !== "suggested", addr = d.mailto ? d.mailto.split("?")[0] : "";
  $("#modal-body").innerHTML = `<h3 style="color:#1f2933;margin-top:0">${again ? "Send again to" : "Notify"} ${esc(to.name)}</h3>
    <div class="small muted">${again ? "A reminder: the department sees it again in its inbox and bell." : "Nothing has been sent yet. Check and edit the message, then send it."} The message names the patient, the record and what is missing, so the department can find the patient in its own system.</div>
    <div class="form reqform">
      <label>To</label><div class="reqto">${esc(to.name)}${to.email ? ` <span class="mono">${esc(to.email)}</span>` : to.role === "coordinator" ? "" : ` <span class="muted small">(no e-mail address recorded)</span>`}${d.uhid ? ` <span class="chip c-mono" title="UHID">${esc(d.uhid)}</span>` : ""}${d.accession ? ` <span class="chip c-mono" title="Accession / Lab No.">${esc(d.accession)}</span>` : ""}</div>
      <label for="reqsubj">Subject</label><input id="reqsubj" value="${esc(d.subject)}">
      <label for="reqtxt">Message</label><textarea id="reqtxt" class="reqtxt" spellcheck="false">${esc(d.body)}</textarea>
      <label for="reqdue">Needed by</label><input type="date" id="reqdue" value="${esc(d.due || "")}" style="max-width:220px"></div>
    <div class="small muted" style="margin-top:10px">"Send in-app" puts the request in the department's Tumour Board inbox and bell (audited). The server sends no e-mail: "Open in mail" opens your own mail program with this message, and is not recorded here; send it in-app too so the request is tracked.</div>
    <div class="actions-row"><button class="ghost" data-closemodal>Cancel</button><button class="ghost" id="reqcopy">Copy draft</button>
      ${addr ? `<a class="ghost" id="reqmail" href="#">Open in mail</a>` : `<span class="small muted" id="reqnomail">${esc(to.name)} has no e-mail address: the root admin adds one under Organisation.</span>`}
      <button class="primary" id="reqsend">${again ? "Send reminder in-app" : "Send in-app"}</button></div>`;
  $("#modal").classList.remove("hidden");
  const mail = () => { if ($("#reqmail")) $("#reqmail").href = `${addr}?subject=${encodeURIComponent($("#reqsubj").value)}&body=${encodeURIComponent(crlf($("#reqtxt").value))}`; };
  mail();
  $("#reqsubj").oninput = mail; $("#reqtxt").oninput = mail;
  $("#reqdue").onchange = () => { const v = $("#reqdue").value; if (v) { $("#reqtxt").value = $("#reqtxt").value.replace(/^Needed by: \d{2}\/\d{2}\/\d{4}/m, "Needed by: " + dmy(v)); mail(); } };
  $("#reqcopy").onclick = () => copyText(`Subject: ${$("#reqsubj").value}\n\n${$("#reqtxt").value}`, $("#reqtxt"));
  $("#reqsend").onclick = async () => {
    const btn = $("#reqsend"); btn.disabled = true;
    try {
      await api(`/cases/${encodeURIComponent(S.caseId)}/requests/${encodeURIComponent(aid)}/send`, { json: { message: $("#reqtxt").value, due: $("#reqdue").value, subject: $("#reqsubj").value } });
      $("#modal").classList.add("hidden"); toast(`${again ? "Reminder" : "Request"} sent to ${to.name} (audited)`); await openCase(S.caseId, true);
    } catch (e) { toast(e.message, 7000); btn.disabled = false; }
  };
}
function requestMessage(a) {
  // read-only: what was sent, to whom, by whom
  const s = a.sent || {};
  $("#modal-body").innerHTML = `<h3 style="color:#1f2933;margin-top:0">Request to ${esc(s.to_name || a.department)}</h3>
    <div class="small muted">Sent by ${esc(s.by)} on ${esc(dmyt(s.at))}${s.count > 1 ? `, ${s.count} times (the last sending is shown)` : ""}, in-app.${a.due ? ` Needed by ${esc(dmyd(a.due))}.` : ""}</div>
    <div class="form"><label for="reqview-subj">Subject</label><input id="reqview-subj" readonly value="${esc(s.subject || "")}"><label for="reqview">Message</label><textarea id="reqview" class="reqtxt" readonly>${esc(s.message || "")}</textarea></div>
    <div class="actions-row"><button class="ghost" id="reqview-copy">Copy</button><button class="primary" data-closemodal>Close</button></div>`;
  $("#modal").classList.remove("hidden");
  $("#reqview-copy").onclick = () => copyText(`Subject: ${s.subject || ""}\n\n${s.message || ""}`, $("#reqview"));
}
async function newRequestDialog() {
  // V2 item 4.2: a request with no gap behind it (a pre-anaesthetic check, a medication review), created and sent in one step
  const ds = S.org?.departments || [];
  const grp = (g, label) => { const l = ds.filter((d) => d.group === g); return l.length ? `<optgroup label="${label}">${l.map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("")}</optgroup>` : ""; };
  $("#modal-body").innerHTML = `<h3 style="color:#1f2933;margin-top:0">Notify a department</h3>
    <div class="small muted">For something no protocol record covers, for example a pre-anaesthetic check-up (Anaesthesiology) or a medication review (Clinical Pharmacology). The request is created and sent in one step: the department sees it in its inbox and bell (audited). It closes when the department sends "done" back, or when you close it.</div>
    <div class="form"><label for="fr-dept">Department</label><select id="fr-dept"><option value="">Choose the department</option>${grp("supporting", "Supporting departments")}${grp("treating", "Treating departments")}</select>
      <label for="fr-label">What you are asking for</label><input id="fr-label" placeholder="e.g. Pre-anaesthetic check-up" maxlength="160">
      <label for="fr-what">Details <span class="muted" style="font-weight:400">(optional)</span></label><textarea id="fr-what" placeholder="e.g. planned for surgery after the board; please record fitness for general anaesthesia"></textarea>
      <label for="fr-due">Needed by <span class="muted" style="font-weight:400">(optional; 3 days from today when empty)</span></label><input type="date" id="fr-due" style="max-width:220px"></div>
    <div class="actions-row"><button class="ghost" data-closemodal>Cancel</button><button class="primary" id="fr-send">Send in-app</button></div>`;
  $("#modal").classList.remove("hidden");
  $("#fr-send").onclick = async () => {
    const department = $("#fr-dept").value, label = $("#fr-label").value.trim();
    if (!department) { toast("Choose the department"); return; }
    if (!label) { toast("Say what you are asking for"); return; }
    const btn = $("#fr-send"); btn.disabled = true;
    try {
      await api(`/cases/${encodeURIComponent(S.caseId)}/requests`, { json: { department, label, what: $("#fr-what").value.trim(), due: $("#fr-due").value } });
      $("#modal").classList.add("hidden"); toast(`Request sent to ${deptName(department)} (audited)`); await openCase(S.caseId, true);
    } catch (e) { toast(e.message, 7000); btn.disabled = false; }
  };
}
async function closeRequest(aid) {
  const a = (S.data.state.actions || []).find((x) => x.id === aid);
  const v = await confirmDialog({ title: "Close this request", intro: `"${a?.label || aid}" to ${a?.department || "the department"} is closed for this Case File. The department is told.`,
    fields: [{ id: "note", label: "Note", type: "textarea", placeholder: "e.g. pre-anaesthetic check-up done in the OPD on 12/10/2026" }], submit: "Close request" });
  if (!v) return;
  try { await api(`/cases/${encodeURIComponent(S.caseId)}/requests/${encodeURIComponent(aid)}/close`, { json: { note: v.note } }); toast("Request closed (audited)"); await openCase(S.caseId, true); }
  catch (e) { toast(e.message, 7000); }
}
// ---- reminders and the ready mark before the board (V2 item 6.1): the MDT Coordinator on the owner's behalf, or the owner's doctors
const remindersHTML = (list) => (list || []).length ? `<div class="small muted reminders" title="${esc(list.map((x) => `${dmyt(x.at)} by ${x.by}${x.to ? " to " + x.to : ""}${x.note ? ": " + x.note : ""}`).join("; "))}">${plural(list.length, "reminder")}, last ${esc(dmyt(list[list.length - 1].at))} by ${esc(list[list.length - 1].by)}</div>` : "";
async function remindNote(title, intro) {
  const v = await confirmDialog({ title, intro, fields: [{ id: "note", label: "Note", type: "textarea", placeholder: "e.g. needed before Friday's board" }], submit: "Send reminder", note: "Sent in-app (the bell), recorded with your name and the time in the audit log." });
  return v ? v.note : null;
}
async function remindRequest(caseId, aid, suggested, label) {
  const note = await remindNote(suggested ? "Remind the owning department" : "Send a reminder", suggested ? `"${label || "This request"}" has not been sent yet: the owning department is reminded to send it.` : `The department holding "${label || "this request"}" sees it again in its inbox and bell; the due date stays.`);
  if (note === null) return false;
  try { await api(`/cases/${encodeURIComponent(caseId)}/requests/${encodeURIComponent(aid)}/remind`, { json: { note } }); toast("Reminder sent (audited)"); return true; }
  catch (e) { toast(e.message, 7000); return false; }
}
async function remindOwner(caseId, patient) {
  const note = await remindNote("Remind the owning department", `One reminder about ${patient || caseId} before the board: the requests not sent, the overdue ones, the summary and the ready mark.`);
  if (note === null) return false;
  try { await api(`/cases/${encodeURIComponent(caseId)}/remind-owner`, { json: { note } }); toast("Reminder sent to the owning department (audited)"); return true; }
  catch (e) { toast(e.message, 7000); return false; }
}
const readyChip = (r) => r ? `<span class="chip c-ok" title="${esc(r.note ? "Note: " + r.note : "Marked ready by the owning department")}">Ready for the board (by ${esc(r.by)}, ${esc(dmyd(r.at))})</span>` : "";
function readyLineHTML() {
  const c = S.data.case, r = c.board_ready, listed = !!c.protocol && (c.listing || { status: "listed" }).status === "listed";
  const btn = can("mark_ready") && (r || listed) ? (r ? `<button class="ghost sm" id="btn-unready" title="Take the ready mark back (audited)">Take back</button>`
    : `<button class="primary sm" id="btn-ready" title="Tell the MDT Coordinator this Case File is ready for the board (audited)">Mark ready for the board</button>`) : "";
  return r || btn ? `<div class="readyline small" id="c-readyline">${readyChip(r)}${btn}</div>` : "";
}
function bindReadyLine() {
  const go = async (ready) => {
    const v = ready ? await confirmDialog({ title: "Mark ready for the board", intro: "The MDT Coordinator is told and builds the agenda from the Case Files their owners marked ready.", fields: [{ id: "note", label: "Note", type: "textarea", placeholder: "e.g. HER2 FISH awaited, discuss anyway" }], submit: "Mark ready", note: "Recorded with your name and the time in the audit log. It can be taken back." })
      : await confirmDialog({ title: "Take back the ready mark", intro: "The Case File is no longer marked ready for the board.", fields: [{ id: "note", label: "Reason", type: "textarea" }], submit: "Take back", note: "Recorded with your name and the time in the audit log." });
    if (!v) return;
    try { await api(`/cases/${encodeURIComponent(S.caseId)}/ready`, { json: { ready, note: v.note } }); toast(ready ? "Marked ready for the board; the MDT Coordinator is told (audited)" : "Ready mark taken back (audited)"); await openCase(S.caseId, true); }
    catch (e) { toast(e.message, 7000); }
  };
  if ($("#btn-ready")) $("#btn-ready").onclick = () => go(true);
  if ($("#btn-unready")) $("#btn-unready").onclick = () => go(false);
}
async function answerRequest(caseId, aid, what) {
  // V2 item 4.3: the department acknowledges, then sends "done" back (with an optional note); the server checks who may
  let note = "";
  if (what === "done") { const v = prompt("Done: the report is signed in your own system. Note for the treating doctor (optional):"); if (v === null) return false; note = v.trim(); }
  try { await api(`/cases/${encodeURIComponent(caseId)}/requests/${encodeURIComponent(aid)}/${what}`, { json: what === "done" ? { note } : {} }); toast(what === "done" ? "\"Done\" sent back to the treating department (audited)" : "Acknowledged (audited)"); return true; }
  catch (e) { toast(e.message, 7000); return false; }
}
function bindActions(root) {
  $$("[data-req]", root).forEach((b) => (b.onclick = () => {
    const a = (S.data.state.actions || []).find((x) => x.id === b.dataset.req);
    $("#modal-body").innerHTML = `<h3 style="color:#1f2933;margin-top:0">Request to ${esc(a.department)}</h3><textarea id="reqtxt" class="reqtxt">${esc(requestText(a))}</textarea>
      <div style="text-align:right;margin-top:10px"><button class="ghost" data-closemodal>Close</button> <button class="primary" id="reqcopy">Copy</button></div>`;
    $("#modal").classList.remove("hidden");
    $("#reqcopy").onclick = () => copyText($("#reqtxt").value, $("#reqtxt"));
  }));
  $$("[data-notify]", root).forEach((b) => (b.onclick = () => notifyDialog(b.dataset.notify)));
  $$("[data-reqmsg]", root).forEach((b) => (b.onclick = () => { const a = (S.data.state.actions || []).find((x) => x.id === b.dataset.reqmsg); if (a) requestMessage(a); }));
  $$("[data-closereq]", root).forEach((b) => (b.onclick = () => closeRequest(b.dataset.closereq)));
  $$("[data-remind]", root).forEach((b) => (b.onclick = async () => { const a = (S.data.state.actions || []).find((x) => x.id === b.dataset.remind);
    if (await remindRequest(S.caseId, b.dataset.remind, !!b.dataset.sug, a?.label)) await openCase(S.caseId, true); }));
  $$("[data-newreq]", root).forEach((b) => (b.onclick = () => newRequestDialog()));
  $$("[data-act]", root).forEach((b) => (b.onclick = async () => {
    const note = prompt("Note for the record (optional):") ?? "";
    await api(`/cases/${S.caseId}/actions/${b.dataset.act}`, { json: { status: b.dataset.st, note } });
    await openCase(S.caseId, true);
  }));
  $$("[data-sugclose]", root).forEach((b) => (b.onclick = async () => {
    try { await api(`/cases/${S.caseId}/actions/${b.dataset.sugclose}/close`, { json: { doc_id: b.dataset.doc } }); toast("Action closed with the document (audited)"); await openCase(S.caseId, true); }
    catch (e) { toast(e.message, 7000); }
  }));
  $$("[data-sugdismiss]", root).forEach((b) => (b.onclick = async () => {
    try { await api(`/cases/${S.caseId}/actions/${b.dataset.sugdismiss}/dismiss-suggestion`, { json: {} }); toast("Suggestion dismissed: that document will not be suggested again for this action"); await openCase(S.caseId, true); }
    catch (e) { toast(e.message, 7000); }
  }));
}

// ------------------------------------------------------------------ upload + jobs
function bindUpload() {
  const drop = $("#drop");
  $("#pick-files").onclick = () => $("#f-files").click();
  $("#pick-folder").onclick = () => $("#f-folder").click();
  $("#f-files").onchange = (e) => uploadFiles([...e.target.files].map((f) => [f, f.name]));
  $("#f-folder").onchange = (e) => uploadFiles([...e.target.files].map((f) => [f, f.webkitRelativePath || f.name]));
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = async (e) => {
    e.preventDefault(); drop.classList.remove("over");
    const out = [];
    const walk = async (entry, path) => {
      if (entry.isFile) { await new Promise((res) => entry.file((f) => { out.push([f, path + f.name]); res(); })); }
      else if (entry.isDirectory) {
        const rd = entry.createReader(); let batch;
        do { batch = await new Promise((res) => rd.readEntries(res)); for (const en of batch) await walk(en, path + entry.name + "/"); } while (batch.length);
      }
    };
    for (const it of e.dataTransfer.items) { const en = it.webkitGetAsEntry?.(); if (en) await walk(en, ""); }
    uploadFiles(out);
  };
}
async function uploadFiles(list) {
  if (!list.length) return;
  const fd = new FormData();
  list.forEach(([f]) => fd.append("files", f));
  fd.append("paths", JSON.stringify(list.map(([, p]) => p)));
  if (S.data?.his) fd.append("outside", "1");  // V2 item 3.6: into an HIS Case File every upload is an outside report
  $("#job").innerHTML = `<div class="small" style="margin-top:8px"><span class="spin"></span> Uploading ${list.length} files...</div>`;
  const r = await fetch(`/api/tb/cases/${S.caseId}/documents`, { method: "POST", body: fd, credentials: "same-origin" });
  if (!r.ok) { toast("Upload failed: " + r.statusText); return; }
  const res = await r.json();
  if (res.warnings?.length) toast(res.warnings.map((w) => w.message).join("; ") + ". The other documents are read meanwhile.", 10000);  // big scans (V1 item 3.7)
  watchJob(res.job);
}
async function watchJob(id) {
  const box = () => $("#job");
  const t0 = Date.now();
  while (true) {
    let j; try { j = await api("/jobs/" + id); } catch (e) { break; }
    const st = Object.values(j.doc_states);
    const count = (k) => st.filter((s) => s === k).length;
    if (box()) box().innerHTML = `<div class="progress"><div style="width:${j.total ? (100 * j.done) / j.total : 100}%"></div></div>
      <div class="jobline"><span>${j.done}/${j.total} documents processed · ${((Date.now() - t0) / 1000).toFixed(1)} s</span>
      ${["reading", "classifying", "extracting"].map((k) => (count(k) ? `<span class="chip c-info">${count(k)} ${k}</span>` : "")).join("")}
      ${count("error") ? `<span class="chip c-bad">${count("error")} errors</span>` : ""}</div>`;
    if (j.state === "failed") { toast("Processing failed: " + (j.error || "unknown error") + ". Use Re-process to retry.", 9000); await openCase(S.caseId, true); break; }
    if (j.state === "interrupted") { toast((j.error || "The server restarted; the documents were queued again automatically") + ".", 8000); await openCase(S.caseId, true); break; }
    if (j.state === "finished") {
      const extra = [j.skipped_duplicates?.length ? `${j.skipped_duplicates.length} identical file(s) already in the Case File were skipped` : "", j.unsupported?.length ? `${j.unsupported.length} file(s) not read: ` + j.unsupported.map(u => `${u.file} (${u.reason})`).join(", ") : "", (j.warnings || []).map((w) => w.message).join("; ")].filter(Boolean).join("; ");
      const gate = j.gate ? ` Pre-Authorization re-checked: ${j.gate.satisfied}/${j.gate.total} satisfied.` : "";
      await openCase(S.caseId, true);
      if (j.his) toast(hisJobText(j) + gate, 10000);
      else toast(`Processed ${j.total} documents in ${j.seconds} s.${gate}${extra ? " " + extra + "." : ""}`, 7000);
      loadNotifications(); refreshInboxCount(); break;
    }
    await new Promise((r) => setTimeout(r, 700));
  }
}

// ------------------------------------------------------------------ HIS-connected Case File (V2 items 3.2 to 3.6): registration, window, re-fetch, links, open orders
function hisCardHTML() {
  const h = S.data.his; if (!h) return "";
  const linked = (h.similar || []).filter((s) => s.linked), last = (h.fetches || []).slice(-1)[0], orders = h.orders || [], unl = h.unlinked || [];
  return `<div class="card hiscard" id="his-card"><h3><span>Hospital system <span class="chip c-info">${esc(h.label || "HIS")}</span></span><span class="btns">${can("refetch") ? `<button class="ghost sm" data-refetch title="Fetch only the records new or changed in the hospital system since the last fetch; the Pre-Authorization then re-checks">Re-fetch</button>` : ""}${can("refetch") && !h.window?.all ? `<button class="ghost sm" id="btn-older" title="Widen the fetch window without starting over">Fetch older records</button>` : ""}</span></h3>
    <div class="kv small"><div>UHID</div><div><span class="mono">${esc(h.uhid)}</span> (${esc(regKind(h.registration_kind))})${h.matched_on?.kind && h.matched_on.kind !== "uhid" ? ` · found by ${esc(ID_KIND[h.matched_on.kind] || h.matched_on.kind)} <span class="mono">${esc(h.matched_on.value)}</span>` : ""}</div>
      <div>Fetch window</div><div>${esc(winLabel(h.window) || h.window_label || "")}${h.window_start && !h.window?.from ? ` (dated from ${dmy(h.window_start)})` : ""}${h.older_available ? ` · <b>${plural(h.older_available, "older record")}</b> in the hospital system` : ""}</div>
      <div>Fetched</div><div>${h.fetched_at ? esc(dmyt(h.fetched_at)) : "not yet"}${last ? ` · last fetch: ${plural(last.added || 0, "new or changed record")}, ${last.skipped || 0} already here${last.errors ? `, ${last.errors} failed` : ""}` : ""}</div></div>
    ${unl.length ? `<h4 class="subh">Registrations to link <span class="chip c-warn">${unl.length}</span></h4><div class="small muted">Possible duplicate or temporary registrations of the same person. Never merged automatically: a person checks and links one; its records then join the Case File labelled with that registration.</div>
      ${unl.map((s) => `<div class="hisrow"><span><b>${esc(s.name || "name not given")}</b> · <span class="mono">${esc(s.uhid)}</span> (${esc(regKind(s.registration_kind))})${ageSex(s) ? " · " + esc(ageSex(s)) : ""}</span>${can("link_registration") ? `<button class="ghost sm" data-link="${esc(s.uhid)}">Link</button>` : ""}</div>`).join("")}` : ""}
    ${linked.length ? `<div class="chips" style="margin-top:8px">${linked.map((s) => `<span class="chip c-ok" title="${esc(`${s.name || ""} ${s.uhid} (${regKind(s.registration_kind)}) linked ${dmyt(s.linked_at)}`)}"><span class="mono">${esc(s.uhid)}</span> linked by ${esc(s.linked_by || "?")}</span>${can("link_registration") ? `<button class="ghost sm" data-unlink="${esc(s.uhid)}" title="Undo the link: the registration's records leave the Case File and the identifiers learned from it are forgotten (audited)">Unlink</button>` : ""}`).join("")}</div>` : ""}
    ${orders.length ? `<h4 class="subh">Open orders in the HIS <span class="muted small">${orders.length}</span></h4><div class="small muted">Tests ordered with no report yet, as the hospital system lists them.</div>
      ${orders.map((o) => `<div class="hisrow"><span><b>${esc(o.test || DT[o.doc_type] || "Order")}</b>${o.accession ? ` <span class="chip c-mono">${esc(o.accession)}</span>` : ""}${o.encounter_number ? ` <span class="small muted mono">${esc(o.encounter_number)}</span>` : ""}</span><span class="small"><span class="chip ${o.stage === "cancelled" ? "c-bad" : "c-info"}">${esc(stageText(o))}</span>${o.performer_department ? " " + esc(o.performer_department) : ""}</span></div>`).join("")}` : ""}
  </div>`;
}
function hisFlagsHTML() {
  const f = S.data.his_flags || []; if (!f.length) return "";
  return `<div class="card"><h3>HIS values the report text does not carry <span class="chip c-rev">Points for review</span></h3>
    <div class="muted small" style="margin-bottom:6px">Structured values the hospital system holds for a report that its signed text does not carry, or carries differently. These are never shown as facts: open the report and check.</div>
    ${f.map((x) => `<div class="conf"><span><b>${esc(x.label || x.fact)}</b>: ${esc(x.text)}</span> <span class="cite" data-doc="${esc(x.doc_id)}" title="Open the report">${esc(x.doc_title || x.doc_id)}</span>${x.accession ? ` <span class="chip c-mono">${esc(x.accession)}</span>` : ""}</div>`).join("")}</div>`;
}
function hisJobText(j) {
  const h = j.his || {}, r = j.refetch_result, acts = S.data?.state?.actions || [];
  const name = (id) => acts.find((a) => a.id === id)?.label || id;
  const what = { first_fetch: "First fetch", refetch: "Re-fetch", older: "Fetch of older records", link: "Fetch of the linked registration" }[h.reason] || "Fetch";
  return `${what} finished from ${S.data?.his?.label || "the hospital system"}: ${plural(h.added || 0, "new or changed record")} read in ${j.seconds} s, ${h.skipped || 0} already in the Case File${h.outside_window ? `, ${h.outside_window} outside the window` : ""}${(h.errors || []).length ? `, ${h.errors.length} could not be fetched` : ""}.`
    + (r ? ` Requests closed: ${r.closed?.length ? r.closed.map(name).join("; ") : "none"}. Requests opened: ${r.opened?.length ? r.opened.map(name).join("; ") : "none"}.` : "");
}
function bindHIS(root) {
  $$("[data-refetch]", root).forEach((b) => (b.onclick = refetchHIS));
  const o = $("#btn-older", root); if (o) o.onclick = fetchOlder;
  $$("[data-link]", root).forEach((b) => (b.onclick = () => linkReg(b.dataset.link)));
  $$("[data-unlink]", root).forEach((b) => (b.onclick = () => unlinkReg(b.dataset.unlink)));
  $$("[data-confmatch]", root).forEach((b) => (b.onclick = () => confirmMatch(b.dataset.confmatch)));
}
async function refetchHIS() {
  $$("[data-refetch]").forEach((b) => (b.disabled = true));
  try {
    const j = await api(`/cases/${S.caseId}/his/refetch`, { method: "POST" });
    toast(`Re-fetch started: ${plural(j.his?.added ?? j.total ?? 0, "new or changed record")} in ${S.data.his?.label || "the hospital system"}; reading and re-checking...`, 5000);
    watchJob(j.job);
  } catch (e) { toast(e.message, 8000); $$("[data-refetch]").forEach((b) => (b.disabled = false)); }
}
async function fetchOlder() {
  const h = S.data.his || {}, cur = h.window || {};
  const opts = [...(cur.months && +cur.months < 24 ? [["24", "Last 24 months"]] : []), ["all", "All records"], ["from", "From a date (below)"]];
  const v = await confirmDialog({ title: "Fetch older records", intro: `This Case File holds ${winLabel(cur)}${h.window_start && !cur.from ? ` (dated from ${dmy(h.window_start)})` : ""}.${h.older_available ? ` The hospital system lists ${plural(h.older_available, "older record")}.` : ""} Widening the window fetches only the records dated before the current start; nothing already fetched is read again.`,
    fields: [{ id: "win", label: "New window", type: "select", options: opts, value: opts[0][0], required: true }, { id: "from", label: "From date (only for From a date)", type: "date" }],
    submit: "Fetch", note: "Recorded with your name and the time in the audit log." });
  if (!v) return;
  if (v.win === "from" && !v.from) { toast("Choose the date to fetch from"); return; }
  try {
    const j = await api(`/cases/${S.caseId}/his/fetch-older`, { json: v.win === "all" ? { all: true } : v.win === "from" ? { from: v.from } : { months: +v.win } });
    await openCase(S.caseId, true); toast(`Fetching older records: ${plural(j.his?.added ?? j.total ?? 0, "record")} to read`, 5000); watchJob(j.job);
  } catch (e) { toast(e.message, 8000); }
}
async function unlinkReg(uhid) {
  const v = await confirmDialog({ title: "Unlink a registration", intro: `The records fetched for ${uhid} leave this Case File, the identifiers learned from it are forgotten and the Pre-Authorization re-checks. The registration is listed again for linking. Recorded in the audit log.`,
    fields: [{ id: "reason", label: "Reason", type: "text", required: true }], submit: "Unlink" });
  if (!v) return;
  try { await api(`/cases/${S.caseId}/his/unlink`, { json: { uhid, reason: v.reason } }); toast(`Registration ${uhid} unlinked; Pre-Authorization re-checked`); await openCase(S.caseId, true); }
  catch (e) { toast(e.message, 7000); }
}
async function linkReg(uhid) {
  const s = (S.data.his?.unlinked || []).find((x) => x.uhid === uhid) || { uhid };
  const v = await confirmDialog({ title: "Link a registration to this Case File", intro: `Link ${s.uhid} (${regKind(s.registration_kind)}; ${s.name || "name not given"}${ageSex(s) ? ", " + ageSex(s) : ""}) as the same person as ${S.data.his?.uhid || "this Case File"}. Registrations are never merged automatically: check the name, age, sex and the registration desk record first. The records of ${s.uhid} are then fetched and labelled with that registration.`,
    fields: [{ id: "reason", label: "How you checked", type: "textarea", required: true, placeholder: "e.g. temporary registration at casualty; same name, date of birth and phone on the registration desk record" }],
    submit: "Link", note: "Recorded with your name and the time in the audit log." });
  if (!v) return;
  try { const j = await api(`/cases/${S.caseId}/his/link`, { json: { uhid: s.uhid, reason: v.reason } }); await openCase(S.caseId, true); toast(`${s.uhid} linked: ${plural(j.his?.added ?? j.total ?? 0, "record")} of that registration being read`, 6000); watchJob(j.job); }
  catch (e) { toast(e.message, 8000); }
}
async function confirmMatch(docId) {
  const d = S.data.documents.find((x) => x.doc_id === docId), p = S.data.case.patient || {};
  const v = await confirmDialog({ title: "Confirm the patient of an outside report", intro: `"${d?.classification?.title || d?.filename || docId}" is an outside report (another hospital or a private laboratory) matched to this Case File by name only: it prints no identifier of this hospital. Open it and check the name, age, sex and any identifier against ${p.name || "the patient"}${p.agesex ? " (" + p.agesex + ")" : ""} before confirming. Once confirmed it counts for the Pre-Authorization like every record.`,
    fields: [{ id: "reason", label: "How you checked", type: "textarea", required: true, placeholder: "e.g. name, age and the referring hospital's ID match the referral letter" }], submit: "Confirm patient" });
  if (!v) return;
  await recordConfirmation("confirm_match", docId, { case_id: S.caseId }, v.reason);
}

// ------------------------------------------------------------------ tab: documents
const DOC_HEAD = `<thead><tr><th>Document</th><th>Type</th><th>Date</th><th>Status</th><th>Read by</th><th>Fields found</th></tr></thead>`;
// V2 items 3.3 to 3.6: the HIS status and signature of a report, where it came from, its version history
const HSTAT = { final: ["c-ok", "Final"], preliminary: ["c-warn", "Preliminary"], partial: ["c-warn", "Preliminary"], registered: ["c-warn", "Registered, no result yet"],
  amended: ["c-info", "Amended"], corrected: ["c-info", "Corrected"], cancelled: ["c-bad", "Cancelled"] };
const sigTitle = (g) => [`Signed by ${g.signer?.name || g.signer || "signer not named"}`, g.signed_at && `at ${dmyt(g.signed_at)}`, g.ca && `CA: ${g.ca}`, g.serial && `certificate serial ${g.serial}`,
  `verification: ${g.verification_status || "not stated"}`].filter(Boolean).join("; ");
function hisStatusChips(d) {
  const h = d.his; if (!h) return "";
  const s = HSTAT[h.status], g = h.signature;
  return [s ? `<span class="chip ${s[0]}" title="Report status in the hospital system">${s[1]}${(h.status === "amended" || h.status === "corrected") && h.version ? " v" + esc(h.version) : ""}</span>` : "",
    h.signed ? `<span class="chip c-ok" title="${esc(sigTitle(g))}">Digitally signed</span>`
      : g && g.verification_status && g.verification_status !== "verified" ? `<span class="chip c-bad" title="${esc(sigTitle(g))}">Signature failed verification</span>`
      : g && g.verification_status === "verified" ? `<span class="chip c-warn" title="${esc(sigTitle(g))}; the signed hash or the report text does not agree with it: not counted as signed">Signature not accepted</span>`
      : ["final", "amended", "corrected"].includes(h.status) ? `<span class="chip c-warn" title="The hospital system holds no verified digital signature for this report">Not signed</span>` : ""].filter(Boolean).join(" ");
}
function docChips(d) {
  const h = d.his;
  return [h ? `<span class="chip c-info" title="Fetched read-only from ${esc(h.label || "the hospital system")}">from HIS</span>` : "",
    h?.registration ? `<span class="chip c-warn" title="A record of a linked registration">Registration <span class="mono">${esc(h.registration)}</span></span>` : "",
    d.outside ? `<span class="chip c-mute" title="${esc(`Uploaded by ${d.outside.by || "?"}${d.outside.at ? " on " + dmyt(d.outside.at) : ""}: another hospital or a private laboratory; read, matched to the patient and checked like every record`)}">Outside report</span>` : "",
    (d.methods || []).includes("vision-transcription") ? `<span class="chip c-scan" title="${SCAN_TITLE}">Scanned (OCR)</span>` : "",
    d.identity_confirmed_by ? `<span class="chip c-ok">patient confirmed by ${esc(d.identity_confirmed_by)}</span>` : "",
    d.superseded ? `<span class="chip c-mute" title="Kept as history; never counted for the Pre-Authorization">History: version ${esc(h?.version || "?")}, superseded by version ${esc(d.superseded.version || "?")}</span>` : "",
    (d.his_flags || []).length ? `<span class="chip c-rev" title="${esc(d.his_flags.map((f) => f.text).join("; "))}">${plural(d.his_flags.length, "HIS value")} not in the text</span>` : ""].filter(Boolean).join(" ");
}
function docRow(d) {
  const c = d.classification || {}; const nf = Object.values(d.facts || {});
  const att = (S.data.state.overrides?.documents || {})[d.doc_id];
  const st = d.state !== "ready" ? `<span class="chip ${d.state === "error" ? "c-bad" : "c-info"}" title="${esc(d.error || "")}">${d.state === "error" ? "failed to read" : esc(d.state)}</span>${d.state === "error" ? `<div class="small muted">${esc(d.error || "")}</div>${d.dismissed ? `<span class="chip c-mute" title="${esc(d.dismissed.reason || "")}">dismissed by ${esc(d.dismissed.by || "")}</span>` : `<span class="chip c-warn" title="A document that failed to read blocks the Pre-Authorization until it is re-processed or dismissed">blocks the gate</span>`}` : ""}` : statusChip(c) + (att?.attested_final ? ` <span class="chip c-ok" title="${esc(att.reason || "")}">attested final by ${esc(att.by)}</span>` : "");
  const unst = d.state === "ready" && c.status === "UNSTATED" && c.signed !== "no" && !att?.attested_final;
  const h = d.his, sup = !!d.superseded, ids = h ? [h.encounter_number, h.accession].filter(Boolean) : [], chips = docChips(d), hst = hisStatusChips(d);
  const btns = (h?.imaging_study_ref ? imagesBtn(d.doc_id) : "") + (sup ? "" : `${d.outside && d.identity === "name_match" && !d.identity_confirmed_by && can("confirm", d.doc_id) ? `<button class="ghost sm" data-confmatch="${esc(d.doc_id)}" title="An outside report matched by name only: check the patient on the report and confirm">Confirm patient</button>` : ""}${d.state === "error" && can("reprocess") ? `<button class="ghost sm" data-reproc-doc="${esc(d.doc_id)}">Re-process</button>` : ""}${d.state === "error" && !d.dismissed && can("confirm", d.doc_id) ? `<button class="ghost sm" data-dismiss="${esc(d.doc_id)}" title="Record, with a reason, that the Case File may pass without this document (audited, undoable)">Dismiss</button>` : ""}${unst && can("confirm", d.doc_id) ? `<button class="ghost sm" data-attest-doc="${esc(d.doc_id)}">Attest final</button>` : ""}${d.state === "ready" && (docDates(c).unconfirmed || docDates(c).flags.length) && can("confirm", d.doc_id) ? `<button class="ghost sm" data-confdate="${esc(d.doc_id)}">Confirm date</button>` : ""}${d.state === "ready" && c.doc_type_disagreement && !c.doc_type_confirmed_by && can("confirm", d.doc_id) ? `<button class="ghost sm" data-conftype="${esc(d.doc_id)}">Confirm type</button>` : ""}${can("unfile", d.doc_id) ? `<button class="ghost sm" data-unfile-doc="${esc(d.doc_id)}" title="Not this patient: move the record back to the Needs matching queue (audited, the Case File forgets what it learned from it)">Back to matching</button>` : ""}${can("delete_document", d.doc_id) ? `<button class="ghost sm" data-del-doc="${esc(d.doc_id)}" title="Remove this document from the Case File (audited)">Remove</button>` : ""}`);
  return `<tr class="click${sup ? " superseded" : ""}" data-doc="${esc(d.doc_id)}"><td><b>${esc(c.title || d.filename)}</b>${ids.length ? `<div class="mono small" title="OP / IP No. and accession No. in the hospital system">${esc(ids.join(" · "))}</div>` : ""}<div class="small muted">${esc(d.rel_path)}${d.department ? ` · ${h ? "from" : "uploaded by"} ${esc(deptName(d.department))}${d.uploaded_by ? " (" + esc(d.uploaded_by) + ")" : ""}` : ""}${d.identity === "mismatch_or_missing" ? ' · <span style="color:#b23a2f">patient ID not found</span>' : d.identity === "id_differs" ? ' · <span style="color:#b23a2f">prints an identifier this Case File does not know</span>' : d.identity === "name_match" ? ' · <span style="color:#8a5300">matched by name only</span>' : ""}</div>${chips ? `<div class="chips" style="margin-top:4px">${chips}</div>` : ""}</td>
      <td>${esc(DT[c.doc_type] || c.doc_type || "")}${c.doc_type_disagreement ? ` <span class="chip c-warn" title="${esc(c.doc_type_disagreement.note || "")}">keywords say ${esc(DT[c.doc_type_disagreement.keyword_type] || c.doc_type_disagreement.keyword_type)}</span>` : ""}</td><td>${dateCell(c)}</td><td>${st}${hst ? `<div class="chips" style="margin-top:4px">${hst}</div>` : ""}</td>
      <td class="small">${(d.methods || []).map((m) => (m === "vision-transcription" ? "Vision reader (scan)" : m === "text-layer" ? "PDF text layer" : m)).join(", ")}${(d.page_flags || []).map((f) => ` <span class="chip c-warn" title="Transcribed as is, never translated into facts; values from these lines need a person's check">${esc(f)}</span>`).join("")}</td>
      <td>${nf.filter((f) => f.verification === "verified").length} verified${nf.filter((f) => f.verification !== "verified").length ? ` · <span class="chip c-rev">${nf.filter((f) => f.verification !== "verified").length} not verified</span>` : ""}
      ${btns ? `<div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap">${btns}</div>` : ""}</td></tr>`;
}
// V2 item 6.3: the images behind an imaging report open in the hospital's viewer (OHIF) through this app; people view them, no model reads them
const IMG_NOTE = "Images are viewed by people; no model reads them";
const imagesBtn = (docId, cid) => `<button class="ghost sm" data-images="${esc(docId)}"${cid ? ` data-case="${esc(cid)}"` : ""} title="Open the study in the hospital's image viewer (audited). ${IMG_NOTE}.">Open images</button>`;
async function openImages(caseId, docId, btn) {
  if (btn) btn.disabled = true;
  try {
    const r = await api(`/cases/${encodeURIComponent(caseId)}/documents/${encodeURIComponent(docId)}/images`, { method: "POST" });  // grants, caches the study on the record, audits
    if (!r.available || !r.viewer_url) { toast(r.reason || "The images are not available in the image viewer", 7000); return; }
    if (!window.open(r.viewer_url, "_blank")) toast("The browser blocked the new window: allow pop-ups for this site to open the image viewer", 8000);
    else toast(`Image viewer opened${r.modality ? ": " + r.modality : ""}${r.instances ? ", " + plural(r.instances, "image") : ""}. ${IMG_NOTE}.`, 6000);
  } catch (e) { toast(e.message, 7000); }
  finally { if (btn) btn.disabled = false; }
}
const bindImages = (root) => $$("[data-images]", root).forEach((b) => (b.onclick = (e) => { e.stopPropagation(); openImages(b.dataset.case || S.caseId, b.dataset.images, b); }));
// V2 item 3.4: the records of an HIS Case File grouped by OP visit and IP admission (newest first), then the groups without an encounter
function groupHTML(g, byId) {
  const ds = (g.docs || []).map((id) => byId[id]).filter(Boolean), enc = g.kind === "OP" || g.kind === "IP";
  const when = enc && g.start ? dmyd(g.start) + (g.kind === "IP" && g.end ? " to " + dmyd(g.end) : "") : "";
  const head = enc ? [g.label, g.department, g.unit, when].filter(Boolean).join(", ") : g.label;
  const wards = (g.ward_history || []).map(wardText).join("; "), pre = g.pmjay_preauth;
  const chips = [g.pre_admission ? `<span class="chip c-info" title="An OP visit before the first IP admission">Pre-admission OPD</span>` : "",
    pre ? `<span class="chip c-mute" title="PM-JAY pre-authorisation as the hospital system records it">PM-JAY pre-authorisation: ${esc(pre.status || "recorded")}${pre.date ? " " + esc(dmyd(pre.date)) : ""}</span>` : "",
    ...(g.registrations || []).map((u) => `<span class="chip c-warn" title="This encounter holds records of a linked registration">Registration <span class="mono">${esc(u)}</span></span>`),
    g.status && g.status !== "finished" ? `<span class="chip c-mute">${esc(g.status)}</span>` : ""].filter(Boolean).join(" ");
  return `<div class="card encgroup" data-group="${esc(g.key || "")}"><h3><span>${esc(head)}</span><span class="muted small">${plural(ds.length, "record")}</span></h3>
    ${chips ? `<div class="chips" style="margin-bottom:6px">${chips}</div>` : ""}
    ${g.consultant || wards ? `<div class="small muted" style="margin-bottom:6px">${g.consultant ? "Consultant: " + esc(g.consultant) : ""}${g.consultant && wards ? " · " : ""}${wards ? "Ward: " + esc(wards) : ""}</div>` : ""}
    ${ds.length ? `<table class="t">${DOC_HEAD}<tbody>${ds.map(docRow).join("")}</tbody></table>` : `<div class="small muted">No record of this encounter in the Case File.</div>`}</div>`;
}
function renderDocs() {
  const docs = S.data.documents, groups = S.data.his ? S.data.groups || [] : [];
  let list;
  if (groups.length) {
    const byId = Object.fromEntries(docs.map((d) => [d.doc_id, d])), seen = new Set(groups.flatMap((g) => g.docs || []));
    const rest = docs.filter((d) => !seen.has(d.doc_id));  // never lose a document the grouping did not place
    const gs = rest.length ? [...groups, { key: "rest", kind: "upload", label: "Other documents", docs: rest.map((d) => d.doc_id) }] : groups;
    list = `<div class="card"><h3>Documents in the Case File <span class="muted small">${docs.length}</span></h3><div class="muted small">Grouped by OP visit and IP admission as ${esc(S.data.his.label || "the hospital system")} records them, newest first; then the hospital records with no encounter, the outside reports and other uploads. An earlier version of an amended report is kept as history and never counted.</div></div>`
      + gs.map((g) => groupHTML(g, byId)).join("");
  } else list = `<div class="card"><h3>Documents in the Case File <span class="muted small">${docs.length}</span></h3>
  <table class="t">${DOC_HEAD}<tbody>${docs.map(docRow).join("")}</tbody></table></div>`;
  $("#tab-docs").innerHTML = `${list}
  <div class="card${isLimited() ? " hidden" : ""}"><h3>Primary fields across the Case File</h3><div class="muted small" style="margin-bottom:8px">Current value = most recent verified value from a final, signed document. Every value links to its source quote.</div>
  <table class="t"><thead><tr><th>Field</th><th>Current value</th><th>Source</th><th>History</th></tr></thead><tbody>
  ${Object.entries(S.data.facts).map(([k, f]) => { const c = f.current;
    return `<tr><td>${esc(f.label)}</td><td><b>${esc(c.value)}</b> ${c.state === "pending" ? '<span class="chip c-warn">pending</span>' : ""}${critChip(k, c)}${c.verification !== "verified" ? '<span class="chip c-rev">' + esc(c.verification) + "</span>" : ""}${!c.doc_final ? '<span class="chip c-bad">non-final doc</span>' : ""}</td>
      <td>${c.verification === "confirmed" ? `<span class="chip c-ok" title="Read by the clinician in the source document; no model quote">confirmed by ${esc(c.confirmed_by || "clinician")}</span> <span class="cite" data-doc="${esc(c.doc_id)}">${esc(c.doc_title || c.doc_id)}</span>` : citeHTML({ ...c.location, doc_id: c.doc_id, doc_title: c.doc_title, date: c.date, quote: c.quote, source_method: c.source_method })}</td>
      <td class="small muted">${f.history.length > 1 ? f.history.map((h) => `${esc(h.value)} (${fmtDate(h.date)})`).join(" → ") : ""}</td></tr>`; }).join("")}
  </tbody></table></div>`;
  $$("tr[data-doc]").forEach((tr) => (tr.onclick = (e) => { if (!e.target.closest("button")) openDoc(tr.dataset.doc); }));
  $$("[data-attest-doc]").forEach((b) => (b.onclick = () => attestDoc(b.dataset.attestDoc)));
  bindImages($("#tab-docs"));
  $$("[data-reproc-doc]", $("#tab-docs")).forEach((b) => (b.onclick = async () => { const j = await api(`/cases/${S.caseId}/reprocess`, { json: { which: [b.dataset.reprocDoc] } }); S.tab = "ready"; showTab("ready"); watchJob(j.job); }));
  $$("[data-dismiss]", $("#tab-docs")).forEach((b) => (b.onclick = () => dismissDoc(b.dataset.dismiss)));
  $$("[data-confdate]", $("#tab-docs")).forEach((b) => (b.onclick = () => confirmDates(b.dataset.confdate)));
  $$("[data-conftype]", $("#tab-docs")).forEach((b) => (b.onclick = () => confirmDocType(b.dataset.conftype)));
  $$("[data-confmatch]", $("#tab-docs")).forEach((b) => (b.onclick = () => confirmMatch(b.dataset.confmatch)));
  $$("[data-unfile-doc]").forEach((b) => (b.onclick = async () => { const v = await confirmDialog({ title: "Move this record back to matching", intro: "The document leaves this Case File and returns to the Needs matching queue; this Case File will not be suggested for it again, and identifiers learned from it are forgotten. Recorded in both audit logs.", fields: [{ id: "reason", label: "Reason", type: "text", required: true }], submit: "Move back" });
    if (!v) return; try { await api(`/cases/${S.caseId}/documents/${b.dataset.unfileDoc}/unfile`, { json: { reason: v.reason } }); await openCase(S.caseId, true); refreshQueueCount(); toast("Record moved back to the Needs matching queue"); } catch (e) { toast(e.message, 7000); } }));
  $$("[data-del-doc]").forEach((b) => (b.onclick = async () => { if (!confirm("Remove this document from the Case File? The removal is recorded in the audit log.")) return;
    await api(`/cases/${S.caseId}/documents/${b.dataset.delDoc}`, { method: "DELETE" }); await openCase(S.caseId, true); toast("Document removed; Pre-Authorization re-checked"); }));
}

// V1 item 8.4: where a quote was read on the scan image, from the independent OCR engine's word boxes (page.box_map: transcription
// offsets -> boxes as fractions of the image). Drawn only where words were matched, and only when at least 60 % of the quote's words were.
function spanBoxes(p, s, e) {
  const map = (p && p.box_map) || []; if (!map.length || isNaN(s) || isNaN(e)) return [];
  const t = (p.text || "").slice(s, e), re = /[^\s|]+/g; let m, tot = 0, hit = 0;
  while ((m = re.exec(t))) { if (!/[\p{L}\p{N}]/u.test(m[0])) continue; tot++; const a = s + m.index, b = a + m[0].length; if (map.some((x) => x[0] < b && a < x[1])) hit++; }
  if (!tot || hit / tot < 0.6) return [];
  const lines = [];
  for (const x of map) { if (!(x[0] < e && s < x[1])) continue; const b = x.slice(2);
    const l = lines.find((r) => Math.min(r[3], b[3]) - Math.max(r[1], b[1]) >= 0.5 * Math.min(r[3] - r[1], b[3] - b[1]));
    if (l) { l[0] = Math.min(l[0], b[0]); l[1] = Math.min(l[1], b[1]); l[2] = Math.max(l[2], b[2]); l[3] = Math.max(l[3], b[3]); } else lines.push([...b]); }
  return lines.map((r) => [Math.max(0, r[0] - 0.003), Math.max(0, r[1] - 0.003), Math.min(1, r[2] + 0.003), Math.min(1, r[3] + 0.003)]);
}
const boxDiv = (r, k, t) => `<div class="ocrbox ${k}" title="${esc(t)}" style="left:${(r[0] * 100).toFixed(2)}%;top:${(r[1] * 100).toFixed(2)}%;width:${((r[2] - r[0]) * 100).toFixed(2)}%;height:${((r[3] - r[1]) * 100).toFixed(2)}%"></div>`;
async function openDoc(docId, focus, base) {
  base = base || `/cases/${S.caseId}/documents/${docId}`;
  const d = await api(base);
  const c = d.classification || {};
  const pages = d.pages || [];
  const pg = focus?.page ?? 0;
  const marks = (pi) => {
    const spans = Object.entries(d.facts || {}).filter(([, f]) => f.location && f.location.page === pi).map(([k, f]) => ({ s: f.location.start, e: f.location.end, k }));
    if (focus && focus.page === pi && focus.start !== "" && !isNaN(focus.start)) spans.push({ s: focus.start, e: focus.end, k: "focus" });
    spans.sort((a, b) => a.s - b.s);
    const t = pages[pi]?.text || ""; let out = "", pos = 0;
    for (const sp of spans) { if (sp.s < pos) continue; out += esc(t.slice(pos, sp.s)) + `<mark class="${sp.k === "focus" ? "focus" : ""}" title="${esc(sp.k)}">` + esc(t.slice(sp.s, sp.e)) + "</mark>"; pos = sp.e; }
    return out + esc(t.slice(pos));
  };
  const isImg = [".png", ".jpg", ".jpeg", ".webp", ".bmp"].includes(d.ext);
  const isPdf = [".pdf", ".tif", ".tiff"].includes(d.ext);  // pages rendered by the server (TIFF: one frame per page)
  const preview = isImg ? `<div class="scanwrap"><img class="orig" src="/api/tb${base}/file" alt="Original document"><div id="ocrboxes"></div></div><div class="small muted" id="boxnote"></div>` :
    isPdf ? `<div class="scanwrap"><img class="orig" id="pdfimg" src="/api/tb${base}/file?render=1&page=${pg}" alt="Page preview"><div id="ocrboxes"></div></div><div class="small muted" id="boxnote"></div>` : `<div class="muted">No image preview for this format.</div>`;
  const drawBoxes = (pi) => {  // V1 item 8.4: the cited quote (strong) and this page's fields (light) on the scan image
    const el = $("#ocrboxes"), note = $("#boxnote"), p = pages[pi] || {}; if (!el) return;
    const out = [];
    if (focus && focus.page === pi && focus.start !== "" && !isNaN(focus.start)) spanBoxes(p, focus.start, focus.end).forEach((r) => out.push(boxDiv(r, "focus", "Cited quote")));
    Object.entries(d.facts || {}).forEach(([k, f]) => { if (f.location?.page === pi) (f.boxes || []).forEach((r) => out.push(boxDiv(r, "fact", S.facts?.[k]?.label || k))); });
    el.innerHTML = out.join("");
    if (note) note.textContent = p.method !== "vision-transcription" ? "" : p.box_map ? (out.length ? "Highlights: where the words were read on the image (independent OCR engine word positions, shown only where its words match the transcription)." : "")
      : p.ocr_engine_note ? `No word positions on this page: ${p.ocr_engine_note}.` : "No word positions on this page (read before the independent OCR engine was added: re-process the document to get them).";
  };
  const idr = d.identity_read;
  const idHTML = idr ? `<div>Identity as printed</div><div>${esc(identityText(idr))}${idr.notes?.length ? ` <span class="muted">(${esc(idr.notes.join("; "))})</span>` : ""}</div>` : "";
  $("#drawer-body").innerHTML = `<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
    <div><div class="eyebrow">${esc(DT[c.doc_type] || c.doc_type || "")} · ${esc(c.department || "")}</div><h2 style="margin:4px 0;color:#1f2933">${esc(c.title || d.filename)}</h2>
    <div class="muted small">${esc(d.rel_path)} · ${dateCell(c)} · ${statusChip(c)}${(c.status_notes || []).length ? ` <span class="chip c-warn">${esc(c.status_notes.join("; "))}</span>` : ""}</div></div>
    <div><a class="ghost" href="/api/tb${base}/file" target="_blank">Open original</a> <button class="ghost" data-close>Close</button></div></div>
    <div class="kv" style="margin:12px 0"><div>Status line</div><div>${esc(c.status_quote || "not found")}</div><div>Signature</div><div>${esc(c.signature_quote || c.signer || "not found")}</div>
    ${datesKV(c)}
    ${d.department ? `<div>Uploaded by</div><div>${esc(deptName(d.department))}${d.uploaded_by ? " (" + esc(d.uploaded_by) + ")" : ""} · ${esc((d.added || "").slice(0, 16).replace("T", " "))}</div>` : ""}${idHTML}
    ${d.intake ? "" : `<div>Patient ID check</div><div>${d.identity === "match" ? "An identifier on the document matches the Case File patient" : d.identity === "name_match" ? "Patient name matches (no identifier agrees)" : d.identity === "id_differs" ? "The document prints an identifier this Case File does not know: verify it belongs to this patient" : "Not found in document: verify it belongs to this patient"}</div>`}
    <div>Read by</div><div>${esc([...new Set(pages.map((p) => p.method))].join(", "))}${pages.some((p) => p.ocr_reads) ? ` (two reads per scanned page by the vision reader${pages.some((p) => p.ocr_engine) ? " and one by the independent OCR engine (Tesseract)" : ""}; numbers compared)` : ""}</div></div>
    <div class="docview"><div>${preview}</div><div>
      ${pages.length > 1 ? `<div style="margin-bottom:6px">${pages.map((p, i) => `<button class="ghost sm" data-pg="${i}">Page ${i + 1}</button>`).join(" ")}</div>` : ""}
      <div class="doctext" id="doctext">${marks(pg)}</div>
      <h4 style="color:#1f2933">Fields found in this document</h4>
      <table class="t"><tbody>${Object.entries(d.facts || {}).map(([k, f]) => `<tr><td>${esc(k)}</td><td><b>${esc(f.value)}</b>${f.state === "pending" ? ' <span class="chip c-warn">pending</span>' : ""}</td>
        <td><span class="chip ${f.verification === "verified" ? "c-ok" : "c-rev"}" title="${esc(f.reason || "")}">${esc(f.verification)}</span>${f.polarity === "negated" ? ' <span class="chip c-mute" title="The value is a negative finding (no / not / negative / absent)">negated</span>' : ""}${f.verification === "confirmed" ? ` <span class="chip c-ok" title="Read by the clinician in the source document; no model quote">confirmed by ${esc(f.confirmed_by || "clinician")}</span>` : scanChip({ ...f, doc_id: d.doc_id })}${critChip(k, f, d.doc_id)}</td><td class="small muted">"${esc(f.quote)}"</td></tr>`).join("") || '<tr><td class="muted">None</td></tr>'}</tbody></table>
      ${pages.some((p) => p.flags?.length) ? `<div class="flag review" style="margin-top:8px"><div class="k">Hindi / regional text or handwriting</div>${esc([...new Set(pages.flatMap((p) => p.flags || []))].join("; "))}. Flagged lines: ${pages.map((p, i) => (p.flagged_lines || []).map((l) => `page ${i + 1}: "${esc(l.line.slice(0, 80))}"`).join("; ")).filter(Boolean).join("; ")}. The text is transcribed as written and never translated; values taken from these lines are marked for a person's check.</div>` : ""}
      ${pages.some((p) => p.ocr_uncertain_numbers?.length) ? `<div class="flag review" style="margin-top:8px"><div class="k">OCR disagreement</div>The reads of this scanned page (vision reader twice${pages.some((p) => p.ocr_engine) ? ", independent OCR engine" : ""}) differ on these numbers: ${esc(pages.flatMap((p) => p.ocr_uncertain_numbers || []).join(", "))}. Values containing them are marked for expert review; read the scan image.</div>` : ""}
    </div></div>`;
  $("#drawer").classList.remove("hidden");
  drawBoxes(pg);
  $$("[data-pg]").forEach((b) => (b.onclick = () => { $("#doctext").innerHTML = marks(+b.dataset.pg); const im = $("#pdfimg"); if (im) im.src = im.src.replace(/page=\d+/, "page=" + b.dataset.pg); drawBoxes(+b.dataset.pg); }));
  setTimeout(() => $("#doctext mark.focus")?.scrollIntoView({ block: "center" }), 50);
}

// ------------------------------------------------------------------ tab: ask
function renderAsk() {
  $("#tab-ask").innerHTML = `<div class="grid2"><div class="card"><h3>Ask the Case File</h3>
    <div class="muted small" style="margin-bottom:10px">Answers come only from the documents. Every statement carries a verified source quote; if nothing in the Case File supports an answer, it says so.</div>
    <div class="search"><input id="q" placeholder="e.g. What is the PD-L1 result?  ·  Where is the CEA trend?  ·  Which reports are unsigned?" autocomplete="off"><button class="primary" id="ask">Ask</button><button class="ghost" id="askgl" title="Search the guideline library (reference text)">Search guidelines</button></div>
    <div class="muted small" style="margin-top:6px">Try: <a href="#" data-q="What is the PD-L1 result and is it final?">PD-L1</a> · <a href="#" data-q="List every CEA value with its date">CEA trend</a> · <a href="#" data-q="Which reports are not final or not signed?">unsigned reports</a> · <a href="#" data-q="What stage is recorded and in which report?">recorded stage</a> · <a href="#" data-q="What treatment should the patient receive?">out-of-scope example</a></div>
    <div id="answers"></div></div>
    <div class="card"><h3>Instant search <span class="muted small" id="ms"></span></h3><div class="muted small">Every line in every document that mentions your term (oncology synonyms included), newest first.</div><div id="hits"></div></div></div>`;
  const q = $("#q");
  let h;
  q.oninput = () => { clearTimeout(h); h = setTimeout(() => instant(q.value), 220); };
  q.onkeydown = (e) => { if (e.key === "Enter") ask(q.value); };
  $("#ask").onclick = () => ask(q.value);
  $("#askgl").onclick = async () => { if (!q.value.trim()) return; const box = $("#answers"); box.insertAdjacentHTML("afterbegin", `<div class="qbox">Guidelines: ${esc(q.value)}</div><div id="glq"><span class="spin"></span></div>`);
    const r = await api("/guidelines/search", { json: { query: q.value, cancer: S.data.case.protocol } });
    $("#glq").outerHTML = `<div class="small muted">Reference text for the board to consult. Not a recommendation for this patient.</div>` + glHTML(r); };
  $$("[data-q]").forEach((a) => (a.onclick = (e) => { e.preventDefault(); q.value = a.dataset.q; instant(q.value); ask(q.value); }));
  renderAnswers();
}
async function instant(text) {
  if (!text.trim()) { $("#hits").innerHTML = ""; return; }
  const r = await api(`/cases/${S.caseId}/search`, { json: { query: text } });
  $("#ms").textContent = `${r.values.hits.length} lines · ${r.ms_values} ms`;
  const rx = r.values.patterns.length ? new RegExp(r.values.patterns.join("|"), "ig") : null;
  $("#hits").innerHTML = r.values.hits.map((h) => `<div class="hit cite-row" data-doc="${esc(h.doc_id)}" data-page="${h.page}" data-start="${h.start}" data-end="${h.end}">
    <div class="small muted">${esc(h.doc_title)} · ${fmtDate(h.date)} · ${esc(h.status || "")}</div><div>${rx ? esc(h.text).replace(rx, (m) => `<mark>${m}</mark>`) : esc(h.text)}</div></div>`).join("")
    || (r.passages.length ? `<div class="small muted" style="margin:8px 0">No exact line match. Closest passages:</div>` + r.passages.slice(0, 5).map((p) => `<div class="hit cite-row" data-doc="${esc(p.doc_id)}" data-page="${p.page}" data-start="${p.start}" data-end="${p.end}"><div class="small muted">${esc(p.doc_title)} · ${fmtDate(p.date)}</div><div>${esc(p.text.slice(0, 220))}</div></div>`).join("") : `<div class="muted small">Nothing found.</div>`);
  $$(".cite-row").forEach((el) => (el.onclick = () => openDoc(el.dataset.doc, { page: +el.dataset.page, start: +el.dataset.start, end: +el.dataset.end })));
}
async function ask(text) {
  if (!text.trim()) return;
  S.chat.push({ q: text, pending: true }); renderAnswers();
  const hist = S.chat.filter((c) => !c.pending && c.a?.status === "answered").slice(-2).flatMap((c) => [{ role: "user", content: c.q }, { role: "assistant", content: c.a.statements.map((s) => s.text).join(" ") }]);
  try { const a = await api(`/cases/${S.caseId}/ask`, { json: { question: text, history: hist } }); Object.assign(S.chat[S.chat.length - 1], { a, pending: false }); }
  catch (e) { Object.assign(S.chat[S.chat.length - 1], { a: { status: "error", message: e.message }, pending: false }); }
  renderAnswers();
}
function renderAnswers() {
  const el = $("#answers"); if (!el) return;
  el.innerHTML = S.chat.slice().reverse().map((c) => `<div class="qbox">${esc(c.q)}</div>` + (c.pending ? `<div class="muted"><span class="spin"></span> Reading the Case File...</div>` :
    c.a.status === "answered" ? `<div class="answer">${c.a.statements.map((s) => `<p>${esc(s.text)} ${s.citations.map(citeHTML).join("")}${flagHTML(s)}</p>`).join("")}</div>
      <div class="small muted">${c.a.seconds} s · ${esc(c.a.mode)}${c.a.dropped_unverified ? ` · ${c.a.dropped_unverified} unverified statement(s) removed` : ""}</div>${can("review") ? removedHTML(c.a.removed) : ""}` :
    c.a.status === "out_of_scope" ? `<div class="refusal"><b>Outside the assistant's scope.</b> ${esc(c.a.message)}</div>` :
    `<div class="refusal"><b>${c.a.status === "error" ? "Error" : "Not documented in the Case File."}</b> ${esc(c.a.message)}</div>${can("review") ? removedHTML(c.a.removed) : ""}`)).join("");
}

// ------------------------------------------------------------------ tab: specialty support (agents)
async function renderRoles() {
  S.roles = S.roles || (await api("/roles"));
  const arts = S.data.state.artefacts || {};
  $("#tab-roles").innerHTML = `<div class="card"><h3>Role-specific AI support <button class="ghost sm" id="all-briefs">Prepare all briefs in parallel</button></h3>
    <div class="muted small">When a specialist is unavailable, the corresponding support agent prepares a specialty-specific brief from the Case File records. Each item carries a verified quote. Briefs are AI drafts until reviewed by an expert. Role-specific support, not autonomous clinical decision-making.</div></div>
    <div class="roles" style="margin-top:12px">${Object.entries(S.roles).map(([k, r]) => `<div class="role" id="role-${k}"><h4>${esc(r.label)}</h4><p>${esc(r.focus)}</p>
      <div style="display:flex;gap:6px"><input placeholder="Optional focus question" id="focus-${k}" style="flex:1;padding:6px 8px;border:1px solid #d9e2ec;border-radius:8px;font-size:12px">
      <button class="primary sm" data-role="${k}">${arts["brief_" + k] ? "Refresh" : "Prepare brief"}</button></div></div>`).join("")}</div>
    <div id="briefs" style="margin-top:14px"></div>`;
  $$("[data-role]").forEach((b) => (b.onclick = () => runAgent(b.dataset.role)));
  $("#all-briefs").onclick = () => Object.keys(S.roles).forEach((k) => runAgent(k));
  Object.keys(S.roles).forEach((k) => arts["brief_" + k] && showBrief(k, arts["brief_" + k]));
}
function briefBox(role) {
  let box = $("#brief-" + role);
  if (!box) { box = document.createElement("div"); box.className = "card brief"; box.id = "brief-" + role; $("#briefs").prepend(box); }
  return box;
}
async function runAgent(role) {
  const box = briefBox(role), label = S.roles[role].label;
  box.innerHTML = `<h3>${esc(label)} <span class="chip c-info"><span class="spin"></span> working</span></h3><div class="trace" id="trace-${role}"></div>`;
  const tr = $("#trace-" + role);
  const res = await fetch(`/api/tb/cases/${S.caseId}/agents/${role}`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ focus: $("#focus-" + role)?.value || "" }) });
  const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
  while (true) {
    const { value, done } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true }); let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i); buf = buf.slice(i + 1); if (!line.trim()) continue;
      const ev = JSON.parse(line);
      if (ev.type === "step") { tr.insertAdjacentHTML("beforeend", `<div><span class="tl">${esc(ev.tool)}</span>(${esc(ev.input || "")}) <span style="opacity:.7">${esc(ev.thought || "")}</span></div>`); tr.scrollTop = 1e9; }
      if (ev.type === "error") box.innerHTML = `<h3>${esc(label)}</h3><div class="refusal">${esc(ev.message)}</div>`;
      if (ev.type === "brief") showBrief(role, ev.brief);
    }
  }
}
function noDocsHTML(b) {  // V1 item 6.6: no documents of the specialty, no model call; the department's open requests
  return `<div class="refusal"><b>${esc(b.message)}.</b> The agent did not run (no model call).</div>
    ${(b.open_items || []).length ? `<h4>Open requests to ${esc(b.department)}</h4><ul>${b.open_items.map((x) => `<li>${esc(x.label)}${x.what ? `: <span class="muted">${esc(x.what)}</span>` : ""}${x.due ? ` <span class="small muted">· due ${fmtDate(x.due)}</span>` : ""}</li>`).join("")}</ul>` : `<div class="small muted">No open Pre-Authorization request to ${esc(b.department)}.</div>`}`;
}
function showBrief(role, b) {
  const box = briefBox(role);
  const rv = b.review || {};
  const stale = S.data.stale?.["brief_" + role];
  if (b.no_documents) {
    box.innerHTML = `<h3>${esc(b.label)} <span class="chip c-mute">No documents</span></h3>${stale ? `<div class="banner warn stale"><b>${esc(stale)}.</b> Prepare the brief again (Refresh).</div>` : ""}${noDocsHTML(b)}`;
    return;
  }
  box.innerHTML = `<h3>${esc(b.label)} <span>${rv.status === "reviewed" ? `<span class="chip c-ok">Reviewed by ${esc(rv.by)}</span>` : rv.status === "flagged" ? `<span class="chip c-bad">Flagged for correction</span>` : `<span class="chip c-rev">AI draft · awaiting expert review</span>`}</span></h3>
    ${stale ? `<div class="banner warn stale"><b>${esc(stale)}.</b> Prepare the brief again (Refresh) before the board relies on it.</div>` : ""}
    <div class="small muted">${esc(b.generated?.replace("T", " "))} · ${b.seconds} s · ${esc(modelLabel(b.model))}${b.dropped_unverified ? ` · ${b.dropped_unverified} unverified item(s) removed` : ""}${b.guardrail_removed ? ` · ${b.guardrail_removed} removed by scope guardrail` : ""}</div>
    ${b.sections.map((s) => `<h4>${esc(s.heading)}</h4><ul>${s.items.map((it) => `<li class="${approxCls(it, rv)}">${esc(it.text)} ${it.citations.map(citeHTML).join("")}${flagHTML(it)}</li>`).join("")}</ul>`).join("")}
    ${b.pack ? `<div class="small muted">Guideline pack: ${packLine(b.pack)}${b.pack.checklist ? ` · Reporting checklist: ${esc(b.pack.checklist.title)} (${esc(b.pack.checklist.region)}, ${esc(b.pack.checklist.pages)})` : ""}</div>` : ""}
    ${b.points_for_review.length ? `<h4>Points for review (not treatment recommendations)</h4><ul>${b.points_for_review.map((it) => `<li class="${approxCls(it, rv)}">${esc(it.text)} ${it.citations.map(citeHTML).join("")}${flagHTML(it)}${(it.references || []).length ? `<div class="grefs">${it.references.map(refHTML).join("")}</div>` : ""}</li>`).join("")}</ul>
      ${b.points_for_review.some((it) => (it.references || []).length) ? `<div class="small muted">References are guideline text for the board to consult, Indian sources first; they are not facts about this patient and not a recommendation for this patient.</div>` : ""}` : ""}
    ${b.not_documented.length ? `<h4>Not documented</h4><ul>${b.not_documented.map((x) => `<li class="muted">${esc(x)}</li>`).join("")}</ul>` : ""}
    ${can("review") ? removedHTML(b.removed) : ""}
    ${reviewBar("brief_" + role, rv)}`;
  bindReview(box);
}
// guideline references of a brief's point for review (V1 item 5.5): labelled "Reference", separate from the record citations
// a PDF has real page numbers; a Word or text guideline is read in parts of 6,000 characters, so it shows "part N" and opens at the start
function glPlace(h) {
  const pdf = /\.pdf$/i.test(h.file || "");
  const span = h.page_end && h.page_end !== h.page ? `${h.page}-${h.page_end}` : `${h.page}`;
  return { label: pdf ? (span.includes("-") ? `pp. ${span}` : `p. ${span}`) : `part ${span}`,
           href: `/api/tb/guidelines/file?path=${encodeURIComponent(h.file)}${pdf ? `#page=${h.page}` : ""}` };
}
function refHTML(r) {
  const at = glPlace(r);
  return `<div class="gref small"><span class="chip ${r.region === "India" ? "c-ok" : "c-info"}">${esc(r.region)}</span> <b>Reference</b> · ${esc(r.org)} · ${esc(r.title)}, ${at.label}
    <a href="${at.href}" target="_blank">open</a>${r.by === "search" ? ` <span class="muted">(found by guideline search)</span>` : ""}<div class="gq">"${esc(r.quote)}"</div></div>`;
}
function packLine(pk) {
  const names = (reg) => [...new Set(pk.sources.filter((x) => (x.region === "India") === reg).map((x) => x.org))].map(esc).join(", ");
  const ind = names(true), intl = names(false);
  return (ind ? `${ind} (India)` : "") + (ind && intl ? ", then " : "") + (intl ? `${intl}` : "");
}
function reviewBar(art, rv) {
  if (!can("review")) return rv.status ? `<div class="small muted">Review: ${esc(rv.status)} by ${esc(rv.by || "")}</div>` : "";
  return `<div class="reviewbar"><b class="small">Human oversight (expert-in-the-loop)</b><input placeholder="Comment for the record" data-cm="${art}" value="${esc(rv.comment || "")}">
    <button class="ghost sm" data-rv="${art}" data-st="reviewed">Mark reviewed</button><button class="danger sm" data-rv="${art}" data-st="flagged">Flag for correction</button></div>`;
}
function bindReview(root) {
  $$("[data-rv]", root).forEach((b) => (b.onclick = async () => {
    await api(`/cases/${S.caseId}/review`, { json: { artefact: b.dataset.rv, status: b.dataset.st, comment: $(`[data-cm="${b.dataset.rv}"]`, root)?.value || "" } });
    S.data = await api("/cases/" + S.caseId); showTab(S.tab); toast("Review recorded in the audit log");
  }));
}

// ------------------------------------------------------------------ tab: summary
function renderSummary() {
  const s = S.data.state.artefacts?.summary, g = S.data.state.gate;
  const gate = g?.passed ? `<span class="chip c-ok">Readiness criteria met</span>` : `<span class="chip c-warn">Pre-Authorization pending (${g ? g.satisfied + "/" + g.total : "not evaluated"})</span>`;
  $("#tab-summary").innerHTML = `<div class="card"><h3>Case File summary ${gate}</h3>
    <div class="muted small">Compiled once every Pre-Authorization check is met. Each sentence links to its source quote; the stage appears only as recorded in a signed report. Points for review, not treatment recommendations.</div>
    ${s && S.data.stale?.summary ? `<div class="banner warn stale"><b>${esc(S.data.stale.summary)}.</b> Regenerate it before the board relies on it or exports it.</div>` : ""}
    <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap"><button class="primary" id="sum" ${g?.passed ? "" : "disabled"}>${s ? "Regenerate" : "Compile Case File summary"}</button>
    ${g?.passed ? "" : `<button class="ghost" id="sum-force">Compile draft anyway (marked incomplete)</button>`}${s ? `<button class="ghost" id="sum-print">Print</button> <button class="ghost" id="sum-export" ${S.data.stale?.summary ? "disabled" : ""} title="${S.data.stale?.summary ? "Regenerate the summary first: the Case File changed since it was compiled" : "Fill the National Cancer Grid Virtual Tumour Board case template (.pptx) from this summary, every sentence cited, for referral to a Regional Cancer Centre or the NCG VTB"}">Export for NCG Virtual Tumour Board / RCC referral (.pptx)</button>` : ""}</div></div>
    <div id="sumout" class="card summary ${s ? "" : "hidden"}"></div>
    <div class="card"><h3>Guideline references for this Case File <button class="ghost sm" id="gl-case">Find relevant sections</button></h3>
      <div class="muted small">Reference text retrieved from the guideline library for the board to consult, India first (National Cancer Grid, ICMR, Tata Memorial Centre, PM-JAY, ICRI / IRIA), then international. Not a recommendation for this patient.</div><div id="glout"></div></div>`;
  const go = async (force) => { $("#sumout").classList.remove("hidden"); $("#sumout").innerHTML = `<span class="spin"></span> Compiling from the signed records...`;
    const r = await api(`/cases/${S.caseId}/summary`, { json: { force } }); if (r.status === "gate_not_met") { $("#sumout").innerHTML = esc(r.message); return; }
    S.data = await api("/cases/" + S.caseId); showSummary(r); };
  $("#gl-case").onclick = async () => { $("#glout").innerHTML = `<span class="spin"></span> Searching the guideline library...`;
    const r = await api(`/cases/${S.caseId}/guidelines`); $("#glout").innerHTML = r.queries.map((q) => `<h4 style="color:#1f2933;margin:14px 0 4px">${esc(q.query)}</h4>` + glHTML(q)).join(""); };
  $("#sum").onclick = () => go(false); if ($("#sum-force")) $("#sum-force").onclick = () => go(true);
  if ($("#sum-print")) $("#sum-print").onclick = () => { document.body.classList.add("print-summary"); window.print(); setTimeout(() => document.body.classList.remove("print-summary"), 500); };
  if ($("#sum-export")) $("#sum-export").onclick = async () => {  // V1 item 4.6
    const r = await fetch(`/api/tb/cases/${encodeURIComponent(S.caseId)}/export/vtb`, { credentials: "same-origin" });
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} toast(m, 9000); return; }
    const blob = await r.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${S.caseId}_ncg_vtb_case.pptx`; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000); toast("NCG Virtual Tumour Board case file exported (.pptx); recorded in the audit log", 6000); };
  if (s) showSummary(s);
}
function showSummary(s) {
  const p = S.data.case.patient || {};
  const rv = s.review || {};
  const stale = S.data.stale?.summary;
  $("#sumout").innerHTML = `${stale ? `<div class="banner warn stale"><b>${esc(stale)}.</b> This summary may no longer reflect the Case File: regenerate it.</div>` : ""}<div class="eyebrow">Automated Case File summary${s.status !== "ready" ? " · INCOMPLETE: Pre-Authorization not met" : ""}</div>
    <h2 style="color:#1f2933;margin:4px 0 12px">${esc(p.name)} · ${esc(p.agesex || "")}</h2>
    ${s.structure ? `<div class="muted small" style="margin-bottom:8px">Structure: ${esc(s.structure)}</div>` : ""}
    ${encountersHTML(s.encounters)}
    ${(s.sections || []).length ? s.sections.map((sec) => `<h4 style="color:#1f2933;margin:12px 0 4px">${esc(sec.title)}</h4>${sec.sentences.length ? `<p>${sec.sentences.map((x) => `<span class="${approxCls(x, rv)}"><span ${x.from_fields ? 'title="Added from the verified primary fields (no model text)" style="color:#334155"' : ""}>${esc(x.text)}</span> ${x.citations.map(citeHTML).join("")}${flagHTML(x)}</span>`).join(" ")}</p>` : `<p class="muted small">Nothing verified for this section in the Case File.</p>`}`).join("")
      : s.paragraphs.map((para) => `<p>${para.map((x) => `${esc(x.text)} ${x.citations.map(citeHTML).join("")}${flagHTML(x)}`).join(" ")}</p>`).join("")}
    ${s.stage_as_recorded ? `<div class="stagebox"><b>Stage, as recorded in the ${esc(s.stage_as_recorded.doc_title)}:</b> ${esc(s.stage_as_recorded.value)} ${citeHTML({ ...s.stage_as_recorded, quote: s.stage_as_recorded.quote })}<div class="small muted">Extracted from the signed source report. The agent does not derive or assign stage.</div></div>` : ""}
    ${s.points_for_review.length ? `<h4 style="color:#1f2933">Points for review</h4><ul>${s.points_for_review.map((x) => `<li class="${approxCls(x, rv)}">${esc(x.text)} ${x.citations.map(citeHTML).join("")}${flagHTML(x)}</li>`).join("")}</ul>` : ""}
    <div class="small muted">${esc(s.generated?.replace("T", " "))} · ${s.seconds} s · ${esc(modelLabel(s.model))}${s.dropped_unverified ? ` · ${s.dropped_unverified} unverified sentence(s) removed` : ""}${s.filled_from_fields ? ` · ${s.filled_from_fields} sentence(s) added from verified fields` : ""}${s.approximate ? ` · ${s.approximate} on an approximate source match (left out of the print view until reviewed)` : ""}</div>
    ${can("review") ? removedHTML(s.removed) : ""}
    ${reviewBar("summary", rv)}`;
  bindReview($("#sumout"));
}

function encountersHTML(list) {  // V2 item 3.4: which records came from which OP visit or IP admission, as the hospital system records them
  if (!(list || []).length) return "";
  const when = (w) => String(w || "").split(" to ").map(dmyd).join(" to ");
  return `<div class="encs"><h4 style="color:#1f2933;margin:4px 0 4px">Encounters</h4><div class="small muted">OP visits and IP admissions from the hospital system's records, with the reports filed under each.</div><ul>
    ${list.map((e) => `<li class="small">${e.kind === "IP" ? "IP admission" : "OP visit"} <span class="mono">${esc(e.number)}</span>${e.department ? ", " + esc(e.department) : ""}${e.unit ? ", " + esc(e.unit) : ""}, ${esc(when(e.when))}${e.pre_admission ? " [pre-admission OPD]" : ""}: ${(e.doc_ids || []).map((id, i) => `<span class="cite" data-doc="${esc(id)}">${esc((e.records || [])[i] || id)}</span>`).join(" ") || esc((e.records || []).join("; "))}</li>`).join("")}</ul></div>`;
}
function glHTML(r) {
  const one = (h) => `<div class="hit"><div class="small"><span class="chip ${h.region === "India" ? "c-ok" : h.region === "US" ? "c-mute" : "c-info"}">${esc(h.region)}</span> <b>${esc(h.org)}</b> · ${esc(h.title)} · ${glPlace(h).label}
    <a href="${glPlace(h).href}" target="_blank">open</a></div><div style="margin-top:4px">${esc(h.text.slice(0, 520))}${h.text.length > 520 ? "..." : ""}</div></div>`;
  return (r.india.length ? r.india.map(one).join("") : `<div class="small muted">No Indian guideline passage matched.</div>`) + r.international.map(one).join("");
}

// ------------------------------------------------------------------ tab: board & follow-up
const BOARD_DEPTS = ["Medical Oncology", "Surgical Oncology", "Radiation Oncology", "Radiology", "Pathology", "Nuclear Medicine", "Biochemistry", "Microbiology", "Medical Gastroenterology", "Pulmonology", "MDT Coordinator"];
const PMJAY = { surgical_oncology: "Surgical Oncologist", radiation_oncology: "Radiation Oncologist", medical_oncology: "Medical Oncologist" };
const FLAGKIND = { transcription: "Possible transcription discrepancy", consistency: "Documentation consistency", composition: "PM-JAY board composition", documentation: "Documentation",
  guideline: "Guideline check", system: "Check not run" };
// guideline checks (V1 item 7.2): doses and RT schedules vs the cancer's dose references (Indian first), stage as written vs the signed report
const GCHECK = { dose: "Guideline check: dose", rt: "Guideline check: radiotherapy schedule", stage: "Stage as recorded" };
const gRefHTML = (f) => f.check === "stage" && f.source ? `<div class="small" style="margin-top:4px">Signed report: ${f.source.doc_id ? citeHTML({ doc_id: f.source.doc_id, doc_title: f.source.doc_title, quote: f.source.quote || f.source.value }) : esc(f.source.doc_title || "")} ${f.source.quote ? `"${esc(f.source.quote)}"` : `value confirmed by ${esc(f.source.confirmed_by || "a clinician")}: ${esc(f.source.value)}`}</div>`
  : (f.references || (f.reference ? [f.reference] : [])).map((r) => refHTML(r) + (r.source_kind === "trial_summary" ? `<div class="small muted" style="margin-left:14px">A dose described in a trial summary, not a regimen line.</div>` : "")).join("");
function guidelineOkHTML(b) {
  const g = b.adjudication.guideline_checks;
  if (!g || !g.checks) return "";
  const ok = g.checks.filter((x) => x.result === "consistent" || x.result === "stage_consistent");
  const label = (x) => x.kind === "stage" ? `Stage "${x.recorded}" matches the signed report` : `${x.kind === "rt" ? "Radiotherapy" : x.drug.charAt(0).toUpperCase() + x.drug.slice(1)} "${x.recorded}" matches a guideline reference${x.references?.[0] ? ` (${x.references[0].org}, p ${x.references[0].page})` : ""}`;
  return ok.map((x) => `<div class="small"><span class="chip c-ok">✓</span> ${esc(label(x))}</div>`).join("") + (g.ran ? "" : `<div class="small muted">Guideline checks did not run for this record.</div>`);
}
// PM-JAY board composition (V1 item 7.1): which of the three oncologists the record shows present; an agent never counts
const compHTML = (c) => !c ? "" : `<div class="small" style="margin-top:6px"><b>PM-JAY board composition</b> ${c.checked ? Object.keys(PMJAY).map((d) => `<span class="chip ${c.present.includes(d) ? "c-ok" : "c-rev"}">${PMJAY[d]}: ${c.present.includes(d) ? "present" : "not recorded"}</span>`).join(" ")
  : `<span class="chip c-rev">Not checked: specialties not recorded</span>`}${c.how ? ` <span class="muted">(${c.how === "attendance" ? "from the attendance" : "read from the participants text"})</span>` : ""}</div>`;
// human over the loop (V1 item 7.3): each flag corrected (the decision is amended, a new version), intentional deviation or false alarm
const RESOLUTION = { corrected: ["c-ok", "Corrected"], intentional_deviation: ["c-info", "Intentional deviation"], false_alarm: ["c-mute", "False alarm"] };
const needsRes = (f) => f.severity === "review" || f.severity === "expert_review";
function recordStatusChip(b) {
  const r = b.resolution;
  if (r && r.checks_complete === false) return `<span class="chip c-rev" title="A check could not run (see below); record the decision again to re-run it">A check did not run: review</span>`;
  if (b.adjudication.status === "consistent" && (!r || r.final)) return `<span class="chip c-ok">Consistent</span>`;
  if (r && r.total && r.final) return `<span class="chip c-ok" title="Every flag was resolved by a person">Final: ${r.total} flag(s) resolved</span>`;
  return `<span class="chip c-rev">${r && r.total ? `${r.open} of ${r.total} flag(s) awaiting resolution` : "Flag for expert review"}</span>`;
}
function resolutionHTML(b, f, i) {
  if (!needsRes(f)) return "";
  const fid = f.id || `F${i + 1}`;  // records from before 7.3 carry no ids: the server numbers them in the same order
  const r = f.resolution;
  if (r) { const k = RESOLUTION[r.resolution] || ["c-mute", r.resolution];
    return `<div class="small" style="margin-top:6px"><span class="chip ${k[0]}">${k[1]}</span> by ${esc(r.by)} · ${esc((r.at || "").replace("T", " ").slice(0, 16))}${r.value ? ` · corrected value "${esc(r.value)}"` : ""}${r.version ? ` · decision version ${r.version}` : ""}${r.reason ? `<div class="muted">${esc(r.reason)}</div>` : ""}
      ${can("board_record") ? ` <button class="ghost sm" data-undores="${esc(r.confirmation)}">Undo</button>` : ""}</div>`; }
  if (!can("board_record")) return `<div class="small muted" style="margin-top:6px">Awaiting resolution by the MDT Coordinator.</div>`;
  return `<div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">${Object.entries(RESOLUTION).map(([k, [, l]]) => `<button class="ghost sm" data-resolve="${esc(b.id)}|${esc(fid)}|${k}">${l}</button>`).join("")}</div>`;
}
const versionsHTML = (b) => (b.versions || []).length < 2 ? "" : `<details class="small" style="margin-top:6px"><summary>Version history (${b.versions.length} versions; the current one is shown above)</summary>
  ${b.versions.slice().reverse().map((v) => `<div style="margin-top:6px"><b>Version ${v.version}</b> · ${esc((v.at || "").replace("T", " ").slice(0, 16))} · ${esc(v.by || "")} · ${esc(v.reason || "")}<div style="white-space:pre-wrap" class="muted">${esc(v.decision_text)}</div></div>`).join("")}</details>`;
async function resolveFlag(rid, fid, kind) {
  const f = ((S.data.state.board_records || []).find((x) => x.id === rid)?.adjudication.flags || []).find((x, i) => (x.id || `F${i + 1}`) === fid) || {};
  const fields = kind === "corrected" ? [{ id: "value", label: f.recorded ? `Corrected value (replaces "${f.recorded}" in the decision)` : "Corrected value (added to the record as an amendment)", value: f.recorded || "", required: true },
      { id: "reason", label: "Note", type: "textarea" }]
    : kind === "intentional_deviation" ? [{ id: "reason", label: "Reason for the intentional deviation", type: "textarea", required: true, placeholder: "Deviating from a guideline is not an error; record why" }]
    : [{ id: "reason", label: "Why this is a false alarm", type: "textarea" }];
  const v = await confirmDialog({ title: `${RESOLUTION[kind][1]}: ${FLAGKIND[f.kind] || "flag"}`, intro: f.text, fields, submit: "Record resolution" });
  if (!v) return;
  try { await api(`/cases/${S.caseId}/board-records/${rid}/flags/${fid}/resolve`, { json: { resolution: kind, value: v.value || "", reason: v.reason || "" } });
    toast(kind === "corrected" ? "Corrected: the decision is amended (new version, history kept)" : "Resolution recorded in the audit log"); await openCase(S.caseId, true); }
  catch (e) { toast(e.message, 7000); }
}
function renderBoard() {
  const st = S.data.state;
  const depts = BOARD_DEPTS;
  const records = (st.board_records || []).slice().reverse();
  const allActs = (st.actions || []).slice().sort((a, b) => (a.status === "completed") - (b.status === "completed") || String(a.due || "").localeCompare(String(b.due || "")));  // a suggested request has no due date (V2 4.2)
  $("#tab-board").innerHTML = `<div class="grid2"><div>
    ${!can("board_record") ? `<div class="card"><h3>Tumour Board decision</h3><div class="muted small">Decisions are recorded by the MDT Coordinator.</div></div>` : `<div class="card form"><h3>Record the Tumour Board decision</h3><div class="muted small">Entered by the clinical team. The agent then checks the record (AI-assisted adjudication): documentation completeness, values against the signed sources, open Pre-Authorization items. It does not judge the clinical decision.</div>
      <label>Board date</label><input type="date" id="b-date" value="${new Date().toISOString().slice(0, 10)}">
      <label>Decision recorded by the board</label><textarea id="b-text" placeholder="As decided and dictated by the board"></textarea>
      <label>Recorded by</label><input id="b-by" placeholder="Name, role">
      <label>Members present (name · department)</label><div id="b-mems"></div><button class="ghost sm" id="b-addm">+ Member</button>
      <div class="small muted">PM-JAY asks for a Surgical, a Radiation and a Medical Oncologist on the board; the check reads the members' departments. An AI support agent is never a member.</div>
      <label>Participants as written (optional: built from the members when empty)</label><input id="b-part" placeholder="e.g. Dr A (Med Onc), Dr B (Surg Onc), Dr C (Rad Onc), Dr D (Pathology)">
      <label>Report corrections or discrepancies raised at the meeting (if any)</label><input id="b-corr" placeholder="e.g. Pathology to issue addendum correcting PD-L1 TPS">
      <label>Divergent opinions / dissenting clinicians (if any)</label><input id="b-div" placeholder="Recorded verbatim, with names">
      <label>Actions (Responsible Department · task · due)</label><div id="b-acts"></div><button class="ghost sm" id="b-add">+ Action</button>
      <label>Next Tumour Board review</label><input type="date" id="b-next">
      <h4 style="margin:14px 0 2px">Outcome and what the board recorded about the patient</h4>
      <div class="muted small">The outcome type is what happened at the board (CRUK 2017: a case not discussed for missing information is recorded as such). The patient-facing items are recorded as the board stated them; missing ones are information flags, never judgements.</div>
      <label>Outcome</label><select id="b-outcome">${Object.entries(S.data.outcomes || { decision: "Decision recorded" }).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join("")}</select>
      <div class="grid2"><div><label>If deferred: reason / what is awaited</label><input id="b-deferred" placeholder="e.g. final histopathology awaited"></div><div><label>If referred: to which board or centre</label><input id="b-referred" placeholder="e.g. NCG Virtual Tumour Board, Tata Memorial"></div></div>
      <div class="grid2"><div><label>Intention to treat, as recorded by the board</label><select id="b-intent"><option value="">Not stated</option><option value="curative">Curative / radical</option><option value="palliative">Palliative</option></select></div>
        <div><label>Clinical trial availability considered</label><select id="b-trial"><option value="">Not recorded</option><option value="yes">Yes</option><option value="no">No</option></select></div></div>
      <div class="grid2"><div><label>Patient consent to the discussion recorded</label><select id="b-consent"><option value="">Not recorded</option><option value="yes">Yes</option><option value="no">No</option></select></div>
        <div><label>Key worker (name and contact)</label><input id="b-keyworker" placeholder="e.g. Sr. Meena, 98450 00000"></div></div>
      <div style="margin-top:12px"><button class="primary" id="b-save">Save record and run adjudication</button></div></div>`}
    ${records.map((b) => `<div class="card"><h3>Tumour Board record · ${fmtDate(b.board_date || (b.recorded_at || "").slice(0, 10))} ${recordStatusChip(b)}${(b.version || 1) > 1 ? ` <span class="chip c-info">Amended: version ${b.version}</span>` : ""}${b.session ? ` <span class="chip c-info click" data-open-session="${esc(b.session)}" title="Recorded in the Board room; open the session">Board session</span>` : ""}</h3>
      <div class="small muted">Recorded by ${esc(b.recorded_by)} · entered ${esc(b.recorded_at.replace("T", " ").slice(0, 16))} by ${esc(b.entered_by)}</div>
      <p style="white-space:pre-wrap">${esc(b.decision_text)}</p>
      <div class="kv small">${b.participants ? `<div>Participants</div><div>${esc(b.participants)}</div>` : ""}${b.report_corrections_raised ? `<div>Report corrections raised</div><div>${esc(b.report_corrections_raised)}</div>` : ""}${b.divergent_opinions ? `<div>Divergent opinions</div><div>${esc(b.divergent_opinions)}</div>` : ""}</div>
      ${outcomeHTML(b)}
      ${compHTML(b.adjudication.composition)}
      ${versionsHTML(b)}
      ${decisionWatchHTML(b)}
      ${communicationHTML(b)}
      ${b.adjudication.flags.map((f, i) => `<div class="flag ${f.severity === "expert_review" ? "" : f.severity === "info" ? "info" : "review"}${f.resolution ? " resolved" : ""}"><div class="k">${f.kind === "guideline" ? GCHECK[f.check] || FLAGKIND.guideline : FLAGKIND[f.kind] || "Documentation"}${f.severity === "info" ? ` <span class="chip c-mute">Info only, not a pass</span>` : ""}</div>
        <div>${esc(f.text)}</div>${f.reference && f.kind === "composition" ? refHTML(f.reference) : ""}${f.kind === "guideline" ? gRefHTML(f) : ""}${f.source_quote ? `<div class="small" style="margin-top:4px">Source: ${citeHTML({ doc_id: f.source_doc, doc_title: f.source_title, quote: f.source_quote })} "${esc(f.source_quote)}"</div><div class="small muted">Expert review required. The agent flags the difference; it does not decide which value is correct.</div>` : ""}${resolutionHTML(b, f, i)}</div>`).join("")}
      ${b.adjudication.value_checks.filter((v) => v.result === "consistent").map((v) => `<div class="small"><span class="chip c-ok">✓</span> ${esc(v.value_as_written)} matches the source</div>`).join("")}${guidelineOkHTML(b)}</div>`).join("")}
  </div><div>
    <div class="card"><h3>Follow-up tracker <span class="muted small">${allActs.filter((a) => a.status !== "completed").length} open</span></h3>
      ${allActs.map(actionHTML).join("") || '<div class="muted small">No actions.</div>'}
      ${st.next_review ? `<div class="stagebox"><b>Next Tumour Board review:</b> ${fmtDate(st.next_review.date)}</div>` : ""}</div>
    ${trendsHTML()}
    <div class="card"><h3>Longitudinal Case File</h3><div class="timeline">${S.data.timeline.map((e) => e.kind === "encounter" ? `<div class="tev encounter"><div class="d">${fmtDate(e.date)}</div>${esc(e.title)}${e.encounter_kind === "IP" && e.end ? ", " + dmyd(e.date) + " to " + dmyd(e.end) : ""}${(e.ward_history || []).length ? `<div class="small muted">Ward: ${esc(e.ward_history.map(wardText).join("; "))}</div>` : ""}</div>` : `<div class="tev ${e.kind}"><div class="d">${fmtDate(e.date)}</div>${e.doc_id ? `<span class="cite" data-doc="${esc(e.doc_id)}">${esc(e.title)}</span> <span class="chip ${["FINAL", "AMENDED", "CORRECTED"].includes(e.status) ? "c-ok" : "c-bad"}">${esc(e.status)}</span>` : esc(e.title)}${e.kind === "action" ? ` <span class="chip c-mute">${esc(e.status)}</span>` : ""}${e.kind === "referral" && e.status ? ` <span class="chip c-mute">${esc(e.status === "owner_changed" ? "owner changed" : e.status)}</span>` : ""}${e.kind === "referral" && e.reason ? `<div class="small muted">${esc(e.reason)}</div>` : ""}</div>`).join("")}</div></div>
  </div></div>`;
  const addRow = (d = "", t = "", due = "") => $("#b-acts").insertAdjacentHTML("beforeend", `<div class="arow"><select>${depts.map((x) => `<option ${x === d ? "selected" : ""}>${x}</option>`).join("")}</select><input placeholder="Task" value="${esc(t)}"><input type="date" value="${due}"><button class="ghost sm" data-rmrow>×</button></div>`);
  if ($("#b-acts")) addRow();
  if ($("#b-add")) $("#b-add").onclick = () => addRow();
  const addMember = () => $("#b-mems").insertAdjacentHTML("beforeend", `<div class="arow"><input placeholder="Name (e.g. Dr. A. Rao)" aria-label="Member name"><select aria-label="Department">${depts.map((x) => `<option>${x}</option>`).join("")}</select><button class="ghost sm" data-rmrow>×</button></div>`);
  if ($("#b-mems")) addMember();
  if ($("#b-addm")) $("#b-addm").onclick = () => addMember();
  if ($("#b-save")) $("#b-save").onclick = async () => {
    const actions = $$("#b-acts .arow").map((r) => ({ department: r.children[0].value, task: r.children[1].value, due: r.children[2].value })).filter((a) => a.task);
    const members = $$("#b-mems .arow").map((r) => ({ name: r.children[0].value.trim(), department: r.children[1].value })).filter((m) => m.name);
    const body = { board_date: $("#b-date").value, decision_text: $("#b-text").value, recorded_by: $("#b-by").value, participants: $("#b-part").value, members,
      report_corrections_raised: $("#b-corr").value, divergent_opinions: $("#b-div").value, actions, next_review: $("#b-next").value,
      outcome_type: $("#b-outcome").value, deferred_reason: $("#b-deferred").value, referred_to: $("#b-referred").value, intent_as_recorded: $("#b-intent").value,
      trial_considered: $("#b-trial").value, consent_recorded: $("#b-consent").value, key_worker: $("#b-keyworker").value };
    $("#b-save").innerHTML = `<span class="spin"></span> Adjudicating...`;
    try { await api(`/cases/${S.caseId}/board-records`, { json: body }); } catch (e) { toast(e.message, 7000); $("#b-save").textContent = "Save record and run adjudication"; return; }
    S.data = await api("/cases/" + S.caseId); renderBoard(); toast("Tumour Board record saved and checked");
  };
  bindActions($("#tab-board"));
  bindDiscord($("#tab-board"));
  $$("[data-cmsave]", $("#tab-board")).forEach((x) => (x.onclick = async () => {
    const box = x.closest(".stagebox");
    const body = { patient_informed_date: $(".cm-date", box).value, informed_by: $(".cm-by", box).value, key_worker: $(".cm-kw", box).value, intent_as_recorded: $(".cm-intent", box).value,
      trial_considered: $(".cm-trial", box).value, consent_recorded: $(".cm-consent", box).value };
    try { await api(`/cases/${S.caseId}/board-records/${x.dataset.cmsave}/communication`, { json: body }); toast("Communication recorded"); S.data = await api("/cases/" + S.caseId); renderBoard(); }
    catch (e) { toast(e.message, 7000); }
  }));
  $$("[data-resolve]", $("#tab-board")).forEach((x) => (x.onclick = () => { const [rid, fid, kind] = x.dataset.resolve.split("|"); resolveFlag(rid, fid, kind); }));
  $$("[data-undores]", $("#tab-board")).forEach((x) => (x.onclick = async () => {
    try { await api(`/cases/${S.caseId}/confirmations/${x.dataset.undores}/undo`, { json: {} }); toast("Resolution undone (kept in the audit log); a correction is taken back as a new version"); await openCase(S.caseId, true); }
    catch (e) { toast(e.message, 7000); }
  }));
}

// ------------------------------------------------------------------ tab: audit
async function renderAudit() {
  const au = await api(`/cases/${S.caseId}/audit`); const ev = au.events.reverse(); const ch = au.chain || {};
  const llm = ev.filter((e) => e.kind === "llm_call");
  const chainChip = ch.ok ? `<span class="chip c-ok" title="Every event carries the hash of the previous one; the chain was recomputed and is intact">chain verified · ${ch.chained} linked${ch.unchained ? ` · ${ch.unchained} earlier` : ""}</span>` : `<span class="chip c-bad" title="An event does not match its hash: the file was changed outside the application">chain broken at event ${ch.first_broken}</span>`;
  $("#tab-audit").innerHTML = `<div class="card"><h3>Audit log <span class="muted small">${ev.length} events · ${llm.length} model calls · ${llm.reduce((a, e) => a + (e.completion_tokens || 0), 0)} tokens generated · ${chainChip}</span></h3>
    <div class="muted small" style="margin-bottom:8px">Append-only record of every AI call (model, purpose, time, prompt hash), every verification and guardrail decision, and every human action.</div>
    <table class="t"><thead><tr><th>Time</th><th>Event</th><th>Detail</th></tr></thead><tbody>
    ${ev.slice(0, 400).map((e) => { const { ts, kind, prev, hash, ...rest } = e; return `<tr><td class="small">${esc(ts.replace("T", " "))}</td><td><span class="chip ${/guardrail|error|unverified/.test(kind) ? "c-rev" : kind === "llm_call" ? "c-mute" : "c-info"}">${esc(kind)}</span></td><td class="small">${esc(JSON.stringify(rest)).slice(0, 300)}</td></tr>`; }).join("")}
    </tbody></table></div>`;
}

// ------------------------------------------------------------------ model and data cards
async function showCards() {
  const r = await api("/models");
  $("#modal-body").innerHTML = `<h2 style="color:#1f2933;margin-top:0">Model and data cards</h2>
    <p class="muted small">Every model and data asset used by the system ships with a published card: source, version, intended use, provenance, limitations.</p>
    ${r.cards.map((c) => `<div class="card"><h3>${esc(c.name)} <span>${(c.tags || []).map((t) => `<span class="chip ${/chin/i.test(t) ? "c-cn" : /non-medical/i.test(t) ? "c-nm" : "c-info"}">${esc(t)}</span>`).join(" ")}</span></h3>
      <div class="kv">${Object.entries(c.fields || {}).map(([k, v]) => `<div>${esc(k)}</div><div>${esc(v)}</div>`).join("")}</div></div>`).join("")}
    <div style="text-align:right;margin-top:12px"><button class="ghost" data-closemodal>Close</button></div>`;
  $("#modal").classList.remove("hidden");
}

// ------------------------------------------------------------------ agent skills (12 Oct): role definitions as SKILL.md files
async function showSkills(role) {
  const r = await api("/skills");
  const cur = r.skills.find((x) => x.role === role) || r.skills[0];
  const act = cur.active || {};
  $("#modal-body").innerHTML = `<h2 style="color:#1f2933;margin-top:0">Agent skills</h2>
    <p class="muted small">${esc(r.note)} ${r.can_edit ? "Admins edit a skill here; the edit is saved as the hospital's version, audited, and can be reset to the default." : "Editing is for Tumour Board admins."}</p>
    <div class="form"><label>Specialty support agent</label><select id="sk-role">${r.skills.map((x) => `<option value="${esc(x.role)}" ${x.role === cur.role ? "selected" : ""}>${esc((x.active || {}).label || x.role)}${x.hospital_edit ? " (hospital edit)" : ""}</option>`).join("")}</select></div>
    <div class="kv small" style="margin:10px 0">
      <div>In use</div><div>${act.origin === "hospital" ? '<span class="chip c-info">hospital edit</span>' : '<span class="chip c-mute">default</span>'} ${esc(act.sha || "")}${cur.problem ? ` <span class="chip c-bad">hospital edit ignored</span> <span class="muted">${esc(cur.problem)}</span>` : ""}</div>
      <div>Department</div><div>${esc(act.department || "")}</div>
      <div>Reads first</div><div>${(act.doc_types || []).map((t) => `<span class="chip c-mute">${esc(t)}</span>`).join(" ")}</div>
      <div>Focus</div><div>${(act.focus || []).map(esc).join("; ")}</div>
      <div>Guideline query</div><div>${esc(act.guideline_query || "")}</div>
    </div>
    <div class="form"><label>SKILL.md ${r.can_edit ? "(edit, then Validate and Save)" : "(read only)"}</label>
      <textarea id="sk-text" style="min-height:320px;font-family:var(--mono);font-size:12.5px" ${r.can_edit ? "" : "readonly"}>${esc(cur.text)}</textarea></div>
    <div id="sk-msg" class="small" style="margin-top:6px"></div>
    <div class="muted small" style="margin-top:8px">Never in a skill file: the tools, the quote rule, the scope rules (no diagnosis, staging, treatment or image interpretation). Those are in code and apply to every skill.</div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px;flex-wrap:wrap">
      ${r.can_edit ? `<button class="ghost" id="sk-default">Show default</button><button class="ghost" id="sk-reset" ${cur.hospital_edit ? "" : "disabled"}>Reset to default</button><button class="ghost" id="sk-validate">Validate</button><button class="primary" id="sk-save">Save as hospital version</button>` : ""}
      <button class="ghost" data-closemodal>Close</button></div>`;
  $("#modal").classList.remove("hidden");
  $("#sk-role").onchange = () => showSkills($("#sk-role").value);
  const msg = (t, ok) => { $("#sk-msg").innerHTML = `<span class="chip ${ok ? "c-ok" : "c-bad"}">${ok ? "valid" : "not valid"}</span> ${esc(t)}`; };
  if (!r.can_edit) return;
  $("#sk-default").onclick = () => { $("#sk-text").value = cur.default_text; msg("default text loaded (not saved)", true); };
  $("#sk-validate").onclick = async () => {
    const v = await api("/skills/validate", { json: { text: $("#sk-text").value } });
    msg(v.ok ? `${v.skill.label} · ${v.skill.department} · reads ${v.skill.doc_types.join(", ")} · focus ${v.skill.focus.length} items` : v.error, v.ok);
  };
  $("#sk-save").onclick = async () => {
    try { const v = await api(`/skills/${cur.role}`, { method: "PUT", json: { text: $("#sk-text").value } }); toast(`Skill saved for ${v.skill.label} (hospital version)`); S.roles = null; showSkills(cur.role); }
    catch (e) { msg(e.message, false); }
  };
  $("#sk-reset").onclick = async () => {
    if (!confirm("Remove the hospital edit and use the default skill again?")) return;
    await api(`/skills/${cur.role}/reset`, { json: {} }); toast("Skill reset to default"); S.roles = null; showSkills(cur.role);
  };
}

// ------------------------------------------------------------------ new case: from the hospital system (V2 item 3.2) or entered manually (V1)
async function newCase() {
  let his = null;
  try { his = await api("/his"); } catch (e) { his = null; }
  const hisOn = !!(his?.status?.ok && his.can_create !== false);
  const way = hisOn && ((his.treating_departments || []).length || S.me?.admin) ? "his" : "manual";
  $("#modal-body").innerHTML = `<h2 style="color:#1f2933;margin-top:0">New Tumour Board Case File</h2>
    ${hisOn ? `<div class="seg" role="tablist" aria-label="How to start the Case File"><button role="tab" data-way="his">From the hospital system</button><button role="tab" data-way="manual">Enter the patient manually</button></div>`
      : his ? `<div class="small muted" style="margin-bottom:6px">The hospital system does not answer (${esc(his.status?.error || "not configured")}): enter the patient manually.</div>` : ""}
    <div id="nc-his"></div><div id="nc-manual"></div>`;
  $("#modal").classList.remove("hidden");
  const setWay = (w) => { $$("[data-way]").forEach((b) => { b.classList.toggle("on", b.dataset.way === w); b.setAttribute("aria-selected", b.dataset.way === w ? "true" : "false"); });
    $("#nc-his").classList.toggle("hidden", w !== "his"); $("#nc-manual").classList.toggle("hidden", w !== "manual"); };
  $$("[data-way]").forEach((b) => (b.onclick = () => setWay(b.dataset.way)));
  if (hisOn) newCaseHIS(his);
  newCaseManual();
  setWay(way);
}
const protoOpts = () => (S.protocols || []).map((p) => `<option value="${esc(p.id)}">${esc(p.label)} (v${esc(p.version)})</option>`).join("");
const settingOpts = (pid) => `<option value="">Not chosen yet</option>` + ((S.protocols || []).find((x) => x.id === pid)?.settings || []).map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join("");
const levelOpts = () => `<option value="essential">Essential</option><option value="optimal">Optimal</option>`;
function newCaseManual() {
  $("#nc-manual").innerHTML = `<div class="form">
    <label for="n-id">Case File ID</label><input id="n-id" placeholder="e.g. TB-2026-0142">
    <label for="n-name">Patient name</label><input id="n-name"><label for="n-mrn">UHID / MRN</label><input id="n-mrn"><label for="n-agesex">Age / Sex</label><input id="n-agesex" placeholder="62 Y / M">
    <label for="n-prot">Protocol</label><select id="n-prot">${protoOpts()}</select>
    <label for="n-setting">NCG setting (as recorded in the signed reports, chosen by the clinician)</label><select id="n-setting"></select>
    <label for="n-level">Hospital level (NCG tiers)</label><select id="n-level">${levelOpts()}</select>
    <label for="n-date">Board date</label><input type="date" id="n-date">
    <div style="margin-top:14px;display:flex;gap:8px;justify-content:flex-end"><button class="ghost" data-closemodal>Cancel</button><button class="primary" id="n-go">Create</button></div></div>`;
  const fill = () => ($("#n-setting").innerHTML = settingOpts($("#n-prot").value));
  fill(); $("#n-prot").onchange = fill; $("#n-level").value = S.org?.hospital?.level || "essential";
  $("#n-go").onclick = async () => {
    try {
      const c = await api("/cases", { json: { case_id: $("#n-id").value.trim(), protocol: $("#n-prot").value, board_date: $("#n-date").value, setting: $("#n-setting").value, hospital_level: $("#n-level").value,
        patient: { name: $("#n-name").value, mrn: $("#n-mrn").value, agesex: $("#n-agesex").value } } });
      $("#modal").classList.add("hidden"); S.tab = "ready"; await openCase(c.case_id);
    } catch (e) { toast(e.message, 7000); }
  };
}
// ---- HIS helpers (V2 items 3.2 to 3.6): dates DD/MM/YYYY, registrations, fetch windows, order stages
const dmyd = (s) => dmy(String(s || "").slice(0, 10));
const dmyt = (s) => (s ? dmyd(s) + (String(s).length > 15 ? " " + String(s).slice(11, 16) : "") : "");
const REGKIND = { permanent: "permanent registration", temporary: "temporary registration", duplicate: "possible duplicate registration" };
const regKind = (k) => REGKIND[k || "permanent"] || `${k} registration`;
const ID_KIND = { uhid: "UHID", mrn: "MRN", cr_no: "CR No.", ip_no: "IP No.", op_no: "OP No.", reg_no: "Reg. No.", hospital_no: "Hospital No.", abha: "ABHA", pmjay: "PM-JAY ID" };
const ageSex = (p) => [p?.age != null && p.age !== "" ? `${p.age} Y` : "", p?.sex || ""].filter(Boolean).join(" / ");
const winLabel = (w) => (!w ? "" : w.all ? "all records" : w.from ? `records from ${dmy(w.from)}` : `last ${w.months || 12} months`);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`;
const encCount = (encs) => `${plural(encs.filter((e) => e.kind === "OP").length, "OP visit")}, ${plural(encs.filter((e) => e.kind === "IP").length, "IP admission")}`;
const stageText = (o) => o.stage === "scheduled" ? `scheduled for ${dmyt(o.scheduled_for) || "a date not given"}`
  : o.stage === "sample_collected" ? `sample collected${o.specimen?.collected || o.collected ? " on " + dmyt(o.specimen?.collected || o.collected) : ""}` : o.stage === "cancelled" ? "cancelled" : "ordered";
const wardText = (w) => `${w.ward || "ward not named"}${w.bed ? " bed " + w.bed : ""}${w.from ? " from " + dmyt(w.from) : ""}${w.to ? " to " + dmyt(w.to) : ""}${w.reason ? " (" + w.reason + ")" : ""}`;
function lookupHTML(r) {
  if (!r.found) return `<div class="lookbox"><b>Not found.</b> No registration in ${esc(r.his || "the hospital system")} matches ${esc(r.identifier)}. Check the number, or enter the patient manually.</div>`;
  const p = r.patient || {}, m = p.matched_on || {};
  return `<div class="lookbox"><div><b>${esc(p.name)}</b> <span class="muted">${esc(ageSex(p))}</span></div>
    <div class="kv small" style="margin-top:4px"><div>UHID</div><div><span class="mono">${esc(p.uhid)}</span> (${esc(regKind(p.registration_kind))})${m.kind && m.kind !== "uhid" ? ` · found by ${esc(ID_KIND[m.kind] || m.kind)} <span class="mono">${esc(m.value)}</span>` : ""}</div>
      ${p.abha ? `<div>ABHA number</div><div class="mono">${esc(p.abha)}</div>` : ""}${p.abha_address ? `<div>ABHA address</div><div class="mono">${esc(p.abha_address)}</div>` : ""}${p.pmjay_id ? `<div>PM-JAY ID</div><div class="mono">${esc(p.pmjay_id)}</div>` : ""}
      <div>Encounters</div><div>${encCount(r.encounters || [])}</div>
      <div>Records</div><div>${plural(r.reports || 0, "record")} in the window (${esc(winLabel(r.window))}${r.window_start ? ", dated from " + dmy(r.window_start) : ""}), ${r.older || 0} older</div></div>
    ${(r.similar || []).length ? `<div class="banner warn small" style="margin-bottom:0"><b>Possible duplicate or temporary registration: link it after creating; never merged automatically.</b>
      ${r.similar.map((s) => `<div class="row"><span>${esc(s.name || "name not given")} · <span class="mono">${esc(s.uhid)}</span> (${esc(regKind(s.registration_kind))})${ageSex(s) ? " · " + esc(ageSex(s)) : ""}${s.registered_on ? " · registered " + dmyd(s.registered_on) : ""}</span></div>`).join("")}</div>` : ""}</div>`;
}
function newCaseHIS(his) {
  const treating = his.treating_departments || [];
  const depts = treating.length ? treating : (S.org?.departments || []).filter((d) => d.group === "treating");
  const pickDept = treating.length > 1 || !!S.me?.admin || !!S.me?.coordinator;
  const dw = his.default_window || { months: 12 };
  const months = [...new Set([...(his.window_months || [6, 12, 24]), ...(dw.months ? [+dw.months] : [])])].sort((a, b) => a - b);
  $("#nc-his").innerHTML = `<div class="form">
    <label for="h-id">Patient identifier in ${esc(his.settings?.label || "the hospital system")}</label>
    <div class="inline-input"><input id="h-id" placeholder="UHID, IP No. or OP No." autocomplete="off"><button class="ghost" id="h-look">Look up</button></div>
    <div id="h-res"></div>
    <div class="grid2f">
      <div><label for="h-prot">Protocol</label><select id="h-prot">${protoOpts()}</select></div>
      <div><label for="h-setting">NCG setting (as recorded in the signed reports, chosen by the clinician)</label><select id="h-setting"></select></div>
      <div><label for="h-level">Hospital level (NCG tiers)</label><select id="h-level">${levelOpts()}</select></div>
      <div><label for="h-win">Fetch window</label><select id="h-win">${months.map((m) => `<option value="${m}">Last ${m} months</option>`).join("")}<option value="all">All records</option><option value="from">From a date</option></select>
        <input type="date" id="h-from" class="hidden" aria-label="Fetch records dated from" style="margin-top:6px"></div>
      <div><label for="h-dept">Owning treating department</label>${pickDept ? `<select id="h-dept"><option value="">Choose the department</option>${depts.map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("")}</select>`
        : `<input id="h-dept" readonly value="${esc(depts[0]?.name || "none")}" data-id="${esc(depts[0]?.id || "")}">`}</div>
      <div><label for="h-date">Board date</label><input type="date" id="h-date"></div></div>
    <div class="small muted" style="margin-top:10px">Every report of every OP visit and IP admission in the window is fetched read-only (nothing is written to the hospital system), then read, matched to the patient and checked like every record. Older records can be fetched later.</div>
    <div style="margin-top:14px;display:flex;gap:8px;justify-content:flex-end"><button class="ghost" data-closemodal>Cancel</button><button class="primary" id="h-go">Create</button></div></div>`;
  const fill = () => ($("#h-setting").innerHTML = settingOpts($("#h-prot").value));
  fill(); $("#h-prot").onchange = fill; $("#h-level").value = S.org?.hospital?.level || "essential";
  $("#h-win").value = dw.all ? "all" : dw.from ? "from" : String(dw.months || 12);
  if (dw.from) { $("#h-from").value = dw.from; $("#h-from").classList.remove("hidden"); }
  const win = () => { const v = $("#h-win").value; return v === "all" ? { all: true } : v === "from" ? { from: $("#h-from").value } : { months: +v }; };
  let looked = "";
  const look = async () => {
    const id = $("#h-id").value.trim(); if (!id) { toast("Enter a UHID, IP No. or OP No."); return; }
    const w = win(); if (w.from === "") { toast("Choose the date to fetch from"); return; }
    const q = new URLSearchParams({ identifier: id, ...(w.all ? { all: "1" } : w.from ? { from_date: w.from } : { months: String(w.months) }) });
    $("#h-res").innerHTML = `<div class="small" style="margin-top:6px"><span class="spin"></span> Asking the hospital system...</div>`;
    try { $("#h-res").innerHTML = lookupHTML(await api("/his/lookup?" + q)); looked = id; }
    catch (e) { $("#h-res").innerHTML = ""; toast(e.message, 8000); }
  };
  $("#h-look").onclick = look;
  $("#h-id").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); look(); } };
  $("#h-win").onchange = () => { $("#h-from").classList.toggle("hidden", $("#h-win").value !== "from"); if (looked && $("#h-win").value !== "from") look(); };
  $("#h-from").onchange = () => { if (looked && $("#h-from").value) look(); };
  $("#h-go").onclick = async () => {
    const identifier = $("#h-id").value.trim(); if (!identifier) { toast("Enter a UHID, IP No. or OP No."); return; }
    const w = win(); if (w.from === "") { toast("Choose the date to fetch from"); return; }
    const department = $("#h-dept").dataset.id || $("#h-dept").value;
    if (pickDept && !department) { toast("Choose the treating department that owns this Case File"); return; }
    const btn = $("#h-go"); btn.disabled = true; btn.innerHTML = `<span class="spin"></span> Creating...`;
    try {
      const r = await api("/cases/from-his", { json: { identifier, protocol: $("#h-prot").value, setting: $("#h-setting").value, hospital_level: $("#h-level").value, board_date: $("#h-date").value, window: w, ...(department ? { department } : {}) } });
      $("#modal").classList.add("hidden"); S.tab = "ready"; await openCase(r.case.case_id);
      toast(`Case File ${r.case.case_id} created from ${his.settings?.label || "the hospital system"}: ${plural(r.total, "record")} fetched, now being read and checked`, 6000);
      watchJob(r.job);
    } catch (e) { toast(e.message, 8000); btn.disabled = false; btn.textContent = "Create"; }
  };
}


// ------------------------------------------------------------------ hospital, departments, users (admin) · V1 item 2.1, V2 item 2.3
const deptName = (id) => (S.org?.departments || []).find((d) => d.id === id)?.name || id || "";
async function loadOrg() {
  try { S.org = await api("/org"); S.me = S.org.me; } catch (e) { S.org = null; S.me = null; }
  $("#btn-org").classList.toggle("hidden", !(S.me?.admin || S.me?.root_admin));  // V2 2.2: the root admin manages the organisation
  $("#btn-mydept").classList.toggle("hidden", !(S.org?.admin_departments || []).length);  // V2 2.3: department admins (and admins)
  $("#btn-sessions").classList.toggle("hidden", !(S.me?.known || S.me?.admin));  // patient data only for placed accounts (read_case)
  $("#btn-connectors").classList.toggle("hidden", !S.me?.admin);
  $("#btn-dashboard").classList.toggle("hidden", !(S.me?.admin || S.me?.coordinator));
  $("#btn-new").classList.toggle("hidden", !meCan("create_case"));
}
// ------------------------------------------------------------------ Organisation (root admin) and My department (department admin) · V2 item 2.3
// Each card saves only its own edits on top of the organisation as last loaded (PUT /org takes the whole file), then the page reloads.
const ROLE = { member: "Doctor", head: "Head" };
const slugOf = (t) => String(t || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
const tscroll = (html) => `<div class="tscroll">${html}</div>`;
const deptOpts = (sel = "") => (S.orgPage?.o.departments || S.org?.departments || []).map((d) => `<option value="${esc(d.id)}" ${d.id === sel ? "selected" : ""}>${esc(d.name)}</option>`).join("");
function rolesList(v, root) {  // [[chip class, text]] for a placement {departments, admin_of, coordinator}
  v = v || {};
  return [...(root ? [["c-info", "Root admin"]] : []), ...(v.coordinator ? [["c-info", "MDT Coordinator"]] : []),
    ...(v.admin_of || []).map((d) => ["c-info", "Admin of " + deptName(d)]),
    ...Object.entries(v.departments || {}).map(([d, r]) => ["c-mute", `${ROLE[r] || r} of ${deptName(d)}`])];
}
const rolesText = (v, root) => rolesList(v, root).map((x) => x[1]).join(", ") || "no roles";
function orgPayload(edit = {}) {
  // each card saves only what it edited; the server keeps the other keys and refuses a stale edit (409) by the version token
  return { ...edit, expected_version: S.orgPage.o.version };
}
async function saveOrg(edit, what) {
  try { await api("/org", { method: "PUT", json: orgPayload(edit) }); toast(what + " saved"); await loadOrg(); await showOrgPage(); if (S.caseId && !$("#case").classList.contains("hidden")) openCase(S.caseId, true); }
  catch (e) { toast(e.message, 7000); }
}

async function showOrgPage() {
  stopRoomPoll(); S.roomId = null; showOnly("orgpage");
  const box = $("#orgpage");
  if (!S.orgPage) box.innerHTML = `<div class="card"><h3>Organisation</h3><div class="muted small"><span class="spin"></span> Loading...</div></div>`;
  let o, acc, aud;
  try { [o, acc, aud] = await Promise.all([api("/org"), api("/org/accounts"), api("/org/audit?limit=50").catch(() => ({ events: [] }))]); }
  catch (e) { box.innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
  S.orgPage = { o, acc, users: JSON.parse(JSON.stringify(o.users || {})), admins: [...(o.admins || [])], editing: null, placed: [] };
  const h = o.hospital || {};
  const deptRow = (d, isNew) => `<tr class="orow" data-id="${esc(d.id)}" ${isNew ? "data-new" : ""}><td><input class="o-name" value="${esc(d.name)}" placeholder="Name used in the hospital" aria-label="Department name"></td>
    <td><select class="o-group" aria-label="Group"><option value="treating" ${d.group !== "supporting" ? "selected" : ""}>Treating</option><option value="supporting" ${d.group === "supporting" ? "selected" : ""}>Supporting</option></select></td>
    <td><input class="o-alias" value="${esc((d.aliases || []).join(", "))}" placeholder="Other names, comma separated" aria-label="Also known as"></td>
    <td><input class="o-email" value="${esc(d.email || "")}" placeholder="department@hospital.example" aria-label="Email"></td>
    <td class="small muted o-id">${esc(d.id) || "(from the name)"}</td><td><button class="ghost sm" data-rmrow title="Remove department" aria-label="Remove department">×</button></td></tr>`;
  box.innerHTML = `<div class="case-head"><div><div class="eyebrow">Root admin</div><h1>Organisation</h1>
      <div class="muted">One hospital: its settings, departments, the Tumour Board accounts and their roles. Logins are plain Vaidyx accounts; a Vaidyx admin is never created or placed here. Every saved change is recorded in the audit below.</div></div></div>
    <div class="card" id="o-hospital"><h3>Hospital settings</h3>
      <div class="form"><div class="grid3">
        <div><label for="o-hname">Hospital name</label><input id="o-hname" value="${esc(h.name || "")}"></div>
        <div><label for="o-level">NCG level</label><select id="o-level"><option value="essential" ${h.level !== "optimal" ? "selected" : ""}>Essential</option><option value="optimal" ${h.level === "optimal" ? "selected" : ""}>Optimal</option></select></div>
        <div><label for="o-type">Hospital type</label><select id="o-type"><option value="" ${!h.type ? "selected" : ""}>Not set</option><option value="public" ${h.type === "public" ? "selected" : ""}>Public</option><option value="private" ${h.type === "private" ? "selected" : ""}>Private</option></select></div></div>
        <div class="grid3">
          <div><label for="o-fetch">HIS fetch window (months)</label><input id="o-fetch" type="number" min="1" max="120" step="1" value="${esc(h.fetch_window_months ?? 12)}"></div>
          <div class="checkrow"><label class="chk"><input type="checkbox" id="o-pmjay" ${h.pmjay_empanelled !== false ? "checked" : ""}> PM-JAY empanelled</label><div class="small muted">The PM-JAY board composition flag (HBP 2.2) applies only to an empanelled hospital</div></div><div></div></div>
        <h4 class="subh">The board</h4>
        ${BOARD_LISTS.map(([k, label, help]) => `<div class="deplist-wrap"><label>${esc(label)}</label><div class="small muted">${esc(help)}</div><div class="deplist" id="o-${k}" data-key="${k}"></div></div>`).join("")}</div>
      <div class="small muted" style="margin-top:6px">The NCG level decides which tier of the work-up applies. The fetch window is how far back the hospital systems are read for a patient.</div>
      <div class="actions-row"><button class="primary sm" id="o-save-h">Save hospital settings</button></div></div>
    <div id="o-his"></div>
    <div class="card"><h3>Departments <button class="ghost sm" id="o-adddept">+ Department</button></h3>
      <div class="muted small" style="margin-bottom:6px">Treating departments own Case Files and send requests; supporting departments receive and answer them. The email is used for the mail draft of a request.</div>
      ${tscroll(`<table class="t edit"><thead><tr><th>Name</th><th>Group</th><th>Also known as</th><th>Email</th><th>Id</th><th></th></tr></thead><tbody id="o-depts">${(o.departments || []).map((d) => deptRow(d)).join("")}</tbody></table>`)}
      <div class="actions-row"><button class="primary sm" id="o-save-d">Save departments</button></div></div>
    <div id="o-routes"></div>
    <div class="card" id="o-acc"><h3>Accounts and roles</h3>
      <div class="muted small" style="margin-bottom:6px">Doctor of a treating department: creates Case Files from a UHID, uploads outside reports, confirms, waives, sends requests. Doctor of a supporting department: sees its inbox and answers requests. Head: the same, named as the department's head. Department admin: manages the doctor logins of the department, no clinical rights. MDT Coordinator: lists Case Files, runs matching and board sessions, records decisions. Root admin: this page.</div>
      ${tscroll(`<table class="t"><thead><tr><th>Login</th><th>Display name</th><th>Roles</th><th>Status</th><th></th></tr></thead><tbody id="o-users"></tbody></table>`)}
      <div id="o-ued"></div>
      <div class="actions-row"><span class="small muted" id="o-users-dirty"></span><button class="primary sm" id="o-save-u">Save accounts and roles</button></div>
      <h4 style="margin:16px 0 4px">New login</h4>
      <div class="form" id="o-new"><div class="grid3">
        <div><label for="na-user">Login name</label><input id="na-user" autocomplete="off" placeholder="lower-case, e.g. dr.rao"></div>
        <div><label for="na-pass">Password</label><input id="na-pass" type="password" autocomplete="new-password" placeholder="at least 8 characters"></div>
        <div><label for="na-name">Display name</label><input id="na-name" autocomplete="off" placeholder="e.g. Dr. A. Rao"></div></div>
        <div class="grid3">
          <div><label for="na-admof">Department admin of</label><select id="na-admof" multiple size="4">${deptOpts()}</select></div>
          <div><label>Doctor or Head of</label><div class="inline"><select id="na-dept" aria-label="Department">${deptOpts()}</select><select id="na-role" aria-label="Role"><option value="doctor">Doctor</option><option value="head">Head</option></select><button class="ghost sm" id="na-add">Add</button></div><div class="u-depts" id="na-placed"></div></div>
          <div><label>Other roles</label><label class="chk"><input type="checkbox" id="na-coord"> MDT Coordinator</label><label class="chk"><input type="checkbox" id="na-root"> Root admin</label></div></div></div>
      <div class="small muted" style="margin-top:6px">An existing plain login is placed without a password. ${esc(acc.reset_note || o.reset_note || "")}</div>
      <div class="actions-row"><button class="primary sm" id="na-create">Create login</button></div></div>
    <div class="card"><h3>Audit <span class="muted small">last 50 changes, newest first</span></h3>
      ${(aud.events || []).length ? tscroll(`<table class="t compact"><thead><tr><th>Time</th><th>By</th><th>Change</th><th>Details</th></tr></thead><tbody>${aud.events.map((e) => `<tr><td class="small nowrap">${esc((e.ts || "").replace("T", " ").slice(0, 16))}</td><td class="small">${esc(e.by)}</td><td class="small">${esc(AUDIT_KIND[e.kind] || e.kind)}</td><td class="small">${esc(auditText(e))}</td></tr>`).join("")}</tbody></table>`) : '<div class="muted small">No changes recorded yet.</div>'}</div>`;
  renderAccounts();
  S.orgPage.lists = Object.fromEntries(BOARD_LISTS.map(([k]) => [k, [...(h[k] || (k === "board_heads" ? DEFAULT_HEADS : []))]]));
  BOARD_LISTS.forEach(([k]) => renderDepList(k));
  $("#o-hospital").addEventListener("click", (e) => { const x = e.target.closest("[data-rmdl]"); if (x) { const k = x.closest(".deplist").dataset.key; S.orgPage.lists[k] = S.orgPage.lists[k].filter((d) => d !== x.dataset.rmdl); renderDepList(k); } });
  $("#o-hospital").addEventListener("change", (e) => { const x = e.target.closest("select[data-adddl]"); if (x && x.value) { const k = x.dataset.adddl; S.orgPage.lists[k] = [...S.orgPage.lists[k], x.value]; renderDepList(k); } });
  $("#o-save-h").onclick = () => {
    const n = Number($("#o-fetch").value);
    if (!Number.isInteger(n) || n < 1 || n > 120) { toast("The HIS fetch window must be 1 to 120 months"); return; }
    if (!S.orgPage.lists.board_heads.length) { toast("The board needs at least one head"); return; }
    saveOrg({ hospital: { ...h, name: $("#o-hname").value.trim(), level: $("#o-level").value, type: $("#o-type").value, pmjay_empanelled: $("#o-pmjay").checked, fetch_window_months: n, ...S.orgPage.lists } }, "Hospital settings");
  };
  $("#o-adddept").onclick = () => { $("#o-depts").insertAdjacentHTML("beforeend", deptRow({ id: "", name: "", group: "treating", aliases: [], email: "" }, true)); $("#o-depts tr:last-child .o-name").focus(); };
  $("#o-depts").addEventListener("input", (e) => { const tr = e.target.closest("tr[data-new]"); if (tr && e.target.matches(".o-name")) $(".o-id", tr).textContent = slugOf(e.target.value) || "(from the name)"; });
  $("#o-depts").addEventListener("click", (e) => { if (e.target.closest("[data-rmrow]")) e.target.closest("tr").remove(); });
  $("#o-save-d").onclick = () => {
    const departments = $$("#o-depts tr.orow").map((tr) => ({ ...((o.departments || []).find((d) => d.id === tr.dataset.id) || {}),
      id: tr.hasAttribute("data-new") ? slugOf($(".o-name", tr).value) : tr.dataset.id, name: $(".o-name", tr).value.trim(), group: $(".o-group", tr).value,
      email: $(".o-email", tr).value.trim(), aliases: $(".o-alias", tr).value.split(",").map((x) => x.trim()).filter(Boolean) }));
    if (departments.some((d) => !d.name)) { toast("Every department needs a name"); return; }
    saveOrg({ departments }, "Departments");
  };
  $("#o-acc").addEventListener("click", accountsClick);
  $("#o-ued").addEventListener("change", accountsChange);
  $("#o-ued").addEventListener("input", (e) => { const ed = e.target.closest("[data-ed]"); if (ed && e.target.matches(".ue-name")) { userOf(ed.dataset.ed).display_name = e.target.value; dirty(); } });
  $("#o-save-u").onclick = () => {
    const P = S.orgPage, users = {};
    Object.entries(P.users).forEach(([u, v]) => { if (Object.keys(v.departments || {}).length || (v.admin_of || []).length || v.coordinator || v.disabled || P.admins.includes(u)) users[u] = v; });
    P.admins.forEach((u) => { if (!users[u]) users[u] = P.users[u] || { departments: {}, admin_of: [], coordinator: false, display_name: "", disabled: false }; });
    saveOrg({ users, admins: P.admins }, "Accounts and roles");
  };
  $("#na-add").onclick = () => { const d = $("#na-dept").value, r = $("#na-role").value; S.orgPage.placed = [...S.orgPage.placed.filter((x) => x[0] !== d), [d, r]]; renderPlaced(); };
  $("#na-placed").addEventListener("click", (e) => { const x = e.target.closest("[data-rmplace]"); if (x) { S.orgPage.placed = S.orgPage.placed.filter((p) => p[0] !== x.dataset.rmplace); renderPlaced(); } });
  $("#na-create").onclick = async () => {
    const username = $("#na-user").value.trim(), password = $("#na-pass").value;
    if (!username) { toast("Login name is required"); return; }
    const body = { username, display_name: $("#na-name").value.trim(), coordinator: $("#na-coord").checked, root_admin: $("#na-root").checked,
      admin_of: [...$("#na-admof").selectedOptions].map((x) => x.value), departments: Object.fromEntries(S.orgPage.placed) };
    if (password) body.password = password;
    $("#na-pass").value = "";
    try { const r = await api("/org/accounts", { json: body }); toast(r.created ? `Login ${r.username} created with its roles` : `Existing login ${r.username} given its roles`); await loadOrg(); await showOrgPage(); }
    catch (e) { toast(e.message, 7000); }
  };
  renderRoutes();  // V2 item 2.4: the routing table (loaded on its own, saved on its own)
  renderHISSettings();  // V2 item 3.1: the hospital information system connection (loaded and saved on its own)
}
// the board's lists of departments (V2 items 6.1 / 6.2 / 6.4): chips in the order chosen, a select adds one; saved with the hospital settings
const DEFAULT_HEADS = ["radiology", "medical_oncology", "surgical_oncology", "pathology"];
const BOARD_LISTS = [["board_heads", "Board heads", "Shown first on every attendance sheet, in this order. A head not recorded present has its AI support agent stand in (role-specific support, never a member)."],
  ["board_attendance", "Also on the attendance sheet", "Departments listed on every session's sheet besides the heads, Radiation Oncology and Nuclear Medicine (on demand) and the owners of the Case Files on the agenda."],
  ["surgical_departments", "Surgical departments", "A surgeon from the Case File's own one fills the surgical seat."],
  ["pmjay_surgical_oncology", "Counted as the Surgical Oncologist for PM-JAY HBP 2.2", "A surgeon from another surgical department fills the seat with a 'check PM-JAY requirement' note."]];
function renderDepList(k) {
  const box = $("#o-" + k), v = S.orgPage.lists[k], rest = (S.orgPage.o.departments || []).filter((d) => !v.includes(d.id));
  box.innerHTML = `${v.map((d, i) => `<span class="chip c-lvl">${k === "board_heads" ? `${i + 1}. ` : ""}${esc(deptName(d))} <button class="x" data-rmdl="${esc(d)}" aria-label="Remove ${esc(deptName(d))}">×</button></span>`).join("") || `<span class="small muted">None</span>`}
    <select data-adddl="${k}" aria-label="Add a department"><option value="">Add a department</option>${rest.map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("")}</select>`;
}
// ------------------------------------------------------------------ HIS connection (root admin) · V2 item 3.1
async function renderHISSettings() {
  const box = $("#o-his"); if (!box) return;
  box.innerHTML = `<div class="card"><h3>HIS connection</h3><div class="muted small"><span class="spin"></span> Asking the hospital system...</div></div>`;
  let r;
  try { r = await api("/his"); } catch (e) { box.innerHTML = `<div class="card"><h3>HIS connection</h3><div class="muted small">${esc(e.message)}</div></div>`; return; }
  const s = r.settings || {}, st = r.status || {};
  box.innerHTML = `<div class="card" id="o-his-card"><h3>HIS connection <span>${st.ok ? `<span class="chip c-ok">Answers</span>` : `<span class="chip c-bad">Not answering</span>`}</span></h3>
    <div class="small" style="margin-bottom:6px">${st.ok ? `Answers: <b>${esc(st.name || s.label || "")}</b>${st.fhir_version ? `, FHIR ${esc(st.fhir_version)}` : ""}${st.token_ok === false ? ` <span class="chip c-bad">token refused</span>` : ""}` : `<span class="muted">${esc(st.error || "No answer")}</span>`}</div>
    <div class="muted small" style="margin-bottom:6px">The hospital information system Case Files are created from (read-only: nothing is written back). The token is stored on the server and never shown; leave it blank to keep the saved one.</div>
    <div class="form"><div class="grid2f">
      <div><label for="hs-label">Label</label><input id="hs-label" value="${esc(s.label || "")}" ${r.can_manage ? "" : "disabled"}></div>
      <div><label for="hs-url">URL</label><input id="hs-url" value="${esc(s.url || "")}" placeholder="http://127.0.0.1:7130" ${r.can_manage ? "" : "disabled"}></div>
      <div><label for="hs-token">Token</label><input id="hs-token" type="password" autocomplete="new-password" value="" placeholder="${s.has_token ? "token set (blank keeps it)" : "bearer token"}" ${r.can_manage ? "" : "disabled"}></div>
      <div><label for="hs-pacs">PACS (image viewer) URL</label><input id="hs-pacs" value="${esc(s.pacs_url || "")}" placeholder="http://127.0.0.1:8042" ${r.can_manage ? "" : "disabled"}><div class="small muted">The app forwards the image viewer to it; the browser never goes there. Loopback or an allowed host.</div></div>
      <div><label>Token file</label><div class="small muted" style="padding:6px 0">${s.token_file ? `set on the server${typeof s.token_file === "string" ? ` (<span class="mono">${esc(s.token_file)}</span>)` : ""}; a change of host drops it` : "none (the token above is used)"}</div></div></div>
      <label class="chk"><input type="checkbox" id="hs-on" ${s.enabled ? "checked" : ""} ${r.can_manage ? "" : "disabled"}> Enabled</label></div>
    <div class="small muted">${s.has_token ? "Token set." : "No token set."} Kind: ${esc(s.kind || "fhir")}.</div>
    ${r.can_manage ? `<div class="actions-row"><button class="primary sm" id="hs-save">Save HIS connection</button></div>` : ""}</div>`;
  if ($("#hs-save")) $("#hs-save").onclick = async () => {
    const body = { kind: s.kind || "fhir", connector: s.connector || "", label: $("#hs-label").value.trim(), url: $("#hs-url").value.trim(), token: $("#hs-token").value, enabled: $("#hs-on").checked, pacs_url: $("#hs-pacs").value.trim() };  // the token file is never sent: it stays what the server holds (review S2)
    $("#hs-token").value = "";
    try { await api("/his", { method: "PUT", json: body }); toast("HIS connection saved"); renderHISSettings(); }
    catch (e) { toast(e.message, 8000); }
  };
}
// ------------------------------------------------------------------ routing map: which department produces each protocol record (V2 item 2.4)
async function renderRoutes() {
  const box = $("#o-routes"); if (!box) return;
  box.innerHTML = `<div class="card"><h3>Routes: who produces each record</h3><div class="muted small"><span class="spin"></span> Loading...</div></div>`;
  let r;
  try { r = await api("/org/routes"); } catch (e) { box.innerHTML = `<div class="card"><h3>Routes</h3><div class="muted small">${esc(e.message)}</div></div>`; return; }
  const targets = r.targets || [];
  const byProto = {}; (r.routes || []).forEach((x) => (byProto[x.protocol] = byProto[x.protocol] || { label: x.protocol_label, rows: [] }).rows.push(x));
  const opt = (x) => {
    const cur = x.override || "";
    const dflt = x.default === "owner" || x.default === "coordinator" ? x.default : x.default_department;
    return `<select class="rt-sel" data-key="${esc(x.protocol + "." + x.record)}"><option value="" ${cur ? "" : "selected"}>Protocol default: ${esc(x.default === "owner" ? "owning department (" + x.default_department + " until the Case File has an owner)" : x.default === "coordinator" ? "MDT Coordinator" : x.default_department)}</option>${targets.map((t) => `<option value="${esc(t.id)}" ${cur === t.id ? "selected" : ""}>${esc(t.name)}${t.group ? " (" + t.group + ")" : ""}</option>`).join("")}</select>`;
  };
  box.innerHTML = `<div class="card"><h3>Routes: who produces each record</h3>
    <div class="muted small" style="margin-bottom:6px">A request for a missing or incomplete record goes to the department that produces it. The protocol sets the default (supporting tests by test, procedures by the treating department that does them, clinical records to the Case File's owning department, previous board records to the MDT Coordinator); choose another department here to override it. Saved changes are audited.</div>
    ${Object.entries(byProto).map(([pid, p]) => `<details ${pid === Object.keys(byProto)[0] ? "open" : ""}><summary><b>${esc(p.label)}</b> <span class="muted small">${p.rows.length} records, ${p.rows.filter((x) => x.override).length} overridden</span></summary>
      <div class="tscroll"><table class="t"><thead><tr><th>Record</th><th>Tier</th><th>Goes to</th><th>Department</th></tr></thead><tbody>${p.rows.map((x) => `<tr><td>${esc(x.label)}${x.kind === "optional" ? ' <span class="chip c-mute">optional</span>' : ""}</td><td class="small muted">${esc(x.tier ? { a: "Essential", b: "Optimal", c: "Optional" }[x.tier] || x.tier : "")}</td><td>${opt(x)}</td><td class="small">${esc(x.department)}${x.override ? ' <span class="chip c-info">override</span>' : ""}</td></tr>`).join("")}</tbody></table></div></details>`).join("")}
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px"><button class="ghost sm" id="rt-reset">Clear every override</button><button class="primary sm" id="rt-save">Save routes</button></div></div>`;
  const save = async (routes) => {
    try { const cur = await api("/org"); await api("/org", { method: "PUT", json: { routes, expected_version: cur.version } }); toast("Routes saved (audited)"); renderRoutes(); }
    catch (e) { toast(e.message, 7000); }
  };
  $("#rt-save").onclick = () => { const routes = {}; $$("#o-routes .rt-sel").forEach((s) => { if (s.value) routes[s.dataset.key] = s.value; }); save(routes); };
  $("#rt-reset").onclick = () => { if (confirm("Use the protocol default for every record?")) save({}); };
}

function renderPlaced() {
  $("#na-placed").innerHTML = S.orgPage.placed.map(([d, r]) => `<span class="chip c-mute">${esc(r === "head" ? "Head" : "Doctor")} of ${esc(deptName(d))} <button class="x" data-rmplace="${esc(d)}" aria-label="remove">×</button></span>`).join("");
}
const AUDIT_KIND = { org_saved: "Organisation saved", org_migrated: "Organisation migrated", account_created: "Login created", account_placed: "Account placed",
  account_roles_changed: "Roles changed", account_unplaced: "Account removed", account_refused: "Login refused", root_admins_changed: "Root admins changed", routes_changed: "Routes changed" };
function auditText(e) {
  const k = e.kind, out = [];
  if (e.username) out.push(e.username);
  if (k === "org_saved") out.push(`${e.departments ?? "?"} department(s), ${e.users ?? "?"} account(s) placed`);
  else if (k === "org_migrated") out.push(`version ${e.from_version ?? "?"} to ${e.to_version ?? "?"}`);
  else if (k === "root_admins_changed") out.push(`before: ${(e.before || []).join(", ") || "none"}; after: ${(e.after || []).join(", ") || "none"}`);
  else if (k === "routes_changed") { const b = e.before || {}, a = e.after || {}; out.push(`${[...new Set([...Object.keys(b), ...Object.keys(a)])].filter((x) => b[x] !== a[x]).length} route(s) changed`); }
  else if (k === "account_roles_changed") {
    const a = e.roles_before || {}, b = e.roles || {}, parts = [];
    if (rolesText(a) !== rolesText(b)) parts.push(`before: ${rolesText(a)}; now: ${rolesText(b)}`);
    if (!!a.disabled !== !!b.disabled) parts.push(b.disabled ? "disabled" : "enabled");
    if ((a.display_name || "") !== (b.display_name || "")) parts.push(`display name: ${b.display_name || "none"}`);
    out.push(parts.join("; ") || rolesText(b));
  }
  else if (k === "account_placed") out.push(rolesText(e.roles));
  else if (k === "account_unplaced") out.push(`had: ${rolesText(e.roles_before)}`);
  else if (e.reason) out.push(e.reason);
  return out.join(": ");
}
function userOf(u) { const P = S.orgPage; return (P.users[u] = P.users[u] || { departments: {}, admin_of: [], coordinator: false, display_name: "", disabled: false }); }
function dirty() { $("#o-users-dirty").textContent = "Unsaved changes"; }
function renderAccounts() {
  const P = S.orgPage, acc = P.acc, info = {};
  (acc.accounts || []).forEach((a) => (info[a.username] = a));
  (acc.vaidyx_users || []).forEach((v) => { info[v.username] = { account: true, ...(info[v.username] || {}), vaidyx_admin: !!v.is_admin || !!info[v.username]?.vaidyx_admin }; });
  const names = [...new Set([...Object.keys(P.users), ...P.admins, ...Object.keys(info)])].sort();
  const row = (u) => {
    const a = info[u] || {}, v = P.users[u], root = P.admins.includes(u);
    const status = [a.vaidyx_admin ? '<span class="chip c-ok" title="Server administrator: a Tumour Board admin by default, never placed here">Vaidyx admin</span>' : "",
      v?.disabled ? '<span class="chip c-bad">Disabled</span>' : "", a.account === false ? '<span class="chip c-warn" title="No Vaidyx login with this name">no Vaidyx login</span>' : "",
      !v && !root && !a.vaidyx_admin ? '<span class="chip c-mute">not placed</span>' : ""].join(" ");
    const roles = rolesList(v, root).map(([c, t]) => `<span class="chip ${c}">${esc(t)}</span>`).join(" ");
    const open = P.editing === u;
    return `<tr data-user="${esc(u)}" class="${open ? "on" : ""}"><td><b>${esc(u)}</b></td><td class="small">${esc(v?.display_name || a.display_name || "")}</td>
      <td><div class="chips">${roles || (a.vaidyx_admin ? '<span class="muted small">every Tumour Board action (server administrator)</span>' : '<span class="muted small">none</span>')}</div></td><td><div class="chips">${status}</div></td>
      <td>${a.vaidyx_admin ? "" : `<button class="ghost sm" data-edit="${esc(u)}" aria-expanded="${open}">${open ? "Close" : "Edit"}</button>`}</td></tr>`;
  };
  $("#o-users").innerHTML = names.map(row).join("") || `<tr><td colspan="5" class="muted">No accounts.</td></tr>`;
  $("#o-ued").innerHTML = P.editing ? editorHTML(P.editing) : "";
}
function editorHTML(u) {
  const P = S.orgPage, v = userOf(u), root = P.admins.includes(u);
  return `<div class="u-ed" data-ed="${esc(u)}"><div class="small b" style="margin-bottom:6px">Editing <span style="color:var(--ink)">${esc(u)}</span>: the changes apply when you save accounts and roles</div><div class="ued">
    <div><label class="small b" for="ue-name-${esc(u)}">Display name</label><input class="ue-name" id="ue-name-${esc(u)}" value="${esc(v.display_name || "")}"></div>
    <div><div class="small b">Doctor or Head of</div><div class="u-depts">${Object.entries(v.departments || {}).map(([d, r]) => `<span class="chip c-mute">${esc(ROLE[r] || r)} of ${esc(deptName(d))} <button class="x" data-rmdept="${esc(d)}" aria-label="remove">×</button></span>`).join("") || '<span class="muted small">none</span>'}</div>
      <div class="inline"><select class="ue-dept" aria-label="Department">${deptOpts()}</select><select class="ue-role" aria-label="Role"><option value="member">Doctor</option><option value="head">Head</option></select><button class="ghost sm" data-adddept>Add</button></div></div>
    <div><div class="small b">Department admin of</div><div class="u-depts">${(v.admin_of || []).map((d) => `<span class="chip c-info">Admin of ${esc(deptName(d))} <button class="x" data-rmadm="${esc(d)}" aria-label="remove">×</button></span>`).join("") || '<span class="muted small">none</span>'}</div>
      <div class="inline"><select class="ue-adm" aria-label="Department">${deptOpts()}</select><button class="ghost sm" data-addadm>Add</button></div></div>
    <div><div class="small b">Other</div><label class="chk"><input type="checkbox" data-flag="coordinator" ${v.coordinator ? "checked" : ""}> MDT Coordinator</label>
      <label class="chk"><input type="checkbox" data-flag="root" ${root ? "checked" : ""}> Root admin</label><label class="chk"><input type="checkbox" data-flag="disabled" ${v.disabled ? "checked" : ""}> Disabled</label>
      <button class="ghost sm" data-unplace>Remove from the Tumour Board</button> <button class="ghost sm" data-edit="${esc(u)}">Close</button></div></div></div>`;
}
function accountsClick(e) {
  const P = S.orgPage, b = e.target.closest("button"); if (!b) return;
  if (b.dataset.edit !== undefined) { const u = b.dataset.edit; P.editing = P.editing === u ? null : u; renderAccounts(); if (P.editing) $("#o-ued").scrollIntoView({ block: "nearest", behavior: "smooth" }); return; }
  const ed = b.closest("[data-ed]"); if (!ed) return;
  const u = ed.dataset.ed, v = userOf(u);
  if (b.dataset.rmdept) { delete v.departments[b.dataset.rmdept]; }
  else if (b.dataset.rmadm) { v.admin_of = (v.admin_of || []).filter((d) => d !== b.dataset.rmadm); }
  else if (b.hasAttribute("data-adddept")) { v.departments = { ...(v.departments || {}), [$(".ue-dept", ed).value]: $(".ue-role", ed).value }; }
  else if (b.hasAttribute("data-addadm")) { const d = $(".ue-adm", ed).value; v.admin_of = [...new Set([...(v.admin_of || []), d])]; }
  else if (b.hasAttribute("data-unplace")) { delete P.users[u]; P.admins = P.admins.filter((x) => x !== u); P.editing = null; }
  else return;
  dirty(); renderAccounts();
}
function accountsChange(e) {
  const P = S.orgPage, f = e.target.dataset.flag, ed = e.target.closest("[data-ed]"); if (!f || !ed) return;
  const u = ed.dataset.ed, on = e.target.checked;
  if (f === "root") P.admins = on ? [...new Set([...P.admins, u])] : P.admins.filter((x) => x !== u);
  else userOf(u)[f] = on;
  dirty(); renderAccounts();
}

async function showMyDept(dept) {
  const ads = S.org?.admin_departments || [];
  if (!ads.length) return;
  dept = ads.some((d) => d.id === dept) ? dept : ads.some((d) => d.id === S.myDept) ? S.myDept : ads[0].id; S.myDept = dept;
  stopRoomPoll(); S.roomId = null; showOnly("deptpage");
  const box = $("#deptpage");
  let r;
  try { r = await api(`/org/departments/${encodeURIComponent(dept)}/doctors`); } catch (e) { box.innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
  const d = r.department || {}, base = `/org/departments/${encodeURIComponent(dept)}/doctors`;
  const chips = (x) => [x.admin ? '<span class="chip c-info">Department admin</span>' : "", x.coordinator ? '<span class="chip c-info">MDT Coordinator</span>' : "",
    x.root_admin ? '<span class="chip c-info">Root admin</span>' : "", x.disabled ? '<span class="chip c-bad">Disabled</span>' : "",
    (x.other_departments || []).length ? `<span class="chip c-mute">also in ${esc(x.other_departments.map((o) => o.name).join(", "))}</span>` : "",
    (x.admin_of_others || []).length ? `<span class="chip c-mute">also admin of ${esc(x.admin_of_others.map(deptName).join(", "))}</span>` : "",
    x.account === false ? '<span class="chip c-warn" title="No Vaidyx login with this name">no Vaidyx login</span>' : "",
    x.vaidyx_admin ? '<span class="chip c-ok">Vaidyx admin</span>' : ""].filter(Boolean).join(" ");
  const row = (x) => `<tr data-user="${esc(x.username)}"><td><b>${esc(x.display_name || x.username)}</b></td><td class="small">${esc(x.username)}</td>
    <td>${x.role ? `<select class="dp-role" aria-label="Role"><option value="doctor" ${x.role !== "head" ? "selected" : ""}>Doctor</option><option value="head" ${x.role === "head" ? "selected" : ""}>Head</option></select>` : '<span class="muted small">Department admin only</span>'}</td>
    <td><div class="chips">${chips(x) || '<span class="chip c-ok">Active</span>'}</div></td>
    <td class="nowrap">${x.disabled ? '<button class="ghost sm" data-dis="0">Enable</button>' : '<button class="ghost sm" data-dis="1">Disable</button>'}${x.role ? ' <button class="ghost sm" data-rm>Remove</button>' : ""}</td></tr>`;
  box.innerHTML = `<div class="case-head"><div><div class="eyebrow">Department admin</div><h1>${esc(d.name || dept)} <span class="chip c-mute">${d.group === "supporting" ? "Supporting" : "Treating"}</span></h1>
      <div class="muted">The doctor logins of this department: create, set Doctor or Head, disable or enable, remove from the department. Removing takes the placement away; the Vaidyx login stays. Every change is recorded in the audit.</div></div>
      ${ads.length > 1 ? `<div class="form dp-switch"><label for="dp-dept">Department</label><select id="dp-dept">${ads.map((a) => `<option value="${esc(a.id)}" ${a.id === dept ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></div>` : ""}</div>
    <div class="card"><h3>Doctors <span class="muted small">${(r.doctors || []).filter((x) => x.role).length} placed</span></h3>
      ${tscroll(`<table class="t"><thead><tr><th>Name</th><th>Login</th><th>Role</th><th>Status</th><th></th></tr></thead><tbody id="dp-doctors">${(r.doctors || []).map(row).join("") || `<tr><td colspan="5" class="muted">No one is placed in this department yet.</td></tr>`}</tbody></table>`)}
      <div class="small muted" style="margin-top:8px">${esc(r.reset_note || "")}</div></div>
    <div class="card"><h3>New doctor login</h3>
      <div class="form"><div class="grid4">
        <div><label for="nd-user">Login name</label><input id="nd-user" autocomplete="off" placeholder="lower-case, e.g. dr.rao"></div>
        <div><label for="nd-pass">Password</label><input id="nd-pass" type="password" autocomplete="new-password" placeholder="at least 8 characters"></div>
        <div><label for="nd-name">Display name</label><input id="nd-name" autocomplete="off" placeholder="e.g. Dr. A. Rao"></div>
        <div><label for="nd-role">Role</label><select id="nd-role"><option value="doctor">Doctor</option><option value="head">Head</option></select></div></div></div>
      <div class="small muted" style="margin-top:6px">An existing plain login is placed in the department without a password.</div>
      <div class="actions-row"><button class="primary sm" id="nd-create">Create and place</button></div></div>`;
  // reload the table after every action; a refused new login keeps the form as typed (the password field is cleared either way)
  const act = async (fn, ok, keepOnError) => { try { const out = await fn(); toast(typeof ok === "function" ? ok(out) : ok); } catch (e) { toast(e.message, 8000); if (keepOnError) return; } await showMyDept(dept); };
  if ($("#dp-dept")) $("#dp-dept").onchange = () => showMyDept($("#dp-dept").value);
  $$("#dp-doctors tr[data-user]").forEach((tr) => {
    const u = tr.dataset.user, url = `${base}/${encodeURIComponent(u)}`;
    const sel = $(".dp-role", tr); if (sel) sel.onchange = () => act(() => api(url, { method: "PUT", json: { role: sel.value } }), `${u} is now ${sel.value === "head" ? "Head" : "Doctor"}`);
    const dis = $("[data-dis]", tr); if (dis) dis.onclick = () => act(() => api(url, { method: "PUT", json: { disabled: dis.dataset.dis === "1" } }), `${u} ${dis.dataset.dis === "1" ? "disabled" : "enabled"}`);
    const rm = $("[data-rm]", tr); if (rm) rm.onclick = async () => {
      const v = await confirmDialog({ title: `Remove ${u} from ${d.name || dept}?`, intro: "The doctor placement in this department is taken away. The Vaidyx login and any other roles stay.", submit: "Remove" });
      if (v) act(() => api(url, { method: "DELETE" }), (out) => `${u} removed from ${d.name || dept}${out.kept ? "; other roles kept" : ""}`);
    };
  });
  $("#nd-create").onclick = () => {
    const username = $("#nd-user").value.trim(), password = $("#nd-pass").value;
    if (!username) { toast("Login name is required"); return; }
    const body = { username, display_name: $("#nd-name").value.trim(), role: $("#nd-role").value }; if (password) body.password = password;
    $("#nd-pass").value = "";
    act(() => api(base, { json: body }), (out) => out.created ? `Login ${out.username} created and placed` : `Existing login ${out.username} placed`, true);
  };
}

// ------------------------------------------------------------------ department uploads and the Needs matching queue · V1 items 2.3 / 2.4
function identityText(idr) {
  if (!idr) return "";
  const ids = (idr.ids || []).map((i) => `${{ uhid: "UHID", mrn: "MRN", cr_no: "CR No.", ip_no: "IP No.", op_no: "OP No.", reg_no: "Reg. No.", hospital_no: "Hospital No.", abha: "ABHA", pmjay: "PM-JAY ID" }[i.kind] || i.kind} ${i.value}`);
  return [idr.name?.value || "name not read", idr.age != null || idr.sex ? `${idr.age ?? "?"} Y / ${idr.sex || "?"}` : "", idr.dob ? "DOB " + fmtDate(idr.dob) : "", idr.relation?.name ? `${idr.relation.kind || ""} ${idr.relation.name}`.trim() : "",
    ...ids, idr.aadhaar_seen ? "Aadhaar seen, masked" : "", (idr.model_read || []).length ? `(${idr.model_read.join(" and ")} read by the Qwen3.5-4B reader, Chinese, non-medical; quote checked)` : ""].filter(Boolean).join(" · ");
}
const DECISION = { auto_link: ["c-ok", "Filed automatically"], suggest: ["c-warn", "Suggested match: confirm"], needs_matching: ["c-warn", "Needs matching"],
  new_case: ["c-info", "New Case File"], id_conflict: ["c-bad", "Possible wrong ID"] };
async function refreshQueueCount() {
  if (!S.me || !(S.me.known || S.me.admin)) return;
  try { const q = await api("/intake"); S.queue = q; const n = q.documents.filter((d) => d.state !== "filed").length;
    $("#queue-count").textContent = n; $("#queue-count").classList.toggle("hidden", !n); } catch (e) {}
}
function bindIntakeUpload() {
  const my = S.org?.my_departments || [];
  $("#side-intake").classList.toggle("hidden", !my.length);
  $("#intake-upload").classList.toggle("hidden", !S.me?.admin);  // V2 item 3.7: records come from the hospital system; the API path stays
  if (!my.length || !S.me?.admin) return;
  $("#up-dept").innerHTML = my.map((d) => `<option value="${esc(d.id)}">${esc(d.name)}${d.role ? " (" + esc(d.role) + ")" : ""}</option>`).join("");
  const send = async (list) => {
    if (!list.length) return;
    const fd = new FormData(); list.forEach(([f]) => fd.append("files", f)); fd.append("paths", JSON.stringify(list.map(([, p]) => p))); fd.append("department", $("#up-dept").value);
    $("#up-job").innerHTML = `<span class="spin"></span> Uploading ${list.length} file(s)...`;
    const r = await fetch("/api/tb/intake/documents", { method: "POST", body: fd, credentials: "same-origin" });
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} $("#up-job").textContent = ""; toast("Upload failed: " + m, 7000); return; }
    const res = await r.json();
    if (res.warnings?.length) toast(res.warnings.map((w) => w.message).join("; "), 10000);
    watchIntakeJob(res.job);
  };
  $("#up-pick").onclick = () => $("#up-files").click(); $("#up-folder").onclick = () => $("#up-files-dir").click();
  $("#up-files").onchange = (e) => send([...e.target.files].map((f) => [f, f.name]));
  $("#up-files-dir").onchange = (e) => send([...e.target.files].map((f) => [f, f.webkitRelativePath || f.name]));
  const drop = $("#up-drop");
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); }; drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); send([...e.dataTransfer.files].map((f) => [f, f.name])); };
}
async function watchIntakeJob(id) {
  const t0 = Date.now();
  while (true) {
    let j; try { j = await api("/jobs/" + id); } catch (e) { break; }
    const st = Object.values(j.doc_states), count = (k) => st.filter((s) => s === k).length;
    $("#up-job").innerHTML = `<div class="progress"><div style="width:${j.total ? (100 * j.done) / j.total : 100}%"></div></div>${j.done}/${j.total} read · ${((Date.now() - t0) / 1000).toFixed(1)} s ${count("needs_matching") ? `· ${count("needs_matching")} need matching` : ""}`;
    if (j.state === "failed" || j.state === "interrupted") { toast((j.error || "Processing failed") + ".", 8000); break; }
    if (j.state === "finished") {
      const filed = Object.entries(j.filed || {}), needs = (j.needs_matching || []).length, errs = (j.errors || []).length;
      const extra = [j.unsupported?.length ? `${j.unsupported.length} file(s) not read: ` + j.unsupported.map((u) => `${u.file} (${u.reason})`).join(", ") : "", j.skipped_duplicates?.length ? `${j.skipped_duplicates.length} already waiting` : "", (j.warnings || []).map((w) => w.message).join("; ")].filter(Boolean).join("; ");
      $("#up-job").innerHTML = `<span class="muted">${filed.length} filed · ${needs} need matching${errs ? ` · ${errs} failed` : ""} · ${j.seconds} s</span>`;
      toast(`${j.total} document(s) read for ${deptName(j.department)}: ${filed.length} filed into Case Files (${[...new Set(filed.map(([, c]) => c))].join(", ") || "none"}), ${needs} waiting for a person to match${errs ? `, ${errs} failed to read` : ""}.${extra ? " " + extra + "." : ""}`, 9000);
      await refreshQueueCount(); if (!$("#intake").classList.contains("hidden")) showIntake(); loadCases(); if (S.caseId) openCase(S.caseId, true);
      break;
    }
    await new Promise((r) => setTimeout(r, 700));
  }
}
async function showIntake() {
  const q = await api("/intake"); S.queue = q;
  MAIN_SECTIONS.forEach((x) => $("#" + x).classList.toggle("hidden", x !== "intake")); stopRoomPoll();
  $$(".citem").forEach((el) => el.classList.remove("on"));
  const caseLabel = (cid) => { const c = q.cases.find((x) => x.case_id === cid); return c ? `${c.patient?.name || cid} (${cid}${c.listing?.status === "awaiting_listing" ? ", awaiting listing" : ""})` : cid; };
  const caseOpts = (sel) => q.cases.map((c) => `<option value="${esc(c.case_id)}" ${c.case_id === sel ? "selected" : ""}>${esc(caseLabel(c.case_id))}</option>`).join("");
  const docs = q.documents.filter((d) => d.state !== "filed");
  const row = (d) => { const m = d.match || {}, c = d.classification || {}, dec = DECISION[m.decision] || ["c-mute", d.state];
    const cands = (m.candidates || []).map((x) => `<div class="small"><span class="cite" data-open-case="${esc(x.case_id)}">${esc(caseLabel(x.case_id))}</span> <span class="muted">${esc(x.why || "")}</span>${q.can_match && ["needs_matching", "duplicate", "error"].includes(d.state) ? ` <button class="ghost sm" data-file="${esc(d.doc_id)}" data-case="${esc(x.case_id)}">File here</button> <button class="ghost sm" data-notthis="${esc(d.doc_id)}" data-case="${esc(x.case_id)}">Not this patient</button>` : ""}</div>`).join("");
    const act = q.can_match && ["needs_matching", "duplicate", "error"].includes(d.state) ? `<div class="iact"><select data-sel="${esc(d.doc_id)}">${caseOpts(m.case_id || (m.candidates || [])[0]?.case_id)}</select><button class="primary sm" data-file="${esc(d.doc_id)}">File into Case File</button>${q.can_create ? `<button class="ghost sm" data-newcase="${esc(d.doc_id)}">New Case File</button>` : ""}<button class="ghost sm" data-discard="${esc(d.doc_id)}">Discard</button>${d.state === "error" ? `<button class="ghost sm" data-retry="${esc(d.doc_id)}">Read again</button>` : ""}</div>` : "";
    return `<tr><td><b class="click" data-intake="${esc(d.doc_id)}">${esc(c.title || d.filename)}</b><div class="small muted">${esc(d.rel_path)} · ${esc(DT[c.doc_type] || c.doc_type || "")}${docDates(c).event ? " · " + fmtDate(docDates(c).event) : ""} ${d.state === "ready" || c.status ? statusChip(c) : ""}</div></td>
      <td class="small">${esc(deptName(d.department))}<div class="muted">${esc(d.uploaded_by || "")} · ${esc((d.added || "").slice(0, 16).replace("T", " "))}</div></td>
      <td class="small">${d.state === "error" ? `<span class="chip c-bad" title="${esc(d.error || "")}">failed to read</span> <span class="muted">${esc(d.error || "")}</span>` : d.state === "duplicate" ? `<span class="chip c-mute">identical file already in ${esc(d.filed?.case_id || "")}</span>` : ["queued", "reading", "classifying", "identifying"].includes(d.state) ? `<span class="chip c-info"><span class="spin"></span> ${esc(d.state)}</span>` : esc(identityText(d.identity_read))}</td>
      <td><span class="chip ${dec[0]}">${esc(dec[1])}</span><div class="small muted">${esc(m.reason || "")}</div>${cands}${act}</td></tr>`; };
  $("#intake").innerHTML = `<div class="case-head"><div><div class="eyebrow">Department uploads</div><h1>Needs matching</h1>
      <div class="muted">Records uploaded by departments that could not be matched to a patient on an exact identifier. A person files each one into a Case File, starts a new Case File, or discards it. Every decision is recorded in the audit log.</div></div></div>
    <div class="card"><h3>Waiting <span class="muted small">${docs.length}</span></h3>
    ${docs.length ? `<table class="t"><thead><tr><th>Record</th><th>Uploaded by</th><th>Patient as printed</th><th>Decision</th></tr></thead><tbody>${docs.map(row).join("")}</tbody></table>` : `<div class="muted">Nothing waiting. Department uploads that match a patient exactly are filed into the Case File automatically.</div>`}</div>
    ${q.audit?.length ? `<div class="card"><h3>Intake log <span class="muted small">${q.audit.length} events</span></h3><table class="t"><tbody>${q.audit.slice().reverse().slice(0, 60).map((e) => { const { ts, kind, ...rest } = e; return `<tr><td class="small">${esc(ts.replace("T", " ").slice(0, 16))}</td><td><span class="chip c-info">${esc(kind)}</span></td><td class="small">${esc(JSON.stringify(rest)).slice(0, 220)}</td></tr>`; }).join("")}</tbody></table></div>` : ""}`;
  const after = async (jobId, cid) => { toast(cid ? `Filed into ${cid}; fields are being extracted` : "Done"); await showIntake(); refreshQueueCount(); loadCases(); if (jobId && cid) { S.caseId = cid; } };
  $$("[data-intake]").forEach((el) => (el.onclick = () => openDoc(el.dataset.intake, null, `/intake/${el.dataset.intake}`)));
  $$("[data-open-case]").forEach((el) => (el.onclick = () => openCase(el.dataset.openCase)));
  $$("[data-file]").forEach((b) => (b.onclick = async () => { const cid = b.dataset.case || $(`[data-sel="${b.dataset.file}"]`)?.value; if (!cid) return;
    const v = await confirmDialog({ title: "File this record into a Case File", intro: `Confirm that this record belongs to ${caseLabel(cid)}. The match is recorded as your confirmation in that Case File.`, fields: [{ id: "reason", label: "Note", type: "text", placeholder: "e.g. UHID checked on the hospital card" }], submit: "File" });
    if (!v) return; try { const r = await api(`/intake/${b.dataset.file}/file-to-case`, { json: { case_id: cid, reason: v.reason } }); await after(r.job, r.duplicate ? null : cid); if (r.duplicate) toast("An identical file is already in that Case File; nothing was added", 6000); } catch (e) { toast(e.message, 7000); } }));
  $$("[data-notthis]").forEach((b) => (b.onclick = async () => { const v = await confirmDialog({ title: "Not this patient", intro: `Record that this document is not ${caseLabel(b.dataset.case)}. The Case File will not be suggested again for it.`, fields: [{ id: "reason", label: "Reason", type: "text", required: true }], submit: "Record" });
    if (!v) return; try { await api(`/intake/${b.dataset.notthis}/not-this-patient`, { json: { case_id: b.dataset.case, reason: v.reason } }); await showIntake(); } catch (e) { toast(e.message, 7000); } }));
  $$("[data-newcase]").forEach((b) => (b.onclick = async () => { const d = q.documents.find((x) => x.doc_id === b.dataset.newcase), idr = d?.identity_read || {};
    const v = await confirmDialog({ title: "Start a new Case File from this record", intro: "A new Case File is created with the identity printed on the record. It waits for the coordinator to list it (cancer, NCG setting, board date) before the Pre-Authorization check runs.",
      fields: [{ id: "case_id", label: "Case File ID", type: "text", placeholder: "leave empty for the next number" }, { id: "name", label: "Patient name", type: "text", value: idr.name?.value || "", required: true }, { id: "mrn", label: "UHID / MRN", type: "text", value: (idr.ids || []).find((i) => ["uhid", "mrn", "hospital_no"].includes(i.kind))?.value || "" }, { id: "agesex", label: "Age / Sex", type: "text", value: idr.age != null && idr.sex ? `${idr.age} Y / ${idr.sex}` : "" }], submit: "Create and file" });
    if (!v) return; try { const r = await api(`/intake/${b.dataset.newcase}/new-case`, { json: { case_id: v.case_id, patient: { name: v.name, mrn: v.mrn, agesex: v.agesex, ids: idr.ids?.map((i) => ({ kind: i.kind, value: i.value })) || [], abha: idr.abha || null, dob: idr.dob || null, sex: idr.sex || null, age: idr.age ?? null } } }); await after(r.job, r.case_id); } catch (e) { toast(e.message, 7000); } }));
  $$("[data-discard]").forEach((b) => (b.onclick = async () => { const v = await confirmDialog({ title: "Discard this record", intro: "The file is removed from the intake area. The removal is recorded in the intake log.", fields: [{ id: "reason", label: "Reason", type: "text", required: true }], submit: "Discard" });
    if (!v) return; try { await api(`/intake/${b.dataset.discard}?reason=${encodeURIComponent(v.reason)}`, { method: "DELETE" }); await showIntake(); refreshQueueCount(); } catch (e) { toast(e.message, 7000); } }));
  $$("[data-retry]").forEach((b) => (b.onclick = async () => { try { const r = await api(`/intake/${b.dataset.retry}/reprocess`, { method: "POST" }); watchIntakeJob(r.job); } catch (e) { toast(e.message, 7000); } }));
}

// ------------------------------------------------------------------ notifications (bell) and the department inbox · V1 item 4.4
const NKIND = { request: ["c-warn", "Request"], request_closed: ["c-ok", "Request closed"], request_acknowledged: ["c-info", "Request acknowledged"], request_done: ["c-ok", "Done by the department"], case_ready: ["c-ok", "Case File ready"],
  board_action: ["c-info", "Tumour Board action"], board_action_suggestion: ["c-ok", "Action may be complete"],
  case_shared: ["c-info", "Case File shared"], case_unshared: ["c-mute", "Case File no longer shared"], referral: ["c-warn", "Referral"], referral_answered: ["c-info", "Referral answered"],  // V2 items 5.1 / 5.2
  request_reminder: ["c-warn", "Reminder"], owner_reminder: ["c-warn", "Before the board"], board_ready: ["c-ok", "Ready for the board"] };  // V2 item 6.1
async function loadNotifications() {
  if (!S.me) return;
  try { const r = await api("/notifications?limit=80"); S.notifications = r.notifications; S.unread = r.unread;
    $("#btn-bell").classList.remove("hidden"); $("#bell-count").textContent = r.unread; $("#bell-count").classList.toggle("hidden", !r.unread); } catch (e) {}
}
const ntfRow = (n) => { const k = NKIND[n.kind] || ["c-mute", n.kind]; return `<div class="ntf ${n.read ? "read" : ""}" data-ntf="${esc(n.id)}" data-case="${esc(n.case_id || "")}" title="Open the Case File">
      <div class="h"><span class="chip ${k[0]}">${esc(k[1])}</span> <b>${esc(n.title)}</b>${n.kind === "referral_answered" && n.status ? " " + rChip(n.status) : ""}${n.level_label ? ` <span class="chip c-lvl">${esc(n.level_label)}</span>` : ""}${n.read ? "" : ' <span class="chip c-info">new</span>'}</div>
      ${n.text ? `<div class="small">${esc(n.text)}</div>` : ""}${(n.kind === "request" || n.kind === "referral") && n.uhid ? `<div class="small"><span class="chip c-mono" title="UHID">${esc(n.uhid)}</span>${n.accession ? ` <span class="chip c-mono" title="Accession / Lab No.">${esc(n.accession)}</span>` : ""}${encText(n.encounter) ? ` <span class="muted">${esc(encText(n.encounter))}</span>` : ""}${n.reminder ? ' <span class="chip c-warn">reminder</span>' : ""}${n.sent_by ? ` <span class="muted">sent by ${esc(n.sent_by)}</span>` : ""}</div>` : ""}${n.kind === "request_done" && n.refetch_offer ? `<div class="small"><b>Re-fetch from the HIS to close it.</b></div>` : ""}<div class="small muted">${esc((n.ts || "").slice(0, 16).replace("T", " "))}${n.due ? " · due " + fmtDate(n.due) : ""}${n.to?.department ? " · to " + esc(deptName(n.to.department)) : n.to?.role ? " · to the coordinator" : ""}</div></div>`; };
function showNotifications() {
  const list = S.notifications || [];
  const row = ntfRow;
  $("#modal-body").innerHTML = `<h3 style="color:#1f2933;margin-top:0">Notifications <span class="muted small" style="font-weight:400">${S.unread || 0} unread</span></h3>
    <div class="small muted">In-app only. The Pre-Authorization check suggests a request for each gap; the treating doctor sends it to the Responsible Department, which acknowledges it and sends "done" back. A request closes by itself when the record arrives; the coordinator hears when a Case File is ready for the board.</div>
    <div style="margin:8px 0;display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap">${(S.org?.inbox_departments || []).length || S.me?.coordinator ? `<button class="ghost sm" id="nt-inbox">Open the department inbox</button>` : ""}${list.some((n) => !n.read) ? `<button class="ghost sm" id="nt-readall">Mark all read</button>` : ""}<button class="ghost sm" data-closemodal>Close</button></div>
    ${list.length ? list.map(row).join("") : `<div class="muted">Nothing yet.</div>`}`;
  $("#modal").classList.remove("hidden");
  if ($("#nt-readall")) $("#nt-readall").onclick = async () => { await api("/notifications/read", { json: { all: true } }); await loadNotifications(); showNotifications(); };
  if ($("#nt-inbox")) $("#nt-inbox").onclick = () => { $("#modal").classList.add("hidden"); showInbox(); };
  $$("[data-ntf]").forEach((el) => (el.onclick = async () => { try { await api("/notifications/read", { json: { ids: [el.dataset.ntf] } }); } catch (e) {} $("#modal").classList.add("hidden"); loadNotifications(); if (el.dataset.case) { await openCaseSafe(el.dataset.case); } }));
}
async function refreshInboxCount() {
  const show = (S.org?.inbox_departments || []).length > 0 || !!S.me?.coordinator;  // V2 2.1: the MDT Coordinator has an inbox row of its own
  $("#btn-inbox").classList.toggle("hidden", !show);
  if (!show) return;
  try { const ib = await api("/inbox"), n = ib.open + (ib.referrals || []).filter((r) => r.can_answer).length; $("#inbox-count").textContent = n; $("#inbox-count").classList.toggle("hidden", !n); } catch (e) {}
}
// the inbox rows (V2 item 4.3), shared by the Department inbox and the supporting doctor's home (V2 item 7.1). The inbox has no per-case
// permissions: the buttons show for the doctors of that inbox department (the coordinator for the MDT Coordinator's row) and admins; the
// server decides and a refusal is toasted.
const ibMayAnswer = (d) => !!S.me && (S.me.admin || (d.id === "coordinator" ? !!S.me.coordinator : !!(S.me.departments || {})[d.id]));
const ibChip = (q) => { if (q.source !== "pre_authorization") return q.status === "completed" ? `<span class="chip c-ok">Closed</span>` : q.overdue ? `<span class="chip c-bad">Overdue ${q.days_overdue} d</span>` : `<span class="chip c-warn">Pending</span>`;
  const [cls, txt] = reqStatus(q); return `<span class="chip ${cls} reqst">${esc(txt)}</span>`; };
const ibFirstLines = (m) => String(m || "").split("\n").map((l) => l.trim()).filter((l) => l && !/^(To|Tumour Board Case File|Patient|Treating department|Sent by)\b/.test(l)).slice(0, 3).join("\n");
const ibAsked = (q) => { const s = q.sent || {}; const head = q.what || ibFirstLines(s.message);
  return `${head ? `<div class="pre">${esc(head)}</div>` : ""}${s.message ? `<details class="small"><summary>Message${s.count > 1 ? ` (sent ${s.count} times)` : ""}</summary><div class="pre msg">${esc(s.message)}</div></details>` : ""}${s.by ? `<div class="muted">Sent by ${esc(s.by)} on ${dmyt(s.at)}</div>` : ""}`; };
const ibActs = (q, d) => { if (q.source !== "pre_authorization" || q.status === "completed" || !(q.sent || q.status === "pending" || q.status === "overdue") || !ibMayAnswer(d)) return "";  // a V1 request (no sending record) is answered too
  return `${!q.acknowledged ? `<button class="ghost sm" data-ack="${esc(q.action_id)}" data-case="${esc(q.case_id)}">Acknowledge</button>` : ""}${!q.done ? `<button class="primary sm" data-done="${esc(q.action_id)}" data-case="${esc(q.case_id)}" title="The report is signed in your own system: send &quot;done&quot; back with an optional note">Done</button>` : ""}`; };
const ibRow = (q, d) => `<tr class="click" data-case="${esc(q.case_id)}" data-aid="${esc(q.action_id)}"><td data-l="Case File"><b>${esc(q.patient?.name || q.case_id)}</b><div class="small muted">${esc(q.case_id)}${q.patient?.agesex ? " · " + esc(q.patient.agesex) : ""}${q.board_date ? " · board " + dmyd(q.board_date) : ""}</div>
      ${q.uhid || q.patient?.mrn ? `<div class="small">UHID <span class="mono">${esc(q.uhid || q.patient.mrn)}</span></div>` : ""}${encHTML(q.encounter)}</td>
    <td data-l="Record needed">${q.source === "board" ? `<span class="chip c-info">${esc(q.source_label)}</span> ` : q.free ? `<span class="chip c-info">Free request</span> ` : ""}<b>${esc(q.label)}</b><div class="chips" style="margin-top:3px">${q.level_label ? `<span class="chip c-lvl">${esc(q.level_label)}</span>` : ""}${q.accession ? `<span class="chip c-mono" title="Accession / Lab No.: find the patient in your PACS / RIS / LIS">${esc(q.accession)}</span>` : ""}${q.pending_order ? `<span class="chip ${q.pending_order.stage === "cancelled" ? "c-bad" : "c-info"}">Ordered in the HIS: ${esc(stageText(q.pending_order))}</span>` : ""}</div></td>
    <td class="small" data-l="What is asked">${q.source === "pre_authorization" ? ibAsked(q) : esc(q.what)}${suggestionHTML(q, true)}</td><td class="small nowrap" data-l="Due">${q.due ? esc(dmyd(q.due)) : ""}</td>
    <td data-l="Status">${ibChip(q)}${q.source === "pre_authorization" ? reqTrail({ ...q, sent: null, earlier: [] }) : q.completed ? `<div class="small muted">${esc(dmyt(q.completed))}</div>` : ""}</td><td class="nowrap"><div class="ibtns">${ibActs(q, d)}</div></td></tr>`;
function bindInboxRows(root, after) {  // open the Case File from a row; Acknowledge and Done re-render through `after`
  $$(`${root} tr[data-case][data-aid]`).forEach((tr) => (tr.onclick = async (e) => { if (e.target.closest("button, details, a")) return; await openCaseSafe(tr.dataset.case); }));
  $$(`${root} [data-ack]`).forEach((b) => (b.onclick = async (e) => { e.stopPropagation(); b.disabled = true; if (await answerRequest(b.dataset.case, b.dataset.ack, "acknowledge")) { await after(); loadNotifications(); } else b.disabled = false; }));
  $$(`${root} [data-done]`).forEach((b) => (b.onclick = async (e) => { e.stopPropagation(); b.disabled = true; if (await answerRequest(b.dataset.case, b.dataset.done, "done")) { await after(); loadNotifications(); } else b.disabled = false; }));
}
async function showInbox() {
  const ib = await api("/inbox"); S.inbox = ib;
  MAIN_SECTIONS.forEach((x) => $("#" + x).classList.toggle("hidden", x !== "inbox")); stopRoomPoll();
  $$(".citem").forEach((el) => el.classList.remove("on"));
  const refs = ib.referrals || [], refCard = inboxReferralsHTML(refs);  // V2 item 5.2: referrals to and from my departments
  const withRows = ib.departments.filter((d) => d.requests.length || ib.departments.length <= 2), empty = ib.departments.filter((d) => !withRows.includes(d));  // V2 item 7.2: an admin's 30 departments as one line when empty
  const emptyCard = empty.length ? `<div class="card"><h3>No requests <span class="muted small">${plural(empty.length, "department")}</span></h3><div class="small muted">${esc(empty.map((d) => d.name).join(", "))}</div></div>` : "";
  $("#inbox").innerHTML = `<div class="case-head"><div><div class="eyebrow">Department inbox</div><h1>Requests to ${ib.departments.length === 1 ? esc(ib.departments[0].name) : "my departments"}</h1>
      <div class="muted">Requests the treating doctors sent to your department across the Tumour Board Case Files, and every action the Tumour Board gave your department: the patient with the UHID, IP / OP No. and accession No. to find the study or sample in your own PACS / RIS / LIS, what is asked, the due date and the status. Acknowledge a request when you take it up, then send "done" back (with a note if needed) once the report is signed in your own system. A request closes by itself when the record arrives in the Case File; a Tumour Board action is closed by a person (a newly arrived matching document is suggested). Requests closed in the last 7 days stay listed. Overdue is worked out when this page is shown.</div></div>
      <div class="readiness"><div class="rtext"><b>${ib.open} open</b><span>${ib.overdue} overdue</span>${refs.some((r) => r.can_answer) ? `<span> · ${plural(refs.filter((r) => r.can_answer).length, "referral")} to answer</span>` : ""}</div></div></div>
    ${refCard}
    ${withRows.map((d) => `<div class="card"><h3>${esc(d.name)} <span class="muted small">${d.open} open · ${d.overdue} overdue</span></h3>
      ${d.requests.length ? `<div class="tscroll"><table class="t inbox-t"><thead><tr><th>Case File</th><th>Record needed</th><th>What is asked</th><th>Due</th><th>Status</th><th>Actions</th></tr></thead><tbody>${d.requests.map((q) => ibRow(q, d)).join("")}</tbody></table></div>` : `<div class="muted small">No requests.</div>`}</div>`).join("") + emptyCard || (refs.length ? "" : `<div class="card"><div class="muted">Your account is not placed in a department with an inbox.</div></div>`)}`;
  bindInboxRows("#inbox", showInbox);
  bindInboxReferrals(refs, "#inbox", showInbox);
  const cnt = ib.open + refs.filter((r) => r.can_answer).length;
  $("#inbox-count").textContent = cnt; $("#inbox-count").classList.toggle("hidden", !cnt);
}

// ------------------------------------------------------------------ Case File listing (coordinator) · V1 item 2.5
async function listCase() {
  const c = S.data.case, ps = S.protocols || [];
  const v = await confirmDialog({ title: c.listing?.status === "awaiting_listing" ? "List this Case File for the Tumour Board" : "Change the listing",
    intro: "Cancer protocol, NCG setting (chosen by the clinician from what the signed reports record) and board date. The Pre-Authorization check starts when the Case File is listed; the hospital level decides which NCG tier applies.",
    fields: [{ id: "protocol", label: "Protocol", type: "select", value: c.protocol || ps[0]?.id, options: ps.map((p) => [p.id, `${p.label} (v${p.version})`]) },
      { id: "setting", label: "NCG setting", type: "select", value: c.setting || "", options: [["", "Not chosen yet"], ...(ps.find((p) => p.id === (c.protocol || ps[0]?.id))?.settings || []).map((x) => [x.id, x.label])] },
      { id: "hospital_level", label: "Hospital level", type: "select", value: c.hospital_level || S.org?.hospital?.level || "essential", options: [["essential", "Essential"], ["optimal", "Optimal"]] },
      { id: "board_date", label: "Board date", type: "date", value: c.board_date || "" }], submit: "List" });
  if (!v) return;
  try { const r = await api(`/cases/${S.caseId}/listing`, { json: v }); toast(r.total ? `Listed. Extracting fields from ${r.total} document(s) and running the Pre-Authorization check...` : "Listing saved; Pre-Authorization re-checked", 6000); S.tab = "ready"; await openCase(S.caseId, true); if (r.total) watchJob(r.job); loadCases(); }
  catch (e) { toast(e.message, 7000); }
}

// ------------------------------------------------------------------ owner, participants, referral, linked Case Files · V2 items 5.1 to 5.3
// The owning treating department's doctors act on the Case File; participating departments read and comment; a department that was
// only asked sees its requests and records. A referral moves the Case File to another treating department once that department
// accepts it. The server decides every permission (S.data.permissions); the UI only hides what the user may not do.
const RSTATUS = { requested: ["c-warn", "Requested"], accepted: ["c-ok", "Accepted"], declined: ["c-bad", "Declined"], withdrawn: ["c-mute", "Withdrawn"] };
const rChip = (s) => { const k = RSTATUS[s] || ["c-mute", s || "unknown"]; return `<span class="chip ${k[0]} rst">${esc(k[1])}</span>`; };
const isLimited = () => S.data?.access?.scope === "requests" || !!S.data?.state?.limited;
const treatingDepts = () => (S.org?.departments || []).filter((d) => d.group === "treating");
const protoLabel = (id) => (S.protocols || []).find((p) => p.id === id)?.label || id || "";
const deptOptions = (list, sel = "") => list.map((d) => `<option value="${esc(d.id)}" ${d.id === sel ? "selected" : ""}>${esc(d.name)}</option>`).join("");
function referredFrom() {
  const acc = (S.data?.referral?.history || []).filter((r) => r.status === "accepted").slice(-1)[0];
  if (acc) return acc.from_name || deptName(acc.from);
  const oh = (S.data?.access?.owner_history || []).slice(-1)[0];
  return oh ? deptName(oh.from) : "another department";
}
async function openCaseSafe(id) {
  // a Case File from a link, the bell or the inbox: a refusal (another department's Case File, a referral already answered) is toasted
  const prev = S.data?.case?.case_id || null;
  S.tab = "ready";
  try { await openCase(id); } catch (e) { if (prev && S.caseId === id) S.caseId = prev; toast(/not found/i.test(e.message) ? "That Case File no longer exists" : e.message, 7000); }
}
async function reopenOrLeave() {
  // after an answer that may end this user's access (a declined referral): reopen the Case File, else go back to the start page
  try { await openCase(S.caseId, true); }
  catch (e) { S.caseId = null; S.data = null; MAIN_SECTIONS.forEach((x) => $("#" + x).classList.toggle("hidden", x !== "welcome")); loadCases(); }
}
function caseRowOwner(c) {
  const chips = [c.referral ? `<span class="chip c-warn" title="${esc(`Referral to ${deptName(c.referral)} waiting for an answer`)}">Referral waiting</span>` : "",
    c.linked ? `<span class="chip c-info" title="Linked Case Files of the same patient">${esc(c.linked)} linked</span>` : "",
    c.scope === "requests" ? `<span class="chip c-mute" title="Your department sees only the items it was asked about">asked</span>` : ""].filter(Boolean).join(" ");
  return c.owner_name || chips ? `<div class="s">${c.owner_name ? `<span title="Owning department">${esc(c.owner_name)}</span>` : ""}${c.owner_name && chips ? " " : ""}${chips}</div>` : "";
}
function ownerLineHTML() {
  const a = S.data.access; if (!a) return "";
  const ref = S.data.referral?.open, out = [];
  out.push(a.owner ? `Owner: <b>${esc(a.owner.name)}</b>` : `<span class="muted">No owning department yet</span>${can("set_owner") ? ` <select id="own-dept" aria-label="Owning treating department"><option value="">Choose the treating department</option>${deptOptions(treatingDepts())}</select> <button class="ghost sm" id="own-set">Set owner</button>` : ""}`);
  if ((a.participants || []).length) out.push(`Participating: ${a.participants.map((p) => esc(p.name)).join(", ")}`);
  (a.linked_cases || []).forEach((l) => out.push(`Linked Case File: <a href="#" data-opencase="${esc(l.case_id)}" title="${esc(`The same patient${l.reason ? ": " + l.reason : ""}${l.linked_at ? ", linked " + dmyd(l.linked_at) : ""}`)}">${esc(l.case_id)}</a> <span class="muted">(${esc([l.protocol ? protoLabel(l.protocol) : "no protocol yet", l.department_name].filter(Boolean).join(", "))})</span>`));
  if (ref) out.push(`<span class="chip c-warn" title="${esc(`Requested by ${ref.by} on ${ref.on}: ${ref.reason}`)}">Referral to ${esc(ref.to_name)} waiting</span>`);
  return `<div class="ownline small" id="c-owner">${out.map((x) => `<span>${x}</span>`).join("")}</div>`;
}
function bindOwnerLine(root) {
  $$("[data-opencase]", root).forEach((a) => (a.onclick = (e) => { e.preventDefault(); openCaseSafe(a.dataset.opencase); }));
  const set = $("#own-set", root);
  if (set) set.onclick = async () => {
    const department = $("#own-dept").value; if (!department) { toast("Choose the treating department that owns this Case File"); return; }
    set.disabled = true;
    try { await api(`/cases/${encodeURIComponent(S.caseId)}/owner`, { json: { department } }); toast(`${deptName(department)} now owns this Case File (audited)`); await openCase(S.caseId, true); }
    catch (e) { toast(e.message, 7000); set.disabled = false; }
  };
}
function ownershipCardHTML() {
  const a = S.data.access; if (!a) return "";
  const R = S.data.referral || {}, o = R.open, hist = (R.history || []).slice().reverse(), sugg = R.suggestions || [];
  const inPart = new Set((a.participants || []).map((p) => p.id));
  const addable = (S.org?.departments || []).filter((d) => d.id !== a.owner?.id && !inPart.has(d.id));
  const grp = (g, label) => { const l = addable.filter((d) => d.group === g); return l.length ? `<optgroup label="${label}">${deptOptions(l)}</optgroup>` : ""; };
  const parts = (a.participants || []).map((p) => `<div class="hisrow"><span><b>${esc(p.name)}</b> <span class="small muted">${[p.since && "since " + dmyd(p.since), p.by && "added by " + p.by, p.reason].filter(Boolean).map(esc).join(" · ")}</span></span>${can("manage_participants") ? `<button class="ghost sm" data-rmpart="${esc(p.id)}" title="The department no longer takes part in this Case File (audited)">Remove</button>` : ""}</div>`).join("");
  const open = o ? `<div class="banner warn small" id="ref-open"><b>Referral to ${esc(o.to_name)} requested by ${esc(o.by)} on ${esc(o.on)}</b>: ${esc(o.reason)}
      <div class="row">${can("answer_referral") ? `<button class="primary sm" id="ref-accept">Accept</button><button class="ghost sm" id="ref-decline">Decline</button>` : ""}${can("withdraw_referral") ? `<button class="ghost sm" id="ref-withdraw" title="Take the referral back before it is answered (audited)">Withdraw</button>` : ""}${!can("answer_referral") && !can("withdraw_referral") ? `<span class="muted">Waiting for ${esc(o.to_name)} to accept or decline.</span>` : ""}</div></div>` : "";
  const sug = sugg.map((s) => `<div class="banner warn small refsug" data-hisref="${esc(s.his_ref)}"><div>${esc(s.text)}</div>${s.encounter_number ? `<div class="muted">Encounter <span class="mono">${esc(s.encounter_number)}</span></div>` : ""}${can("refer") ? `<div class="row"><button class="primary sm" data-refsug="${esc(s.his_ref)}">Refer</button><button class="ghost sm" data-refsugx="${esc(s.his_ref)}" title="Do not follow the hospital system's referral for this Case File (audited; not suggested again)">Dismiss</button></div>` : ""}</div>`).join("");
  const hrow = (r) => `<div class="hisrow refrow-h"><span>${esc(r.from_name)} → ${esc(r.to_name)} · ${esc(r.on)} ${rChip(r.status)} <span class="small muted">requested by ${esc(r.by)}${r.answered_by && r.status !== "requested" ? `; ${esc(r.status)} by ${esc(r.answered_by)}${r.answered_on ? " on " + esc(r.answered_on) : ""}` : ""}${r.note ? `: "${esc(r.note)}"` : ""}${r.protocol_after ? ` · listed under ${esc(protoLabel(r.protocol_after))}` : ""}</span>${r.reason ? `<div class="small muted">Reason: ${esc(r.reason)}</div>` : ""}</span></div>`;
  const ohist = (a.owner_history || []).slice().reverse().map((h) => `<div class="hisrow"><span>${esc(deptName(h.from))} → ${esc(deptName(h.to))} <span class="small muted">on ${esc(dmyt(h.at))} by ${esc(h.by)}${h.referral ? " (referral " + esc(h.referral) + ")" : ""}</span></span></div>`).join("");
  const linked = (a.linked_cases || []).map((l) => `<div class="hisrow"><span><a href="#" data-opencase="${esc(l.case_id)}">${esc(l.case_id)}</a> <span class="small muted">${esc([l.protocol ? protoLabel(l.protocol) : "no protocol yet", l.department_name, l.linked_at && "linked " + dmyd(l.linked_at), l.reason].filter(Boolean).join(" · "))}</span></span></div>`).join("");
  return `<div class="card owncard" id="own-card"><h3>Ownership and referral${can("refer") ? `<span class="btns"><button class="ghost sm" id="btn-refer" title="When the signed records move the work-up to another treating department">Refer to another department</button></span>` : ""}</h3>
    <div class="muted small" style="margin-bottom:6px">The owning department's doctors act on this Case File; participating departments read and comment. A referral moves the Case File to another treating department once that department accepts it: it then owns the Case File and chooses the cancer protocol, and the earlier protocol's check is kept read-only.</div>
    <div class="kv small"><div>Owner</div><div id="own-name">${a.owner ? `<b>${esc(a.owner.name)}</b>` : `<span class="muted">No owning department yet</span>`}</div></div>
    ${open}
    ${sug ? `<h4 class="subh">Suggested by the hospital system</h4>${sug}` : ""}
    <h4 class="subh">Participating departments</h4>${parts || `<div class="small muted">None</div>`}
    ${can("manage_participants") && addable.length ? `<div class="inline addpart"><select id="part-dept" aria-label="Department to add"><option value="">Choose the department</option>${grp("treating", "Treating departments")}${grp("supporting", "Supporting departments")}</select><input id="part-reason" placeholder="Reason (optional)" maxlength="300" aria-label="Reason for adding the department"><button class="ghost sm" id="part-add">Add a department</button></div>` : ""}
    ${linked ? `<h4 class="subh">Linked Case Files of the same patient</h4>${linked}` : ""}
    ${hist.length ? `<h4 class="subh">Referral history</h4>${hist.map(hrow).join("")}` : ""}
    ${ohist ? `<h4 class="subh">Owner history</h4>${ohist}` : ""}</div>`;
}
function bindOwnership(root) {
  const card = $("#own-card", root); if (!card) return;
  bindOwnerLine(card);
  const cid = () => encodeURIComponent(S.caseId);
  const participants = async (body, what) => { try { await api(`/cases/${cid()}/participants`, { method: "PUT", json: body }); toast(what); await openCase(S.caseId, true); } catch (e) { toast(e.message, 7000); } };
  const add = $("#part-add", card);
  if (add) add.onclick = async () => {
    const d = $("#part-dept", card).value; if (!d) { toast("Choose the department to add"); return; }
    add.disabled = true; await participants({ add: [d], reason: $("#part-reason", card).value.trim() }, `${deptName(d)} takes part in this Case File (audited)`); add.disabled = false;
  };
  $$("[data-rmpart]", card).forEach((b) => (b.onclick = async () => {
    const d = b.dataset.rmpart;
    const v = await confirmDialog({ title: `Remove ${deptName(d)}`, intro: `${deptName(d)} no longer takes part in this Case File (read and comment).`, fields: [{ id: "reason", label: "Reason", type: "text" }], submit: "Remove", note: "Recorded with your name and the time in the audit log." });
    if (v) participants({ remove: [d], reason: v.reason }, `${deptName(d)} removed from the participating departments (audited)`);
  }));
  const refer = $("#btn-refer", card); if (refer) refer.onclick = () => referDialog({});
  $$("[data-refsug]", card).forEach((b) => (b.onclick = () => { const s = (S.data.referral?.suggestions || []).find((x) => x.his_ref === b.dataset.refsug); if (s) referDialog({ to: s.to, reason: s.reason, his_ref: s.his_ref, text: s.text }); }));
  $$("[data-refsugx]", card).forEach((b) => (b.onclick = async () => {
    const v = await confirmDialog({ title: "Dismiss the suggested referral", intro: "The hospital system's referral is not followed for this Case File and is not suggested again.", fields: [{ id: "note", label: "Reason", type: "textarea", required: true }], submit: "Dismiss", note: "Recorded with your name and the time in the audit log." });
    if (!v) return;
    try { await api(`/cases/${cid()}/referrals/suggestions/${encodeURIComponent(b.dataset.refsugx)}/dismiss`, { json: { note: v.note } }); toast("Suggested referral dismissed (audited)"); await openCase(S.caseId, true); }
    catch (e) { toast(e.message, 7000); }
  }));
  const o = S.data.referral?.open; if (!o) return;
  const acc = $("#ref-accept", card); if (acc) acc.onclick = () => acceptReferralDialog(S.caseId, o, S.data.case.hospital_level);
  const dec = $("#ref-decline", card); if (dec) dec.onclick = () => answerReferral(S.caseId, o, "decline", reopenOrLeave);
  const wd = $("#ref-withdraw", card); if (wd) wd.onclick = () => answerReferral(S.caseId, o, "withdraw", () => openCase(S.caseId, true));
}
function referDialog(pre = {}) {
  // V2 item 5.2: the owning department refers the Case File to another treating department, with a reason (the hospital system's own
  // referral pre-fills it); the receiving department accepts or declines
  const own = S.data.access?.owner, ds = treatingDepts().filter((d) => d.id !== own?.id);
  $("#modal-body").innerHTML = `<h3 style="color:#1f2933;margin-top:0">Refer to another department</h3>
    <div class="small muted">The receiving department sees the referral in its inbox and bell and accepts or declines it. On acceptance it owns the Case File and chooses the cancer protocol; ${esc(own?.name || "the referring department")} stays as a participating department (read and comment). The earlier protocol's Pre-Authorization check is kept as read-only history.</div>
    ${pre.text ? `<div class="banner warn small">${esc(pre.text)}</div>` : ""}
    <div class="form"><label for="rf-to">Treating department</label><select id="rf-to"><option value="">Choose the department</option>${deptOptions(ds, pre.to || "")}</select>
      <label for="rf-reason">Reason</label><textarea id="rf-reason" maxlength="1000" placeholder="What the signed records now say that moves the work-up to this department">${esc(pre.reason || "")}</textarea></div>
    <div class="small muted" style="margin-top:10px">Recorded with your name and the time in the audit log.</div>
    <div class="actions-row"><button class="ghost" data-closemodal>Cancel</button><button class="primary" id="rf-send">Send</button></div>`;
  $("#modal").classList.remove("hidden");
  $("#rf-send").onclick = async () => {
    const to = $("#rf-to").value, reason = $("#rf-reason").value.trim();
    if (!to) { toast("Choose the treating department"); return; }
    if (!reason) { toast("A referral needs a reason"); return; }
    const btn = $("#rf-send"); btn.disabled = true;
    try {
      await api(`/cases/${encodeURIComponent(S.caseId)}/referrals`, { json: { to, reason, ...(pre.his_ref ? { his_ref: pre.his_ref } : {}) } });
      $("#modal").classList.add("hidden"); toast(`Referral sent to ${deptName(to)} (audited)`); await openCase(S.caseId, true);
    } catch (e) { toast(e.message, 7000); btn.disabled = false; }
  };
}
function acceptReferralDialog(caseId, ref, level) {
  // V2 item 5.2: the receiving department accepts; with a protocol the Pre-Authorization runs again on the same records under it
  $("#modal-body").innerHTML = `<h3 style="color:#1f2933;margin-top:0">Accept the referral to ${esc(ref.to_name)}</h3>
    <div class="small muted">${esc(ref.from_name)} refers ${esc(ref.patient?.name || caseId)} (${esc(caseId)}${ref.uhid ? ", UHID " + esc(ref.uhid) : ""}) to ${esc(ref.to_name)}. Reason: ${esc(ref.reason)}</div>
    <div class="small muted" style="margin-top:6px">On acceptance ${esc(ref.to_name)} owns the Case File and ${esc(ref.from_name)} stays as a participating department (read and comment). The earlier protocol's Pre-Authorization check is kept as read-only history; under the chosen protocol the check runs again on the same records.</div>
    <div class="form"><label for="ra-note">Note <span class="muted" style="font-weight:400">(optional)</span></label><textarea id="ra-note" maxlength="500"></textarea>
      <label for="ra-prot">Cancer protocol for the new work-up</label><select id="ra-prot">${protoOpts()}</select>
      <label for="ra-setting">NCG setting (as recorded in the signed reports, chosen by the clinician)</label><select id="ra-setting"></select>
      <label for="ra-level">Hospital level (NCG tiers)</label><select id="ra-level">${levelOpts()}</select></div>
    <div class="small muted" style="margin-top:10px">Recorded with your name and the time in the audit log; ${esc(ref.from_name)} is told.</div>
    <div class="actions-row"><button class="ghost" data-closemodal>Cancel</button><button class="ghost" id="ra-later">Accept, choose the protocol later</button><button class="primary" id="ra-go">Accept and list under the chosen protocol</button></div>`;
  $("#modal").classList.remove("hidden");
  const fill = () => ($("#ra-setting").innerHTML = settingOpts($("#ra-prot").value));
  fill(); $("#ra-prot").onchange = fill;
  $("#ra-level").value = level || S.org?.hospital?.level || "essential";
  const go = async (withProtocol) => {
    const bs = [$("#ra-go"), $("#ra-later")]; bs.forEach((b) => (b.disabled = true));
    const body = { note: $("#ra-note").value.trim(), ...(withProtocol ? { protocol: $("#ra-prot").value, setting: $("#ra-setting").value, hospital_level: $("#ra-level").value } : {}) };
    try {
      const r = await api(`/cases/${encodeURIComponent(caseId)}/referrals/${encodeURIComponent(ref.id)}/accept`, { json: body });
      $("#modal").classList.add("hidden");
      toast(r.job ? `Accepted: ${ref.to_name} owns the Case File. The Pre-Authorization runs again under ${protoLabel(body.protocol)} on the same records...` : `Accepted: ${ref.to_name} owns the Case File. Choose the cancer protocol to start the Pre-Authorization check.`, 8000);
      S.tab = "ready"; await openCase(caseId, true);
      if (r.job) watchJob(r.job);
      loadNotifications(); refreshInboxCount();
    } catch (e) { toast(e.message, 7000); bs.forEach((b) => (b.disabled = false)); }
  };
  $("#ra-go").onclick = () => go(true);
  $("#ra-later").onclick = () => go(false);
}
async function answerReferral(caseId, ref, what, after) {
  // decline (the receiving department) or withdraw (the referring department), with an optional note; the other side is told
  const T = { decline: ["Decline the referral", `${ref.from_name} refers ${ref.patient?.name || caseId} to ${ref.to_name}. On declining, the Case File stays with ${ref.from_name}, which is told.`, "Decline", "Referral declined (audited)"],
    withdraw: ["Withdraw the referral", `The referral to ${ref.to_name} is taken back before it is answered; ${ref.to_name} is told.`, "Withdraw", "Referral withdrawn (audited)"] }[what];
  const v = await confirmDialog({ title: T[0], intro: T[1], fields: [{ id: "note", label: "Note", type: "textarea" }], submit: T[2], note: "Recorded with your name and the time in the audit log." });
  if (!v) return;
  try { await api(`/cases/${encodeURIComponent(caseId)}/referrals/${encodeURIComponent(ref.id)}/${what}`, { json: { note: v.note } }); toast(T[3]); loadNotifications(); refreshInboxCount(); await after(); }
  catch (e) { toast(e.message, 7000); }
}
const GH_ACT = { suggested: "Suggested (not sent)", pending: "Sent", overdue: "Overdue", completed: "Closed" };
function gateHistoryHTML() {
  // V2 item 5.2: the earlier protocol's gate and the requests open when it was archived, read-only (never re-checked, nothing to act on)
  const hs = S.data.state?.gate_history || []; if (!hs.length) return "";
  return hs.slice().reverse().map((h) => {
    const g = h.gate, reqs = g?.requirements || [], acts = h.actions || [];
    const head = `Earlier protocol (read-only history): ${protoLabel(h.protocol) || "no protocol"}${h.protocol_version ? " v" + h.protocol_version : ""}, ${h.setting_label || h.setting || "NCG setting not recorded"}, hospital level ${h.hospital_level || "essential"}, owned by ${h.owner_name || deptName(h.owner)}, archived ${dmyd(h.archived_at)}`;
    const row = (r) => { const s = STATUS[r.status] || STATUS.needs_review;
      return `<div class="hisrow"><span>${esc(r.label)} <span class="small muted">· Responsible Department: ${esc(r.department || "")}</span>${r.level && LEVEL[r.level] ? ` <span class="chip c-lvl">${esc(LEVEL[r.level][0])}</span>` : ""}</span><span class="chip ${s[0]}">${esc(s[1])}</span></div>`; };
    return `<details class="gatehist" data-protocol="${esc(h.protocol)}"><summary>${esc(head)}</summary>
      <div class="small muted" style="margin:4px 0 6px">Kept as it stood when ${esc(h.owner_name || deptName(h.owner))} referred the Case File${h.by ? ` (accepted by ${esc(h.by)})` : ""}. Nothing here is re-checked or actionable.</div>
      ${g ? `<div class="small">${esc(g.satisfied ?? "?")} of ${esc(g.total ?? "?")} counted records were satisfied.</div>${reqs.map(row).join("")}` : `<div class="small muted">No Pre-Authorization check was listed under it.</div>`}
      <h4 class="subh">Requests open at the time</h4>
      ${acts.length ? acts.map((x) => `<div class="hisrow"><span>${esc(x.label)} <span class="small muted">${esc([x.department, x.level_label].filter(Boolean).join(" · "))}${x.accession ? " · " + esc(x.accession) : ""}</span></span><span class="chip c-mute">${esc(GH_ACT[x.status] || x.status || "")}</span></div>`).join("") : `<div class="small muted">None</div>`}</details>`;
  }).join("");
}
function renderLimited() {
  // V2 item 5.1: a department that was only asked sees its requests (Acknowledge / Done as in its inbox) and the records in its scope
  const acts = S.data.state.actions || [], docs = S.data.documents || [];
  $("#tab-ready").innerHTML = `<div class="banner small" id="limited-note"><b>Your department sees only the items it was asked about in this Case File.</b> The requests sent to it and the records it produced or the requests name; the rest of the Case File stays with ${esc(S.data.access?.owner?.name || "the owning department")}.</div>
    <div class="grid2"><div><div class="card" id="req-card"><h3>Requests to your department <span class="muted small">${acts.length}</span></h3>
      ${acts.length ? acts.map((a) => a.source === "pre_authorization" ? requestHTML(a, true) : actionHTML(a)).join("") : `<div class="muted small">No requests.</div>`}</div></div>
    <div><div class="card"><h3>Records in your department's scope <span class="muted small">${docs.length}</span></h3>
      ${docs.length ? `<div class="tscroll"><table class="t">${DOC_HEAD}<tbody>${docs.map(docRow).join("")}</tbody></table></div>` : `<div class="muted small">No record in your department's scope yet.</div>`}</div></div></div>`;
  const root = $("#tab-ready");
  bindActions(root);
  $$("[data-ack], [data-done]", root).forEach((b) => (b.onclick = async () => { b.disabled = true; const what = b.dataset.ack ? "acknowledge" : "done";
    if (await answerRequest(S.caseId, b.dataset.ack || b.dataset.done, what)) { await openCase(S.caseId, true); loadNotifications(); refreshInboxCount(); } else b.disabled = false; }));
  $$("tr[data-doc]", root).forEach((tr) => (tr.onclick = (e) => { if (!e.target.closest("button")) openDoc(tr.dataset.doc); }));
  bindImages(root);
}
function inboxReferralsHTML(refs) {
  if (!refs.length) return "";
  const waiting = refs.filter((r) => r.status === "requested").length;
  const dir = { to: "to your department", from: "sent by your department", other: "" };
  const row = (r) => `<tr class="click" data-case="${esc(r.case_id)}" data-rid="${esc(r.id)}"><td data-l="Case File"><b>${esc(r.patient?.name || r.case_id)}</b><div class="small muted">${esc(r.case_id)}${r.patient?.agesex ? " · " + esc(r.patient.agesex) : ""}${r.board_date ? " · board " + dmyd(r.board_date) : ""}</div>
      ${r.uhid ? `<div class="small">UHID <span class="mono">${esc(r.uhid)}</span></div>` : ""}</td>
    <td data-l="Referral"><b>${esc(r.from_name)} to ${esc(r.to_name)}</b>${dir[r.direction] ? `<div class="small muted">${esc(dir[r.direction])}</div>` : ""}</td>
    <td class="small" data-l="Reason"><div class="pre">${esc(r.reason)}</div>${r.note ? `<div class="muted">Note: ${esc(r.note)}</div>` : ""}${r.protocol_after ? `<div class="muted">Listed under ${esc(protoLabel(r.protocol_after))}</div>` : ""}</td>
    <td class="small nowrap" data-l="By">${esc(r.by)}<div class="muted">${esc(r.on)}</div></td>
    <td data-l="Status">${rChip(r.status)}${r.answered_by && r.status !== "requested" ? `<div class="small muted">by ${esc(r.answered_by)}${r.answered_on ? " on " + esc(r.answered_on) : ""}</div>` : ""}</td>
    <td class="nowrap"><div class="ibtns">${r.can_answer ? `<button class="primary sm" data-racc="${esc(r.id)}" data-rcase="${esc(r.case_id)}">Accept</button><button class="ghost sm" data-rdec="${esc(r.id)}" data-rcase="${esc(r.case_id)}">Decline</button>` : ""}${r.can_withdraw ? `<button class="ghost sm" data-rwd="${esc(r.id)}" data-rcase="${esc(r.case_id)}">Withdraw</button>` : ""}</div></td></tr>`;
  return `<div class="card" id="ib-referrals"><h3>Referrals <span class="muted small">${waiting} waiting for an answer</span></h3>
    <div class="muted small" style="margin-bottom:6px">Tumour Board Case Files referred to or by your department. On acceptance the receiving department owns the Case File and chooses the cancer protocol; the referring department stays as a participating department (read and comment). Answered referrals stay listed for 7 days.</div>
    <div class="tscroll"><table class="t inbox-t"><thead><tr><th>Case File</th><th>Referral</th><th>Reason</th><th>By</th><th>Status</th><th>Actions</th></tr></thead><tbody>${refs.map(row).join("")}</tbody></table></div></div>`;
}
function bindInboxReferrals(refs, root = "#inbox", after = showInbox) {  // the inbox and the treating doctor's home (V2 item 7.1)
  const find = (b, k) => refs.find((r) => r.id === b.dataset[k] && r.case_id === b.dataset.rcase);
  $$(`${root} #ib-referrals tr[data-case]`).forEach((tr) => (tr.onclick = async (e) => { if (e.target.closest("button, details, a")) return; await openCaseSafe(tr.dataset.case); }));
  $$(`${root} [data-racc]`).forEach((b) => (b.onclick = (e) => { e.stopPropagation(); const r = find(b, "racc"); if (r) acceptReferralDialog(r.case_id, r, null); }));
  $$(`${root} [data-rdec]`).forEach((b) => (b.onclick = (e) => { e.stopPropagation(); const r = find(b, "rdec"); if (r) answerReferral(r.case_id, r, "decline", after); }));
  $$(`${root} [data-rwd]`).forEach((b) => (b.onclick = (e) => { e.stopPropagation(); const r = find(b, "rwd"); if (r) answerReferral(r.case_id, r, "withdraw", after); }));
}

// ------------------------------------------------------------------ board sessions and the Board room · V1 items 6.1 to 6.3
const SSTATUS = { planned: ["c-mute", "Planned"], in_session: ["c-info", "In session"], closed: ["c-ok", "Closed"] };
const ASTATUS = { waiting: ["c-mute", "Waiting"], current: ["c-info", "Current"], decided: ["c-ok", "Decided"] };
const AGSTATUS = { queued: ["c-mute", "Waiting to start"], running: ["c-info", "Preparing the brief"], ready: ["c-ok", "Brief ready"], no_documents: ["c-mute", "No documents"], error: ["c-bad", "Error"] };
const KIND = { brief_item: "Brief item", point_for_review: "Point for review", not_documented: "Not documented", no_documents: "No documents", answer: "Answer" };
let roomTimer = null;
function stopRoomPoll() { clearTimeout(roomTimer); roomTimer = null; }
function showOnly(id) {
  MAIN_SECTIONS.forEach((x) => $("#" + x).classList.toggle("hidden", x !== id));
  $$(".citem").forEach((el) => el.classList.remove("on"));
}
async function showSessions() {
  stopRoomPoll(); S.roomId = null;
  const r = await api("/sessions"); showOnly("sessions");
  const today = new Date().toISOString().slice(0, 10);
  $("#sessions").innerHTML = `<div class="case-head"><div><div class="eyebrow">During the board</div><h1>Board sessions</h1>
      <div class="muted">A board session takes the Case Files their owners marked ready for its date, in agenda order. The attendance sheet lists the board's heads first, then the departments of the Case Files; mark each present or absent and record the members present by name. When the session starts, the AI support agent of every head not recorded as present, and of every specialty marked absent, prepares its brief from the Case File records and its guideline pack (Indian sources first) and answers the board's questions; Radiation Oncology and Nuclear Medicine are on demand. An agent is role-specific support, never a member. The board decides.</div></div></div>
    ${r.can_manage ? `<div class="card form"><h3>New board session</h3>
      <label for="s-date">Board date</label><input type="date" id="s-date" value="${today}">
      <label for="s-title">Title (optional)</label><input id="s-title" placeholder="e.g. Thoracic Tumour Board">
      <label>Case Files listed for that date (agenda order; the ones their owners marked ready are ticked)</label><div id="s-cands" class="small muted"></div>
      <div style="margin-top:12px"><button class="primary" id="s-create">Create board session</button></div></div>` : ""}
    <div class="card"><h3>Agenda readiness and chase list <span class="muted small">before the board</span></h3>
      <div class="muted small" style="margin-bottom:6px">For a board date: which listed Case Files are ready, on track, at risk or blocked (from the Pre-Authorization check and the due dates of the open requests), and what to ask which department before the meeting.</div>
      <div class="dash-filters"><div><label>Board date</label><input type="date" id="ag-date" value="${today}"></div><button class="ghost sm" id="ag-go">Show</button></div>
      <div id="ag-out" class="small muted">Choose a board date.</div></div>
    <div class="card"><h3>Sessions <span class="muted small">${r.sessions.length}</span></h3>
      ${r.sessions.length ? `<table class="t"><thead><tr><th>Date</th><th>Title</th><th>Case Files</th><th>Status</th></tr></thead><tbody>${r.sessions.map((x) => `<tr class="click" data-sid="${esc(x.id)}"><td><b>${fmtDate(x.date)}</b></td><td>${esc(x.title || "Tumour Board")}<div class="small muted">${esc(x.id)} · created by ${esc(x.created_by || "")}</div></td><td>${x.cases}</td><td><span class="chip ${(SSTATUS[x.status] || SSTATUS.planned)[0]}">${(SSTATUS[x.status] || SSTATUS.planned)[1]}</span></td></tr>`).join("")}</tbody></table>` : `<div class="muted small">No board sessions yet.</div>`}</div>`;
  $$("#sessions tr[data-sid]").forEach((tr) => (tr.onclick = () => openSession(tr.dataset.sid)));
  const agendaGo = async () => {
    $("#ag-out").innerHTML = `<span class="spin"></span>`;
    try { const a = await api("/metrics/agenda?date=" + encodeURIComponent($("#ag-date").value)); $("#ag-out").innerHTML = readinessHTML(a, !!(S.me?.coordinator || S.me?.admin));
      $$("#ag-out tr[data-open]").forEach((tr) => (tr.onclick = (e) => { if (!e.target.closest("button")) openCase(tr.dataset.open); }));
      $$("#ag-out [data-remowner]").forEach((b) => (b.onclick = async (e) => { e.stopPropagation(); if (await remindOwner(b.dataset.remowner, b.dataset.patient)) agendaGo(); }));
      $$("#ag-out [data-remreq]").forEach((b) => (b.onclick = async (e) => { e.stopPropagation(); if (await remindRequest(b.dataset.case, b.dataset.remreq, !!b.dataset.sug, b.dataset.label)) agendaGo(); })); }
    catch (e) { $("#ag-out").textContent = e.message; }
  };
  $("#ag-go").onclick = agendaGo;
  const listedDates = [...new Set((S.cases || []).map((c) => c.board_date).filter(Boolean))].sort();
  if (listedDates.length) { $("#ag-date").value = listedDates.find((d) => d >= today) || listedDates[listedDates.length - 1]; if ($("#s-date")) $("#s-date").value = $("#ag-date").value; }
  agendaGo();
  if (!r.can_manage) return;
  const cands = async () => {
    const c = await api("/sessions/candidates?date=" + encodeURIComponent($("#s-date").value));
    const anyReady = c.cases.some((x) => x.ready);  // none marked: every listed Case File is ticked, as before V2
    const SUMM = { ready: ["c-ok", "Summary ready"], stale: ["c-warn", "Summary stale"], none: ["c-mute", "No summary"] };
    $("#s-cands").innerHTML = c.cases.length ? (anyReady ? "" : `<div class="small muted" style="margin-bottom:4px">No owner has marked a Case File ready for this date: all are ticked.</div>`) + c.cases.map((x, i) => { const sm = SUMM[x.summary] || SUMM.none;
      return `<label class="cand" data-cand-row="${esc(x.case_id)}"><input type="checkbox" data-cand="${esc(x.case_id)}" ${x.ready || !anyReady ? "checked" : ""}>
        <span><span>${i + 1}. <b>${esc(x.patient?.name || x.case_id)}</b> <span class="muted">${esc(x.case_id)} · ${esc(protoLabel(x.protocol))}${x.owner_name ? " · " + esc(x.owner_name) : ""}</span></span>
        <span class="chips">${x.ready ? `<span class="chip c-ok" title="${esc(x.ready.note ? "Note: " + x.ready.note : "")}">Ready (by ${esc(x.ready.by)})</span>` : `<span class="chip c-warn">Not marked ready by the owner</span>`}
          ${x.gate_passed ? `<span class="chip c-ok">Pre-Authorization met</span>` : `<span class="chip c-warn">Pre-Authorization ${x.gate?.total ? esc(x.gate.satisfied + "/" + x.gate.total) : "not evaluated"}</span>`}<span class="chip ${sm[0]}">${sm[1]}</span></span></span></label>`; }).join("")
      : `No Case File is listed for the board on ${fmtDate($("#s-date").value)}. List Case Files with this board date first (open a Case File, Change listing).`;
  };
  $("#s-date").onchange = cands; cands();
  $("#s-create").onclick = async () => {
    const ids = $$("[data-cand]").filter((x) => x.checked).map((x) => x.dataset.cand);
    try { const s = await api("/sessions", { json: { date: $("#s-date").value, title: $("#s-title").value, case_ids: ids } }); toast("Board session created"); openSession(s.id); }
    catch (e) { toast(e.message, 7000); }
  };
}
async function openSession(sid, caseId) {
  const r = await api("/sessions/" + encodeURIComponent(sid));
  const first = S.roomId !== sid;
  S.room = r; S.roomId = sid; showOnly("sessions");
  const ids = r.session.agenda.map((a) => a.case_id);
  if (caseId && ids.includes(caseId)) S.roomCase = caseId;
  else if (first || !ids.includes(S.roomCase)) S.roomCase = r.session.current || ids[0];
  renderRoom(); pollRoom();
}
function pollRoom() {
  stopRoomPoll();
  const busy = Object.values(S.room?.session.agents || {}).some((by) => Object.values(by).some((x) => ["queued", "running"].includes(x.status)));
  if (busy) roomTimer = setTimeout(async () => {
    if (!S.roomId || $("#sessions").classList.contains("hidden")) return;
    try { S.room = await api("/sessions/" + encodeURIComponent(S.roomId)); refreshRoom(); } catch (e) { /* the next open shows the error */ }
    pollRoom();
  }, 3000);
}
// re-render the parts that change while agents work, keeping what the user is typing
function keepInputs(root, fn) {
  const vals = {}; let focus = document.activeElement?.id;
  $$("input[id], textarea[id], select[id]", root).forEach((el) => (vals[el.id] = el.value));
  fn();
  Object.entries(vals).forEach(([id, v]) => { const el = document.getElementById(id); if (el && el.type !== "checkbox") el.value = v; });
  if (focus && document.getElementById(focus)) document.getElementById(focus).focus();
}
function refreshRoom() {
  keepInputs($("#room-agents"), () => { $("#room-agents").innerHTML = agentsHTML(); bindAgents(); });
  $("#room-agenda").innerHTML = agendaHTML(); bindAgenda();
  $("#room-log").innerHTML = logHTML(); bindLog();
}
function roomCase() { return S.room.cases[S.roomCase] || {}; }
function renderRoom() {
  const r = S.room, s = r.session, st = SSTATUS[s.status] || SSTATUS.planned, c = roomCase();
  const m = r.can_manage;
  $("#sessions").innerHTML = `<div class="case-head"><div><div class="eyebrow">Board room · ${esc(s.id)}</div><h1>${esc(s.title || "Tumour Board")} · ${fmtDate(s.date)} <span class="chip ${st[0]}">${st[1]}</span></h1>
      <div class="muted">${s.agenda.length} Case File${s.agenda.length === 1 ? "" : "s"} · created by ${esc(s.created_by || "")}${s.started_at ? ` · started ${esc(s.started_at.replace("T", " ").slice(0, 16))}` : ""}${s.closed_at ? ` · closed ${esc(s.closed_at.replace("T", " ").slice(0, 16))}` : ""}</div>
      <div class="room-btns">${m && s.status === "planned" ? `<button class="primary sm" id="r-start" title="The AI support agents of the heads not recorded as present and of the absent specialties prepare their briefs for every Case File on the agenda">Start session</button>` : ""}
        ${m && s.status === "in_session" ? `<button class="ghost sm" id="r-close">Close session</button>` : ""}
        <button class="ghost sm" id="r-export" title="What the agents said and what the board decided, side by side (reporting only)">Export agent log and decisions</button>
        <button class="ghost sm" id="r-minutes" title="Attendance, the decisions as dictated, the actions and their follow-up (what people recorded; no model output)">Minutes</button>
        <button class="ghost sm" id="r-back">All board sessions</button></div></div></div>
    <div class="room"><div>
      <div class="card"><h3>Agenda</h3><div id="room-agenda">${agendaHTML()}</div></div>
      <div class="card"><h3>Attendance</h3><div id="room-att">${attendanceHTML()}</div></div>
    </div><div>
      ${c.missing ? `<div class="card"><div class="refusal">This Case File no longer exists.</div></div>` : c.restricted ? `<div class="card" id="room-case"><div class="eyebrow">${esc(protoLabel(c.protocol))}</div><h2 style="margin:4px 0">${esc(S.roomCase)}</h2>
        <div class="refusal" id="room-restricted">Restricted: another department's Case File${c.owner_name ? ` (owner: ${esc(c.owner_name)})` : ""}. Its records, summary and briefs are not shown to your department.</div>${seatHTML(c)}</div>` : `
      <div class="card" id="room-case"><div class="eyebrow">${esc(protoLabel(c.protocol))}</div><h2 style="margin:4px 0">${esc(c.patient?.name || S.roomCase)}</h2>
        <div class="muted small">${esc(S.roomCase)}${c.patient?.mrn ? " · UHID / MRN " + esc(c.patient.mrn) : ""}${c.patient?.agesex ? " · " + esc(c.patient.agesex) : ""}${c.owner_name ? " · Owner: " + esc(c.owner_name) : ""}${(c.linked_cases || []).length ? " · Linked: " + c.linked_cases.map(esc).join(", ") : ""}</div>
        <div class="chips" style="margin-top:6px">${c.gate?.passed ? `<span class="chip c-ok">Readiness criteria met</span>` : `<span class="chip c-warn">Pre-Authorization ${c.gate?.total ? c.gate.satisfied + "/" + c.gate.total : "not evaluated"}</span>`}
          ${c.ready ? readyChip(c.ready) : `<span class="chip c-warn">Not marked ready by the owner</span>`}
          <button class="ghost sm" id="r-open">Open Case File</button></div>
        ${seatHTML(c)}</div>
      <div class="card summary"><h3>Case File summary</h3>${roomSummaryHTML(c)}</div>
      <div class="card" id="room-records-card"><h3>Records <span class="muted small">${(c.records || []).length}</span></h3><div id="room-records">${recordsHTML(c)}</div></div>
      <div class="card"><h3>AI support <span class="muted small">role-specific, AI draft; the board decides</span></h3><div id="room-agents">${agentsHTML()}</div></div>
      <div class="card"><h3>Board decision</h3><div id="room-decision">${decisionHTML()}</div></div>
      ${followupHTML()}
      <div class="card"><h3>What the agents said and what the board decided <span class="muted small">reporting only</span></h3><div id="room-log">${logHTML()}</div></div>`}
    </div></div>`;
  if ($("#r-start")) $("#r-start").onclick = async () => { try { const x = await api(`/sessions/${s.id}/start`, { method: "POST" }); toast(x.preparing ? `Session started. ${x.preparing} brief(s) being prepared for the heads not recorded as present and the absent specialties.` : "Session started. Every head is recorded present and no specialty is marked absent: no agent to prepare.", 7000); openSession(s.id); } catch (e) { toast(e.message, 7000); } };
  if ($("#r-close")) $("#r-close").onclick = async () => { if (!confirm("Close this board session? Decisions and marks can still be recorded afterwards.")) return; try { await api(`/sessions/${s.id}/close`, { method: "POST" }); openSession(s.id); } catch (e) { toast(e.message, 7000); } };
  $("#r-back").onclick = showSessions;
  const download = async (path, name, done) => {
    const x = await fetch(`/api/tb/sessions/${encodeURIComponent(s.id)}/${path}?format=html`, { credentials: "same-origin" });
    if (!x.ok) { toast(x.statusText, 7000); return; }
    const blob = await x.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${s.id}_${name}.html`; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000); toast(done);
  };
  $("#r-export").onclick = () => download("export", "agent_log_and_decisions", "Exported; recorded in the audit log");
  $("#r-minutes").onclick = () => download("minutes", "minutes", "Minutes downloaded; recorded in the audit log");
  if ($("#r-open")) $("#r-open").onclick = () => openCase(S.roomCase);
  bindAgenda(); bindAttendance(); bindAgents(); bindDecision(); bindLog(); bindRecords();
}
function agendaHTML() {
  const s = S.room.session, m = S.room.can_manage && s.status === "in_session";
  return s.agenda.map((a, i) => { const c = S.room.cases[a.case_id] || {}, st = ASTATUS[a.status] || ASTATUS.waiting;
    return `<div class="agenda ${a.case_id === S.roomCase ? "on" : ""}" data-rc="${esc(a.case_id)}"><div class="t"><span>${i + 1}. ${esc(c.patient?.name || a.case_id)}</span><span class="chip ${st[0]}">${st[1]}</span></div>
      <div class="small muted">${esc(a.case_id)} · ${esc(c.protocol || "")}${c.owner_name ? " · " + esc(c.owner_name) : ""}${c.restricted ? ' · <span class="chip c-mute">Restricted</span>' : ""}${a.owner_ready === false ? ' <span class="chip c-warn" title="Put on the agenda without the owner\'s ready mark">Not marked ready by the owner</span>' : ""}${m && s.current !== a.case_id ? ` · <button class="ghost sm" data-cur="${esc(a.case_id)}">Make current</button>` : ""}</div></div>`; }).join("");
}
function bindAgenda() {
  $$("#room-agenda [data-rc]").forEach((el) => (el.onclick = (e) => { if (e.target.closest("[data-cur]")) return; S.roomCase = el.dataset.rc; renderRoom(); }));
  $$("#room-agenda [data-cur]").forEach((b) => (b.onclick = async () => { try { await api(`/sessions/${S.roomId}/current`, { json: { case_id: b.dataset.cur } }); openSession(S.roomId, b.dataset.cur); } catch (e) { toast(e.message, 7000); } }));
}
const ATT = { present: ["c-ok", "Present"], absent: ["c-warn", "Absent"], not_marked: ["c-mute", "Not marked"] };
function attendanceHTML() {
  // V2 item 6.1: the session's attendance sheet (heads first, then on demand, the hospital's list, the Case Files' departments)
  const r = S.room, s = r.session, m = r.can_manage && s.status !== "closed";
  const att = (d) => s.attendance?.[d.id] || "not_marked";
  const stands = (d) => d.role && (att(d) === "absent" || (d.head && att(d) !== "present"));
  const list = r.attendance_list || [];
  return `<table class="t att" id="att-list"><thead><tr><th>Department</th><th>Attendance</th></tr></thead><tbody>${list.map((d) => `<tr data-dept="${esc(d.id)}"><td><b>${esc(d.name)}</b>${d.head ? ' <span class="chip c-info att-head">Head</span>' : ""}${d.on_demand ? ' <span class="chip c-mute" title="AI support on demand: the board asks for a brief during the session">On demand</span>' : ""}
        <div class="small muted">${esc(d.why || "")}${d.role ? ` · ${esc(r.roles[d.role]?.label || d.role)}` : ""}${stands(d) ? ' · <span class="chip c-info">AI support stands in</span>' : ""}</div></td>
      <td>${m ? `<select data-att="${esc(d.id)}" aria-label="Attendance of ${esc(d.name)}">${Object.entries(ATT).map(([v, x]) => `<option value="${v}" ${att(d) === v ? "selected" : ""}>${x[1]}</option>`).join("")}</select>`
        : `<span class="chip ${ATT[att(d)][0]}">${ATT[att(d)][1]}</span>`}</td></tr>`).join("")}</tbody></table>
    <h4 style="margin:12px 0 6px">Members present</h4>
    <div id="att-members">${(s.members || []).map((x) => `<span class="chip c-lvl" style="margin:2px">${esc(x.name)} (${esc(deptName(x.department))})${m ? ` <button class="x" data-rmm="${esc(x.id)}" aria-label="Remove ${esc(x.name)}">×</button>` : ""}</span>`).join("") || `<span class="small muted">None recorded.</span>`}</div>
    ${m ? `<div class="arow memrow" style="margin-top:8px"><input id="m-name" placeholder="Name, e.g. Dr. A. Rao" aria-label="Member name"><select id="m-dept" aria-label="Department">${[...list, ...r.specialties.filter((d) => !list.some((x) => x.id === d.id)), { id: "coordinator", name: "MDT Coordinator" }].map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("")}</select><button class="ghost sm" id="m-add">Add</button></div>
      <div class="small muted" style="margin-top:4px">Adding a member marks the department present.</div>` : ""}
    <div class="small muted" style="margin-top:8px">An AI support agent stands in for a head not recorded as present or a specialty marked absent, only as role-specific support; it is never counted as a member.</div>`;
}
function bindAttendance() {
  const sid = S.roomId;
  $$("[data-att]").forEach((sel) => (sel.onchange = async () => { try { await api(`/sessions/${sid}/attendance`, { json: { department: sel.dataset.att, status: sel.value } }); openSession(sid, S.roomCase); } catch (e) { toast(e.message, 7000); } }));
  $$("[data-rmm]").forEach((b) => (b.onclick = async () => { try { await api(`/sessions/${sid}/members/${b.dataset.rmm}`, { method: "DELETE" }); openSession(sid, S.roomCase); } catch (e) { toast(e.message, 7000); } }));
  if ($("#m-add")) $("#m-add").onclick = async () => { if (!$("#m-name").value.trim()) return; try { await api(`/sessions/${sid}/members`, { json: { name: $("#m-name").value, department: $("#m-dept").value } }); openSession(sid, S.roomCase); } catch (e) { toast(e.message, 7000); } };
}
function seatHTML(c) {
  // V2 items 6.2 / 6.4: who fills the surgical seat for this Case File; the PM-JAY note never blocks
  const x = c.seat; if (!x) return "";
  const who = x.filled ? `filled by ${esc((x.members || []).join(", ") || "a surgeon recorded present")} (${esc((x.filled_by_names || []).join(", "))})` : "no surgeon recorded present: the Surgical Oncology agent stands in (AI support, never a member)";
  const pm = x.check_pmjay && S.room.pmjay_empanelled ? ` <span class="chip c-warn" id="r-seat-pmjay" title="A surgeon from a department outside the hospital's PM-JAY surgical oncology list fills the seat; HBP 2.2 names a Surgical Oncologist">check PM-JAY requirement</span>` : "";
  return `<div class="small seatline" id="r-seat"><b>Surgical seat:</b> ${who}${pm}${!x.filled && (x.own_surgical_names || []).length ? ` <span class="muted">(a surgeon of ${esc(x.own_surgical_names.join(" or "))} or Surgical Oncology fills it)</span>` : ""}</div>`;
}
function recordsHTML(c) {
  // V2 item 6.3: the Case File's records during the board; Open shows the drawer, Open images the hospital's viewer (people view, no model reads)
  const rs = c.records || [];
  if (!rs.length) return `<div class="muted small">No processed record in the Case File.</div>`;
  return `<div class="small muted" style="margin-bottom:6px">${IMG_NOTE}. Open images goes through this app to the hospital's image viewer and is audited.</div>
    <div class="tscroll"><table class="t" id="rec-list"><thead><tr><th>Record</th><th>Date</th><th>Status</th><th></th></tr></thead><tbody>${rs.map((d) => { const h = d.his, hs = h && HSTAT[h.status], ids = h ? [h.encounter_number, h.accession].filter(Boolean) : [];
      return `<tr data-rec="${esc(d.doc_id)}"${d.superseded ? ' class="superseded"' : ""}><td><b>${esc(d.title || d.doc_id)}</b><div class="small muted">${esc(DT[d.doc_type] || d.doc_type || "")}${d.department ? " · " + esc(deptName(d.department)) : ""}</div>${ids.length ? `<div class="mono small" title="OP / IP No. and accession No. in the hospital system">${esc(ids.join(" · "))}</div>` : ""}</td>
        <td class="small nowrap">${d.date ? esc(dmyd(d.date)) : '<span class="muted">not found</span>'}</td>
        <td><div class="chips">${hs ? `<span class="chip ${hs[0]}" title="Report status in the hospital system">${hs[1]}</span>` : d.status ? `<span class="chip ${/final/i.test(d.status) ? "c-ok" : "c-warn"}">${esc(d.status)}</span>` : ""}${(h ? h.signed : d.signed === "yes") ? '<span class="chip c-ok">Signed</span>' : ""}${h ? '<span class="chip c-info">from HIS</span>' : ""}${d.outside ? '<span class="chip c-mute">Outside report</span>' : ""}${d.superseded ? '<span class="chip c-mute">History</span>' : ""}${d.study?.modality ? `<span class="chip c-lvl" title="${esc(d.study.instances ? plural(d.study.instances, "image") : "")}">${esc(d.study.modality)}</span>` : ""}</div></td>
        <td><div class="ibtns"><button class="ghost sm" data-recopen="${esc(d.doc_id)}">Open</button>${d.images ? imagesBtn(d.doc_id, S.roomCase) : ""}</div></td></tr>`; }).join("")}</tbody></table></div>`;
}
function bindRecords() {
  const box = $("#room-records"); if (!box) return;
  $$("[data-recopen]", box).forEach((b) => (b.onclick = () => { const cid = S.roomCase; openDoc(b.dataset.recopen, null, `/cases/${encodeURIComponent(cid)}/documents/${encodeURIComponent(b.dataset.recopen)}`).catch((e) => toast(e.message, 7000)); }));
  bindImages(box);
}
function followupHTML() {
  // V2 item 6.1: the Tumour Board actions the decisions of this session gave departments, and where they stand now
  const f = S.room.followup; if (!f) return "";
  return `<div class="card" id="room-followup"><h3>Follow-up <span class="muted small">${f.open} open · ${f.overdue} overdue · ${f.closed} closed</span></h3>
    ${f.actions.length ? `<div class="tscroll"><table class="t"><thead><tr><th>Case File</th><th>Responsible Department</th><th>Task</th><th>Due</th><th>Status</th></tr></thead><tbody>${f.actions.map((x) => `<tr><td class="small"><b>${esc(x.patient)}</b><div class="muted">${esc(x.case_id)}</div></td><td class="small">${esc(x.department)}</td><td class="small">${esc(x.task)}</td><td class="small nowrap">${x.due ? esc(dmyd(x.due)) : ""}</td>
      <td>${x.status === "completed" ? `<span class="chip c-ok">Closed</span>${x.completed ? `<div class="small muted">${esc(dmyt(x.completed))}</div>` : ""}` : x.overdue ? '<span class="chip c-bad">Overdue</span>' : '<span class="chip c-warn">Open</span>'}</td></tr>`).join("")}</tbody></table></div>` : `<div class="muted small">The decisions recorded so far gave no department an action.</div>`}</div>`;
}
function roomSummaryHTML(c) {
  const sm = c.summary;
  if (!sm) return `<div class="muted small">No Case File summary yet. Compile it on the Case File (Case File summary tab) before the board.</div>`;
  const rv = sm.review || {};
  return `${c.summary_stale ? `<div class="banner warn stale"><b>${esc(c.summary_stale)}.</b> Regenerate it on the Case File before the board relies on it.</div>` : ""}
    <div class="small muted">${rv.status === "reviewed" ? `Reviewed by ${esc(rv.by)}` : "AI draft · awaiting expert review"} · ${esc((sm.generated || "").replace("T", " "))}</div>
    ${(sm.sections || []).filter((x) => x.sentences.length).map((sec) => `<h4 style="margin:10px 0 2px">${esc(sec.title)}</h4><p style="margin:0">${sec.sentences.map((x) => `<span class="${approxCls(x, rv)}">${esc(x.text)} ${x.citations.map(citeHTML).join("")}${flagHTML(x)}</span>`).join(" ")}</p>`).join("")}
    ${sm.stage_as_recorded ? `<div class="stagebox"><b>Stage, as recorded in the ${esc(sm.stage_as_recorded.doc_title)}:</b> ${esc(sm.stage_as_recorded.value)}</div>` : ""}`;
}
function answersFor(role) { return (S.room.session.log || []).filter((e) => e.case_id === S.roomCase && e.role === role && e.kind === "answer").reverse(); }
function agentBlock(role, why, onDemand) {
  const r = S.room, s = r.session, c = roomCase();
  const ag = (s.agents?.[S.roomCase] || {})[role], b = (c.briefs || {})[role], label = r.roles[role]?.label || role, busy = ["queued", "running"].includes(ag?.status);
  const st = ag ? AGSTATUS[ag.status] || ["c-mute", ag.status] : b ? AGSTATUS.ready : ["c-mute", onDemand ? (s.status === "in_session" ? "Not asked for" : "On demand during the session") : s.status === "planned" ? "Prepared when the session starts" : "Not prepared"];
  const stale = (c.briefs_stale || {})[role];
  const brief = !b ? "" : b.no_documents ? noDocsHTML(b) : `${b.points_for_review.length ? `<h4>Points for review (not treatment recommendations)</h4><ul>${b.points_for_review.map((it) => `<li class="${approxCls(it, b.review)}">${esc(it.text)} ${it.citations.map(citeHTML).join("")}${flagHTML(it)}${(it.references || []).length ? `<div class="grefs">${it.references.map(refHTML).join("")}</div>` : ""}</li>`).join("")}</ul>` : `<div class="small muted">No points for review.</div>`}
    <details><summary class="small">Brief: ${b.sections.reduce((n, x) => n + x.items.length, 0)} cited item(s)${b.not_documented.length ? `, ${b.not_documented.length} not documented` : ""}</summary>${b.sections.map((x) => `<h4>${esc(x.heading)}</h4><ul>${x.items.map((it) => `<li class="${approxCls(it, b.review)}">${esc(it.text)} ${it.citations.map(citeHTML).join("")}${flagHTML(it)}</li>`).join("")}</ul>`).join("")}${b.not_documented.length ? `<h4>Not documented</h4><ul>${b.not_documented.map((x) => `<li class="muted">${esc(x)}</li>`).join("")}</ul>` : ""}</details>
    ${r.can_review ? removedHTML(b.removed) : ""}<div class="small muted">${esc((b.generated || "").replace("T", " "))} · ${esc(modelLabel(b.model))}${b.review?.status === "reviewed" ? ` · reviewed by ${esc(b.review.by)}` : " · AI draft"}</div>`;
  const ans = answersFor(role).map((e) => `<div class="qbox">${esc(e.question)}</div>${e.status === "answered" ? `<div class="answer">${(e.statements || []).map((x) => `<p>${esc(x.text)} ${(x.citations || []).map(citeHTML).join("")}${flagHTML(x)}</p>`).join("")}${(e.references || []).length ? `<div class="grefs">${e.references.map(refHTML).join("")}</div>` : ""}${e.model ? `<div class="small muted">${esc(modelLabel(e.model))} · AI draft</div>` : ""}</div>`
    : `<div class="refusal"><b>${e.status === "out_of_scope" ? "Outside the agent's scope." : "Not documented in the Case File."}</b> ${esc(e.text)}</div>`}${r.can_review ? removedHTML(e.removed) : ""}`).join("");
  const pending = (S.asking || {})[S.roomCase + ":" + role];
  const prep = r.can_manage && s.status === "in_session" && !busy ? `<button class="ghost sm" data-prep="${role}">${onDemand && !b && !ag ? "Prepare" : "Prepare again"}</button>` : "";
  const mayAsk = r.can_ask && s.status !== "closed" && c.protocol && (!onDemand || b);
  return `<div class="agent" id="ag-${role}" data-agent="${role}"><h4>${esc(label)} <span class="chip ${st[0]}">${busy ? '<span class="spin"></span> ' : ""}${esc(st[1])}</span>${ag?.reused ? ' <span class="small muted">(brief still current, reused)</span>' : ""}${prep}</h4>
    ${why ? `<div class="small muted agent-why">${esc(why)}</div>` : ""}
    ${ag?.status === "error" ? `<div class="refusal">${esc(ag.message || "The brief could not be prepared")}</div>` : ""}
    ${stale && !busy ? `<div class="banner warn stale"><b>${esc(stale)}.</b> Prepare the brief again before the board relies on it.</div>` : ""}
    ${brief}
    ${mayAsk ? `<div class="search" style="margin-top:10px"><input id="ask-${role}" placeholder="Ask the ${esc(label.replace(" support", ""))} agent about the records" autocomplete="off"><button class="primary sm" data-ask="${role}" ${pending ? "disabled" : ""}>${pending ? '<span class="spin"></span>' : "Ask"}</button></div>` : ""}
    ${b || !onDemand ? `<div class="small muted" style="margin-top:4px">AI support (role-specific): answers only from the Case File records and the specialty's guideline pack, every statement with a verified quote. No image reading, diagnosis or treatment advice. References are guideline text for the board to consult, Indian sources first; they are not facts about this patient and not a recommendation for this patient.</div>` : ""}
    ${ans}</div>`;
}
function agentsHTML() {
  // V2 item 6.2: the agents active for THIS Case File (a head not recorded present, a specialty marked absent, Surgical Oncology only when
  // the surgical seat is not filled for it), then Radiation Oncology and Nuclear Medicine on demand
  const r = S.room, s = r.session, c = roomCase();
  const roles = c.agents || [], heads = new Set((r.heads || []).map((h) => h.role).filter(Boolean)), od = (r.on_demand || []).filter((x) => !roles.includes(x));
  const why = (role) => { const d = r.roles[role]?.department, a = s.attendance?.[d] || "not_marked";
    if (role === "surgical_oncology" && a !== "absent") return "The surgical seat is not filled for this Case File" + (heads.has(role) ? "; the head is not recorded as present" : "");
    return a === "absent" ? "Absent" : heads.has(role) ? "Head not recorded as present" : "Absent"; };
  const active = roles.length ? roles.map((role) => agentBlock(role, why(role), false)).join("")
    : `<div class="muted small">Every head is recorded present and no specialty is marked absent for this Case File: no agent stands in. Mark absent specialties under Attendance: their agents prepare a brief${s.status === "in_session" ? " at once" : " when the session starts"}.</div>`;
  return `${active}${od.length ? `<div class="ondemand" id="room-ondemand"><h4 class="subh">On demand</h4><div class="small muted">The board may ask for these during the session; they answer from the records and their guideline pack like the others.</div>${od.map((role) => agentBlock(role, "", true)).join("")}</div>` : ""}`;
}
function bindAgents() {
  $$("[data-prep]").forEach((b) => (b.onclick = async () => { try { const x = await api(`/sessions/${S.roomId}/agents/prepare`, { json: { case_id: S.roomCase, role: b.dataset.prep, refresh: true } }); toast(`${x.preparing} brief(s) being prepared`); openSession(S.roomId, S.roomCase); } catch (e) { toast(e.message, 7000); } }));
  $$("[data-ask]").forEach((b) => {
    const role = b.dataset.ask, inp = $("#ask-" + role);
    const go = async () => {
      const q = inp.value.trim(); if (!q) return;
      const key = S.roomCase + ":" + role, cid = S.roomCase, sid = S.roomId;
      const hist = answersFor(role).filter((e) => e.status === "answered").slice(0, 2).reverse().flatMap((e) => [{ role: "user", content: e.question }, { role: "assistant", content: e.text }]);
      S.asking = S.asking || {}; S.asking[key] = true; refreshRoom(); $("#ask-" + role).value = q;
      try { const a = await api(`/sessions/${sid}/cases/${cid}/agents/${role}/ask`, { json: { question: q, history: hist } }); if ($("#ask-" + role)) $("#ask-" + role).value = ""; if (a.log_warning) toast(a.log_warning, 7000); }
      catch (e) { toast(e.message, 7000); }
      delete S.asking[key];
      if (S.roomId === sid) { S.room = await api("/sessions/" + encodeURIComponent(sid)); if (S.roomCase === cid) { refreshRoom(); if ($("#ask-" + role)) $("#ask-" + role).value = ""; } }
    };
    b.onclick = go; if (inp) inp.onkeydown = (e) => { if (e.key === "Enter") go(); };
  });
}
function decisionHTML() {
  const r = S.room, s = r.session, d = (s.decisions || {})[S.roomCase], c = roomCase();
  if (d) { const rec = (c.board_records || []).find((x) => x.id === d.board_record) || {};
    return `<p style="white-space:pre-wrap;margin-top:0">${esc(d.decision_text || "")}</p><div class="small muted">Recorded by ${esc(d.recorded_by || "")} · ${esc((d.recorded_at || "").replace("T", " ").slice(0, 16))} ·
      <span class="chip ${rec.resolution?.checks_complete !== false && (rec.status === "consistent" || rec.resolution?.final) ? "c-ok" : "c-rev"}">${rec.resolution?.checks_complete === false ? "Adjudication: a check did not run (open on the Case File)" : rec.status === "consistent" ? "Adjudication: consistent" : rec.resolution?.total && rec.resolution.final ? `Final: ${rec.resolution.total} flag(s) resolved` : `Adjudication: ${rec.resolution?.open ?? rec.flags ?? 0} flag(s) awaiting resolution`}</span>${(rec.version || 1) > 1 ? ` <span class="chip c-info">Amended: version ${rec.version}</span>` : ""} <button class="ghost sm" id="r-board">Open on the Case File</button></div>${compHTML(rec.composition)}
      <div class="small muted" style="margin-top:6px">Mark each agent point below: discussed, accepted or not relevant.</div>`; }
  if (!r.can_manage) return `<div class="muted small">The decision is recorded by the MDT Coordinator.</div>`;
  const depts = BOARD_DEPTS;
  return `<div class="form"><div class="muted small">Entered by the clinical team. The agent then checks the record (documentation, values against the signed sources, open Pre-Authorization items); it does not judge the clinical decision.</div>
    <label for="d-text">Decision recorded by the board</label><textarea id="d-text" placeholder="As decided and dictated by the board"></textarea>
    <label for="d-by">Recorded by</label><input id="d-by" placeholder="Name, role">
    <label for="d-part">Participants (from the attendance)</label><input id="d-part" value="${esc(r.participants?.text || "")}">
    <label for="d-corr">Report corrections or discrepancies raised (if any)</label><input id="d-corr">
    <label for="d-div">Divergent opinions (if any)</label><input id="d-div">
    <label>Actions (Responsible Department · task · due)</label><div id="d-acts"><div class="arow"><select>${depts.map((x) => `<option>${x}</option>`).join("")}</select><input placeholder="Task"><input type="date"></div></div>
    <label for="d-next">Next Tumour Board review</label><input type="date" id="d-next">
    <label for="d-outcome">Outcome</label><select id="d-outcome">${Object.entries(S.data?.outcomes || { decision: "Decision recorded", deferred: "Deferred: information awaited", referred: "Referred to another board or centre", not_discussed: "Not discussed: information missing" }).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join("")}</select>
    <div class="grid2"><div><label for="d-deferred">If deferred: what is awaited</label><input id="d-deferred"></div><div><label for="d-referred">If referred: to which board or centre</label><input id="d-referred"></div></div>
    <div class="grid2"><div><label for="d-intent">Intention to treat (as recorded)</label><select id="d-intent"><option value="">Not stated</option><option value="curative">Curative / radical</option><option value="palliative">Palliative</option></select></div><div><label for="d-trial">Clinical trial considered</label><select id="d-trial"><option value="">Not recorded</option><option value="yes">Yes</option><option value="no">No</option></select></div></div>
    <div style="margin-top:12px"><button class="primary" id="d-save">Record decision and run adjudication</button></div></div>`;
}
function bindDecision() {
  if ($("#r-board")) $("#r-board").onclick = async () => { S.tab = "board"; await openCase(S.roomCase, true); showTab("board"); };
  if (!$("#d-save")) return;
  $("#d-save").onclick = async () => {
    if (!$("#d-text").value.trim()) { toast("Write the board's decision first"); return; }
    const actions = $$("#d-acts .arow").map((x) => ({ department: x.children[0].value, task: x.children[1].value, due: x.children[2].value })).filter((a) => a.task);
    $("#d-save").innerHTML = `<span class="spin"></span> Adjudicating...`; $("#d-save").disabled = true;
    try { await api(`/sessions/${S.roomId}/cases/${S.roomCase}/decision`, { json: { decision_text: $("#d-text").value, recorded_by: $("#d-by").value, participants: $("#d-part").value,
        outcome_type: $("#d-outcome").value, deferred_reason: $("#d-deferred").value, referred_to: $("#d-referred").value, intent_as_recorded: $("#d-intent").value, trial_considered: $("#d-trial").value,
        report_corrections_raised: $("#d-corr").value, divergent_opinions: $("#d-div").value, actions, next_review: $("#d-next").value } });
      toast("Decision recorded, checked and linked to the agent log"); openSession(S.roomId, S.roomCase); }
    catch (e) { toast(e.message, 7000); $("#d-save").disabled = false; $("#d-save").textContent = "Record decision and run adjudication"; }
  };
}
function logHTML() {
  const r = S.room, s = r.session, decided = !!(s.decisions || {})[S.roomCase], m = r.can_manage && decided;
  const log = (s.log || []).filter((e) => e.case_id === S.roomCase && !e.superseded);
  if (!log.length) return `<div class="muted small">Nothing yet. The agents' briefs and their answers to the board's questions are kept here, with what the board made of each.</div>`;
  return `${decided ? "" : `<div class="small muted" style="margin-bottom:6px">Marks open once the board's decision is recorded.</div>`}<table class="t"><thead><tr><th>What the agent said</th><th>The board</th></tr></thead><tbody>${log.map((e) => `<tr class="${e.approximate ? "approx noprint" : ""}"><td>
      <div class="small muted">${esc(e.label || e.role)} · ${esc(KIND[e.kind] || e.kind)}${e.heading ? ` (${esc(e.heading)})` : ""}</div>${e.kind === "answer" ? `<div class="small"><b>Q:</b> ${esc(e.question)}</div>` : ""}
      <div>${esc(e.text)} ${(e.citations || []).map(citeHTML).join("")}${flagHTML(e)}</div></td>
      <td>${m ? Object.entries(r.marks).map(([k, l]) => `<button class="${e.mark === k ? "primary" : "ghost"} sm" data-mark="${esc(e.id)}" data-v="${k}" aria-pressed="${e.mark === k}">${esc(l)}</button>`).join(" ") : `<span class="chip ${e.mark ? "c-ok" : "c-mute"}">${esc(r.marks[e.mark] || "Not marked")}</span>`}
        ${e.mark_by ? `<div class="small muted">${esc(e.mark_by)}</div>` : ""}</td></tr>`).join("")}</tbody></table>`;
}
function bindLog() {
  $$("[data-mark]").forEach((b) => (b.onclick = async () => {
    const e = (S.room.session.log || []).find((x) => x.id === b.dataset.mark);
    try { await api(`/sessions/${S.roomId}/cases/${S.roomCase}/log/${b.dataset.mark}/mark`, { json: { mark: e?.mark === b.dataset.v ? null : b.dataset.v } }); S.room = await api("/sessions/" + encodeURIComponent(S.roomId)); refreshRoom(); }
    catch (err) { toast(err.message, 7000); }
  }));
}
document.addEventListener("click", (e) => { const x = e.target.closest("[data-open-session]"); if (x) openSession(x.dataset.openSession); });

// ------------------------------------------------------------------ a home per role · V2 item 7.1
// What each person sees first: the treating doctor its department's Case Files, Create from UHID, requests, referrals and notifications;
// the supporting doctor its inbox; the department admin its doctors; the MDT Coordinator the sessions, the readiness of the next board
// and the chase list; the root admin the organisation and its settings (with the first set-up question until it is answered once). One
// login with several roles sees the sections stacked, the clinical one first. The server builds the home (GET /home) from the roles in
// org.json and the Case Files the login may open; the V1 Case File page stays the work area.
const ROLE_LABEL = { treating: "Treating doctor", supporting: "Supporting department", coordinator: "MDT Coordinator", dept_admin: "Department admin", root_admin: "Root admin" };
const RELATION = { owner: ["c-ok", "Owned by my department"], participant: ["c-info", "Participating"], referred: ["c-warn", "Referred to my department"], asked: ["c-mute", "Asked"], open: ["c-mute", "No owner yet"] };
const HOME_ROLE_TEXT = {
  treating: "Your department's Case Files, with the Pre-Authorization check of each. Create a Case File from the patient's UHID, send the suggested requests, re-fetch, mark it ready for the board.",
  supporting: "Requests the treating doctors sent to your department. Acknowledge one when you take it up; once the report is signed in your own system send \"done\" back. A request closes by itself when the record arrives in the Case File.",
  coordinator: "Board sessions and agendas from the Case Files their owners marked ready, the readiness of the next board date and what to chase before the meeting.",
  dept_admin: "The doctor logins of the department you administer: create, set Doctor or Head, disable, remove. No clinical action as admin.",
  root_admin: "The hospital, its departments, the Tumour Board accounts and their roles, the hospital-system connection, the routing of each record. No clinical action.",
};
const welcomeHTML = (note = "") => `<div class="intro"><h1>Make the Tumour Board Case File complete, before the board.</h1>
  <p class="lead">Vaidyx checks every Case File against the records configured as mandatory for that cancer, confirms each report is the final signed version, finds the required fields inside each document with a verifiable source quote, routes gaps to the Responsible Department, and prepares a cited Case File summary and role-specific support for the board.</p>
  <div class="pillars"><div><b>Before the board</b><span>Pre-Authorization gate, gap routing, re-check</span></div><div><b>During the board</b><span>Ask the Case File, specialty support, cited summary</span></div><div><b>After the board</b><span>AI-assisted adjudication, follow-up tracking</span></div></div>
  ${note || `<p class="muted">Select a Case File on the left, or load a synthetic demo case.</p>`}</div>`;
const homeSec = (k, body, extra = "") => `<section class="home-sec" id="home-${k === "dept_admin" ? "deptadmin" : k === "root_admin" ? "root" : k}"><h2>${esc(ROLE_LABEL[k])}${extra}</h2><div class="muted small" style="margin-bottom:8px">${esc(HOME_ROLE_TEXT[k])}</div>${body}</section>`;
const readyBar = (c) => c.gate_passed ? `<span class="chip c-ok">Pre-Authorization met</span>` : c.readiness != null ? `<div class="bar" style="min-width:80px"><i style="width:${Number(c.readiness) || 0}%"></i></div><div class="small muted">${esc(c.readiness)}% of the records</div>` : c.listing === "awaiting_listing" ? `<span class="chip c-mute">Awaiting listing</span>` : `<span class="chip c-mute">Not checked yet</span>`;
function homeCaseRow(c, mine) {
  const rel = RELATION[c.relation];
  return `<tr class="click" data-open="${esc(c.case_id)}"><td data-l="Case File"><b>${esc(c.patient?.name || c.case_id)}</b><div class="small muted">${esc(c.case_id)}${c.patient?.agesex ? " · " + esc(c.patient.agesex) : ""}</div>${c.uhid ? `<div class="small">UHID <span class="mono">${esc(c.uhid)}</span></div>` : ""}</td>
    <td class="small" data-l="Protocol">${esc(protoLabel(c.protocol) || "no protocol yet")}${!mine && c.owner_name ? `<div class="muted">Owner: ${esc(c.owner_name)}</div>` : ""}${rel && rel[1] && !(mine && c.relation === "owner") ? `<div><span class="chip ${rel[0]}">${esc(rel[1])}</span></div>` : ""}</td>
    <td data-l="Pre-Authorization">${readyBar(c)}${c.open_actions ? `<div class="small muted">${plural(c.open_actions, "open request")}</div>` : ""}${c.suggested_unsent ? `<div class="small"><span class="chip c-warn">${plural(c.suggested_unsent, "suggested request")} not sent</span></div>` : ""}</td>
    <td class="small nowrap" data-l="Board date">${c.board_date ? esc(dmyd(c.board_date)) : '<span class="muted">not set</span>'}${c.ready ? `<div>${readyChip(c.ready)}</div>` : ""}</td>
    <td class="small">${[c.referral ? `<span class="chip c-warn" title="Referral waiting for an answer">Referral to ${esc(c.referral)} waiting</span>` : "", c.linked ? `<span class="chip c-info">${esc(c.linked)} linked</span>` : "", c.scope === "requests" ? `<span class="chip c-mute" title="Your department sees only the items it was asked about">limited view</span>` : ""].filter(Boolean).map((x) => `<div class="chips">${x}</div>`).join("")}</td></tr>`;
}
function homeTreatingHTML(h) {
  const t = h.treating, c = t.counts, mine = !h.roles?.admin;
  const tiles = `<div class="tiles">${tile(mine ? "My Case Files" : "Case Files", mine ? c.mine : c.visible, "", mine ? [c.participating ? plural(c.participating, "participating") : "", c.asked ? `${c.asked} asked about` : ""].filter(Boolean).join(", ") : "every Case File (admin)")}
    ${tile("Pre-Authorization met", c.gate_passed, "", mine ? `of ${c.mine} owned` : "")}${tile("Ready for the board", c.ready_marked, "", "marked by the owner")}
    ${tile("Suggested requests not sent", c.suggested_unsent, "", c.suggested_unsent ? "open the Case File to send them" : "")}
    ${tile("Referrals to answer", t.referrals_to_answer, "", c.referral_waiting ? `${plural(c.referral_waiting, "referral")} sent, waiting` : "")}
    ${t.inbox.departments.length ? tile("Requests to my department", t.inbox.open, "", `${t.inbox.overdue} overdue`) : ""}</div>`;
  const cases = t.cases.filter((x) => !["asked", "open"].includes(x.relation)), asked = t.cases.filter((x) => x.relation === "asked"), open = t.cases.filter((x) => x.relation === "open");
  const table = (rows) => `<div class="tscroll"><table class="t home-t"><thead><tr><th>Case File</th><th>Protocol</th><th>Pre-Authorization</th><th>Board date</th><th></th></tr></thead><tbody>${rows.map((x) => homeCaseRow(x, mine)).join("")}</tbody></table></div>`;
  return homeSec("treating", `${tiles}
    <div class="card"><h3>${mine ? "My Case Files" : "Case Files"} <span class="btns">${t.can_create ? `<button class="primary sm" id="hm-new">+ Create from UHID</button>` : ""}</span></h3>
      ${cases.length ? table(cases) : `<div class="muted small">No Case File of ${mine ? "your department" : "an owning department"} yet.${t.can_create ? " Create one from the patient's UHID (or IP / OP No.)." : ""}</div>`}
      ${open.length ? `<h4 class="subh">Case Files without an owning department <span class="muted small">${plural(open.length, "Case File")}, open to every placed account (V1 demo and manual Case Files)</span></h4>${table(open)}` : ""}
      ${asked.length ? `<h4 class="subh">Asked of my department <span class="muted small">${plural(asked.length, "Case File")}, limited view</span></h4>${table(asked)}` : ""}</div>
    ${t.referrals.length ? inboxReferralsHTML(t.referrals) : ""}
    ${t.inbox.departments.length ? `<div class="card"><h3>Requests to ${esc(t.inbox.departments.map((d) => d.name).join(", "))} <span class="btns"><button class="ghost sm" id="hm-inbox">Open the department inbox</button></span></h3>
      <div class="small">${t.inbox.open ? `<b>${t.inbox.open} open</b>${t.inbox.overdue ? `, <span class="chip c-bad">${t.inbox.overdue} overdue</span>` : ""}` : `<span class="muted">No open request to your department.</span>`}</div></div>` : ""}`,
    h.departments.filter((d) => d.group === "treating").map((d) => ` <span class="chip c-mute">${esc(d.name)}${d.role === "head" ? " (Head)" : ""}</span>`).join(""));
}
function homeSupportingHTML(h) {
  const s = h.supporting;
  const tiles = `<div class="tiles">${tile("Open requests", s.open, "", s.departments.map((d) => d.name).join(", "))}${tile("Overdue", s.overdue)}${tile("Taken up", s.departments.reduce((n, d) => n + d.acknowledged, 0), "", "acknowledged, not yet done")}${tile("Done, awaiting re-fetch", s.departments.reduce((n, d) => n + d.done, 0), "", "closes when the record arrives")}</div>`;
  return homeSec("supporting", `${tiles}${s.departments.map((d) => `<div class="card"><h3>${esc(d.name)} <span class="muted small">${d.open} open · ${d.overdue} overdue</span> <span class="btns"><button class="ghost sm" data-inbox>Open the department inbox</button></span></h3>
      ${d.requests.length ? `<div class="tscroll"><table class="t inbox-t"><thead><tr><th>Case File</th><th>Record needed</th><th>What is asked</th><th>Due</th><th>Status</th><th>Actions</th></tr></thead><tbody>${d.requests.map((q) => ibRow(q, d)).join("")}</tbody></table></div>${d.more ? `<div class="small muted" style="margin-top:6px">${plural(d.more, "more request")} in the department inbox.</div>` : ""}` : `<div class="muted small">No request to this department.</div>`}</div>`).join("")}`,
    h.departments.filter((d) => d.group === "supporting").map((d) => ` <span class="chip c-mute">${esc(d.name)}${d.role === "head" ? " (Head)" : ""}</span>`).join(""));
}
function homeCoordinatorHTML(h) {
  const c = h.coordinator, ag = c.agenda, s = c.sessions;
  const days = ag && ag.days_to_board != null ? (ag.days_to_board < 0 ? `${-ag.days_to_board} day(s) ago` : ag.days_to_board === 0 ? "today" : `in ${plural(ag.days_to_board, "day")}`) : "";
  const tiles = `<div class="tiles">${tile("Next board", c.next_board_date ? dmyd(c.next_board_date) : "none", "", days)}${tile("Case Files listed", ag ? ag.cases.length : 0, "", ag ? `${ag.counts.ready} ready, ${ag.counts.on_track} on track, ${ag.counts.at_risk} at risk, ${ag.counts.blocked} blocked` : "for the next board")}
    ${tile("Marked ready by owners", c.ready_marked, "", `${c.listed_total} listed in all${c.awaiting_listing ? `, ${c.awaiting_listing} awaiting listing` : ""}`)}${tile("Sessions", s.planned + s.in_session, "", `${s.planned} planned, ${s.in_session} in session, ${s.closed_n} closed`)}</div>`;
  const srow = (x) => `<tr class="click" data-open-session="${esc(x.id)}"><td><b>${fmtDate(x.date)}</b></td><td>${esc(x.title || "Tumour Board")}<div class="small muted">${esc(x.id)}</div></td><td>${x.cases}</td><td><span class="chip ${(SSTATUS[x.status] || SSTATUS.planned)[0]}">${(SSTATUS[x.status] || SSTATUS.planned)[1]}</span></td></tr>`;
  return homeSec("coordinator", `${tiles}
    <div class="card"><h3>Board sessions <span class="btns">${c.can_manage ? `<button class="primary sm" id="hm-sessions-new">Create board session</button>` : ""}<button class="ghost sm" id="hm-sessions">All sessions</button></span></h3>
      ${s.open.length ? `<div class="tscroll"><table class="t"><thead><tr><th>Date</th><th>Title</th><th>Case Files</th><th>Status</th></tr></thead><tbody>${s.open.map(srow).join("")}</tbody></table></div>` : `<div class="muted small">No open board session.${c.can_manage ? " Create one from the Case Files marked ready for a board date." : ""}</div>`}
      ${s.closed.length ? `<div class="small muted" style="margin-top:6px">Closed: ${s.closed.map((x) => `<a href="#" data-open-session="${esc(x.id)}">${esc(fmtDate(x.date))}${x.title ? " " + esc(x.title) : ""}</a>`).join(", ")}</div>` : ""}</div>
    <div class="card" id="hm-readiness"><h3>Readiness for ${c.next_board_date ? esc(dmyd(c.next_board_date)) : "the next board"} <span class="muted small">before the board</span></h3>
      ${ag ? readinessHTML(ag, !!(S.me?.coordinator || S.me?.admin)) : `<div class="muted small">No Case File is listed for a board date yet.</div>`}</div>`);
}
function homeDeptAdminHTML(h) {
  const d = h.dept_admin;
  const row = (x) => `<tr><td><b>${esc(x.display_name || x.username)}</b></td><td class="small">${esc(x.username)}</td><td>${x.role === "head" ? "Head" : "Doctor"}</td><td><div class="chips">${x.disabled ? '<span class="chip c-bad">Disabled</span>' : '<span class="chip c-ok">Active</span>'}${x.account === false ? '<span class="chip c-warn" title="No Vaidyx login with this name">no Vaidyx login</span>' : ""}</div></td></tr>`;
  return homeSec("dept_admin", d.departments.map((x) => `<div class="card"><h3>${esc(x.name)} <span class="chip c-mute">${x.group === "supporting" ? "Supporting" : "Treating"}</span> <span class="btns"><button class="primary sm" data-mydept="${esc(x.id)}">Manage doctors</button></span></h3>
      <div class="tiles">${tile("Doctors", x.doctors, "", `${plural(x.heads, "head")}`)}${tile("Disabled", x.disabled)}${x.no_login ? tile("Without a Vaidyx login", x.no_login) : ""}${tile("Department admins", x.admins)}</div>
      ${x.list.length ? `<div class="tscroll"><table class="t"><thead><tr><th>Name</th><th>Login</th><th>Role</th><th>Status</th></tr></thead><tbody>${x.list.map(row).join("")}</tbody></table></div>${x.doctors > x.list.length ? `<div class="small muted">${x.doctors - x.list.length} more under Manage doctors.</div>` : ""}` : `<div class="muted small">No one is placed in this department yet. Create the first doctor login under Manage doctors.</div>`}</div>`).join("") || `<div class="card"><div class="muted small">You administer no department.</div></div>`);
}
function homeRootHTML(h) {
  const r = h.root_admin, hs = r.hospital, a = r.accounts;
  const setup = r.setup_needed && meCan("manage_org") ? `<div class="card fs-card" id="hm-setup"><h3>First set-up <span class="chip c-warn">answer once</span></h3>
      <div class="muted small" style="margin-bottom:6px">Three questions before the first board. The PM-JAY board composition check (a surgical, a radiation and a medical oncologist present, HBP 2.2) runs only for an empanelled hospital; it flags, never blocks. Everything can be changed later under Organisation.</div>
      <div class="form"><div class="grid3">
        <div><label for="fs-name">Hospital name</label><input id="fs-name" value="${esc(hs.name || "")}" placeholder="As the hospital writes it"></div>
        <div><label for="fs-level">NCG level</label><select id="fs-level"><option value="essential" ${hs.level !== "optimal" ? "selected" : ""}>Essential</option><option value="optimal" ${hs.level === "optimal" ? "selected" : ""}>Optimal</option></select></div>
        <div><label>Is the hospital PM-JAY empanelled?</label><div class="radio-row"><label class="chk"><input type="radio" name="fs-pmjay" value="yes" ${hs.pmjay_empanelled !== false ? "checked" : ""}> Yes</label><label class="chk"><input type="radio" name="fs-pmjay" value="no" ${hs.pmjay_empanelled === false ? "checked" : ""}> No</label></div></div></div></div>
      <div class="actions-row"><button class="primary sm" id="fs-save">Save first set-up</button></div></div>` : "";
  const tiles = `<div class="tiles">${tile("Hospital", hs.name || "not named", "", `NCG ${esc(hs.level || "essential")}${hs.type ? ", " + hs.type : ""}`)}${tile("PM-JAY empanelled", hs.pmjay_empanelled === false ? "No" : "Yes", "", r.first_setup ? `set up ${dmyd(r.first_setup.at)} by ${esc(r.first_setup.by)}` : "default, not yet confirmed")}
    ${tile("Departments", r.departments.treating + r.departments.supporting, "", `${r.departments.treating} treating, ${r.departments.supporting} supporting${r.departments.placeholder_emails ? `, ${r.departments.placeholder_emails} with a placeholder email` : ""}`)}
    ${tile("Accounts", a.placed, "", `${a.doctors} doctors, ${a.dept_admins} department admins, ${a.coordinators} coordinator(s), ${a.root_admins} root admin(s)${a.disabled ? `, ${a.disabled} disabled` : ""}${a.no_login ? `, ${a.no_login} without a Vaidyx login` : ""}`)}
    ${tile("Hospital system", r.his.enabled ? "On" : "Off", "", r.his.label || r.his.url || "not configured")}${tile("Routes overridden", r.routes_overridden, "", "records routed by hand")}</div>`;
  return homeSec("root_admin", `${setup}${tiles}<div class="card"><h3>Organisation <span class="btns"><button class="primary sm" id="hm-org">Open the organisation</button>${S.me?.admin || S.me?.coordinator ? `<button class="ghost sm" id="hm-dash">Quality dashboard</button>` : ""}</span></h3>
      <div class="small muted">Board heads: ${esc(r.board_heads.join(", ") || "none")}. Hospital settings, departments and emails, accounts and roles, the hospital-system connection and the routing map are edited there; every change is audited.</div></div>`);
}
const HOME_HTML = { treating: homeTreatingHTML, supporting: homeSupportingHTML, coordinator: homeCoordinatorHTML, dept_admin: homeDeptAdminHTML, root_admin: homeRootHTML };
function homeNotificationsHTML(h) {
  const list = h.notifications || [];
  return `<section class="home-sec" id="home-notifications"><h2>Notifications ${h.unread ? `<span class="chip c-warn">${h.unread} unread</span>` : ""}</h2>
    <div class="card">${list.length ? list.map(ntfRow).join("") : `<div class="muted small">Nothing yet.</div>`}<div class="actions-row"><button class="ghost sm" id="hm-ntf-all">All notifications</button></div></div></section>`;
}
async function showHome() {
  stopRoomPoll(); S.roomId = null; showOnly("welcome");
  const box = $("#welcome");
  if (!S.me) { box.classList.remove("home"); box.innerHTML = welcomeHTML(); return; }
  if (!S.home) box.innerHTML = `<div class="card"><div class="muted small"><span class="spin"></span> Loading your home...</div></div>`;
  let h;
  try { h = await api("/home"); } catch (e) { box.classList.remove("home"); box.innerHTML = welcomeHTML(`<div class="card">${esc(e.message)}</div>`); return; }
  S.home = h;
  if (!h.sections.length) {
    box.classList.remove("home");
    box.innerHTML = welcomeHTML(`<div class="card"><h3>Your login has no Tumour Board role yet</h3><div class="muted small">Case Files are shown to accounts placed in a department (as a doctor), to the MDT Coordinator and to admins. Ask your department admin to place you, or the root admin for a role.</div></div>`);
    return;
  }
  box.classList.add("home");
  const roles = [...(h.roles?.admin ? ["Vaidyx admin"] : []), ...h.sections.map((k) => ROLE_LABEL[k])];
  box.innerHTML = `<div class="home-head"><div><div class="eyebrow">Home · ${esc(roles.join(" · "))}</div><h1>${esc(h.display_name || h.user)}</h1>
      <div class="muted small">${esc([h.departments.map((d) => `${d.name}${d.role === "head" ? " (Head)" : ""}`).join(", "), h.admin_of.length ? "admin of " + h.admin_of.map((d) => d.name).join(", ") : ""].filter(Boolean).join(" · ") || "Tumour Board")} · ${esc(dmyd(h.today))}</div></div>
    <div class="home-actions"><button class="ghost sm" id="hm-refresh" title="Reload the home">Refresh</button></div></div>
    ${h.sections.map((k) => HOME_HTML[k](h)).join("")}${homeNotificationsHTML(h)}`;
  bindHome(h);
}
function bindHome(h) {
  const on = (sel, fn) => { const el = $(sel); if (el) el.onclick = fn; };
  on("#hm-refresh", showHome); on("#hm-new", newCase); on("#hm-inbox", showInbox); on("#hm-sessions", showSessions); on("#hm-sessions-new", showSessions);
  on("#hm-org", () => showOrgPage()); on("#hm-dash", () => showDashboard()); on("#hm-ntf-all", async () => { await loadNotifications(); showNotifications(); });
  $$("#welcome [data-inbox]").forEach((b) => (b.onclick = showInbox));
  $$("#welcome [data-mydept]").forEach((b) => (b.onclick = () => showMyDept(b.dataset.mydept)));
  $$("#welcome tr[data-open]").forEach((tr) => (tr.onclick = (e) => { if (!e.target.closest("button, a, details")) openCaseSafe(tr.dataset.open); }));
  $$("#welcome [data-ntf]").forEach((el) => (el.onclick = async () => { try { await api("/notifications/read", { json: { ids: [el.dataset.ntf] } }); } catch (e) {} loadNotifications(); if (el.dataset.case) await openCaseSafe(el.dataset.case); else showHome(); }));
  if (h.supporting) bindInboxRows("#home-supporting", showHome);
  if (h.treating?.referrals?.length) bindInboxReferrals(h.treating.referrals, "#home-treating", showHome);
  // the coordinator chases from the home as from the Board sessions page (V2 item 6.1)
  $$("#hm-readiness [data-remowner]").forEach((b) => (b.onclick = async (e) => { e.stopPropagation(); if (await remindOwner(b.dataset.remowner, b.dataset.patient)) showHome(); }));
  $$("#hm-readiness [data-remreq]").forEach((b) => (b.onclick = async (e) => { e.stopPropagation(); if (await remindRequest(b.dataset.case, b.dataset.remreq, !!b.dataset.sug, b.dataset.label)) showHome(); }));
  on("#fs-save", async () => {
    const yes = $('input[name="fs-pmjay"]:checked');
    if (!yes) { toast("Answer whether the hospital is PM-JAY empanelled"); return; }
    try { await api("/org/setup", { json: { pmjay_empanelled: yes.value === "yes", name: $("#fs-name").value.trim(), level: $("#fs-level").value } }); toast("First set-up saved"); await loadOrg(); S.orgPage = null; showHome(); }
    catch (e) { toast(e.message, 8000); }
  });
}

// ------------------------------------------------------------------ boot
$$("#tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
$("#btn-new").onclick = newCase;
$("#btn-home").onclick = showHome;
$("#btn-cards").onclick = showCards;
$("#btn-skills").onclick = () => showSkills();
$("#btn-connectors").onclick = showConnectors;
$("#btn-dashboard").onclick = () => showDashboard();
$("#btn-org").onclick = () => showOrgPage();
$("#btn-mydept").onclick = () => showMyDept();
$("#btn-queue").onclick = showIntake;
$("#btn-inbox").onclick = showInbox;
$("#btn-bell").onclick = async () => { await loadNotifications(); showNotifications(); };  // fresh on open: a department may have answered since the last poll (V2 4.3)
$("#btn-sessions").onclick = showSessions;
(async () => {
  const pr = await api("/protocols"); S.protocols = pr.protocols; S.facts = pr.facts;
  await loadOrg(); bindIntakeUpload(); refreshQueueCount(); refreshInboxCount(); loadNotifications();
  if (S.me?.known || S.me?.admin) await loadCases();  // a login not placed in any department (a department admin, a root admin) sees no Case Files
  else { $("#case-list").innerHTML = `<div class="small muted">Case Files are shown to accounts placed in a department, to the MDT Coordinator and to admins.</div>`; $("#demo-list").innerHTML = ""; }
  loadModels(); setInterval(loadModels, 30000); setInterval(() => { loadNotifications(); refreshInboxCount(); }, 30000);
  const m = location.hash.match(/case=([\w.-]+)/); if (m) openCase(m[1]); else showHome();  // a home per role (V2 item 7.1)
})();

// small screens: the case list is a slide-over panel
(function () {
  const btn = document.getElementById("btn-side"); if (!btn) return;
  const set = (on) => { document.body.classList.toggle("side-open", on); btn.setAttribute("aria-expanded", on ? "true" : "false"); };
  btn.addEventListener("click", () => set(!document.body.classList.contains("side-open")));
  document.addEventListener("click", (e) => {
    if (!document.body.classList.contains("side-open")) return;
    if (e.target.closest(".side .citem, .side [data-demo], .side #btn-new, .side #btn-queue, .side #btn-inbox") || (!e.target.closest(".side") && !e.target.closest("#btn-side"))) set(false);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") set(false); });
  window.addEventListener("resize", () => { if (innerWidth > 860) set(false); });
})();
