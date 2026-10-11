// Vaidyx-TB frontend. Vanilla JS, same-origin only (CSP). All document-derived text is escaped before rendering.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { caseId: null, data: null, tab: "ready", cards: null, roles: null, protocols: null, chat: [], briefs: {}, me: null, org: null };
// permissions: the server decides (org.can on every route); the UI only hides what the current user may not do (V1 item 2.1)
const can = (k, id) => { const v = (S.data?.permissions || {})[k]; return v === true || !!(v && typeof v === "object" && id && v[id]); };
const meCan = (k) => !!S.me && (S.me.admin || (k === "create_case" ? S.me.coordinator : false));

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
  const d = await api("/cases"); S.demoList = d.demo;
  const awaiting = d.cases.filter((c) => c.listing?.status === "awaiting_listing");
  $("#case-list").innerHTML = (awaiting.length ? `<div class="small muted" style="margin:2px 0 6px">${awaiting.length} awaiting listing</div>` : "") + (d.cases.length ? d.cases.slice().sort((a, b) => (b.listing?.status === "awaiting_listing") - (a.listing?.status === "awaiting_listing")).map((c) => `
    <div class="citem ${c.case_id === S.caseId ? "on" : ""}" data-case="${esc(c.case_id)}">
      <div class="t"><span>${esc(c.patient?.name || c.case_id)}</span>${c.gate_passed ? '<span class="chip c-ok">Ready</span>' : c.readiness != null ? `<span class="chip c-warn">${c.readiness}%</span>` : c.listing?.status === "awaiting_listing" ? '<span class="chip c-mute">Awaiting listing</span>' : ""}</div>
      <div class="s">${esc(c.case_id)} · ${esc(c.protocol || "no protocol yet")} · ${c.documents} documents${c.open_actions ? ` · ${c.open_actions} open actions` : ""}</div>
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
  if (id !== S.caseId) { S.tab = "ready"; S.chat = []; }
  S.caseId = id; S.data = await api("/cases/" + encodeURIComponent(id));
  $("#welcome").classList.add("hidden"); $("#intake").classList.add("hidden"); $("#inbox").classList.add("hidden"); $("#case").classList.remove("hidden");
  const c = S.data.case, p = c.patient || {};
  $("#c-protocol").textContent = (S.protocols?.find((x) => x.id === c.protocol)?.label || c.protocol) + " · Tumour Board Case File";
  $("#c-title").textContent = p.name || c.case_id;
  const setLabel = S.protocols?.find((x) => x.id === c.protocol)?.settings?.find((x) => x.id === c.setting)?.label;
  $("#c-meta").textContent = [c.case_id, p.mrn && "UHID / MRN " + p.mrn, p.agesex, c.listing?.status === "awaiting_listing" ? "Awaiting listing: no Pre-Authorization check until the coordinator lists it" : "", setLabel && "NCG setting: " + setLabel,
    c.hospital_level && "Hospital level: " + c.hospital_level, c.board_date && "Board " + fmtDate(c.board_date)].filter(Boolean).join(" · ");
  $("#c-actions").innerHTML = can("list_case") ? `<button class="${c.listing?.status === "awaiting_listing" ? "primary" : "ghost"} sm" id="btn-list">${c.listing?.status === "awaiting_listing" ? "List for the board" : "Change listing"}</button>` : "";
  if ($("#btn-list")) $("#btn-list").onclick = listCase;
  renderReadiness();
  const unlisted = c.listing?.status === "awaiting_listing";
  $$("#tabs button").forEach((b) => b.classList.toggle("hidden", unlisted && ["roles", "summary", "board"].includes(b.dataset.tab)));
  if (unlisted && ["roles", "summary", "board"].includes(S.tab)) S.tab = "ready";
  if (!keepTab) S.tab = S.tab || "ready";
  showTab(S.tab);
  loadCases();
}

function renderReadiness() {
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
const flagHTML = (x) => (x.flags || []).map((f) => `<span class="chip c-warn" title="The cited source contains a negation (no / not / negative / absent) that this sentence does not; read the source before relying on it.">${esc(f)}</span>`).join("");
function citeHTML(c) {
  const label = `${c.doc_title || c.doc_id}${c.date ? " · " + fmtDate(c.date) : ""}`;
  return `<span class="cite" data-doc="${esc(c.doc_id)}" data-page="${c.page ?? ""}" data-start="${c.start ?? ""}" data-end="${c.end ?? ""}" title="&quot;${esc(c.quote)}&quot;">${esc(label)}</span>`;
}
document.addEventListener("click", (e) => {
  const c = e.target.closest(".cite");
  if (c) openDoc(c.dataset.doc, c.dataset.page !== "" ? { page: +c.dataset.page, start: +c.dataset.start, end: +c.dataset.end } : null);
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
    return `<span class="cite" data-doc="${esc(e.doc_id)}" title="${esc(e.quote || "")}">${esc(e.value ? `${S.facts?.[e.fact]?.label || e.fact}: ${e.value}` : (cl.title || e.doc_id))}${docDates(cl).event ? " · " + fmtDate(docDates(cl).event) : ""}</span>`;
  }).join("");
  const needs = r.needs || (r.status === "needs_confirmation" && r.evidence[0]?.doc_id ? [{ type: "attest_final", doc_id: r.evidence[0].doc_id }] : []);
  const attest = needs.filter((n) => can("confirm", n.doc_id)).map((n) => n.type === "attest_final" ? `<button class="ghost sm" data-attest="${esc(n.doc_id)}">Attest: final, signed</button>`
    : n.type === "confirm_dates" ? `<button class="ghost sm" data-confdate="${esc(n.doc_id)}">Confirm date</button>`
    : n.type === "confirm_doc_type" ? `<button class="ghost sm" data-conftype="${esc(n.doc_id)}">Confirm document type</button>` : "").join("");
  const waive = shown || !can("waive", r.id) ? "" : r.status === "waived" ? `<button class="ghost sm" data-unwaive="${esc(r.id)}">Remove waiver</button>` : (r.status !== "satisfied" && r.status !== "not_applicable") ? `<button class="ghost sm" data-waive="${esc(r.id)}" title="Clinical decision that this record is not required for this Case File (audited)">Waive</button>` : "";
  const tier = TIER[r.tier] || TIER.a;
  const lvl = r.level && !shown ? ` <span class="chip c-lvl" title="${esc(LEVEL[r.level][1])}">${LEVEL[r.level][0]}</span>` : "";
  const chip = shown && r.status !== "satisfied" && r.status !== "not_applicable" ? `<span class="chip c-mute" title="Shown for information: not counted at this hospital level or in this setting">${esc(s[1])} (not counted)</span>` : `<span class="chip ${s[0]}">${s[1]}</span>`;
  return `<div class="req ${shown ? "shown" : ""}"><div class="icon ${s[2]}">${s[3]}</div><div style="flex:1">
    <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap"><span class="lbl">${esc(r.label)} <span class="chip ${tier[0]}" title="${esc(r.tier_note || r.tier_label || "")}">${tier[1]}</span>${lvl}</span><span style="display:flex;gap:4px;align-items:center;flex-wrap:wrap">${attest}${waive}${chip}</span></div>
    <div class="dept">Responsible Department: ${esc(r.department)}${r.tier_note ? " · " + esc(r.tier_note) : ""}</div>
    ${r.problems.map((p) => `<div class="prob">${esc(p)}</div>`).join("")}${(r.notes || []).map((p) => `<div class="prob muted">${esc(p)}</div>`).join("")}${ncgLine(r)}<div class="ev">${ev}</div></div></div>`;
}
function renderReady() {
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
  } else reqs = `<div class="muted">Not evaluated yet. Add documents to start.</div>`;
  const blockers = g?.blockers?.length ? `<div class="banner bad"><b>${g.blockers.length} document${g.blockers.length > 1 ? "s" : ""} failed to read</b> and block the Pre-Authorization until re-processed or dismissed (a dismissal needs a reason and is audited; the Case File can then pass without that document).
    ${g.blockers.map((b) => `<div class="row"><span>${esc(b.filename)}: <span class="muted">${esc(b.error)}</span></span>${can("reprocess") ? `<button class="ghost sm" data-reproc-doc="${esc(b.doc_id)}">Re-process</button>` : ""}${can("confirm", b.doc_id) ? `<button class="ghost sm" data-dismiss="${esc(b.doc_id)}">Dismiss</button>` : ""}</div>`).join("")}</div>` : "";
  const opt = g ? g.optional.map((o) => `<span class="chip ${o.available ? "c-info" : "c-mute"}" style="margin:2px">${o.available ? "✓ " : ""}${esc(o.label)}</span>`).join("") : "";
  const acts = (state.actions || []).filter((a) => a.source === "pre_authorization");
  const actHTML = acts.length ? acts.sort((a, b) => (a.status === "completed") - (b.status === "completed")).map(actionHTML).join("") : `<div class="muted small">No gaps routed.</div>`;
  const docs = g?.documents || {};
  const setting = g ? `NCG setting: <b>${esc(g.setting_label || "not recorded (the strictest tier of each record applies until the coordinator records it)")}</b> · Hospital level: <b>${esc(g.hospital_level || "essential")}</b> · Protocol ${esc(g.protocol)} v${esc(g.protocol_version || "")}` : "";
  $("#tab-ready").innerHTML = `<div class="grid2"><div>
    <div class="card"><h3>Pre-Authorization check <span><button class="ghost sm" id="btn-recheck">Re-check now</button></span></h3>
      <div class="muted small" style="margin-bottom:6px">Required records from the NCG Essential / Optimal / Optional tiers for this cancer and setting (clinical review before real use). A record counts only when it is the final, signed version and its required primary fields are found with a verified source quote. Document exists ≠ Document is ready.</div>
      ${setting ? `<div class="small" style="margin-bottom:4px">${setting}</div>` : ""}${g?.tiers_note ? `<div class="muted small" style="margin-bottom:6px">${esc(g.tiers_note)}</div>` : ""}
      ${blockers}${orphanHTML(g)}${reqs}</div>
    ${g?.core_data?.length ? `<div class="card"><h3>MDT minimum core data <span class="muted small">${g.core_data.filter((c) => c.present).length} of ${g.core_data.length} documented</span></h3>
      <div class="muted small" style="margin-bottom:6px">Informational checklist (not part of the gate). Source: ${esc(g.core_data_source || "")}.</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">${g.core_data.map((c) => c.present ? `<span class="cite" data-doc="${esc(c.evidence[0]?.doc_id || "")}" title="${esc((c.evidence[0]?.value || "") + " | " + (c.evidence[0]?.quote || ""))}">✓ ${esc(c.label)}</span>` : `<span class="chip c-mute">– ${esc(c.label)}</span>`).join("")}</div></div>` : ""}
    <div class="card"><h3>Optional records available</h3><div>${opt || '<span class="muted small">None</span>'}</div></div>
    ${confirmationsHTML()}
    ${g?.policy_basis ? `<div class="card"><h3>Why a Pre-Authorization gate</h3><div class="small" style="color:#475569">${esc(g.policy_basis)}</div>${g.pmjay_note ? `<div class="small muted" style="margin-top:6px">${esc(g.pmjay_note)}</div>` : ""}</div>` : ""}
  </div><div>
    <div class="card"><h3>Routed requests <span class="muted small">${acts.filter((a) => a.status !== "completed").length} open</span></h3>
      <div class="muted small" style="margin-bottom:8px">Every gap becomes a request to the department that can act on it: a Level 1 gap to the department that owns the record, a Level 2 gap to the department that uploaded the record. Requests close by themselves when the record arrives; the department sees them in its inbox and the bell. The agent routes the gap; it does not perform the missing clinical task.</div>${actHTML}</div>
    <div class="card"><h3>${can("upload") ? "Add documents" : "Documents"}</h3>
      ${can("upload") ? `<div class="drop" id="drop">Drop files or a whole folder here<br><span class="small">PDF, scanned images (PNG / JPG / TIFF), text and Office files</span><br>
      <button class="ghost sm" id="pick-files" style="margin-top:8px">Choose files</button> <button class="ghost sm" id="pick-folder">Choose folder</button></div>
      <input type="file" id="f-files" multiple class="hidden"><input type="file" id="f-folder" webkitdirectory multiple class="hidden">` : `<div class="muted small">Department users upload through "Upload for my department" in the side panel; records are matched to the patient and filed here.</div>`}
      <div id="job"></div>
      ${can("upload") && (S.demoList || []).some((x) => x.case_id === S.caseId && x.has_arrivals) ? `<button class="ghost sm" id="btn-arrivals" style="margin-top:10px">Demo: new reports arrive from departments</button>` : ""}
      <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">${can("reprocess") && docs.errors ? `<button class="ghost sm" id="btn-reproc-err">Re-process ${docs.errors} failed</button>` : ""}${can("reprocess") ? `<button class="ghost sm" id="btn-reproc-all" title="Re-read, re-classify and re-extract every document (after a protocol or model change)">Re-process all documents</button>` : ""}<a class="ghost sm" href="/api/tb/cases/${esc(S.caseId)}/export">Export Case File record</a></div>
      <div class="muted small" style="margin-top:10px">${docs.total || 0} documents · ${docs.ready || 0} processed${docs.processing ? ` · ${docs.processing} processing` : ""}${docs.errors ? ` · ${docs.errors} failed to read${docs.dismissed?.length ? ` (${docs.dismissed.length} dismissed)` : ""}` : ""}${docs.identity_flags?.length ? ` · <b style="color:#b23a2f">${docs.identity_flags.length} identity flags</b>` : ""}</div>
    </div></div></div>`;
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
  $$("[data-attest]", $("#tab-ready")).forEach((b) => (b.onclick = () => attestDoc(b.dataset.attest)));
  if ($("#drop")) bindUpload();
  const arr = $("#btn-arrivals");
  if (arr) arr.onclick = async () => { try { const j = await api(`/cases/${S.caseId}/demo-arrivals`, { method: "POST" }); watchJob(j.job); } catch (e) { toast(e.message); } };
  bindActions($("#tab-ready"));
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
function confirmDialog({ title, intro, fields = [], submit = "Record" }) {
  // Returns a promise of {field: value} or null. Every field: {id, label, type: text|textarea|select|date, options: [[value, label]], required, value, placeholder}
  return new Promise((resolve) => {
    const f = (x) => x.type === "textarea" ? `<textarea id="cd-${x.id}" placeholder="${esc(x.placeholder || "")}">${esc(x.value || "")}</textarea>`
      : x.type === "select" ? `<select id="cd-${x.id}">${(x.options || []).map(([v, l]) => `<option value="${esc(v)}" ${v === x.value ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`
      : `<input id="cd-${x.id}" type="${x.type === "date" ? "date" : "text"}" value="${esc(x.value || "")}" placeholder="${esc(x.placeholder || "")}">`;
    $("#modal-body").innerHTML = `<h3 style="color:#1f2933;margin-top:0">${esc(title)}</h3>${intro ? `<div class="small muted">${esc(intro)}</div>` : ""}
      <div class="form">${fields.map((x) => `<label>${esc(x.label)}${x.required ? "" : ' <span class="muted" style="font-weight:400">(optional)</span>'}</label>${f(x)}`).join("")}</div>
      <div class="small muted" style="margin-top:10px">Recorded with your name and the time in the audit log. It can be undone; the record of both stays.</div>
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
      <span class="small muted">by ${esc(c.by)} ${esc((c.at || "").slice(0, 16).replace("T", " "))}</span> ${can("undo_confirmation", c.id) ? `<button class="ghost sm" data-undo="${esc(c.id)}" title="${c.type === "confirm_match" && c.fields?.case_id ? "The document goes back to the Needs matching queue" : "Undo this confirmation"}">${c.type === "confirm_match" && c.fields?.case_id ? "Undo: back to matching" : "Undo"}</button>` : ""}</div>`).join("")}</div>`;
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
async function waiveReq(reqId) {
  const r = S.data.state.gate?.requirements?.find((x) => x.id === reqId);
  const v = await confirmDialog({ title: "Waive a requirement for this Case File", intro: `Clinical decision that "${r?.label || reqId}" is not required for this Case File. It leaves the Pre-Authorization check for this Case File only.`,
    fields: [{ id: "reason", label: "Reason", type: "textarea", required: true, placeholder: "e.g. CT done at the referring hospital, report in the file" }], submit: "Waive" });
  if (!v) return;
  await recordConfirmation("waive", reqId, {}, v.reason);
}
function actionHTML(a) {
  return `<div class="action ${a.status}"><div class="h"><span>${esc(a.label)}${a.level ? ` <span class="chip c-lvl" title="${esc((LEVEL[a.level] || [])[1] || "")}">${esc(a.level_label || (LEVEL[a.level] || [])[0] || "")}</span>` : ""}</span><span class="chip ${a.status === "completed" ? "c-ok" : a.status === "overdue" ? "c-bad" : "c-warn"}">${a.status === "completed" ? "Completed" : a.status === "overdue" ? "Overdue" : "Pending"}</span></div>
    <div class="w">${esc(a.what)}</div>
    <div class="f"><span>Responsible Department: <b>${esc(a.department)}</b> · due ${fmtDate(a.due)}</span>
    ${a.status !== "completed" ? `<span><button class="ghost sm" data-req="${a.id}">Request message</button> ${can("update_action", a.id) ? `<button class="ghost sm" data-act="${a.id}" data-st="completed">Mark completed</button>` : ""}</span>` : `<span>${a.completed ? "closed " + esc(a.completed.slice(0, 16).replace("T", " ")) : ""}</span>`}</div>
    ${a.history?.length > 1 ? `<details class="small muted"><summary>History</summary>${a.history.map((h) => `<div>${esc(h.ts.slice(0, 16).replace("T", " "))} ${esc(h.event)}</div>`).join("")}</details>` : ""}</div>`;
}
function requestText(a) {
  const c = S.data.case, p = c.patient || {};
  return `Tumour Board Case File ${c.case_id}: ${p.name || ""}${p.mrn ? ", UHID " + p.mrn : ""}${p.agesex ? ", " + p.agesex : ""}
To: ${a.department}
Required before the Tumour Board${c.board_date ? " on " + fmtDate(c.board_date) : ""}: ${a.label}${a.level_label ? " (" + a.level_label + ")" : ""}
Details: ${a.what}
Please upload the final, signed report to the Case File by ${fmtDate(a.due)}. The Case File is re-checked automatically when it arrives.
(Generated by Vaidyx Tumour Board assistant, action ${a.id})`;
}
function bindActions(root) {
  $$("[data-req]", root).forEach((b) => (b.onclick = () => {
    const a = (S.data.state.actions || []).find((x) => x.id === b.dataset.req);
    $("#modal-body").innerHTML = `<h3 style="color:#1f2933;margin-top:0">Request to ${esc(a.department)}</h3><textarea id="reqtxt" style="width:100%;min-height:190px;padding:10px;border:1px solid #d9e2ec;border-radius:8px">${esc(requestText(a))}</textarea>
      <div style="text-align:right;margin-top:10px"><button class="ghost" data-closemodal>Close</button> <button class="primary" id="reqcopy">Copy</button></div>`;
    $("#modal").classList.remove("hidden");
    $("#reqcopy").onclick = async () => { try { await navigator.clipboard.writeText($("#reqtxt").value); toast("Copied"); } catch (e) { $("#reqtxt").select(); toast("Select and copy the text"); } };
  }));
  $$("[data-act]", root).forEach((b) => (b.onclick = async () => {
    const note = prompt("Note for the record (optional):") ?? "";
    await api(`/cases/${S.caseId}/actions/${b.dataset.act}`, { json: { status: b.dataset.st, note } });
    await openCase(S.caseId, true);
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
      toast(`Processed ${j.total} documents in ${j.seconds} s. Pre-Authorization re-checked: ${j.gate.satisfied}/${j.gate.total} satisfied.${extra ? " " + extra + "." : ""}`, 7000);
      await openCase(S.caseId, true); loadNotifications(); refreshInboxCount(); break;
    }
    await new Promise((r) => setTimeout(r, 700));
  }
}

// ------------------------------------------------------------------ tab: documents
function renderDocs() {
  const docs = S.data.documents;
  $("#tab-docs").innerHTML = `<div class="card"><h3>Documents in the Case File <span class="muted small">${docs.length}</span></h3>
  <table class="t"><thead><tr><th>Document</th><th>Type</th><th>Date</th><th>Status</th><th>Read by</th><th>Fields found</th></tr></thead><tbody>
  ${docs.map((d) => { const c = d.classification || {}; const nf = Object.values(d.facts || {});
    const att = (S.data.state.overrides?.documents || {})[d.doc_id];
    const st = d.state !== "ready" ? `<span class="chip ${d.state === "error" ? "c-bad" : "c-info"}" title="${esc(d.error || "")}">${d.state === "error" ? "failed to read" : esc(d.state)}</span>${d.state === "error" ? `<div class="small muted">${esc(d.error || "")}</div>${d.dismissed ? `<span class="chip c-mute" title="${esc(d.dismissed.reason || "")}">dismissed by ${esc(d.dismissed.by || "")}</span>` : `<span class="chip c-warn" title="A document that failed to read blocks the Pre-Authorization until it is re-processed or dismissed">blocks the gate</span>`}` : ""}` : statusChip(c) + (att?.attested_final ? ` <span class="chip c-ok" title="${esc(att.reason || "")}">attested final by ${esc(att.by)}</span>` : "");
    const unst = d.state === "ready" && c.status === "UNSTATED" && c.signed !== "no" && !att?.attested_final;
    return `<tr class="click" data-doc="${esc(d.doc_id)}"><td><b>${esc(c.title || d.filename)}</b><div class="small muted">${esc(d.rel_path)}${d.department ? ` · uploaded by ${esc(deptName(d.department))}${d.uploaded_by ? " (" + esc(d.uploaded_by) + ")" : ""}` : ""}${d.identity === "mismatch_or_missing" ? ' · <span style="color:#b23a2f">patient ID not found</span>' : d.identity === "id_differs" ? ' · <span style="color:#b23a2f">prints an identifier this Case File does not know</span>' : d.identity === "name_match" ? ' · <span style="color:#8a5300">matched by name only</span>' : ""}</div></td>
      <td>${esc(DT[c.doc_type] || c.doc_type || "")}${c.doc_type_disagreement ? ` <span class="chip c-warn" title="${esc(c.doc_type_disagreement.note || "")}">keywords say ${esc(DT[c.doc_type_disagreement.keyword_type] || c.doc_type_disagreement.keyword_type)}</span>` : ""}</td><td>${dateCell(c)}</td><td>${st}</td>
      <td class="small">${(d.methods || []).map((m) => (m === "vision-transcription" ? "Vision reader (scan)" : m === "text-layer" ? "PDF text layer" : m)).join(", ")}${(d.page_flags || []).map((f) => ` <span class="chip c-warn" title="Transcribed as is, never translated into facts; values from these lines need a person's check">${esc(f)}</span>`).join("")}</td>
      <td>${nf.filter((f) => f.verification === "verified").length} verified${nf.filter((f) => f.verification !== "verified").length ? ` · <span class="chip c-rev">${nf.filter((f) => f.verification !== "verified").length} not verified</span>` : ""}
      <div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap">${d.state === "error" && can("reprocess") ? `<button class="ghost sm" data-reproc-doc="${esc(d.doc_id)}">Re-process</button>` : ""}${d.state === "error" && !d.dismissed && can("confirm", d.doc_id) ? `<button class="ghost sm" data-dismiss="${esc(d.doc_id)}" title="Record, with a reason, that the Case File may pass without this document (audited, undoable)">Dismiss</button>` : ""}${unst && can("confirm", d.doc_id) ? `<button class="ghost sm" data-attest-doc="${esc(d.doc_id)}">Attest final</button>` : ""}${d.state === "ready" && (docDates(c).unconfirmed || docDates(c).flags.length) && can("confirm", d.doc_id) ? `<button class="ghost sm" data-confdate="${esc(d.doc_id)}">Confirm date</button>` : ""}${d.state === "ready" && c.doc_type_disagreement && !c.doc_type_confirmed_by && can("confirm", d.doc_id) ? `<button class="ghost sm" data-conftype="${esc(d.doc_id)}">Confirm type</button>` : ""}${can("unfile", d.doc_id) ? `<button class="ghost sm" data-unfile-doc="${esc(d.doc_id)}" title="Not this patient: move the record back to the Needs matching queue (audited, the Case File forgets what it learned from it)">Back to matching</button>` : ""}${can("delete_document", d.doc_id) ? `<button class="ghost sm" data-del-doc="${esc(d.doc_id)}" title="Remove this document from the Case File (audited)">Remove</button>` : ""}</div></td></tr>`; }).join("")}
  </tbody></table></div>
  <div class="card"><h3>Primary fields across the Case File</h3><div class="muted small" style="margin-bottom:8px">Current value = most recent verified value from a final, signed document. Every value links to its source quote.</div>
  <table class="t"><thead><tr><th>Field</th><th>Current value</th><th>Source</th><th>History</th></tr></thead><tbody>
  ${Object.entries(S.data.facts).map(([k, f]) => { const c = f.current;
    return `<tr><td>${esc(f.label)}</td><td><b>${esc(c.value)}</b> ${c.state === "pending" ? '<span class="chip c-warn">pending</span>' : ""}${c.verification !== "verified" ? '<span class="chip c-rev">' + esc(c.verification) + "</span>" : ""}${!c.doc_final ? '<span class="chip c-bad">non-final doc</span>' : ""}</td>
      <td>${c.verification === "confirmed" ? `<span class="chip c-ok" title="Read by the clinician in the source document; no model quote">confirmed by ${esc(c.confirmed_by || "clinician")}</span> <span class="cite" data-doc="${esc(c.doc_id)}">${esc(c.doc_title || c.doc_id)}</span>` : citeHTML({ ...c.location, doc_id: c.doc_id, doc_title: c.doc_title, date: c.date, quote: c.quote })}</td>
      <td class="small muted">${f.history.length > 1 ? f.history.map((h) => `${esc(h.value)} (${fmtDate(h.date)})`).join(" → ") : ""}</td></tr>`; }).join("")}
  </tbody></table></div>`;
  $$("tr[data-doc]").forEach((tr) => (tr.onclick = (e) => { if (!e.target.closest("button")) openDoc(tr.dataset.doc); }));
  $$("[data-attest-doc]").forEach((b) => (b.onclick = () => attestDoc(b.dataset.attestDoc)));
  $$("[data-reproc-doc]", $("#tab-docs")).forEach((b) => (b.onclick = async () => { const j = await api(`/cases/${S.caseId}/reprocess`, { json: { which: [b.dataset.reprocDoc] } }); S.tab = "ready"; showTab("ready"); watchJob(j.job); }));
  $$("[data-dismiss]", $("#tab-docs")).forEach((b) => (b.onclick = () => dismissDoc(b.dataset.dismiss)));
  $$("[data-confdate]", $("#tab-docs")).forEach((b) => (b.onclick = () => confirmDates(b.dataset.confdate)));
  $$("[data-conftype]", $("#tab-docs")).forEach((b) => (b.onclick = () => confirmDocType(b.dataset.conftype)));
  $$("[data-unfile-doc]").forEach((b) => (b.onclick = async () => { const v = await confirmDialog({ title: "Move this record back to matching", intro: "The document leaves this Case File and returns to the Needs matching queue; this Case File will not be suggested for it again, and identifiers learned from it are forgotten. Recorded in both audit logs.", fields: [{ id: "reason", label: "Reason", type: "text", required: true }], submit: "Move back" });
    if (!v) return; try { await api(`/cases/${S.caseId}/documents/${b.dataset.unfileDoc}/unfile`, { json: { reason: v.reason } }); await openCase(S.caseId, true); refreshQueueCount(); toast("Record moved back to the Needs matching queue"); } catch (e) { toast(e.message, 7000); } }));
  $$("[data-del-doc]").forEach((b) => (b.onclick = async () => { if (!confirm("Remove this document from the Case File? The removal is recorded in the audit log.")) return;
    await api(`/cases/${S.caseId}/documents/${b.dataset.delDoc}`, { method: "DELETE" }); await openCase(S.caseId, true); toast("Document removed; Pre-Authorization re-checked"); }));
}

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
  const isPdf = d.ext === ".pdf";
  const preview = isImg ? `<img class="orig" src="/api/tb${base}/file">` :
    isPdf ? `<img class="orig" id="pdfimg" src="/api/tb${base}/file?render=1&page=${pg}">` : `<div class="muted">No image preview for this format.</div>`;
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
    <div>Read by</div><div>${esc([...new Set(pages.map((p) => p.method))].join(", "))}${pages.some((p) => p.ocr_reads) ? " (two independent reads per scanned page; numbers compared)" : ""}</div></div>
    <div class="docview"><div>${preview}</div><div>
      ${pages.length > 1 ? `<div style="margin-bottom:6px">${pages.map((p, i) => `<button class="ghost sm" data-pg="${i}">Page ${i + 1}</button>`).join(" ")}</div>` : ""}
      <div class="doctext" id="doctext">${marks(pg)}</div>
      <h4 style="color:#1f2933">Fields found in this document</h4>
      <table class="t"><tbody>${Object.entries(d.facts || {}).map(([k, f]) => `<tr><td>${esc(k)}</td><td><b>${esc(f.value)}</b>${f.state === "pending" ? ' <span class="chip c-warn">pending</span>' : ""}</td>
        <td><span class="chip ${f.verification === "verified" ? "c-ok" : "c-rev"}" title="${esc(f.reason || "")}">${esc(f.verification)}</span>${f.polarity === "negated" ? ' <span class="chip c-mute" title="The value is a negative finding (no / not / negative / absent)">negated</span>' : ""}</td><td class="small muted">"${esc(f.quote)}"</td></tr>`).join("") || '<tr><td class="muted">None</td></tr>'}</tbody></table>
      ${pages.some((p) => p.flags?.length) ? `<div class="flag review" style="margin-top:8px"><div class="k">Hindi / regional text or handwriting</div>${esc([...new Set(pages.flatMap((p) => p.flags || []))].join("; "))}. Flagged lines: ${pages.map((p, i) => (p.flagged_lines || []).map((l) => `page ${i + 1}: "${esc(l.line.slice(0, 80))}"`).join("; ")).filter(Boolean).join("; ")}. The text is transcribed as written and never translated; values taken from these lines are marked for a person's check.</div>` : ""}
      ${pages.some((p) => p.ocr_uncertain_numbers?.length) ? `<div class="flag review" style="margin-top:8px"><div class="k">OCR disagreement</div>The two reads of this scanned page differ on these numbers: ${esc(pages.flatMap((p) => p.ocr_uncertain_numbers || []).join(", "))}. Values containing them are marked for expert review; read the scan image.</div>` : ""}
    </div></div>`;
  $("#drawer").classList.remove("hidden");
  $$("[data-pg]").forEach((b) => (b.onclick = () => { $("#doctext").innerHTML = marks(+b.dataset.pg); const im = $("#pdfimg"); if (im) im.src = im.src.replace(/page=\d+/, "page=" + b.dataset.pg); }));
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
      <div class="small muted">${c.a.seconds} s · ${esc(c.a.mode)}${c.a.dropped_unverified ? ` · ${c.a.dropped_unverified} unverified statement(s) removed` : ""}</div>` :
    c.a.status === "out_of_scope" ? `<div class="refusal"><b>Outside the assistant's scope.</b> ${esc(c.a.message)}</div>` :
    `<div class="refusal"><b>${c.a.status === "error" ? "Error" : "Not documented in the Case File."}</b> ${esc(c.a.message)}</div>`)).join("");
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
function showBrief(role, b) {
  const box = briefBox(role);
  const rv = b.review || {};
  const stale = S.data.stale?.["brief_" + role];
  box.innerHTML = `<h3>${esc(b.label)} <span>${rv.status === "reviewed" ? `<span class="chip c-ok">Reviewed by ${esc(rv.by)}</span>` : rv.status === "flagged" ? `<span class="chip c-bad">Flagged for correction</span>` : `<span class="chip c-rev">AI draft · awaiting expert review</span>`}</span></h3>
    ${stale ? `<div class="banner warn stale"><b>${esc(stale)}.</b> Prepare the brief again (Refresh) before the board relies on it.</div>` : ""}
    <div class="small muted">${esc(b.generated?.replace("T", " "))} · ${b.seconds} s · ${esc(b.model)}${b.dropped_unverified ? ` · ${b.dropped_unverified} unverified item(s) removed` : ""}${b.guardrail_removed ? ` · ${b.guardrail_removed} removed by scope guardrail` : ""}</div>
    ${b.sections.map((s) => `<h4>${esc(s.heading)}</h4><ul>${s.items.map((it) => `<li>${esc(it.text)} ${it.citations.map(citeHTML).join("")}${flagHTML(it)}</li>`).join("")}</ul>`).join("")}
    ${b.pack ? `<div class="small muted">Guideline pack: ${packLine(b.pack)}${b.pack.checklist ? ` · Reporting checklist: ${esc(b.pack.checklist.title)} (${esc(b.pack.checklist.region)}, ${esc(b.pack.checklist.pages)})` : ""}</div>` : ""}
    ${b.points_for_review.length ? `<h4>Points for review (not treatment recommendations)</h4><ul>${b.points_for_review.map((it) => `<li>${esc(it.text)} ${it.citations.map(citeHTML).join("")}${(it.references || []).length ? `<div class="grefs">${it.references.map(refHTML).join("")}</div>` : ""}</li>`).join("")}</ul>
      ${b.points_for_review.some((it) => (it.references || []).length) ? `<div class="small muted">References are guideline text for the board to consult, Indian sources first; they are not facts about this patient and not a recommendation for this patient.</div>` : ""}` : ""}
    ${b.not_documented.length ? `<h4>Not documented</h4><ul>${b.not_documented.map((x) => `<li class="muted">${esc(x)}</li>`).join("")}</ul>` : ""}
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
    ${(s.sections || []).length ? s.sections.map((sec) => `<h4 style="color:#1f2933;margin:12px 0 4px">${esc(sec.title)}</h4>${sec.sentences.length ? `<p>${sec.sentences.map((x) => `<span ${x.from_fields ? 'title="Added from the verified primary fields (no model text)" style="color:#334155"' : ""}>${esc(x.text)}</span> ${x.citations.map(citeHTML).join("")}${flagHTML(x)}`).join(" ")}</p>` : `<p class="muted small">Nothing verified for this section in the Case File.</p>`}`).join("")
      : s.paragraphs.map((para) => `<p>${para.map((x) => `${esc(x.text)} ${x.citations.map(citeHTML).join("")}${flagHTML(x)}`).join(" ")}</p>`).join("")}
    ${s.stage_as_recorded ? `<div class="stagebox"><b>Stage, as recorded in the ${esc(s.stage_as_recorded.doc_title)}:</b> ${esc(s.stage_as_recorded.value)} ${citeHTML({ ...s.stage_as_recorded, quote: s.stage_as_recorded.quote })}<div class="small muted">Extracted from the signed source report. The agent does not derive or assign stage.</div></div>` : ""}
    ${s.points_for_review.length ? `<h4 style="color:#1f2933">Points for review</h4><ul>${s.points_for_review.map((x) => `<li>${esc(x.text)} ${x.citations.map(citeHTML).join("")}</li>`).join("")}</ul>` : ""}
    <div class="small muted">${esc(s.generated?.replace("T", " "))} · ${s.seconds} s · ${esc(s.model)}${s.dropped_unverified ? ` · ${s.dropped_unverified} unverified sentence(s) removed` : ""}${s.filled_from_fields ? ` · ${s.filled_from_fields} sentence(s) added from verified fields` : ""}</div>
    ${reviewBar("summary", rv)}`;
  bindReview($("#sumout"));
}

function glHTML(r) {
  const one = (h) => `<div class="hit"><div class="small"><span class="chip ${h.region === "India" ? "c-ok" : h.region === "US" ? "c-mute" : "c-info"}">${esc(h.region)}</span> <b>${esc(h.org)}</b> · ${esc(h.title)} · ${glPlace(h).label}
    <a href="${glPlace(h).href}" target="_blank">open</a></div><div style="margin-top:4px">${esc(h.text.slice(0, 520))}${h.text.length > 520 ? "..." : ""}</div></div>`;
  return (r.india.length ? r.india.map(one).join("") : `<div class="small muted">No Indian guideline passage matched.</div>`) + r.international.map(one).join("");
}

// ------------------------------------------------------------------ tab: board & follow-up
function renderBoard() {
  const st = S.data.state;
  const depts = ["Medical Oncology", "Surgical Oncology", "Radiation Oncology", "Radiology", "Pathology", "Molecular Pathology", "Nuclear Medicine", "Laboratory Medicine", "GI Oncology", "Gastroenterology", "Pulmonology", "Tumour Board coordinator"];
  const records = (st.board_records || []).slice().reverse();
  const allActs = (st.actions || []).slice().sort((a, b) => (a.status === "completed") - (b.status === "completed") || a.due.localeCompare(b.due));
  $("#tab-board").innerHTML = `<div class="grid2"><div>
    ${!can("board_record") ? `<div class="card"><h3>Tumour Board decision</h3><div class="muted small">Decisions are recorded by the Tumour Board coordinator.</div></div>` : `<div class="card form"><h3>Record the Tumour Board decision</h3><div class="muted small">Entered by the clinical team. The agent then checks the record (AI-assisted adjudication): documentation completeness, values against the signed sources, open Pre-Authorization items. It does not judge the clinical decision.</div>
      <label>Board date</label><input type="date" id="b-date" value="${new Date().toISOString().slice(0, 10)}">
      <label>Decision recorded by the board</label><textarea id="b-text" placeholder="As decided and dictated by the board"></textarea>
      <label>Recorded by</label><input id="b-by" placeholder="Name, role">
      <label>Participants present (names and specialties)</label><input id="b-part" placeholder="e.g. Dr A (Med Onc), Dr B (Surg Onc), Dr C (Radiology), Dr D (Pathology)">
      <label>Report corrections or discrepancies raised at the meeting (if any)</label><input id="b-corr" placeholder="e.g. Pathology to issue addendum correcting PD-L1 TPS">
      <label>Divergent opinions / dissenting clinicians (if any)</label><input id="b-div" placeholder="Recorded verbatim, with names">
      <label>Actions (Responsible Department · task · due)</label><div id="b-acts"></div><button class="ghost sm" id="b-add">+ Action</button>
      <label>Next Tumour Board review</label><input type="date" id="b-next">
      <div style="margin-top:12px"><button class="primary" id="b-save">Save record and run adjudication</button></div></div>`}
    ${records.map((b) => `<div class="card"><h3>Tumour Board record · ${fmtDate(b.board_date)} <span class="chip ${b.adjudication.status === "consistent" ? "c-ok" : "c-rev"}">${b.adjudication.status === "consistent" ? "Consistent" : "Flag for expert review"}</span></h3>
      <div class="small muted">Recorded by ${esc(b.recorded_by)} · entered ${esc(b.recorded_at.replace("T", " ").slice(0, 16))} by ${esc(b.entered_by)}</div>
      <p style="white-space:pre-wrap">${esc(b.decision_text)}</p>
      <div class="kv small">${b.participants ? `<div>Participants</div><div>${esc(b.participants)}</div>` : ""}${b.report_corrections_raised ? `<div>Report corrections raised</div><div>${esc(b.report_corrections_raised)}</div>` : ""}${b.divergent_opinions ? `<div>Divergent opinions</div><div>${esc(b.divergent_opinions)}</div>` : ""}</div>
      ${b.adjudication.flags.map((f) => `<div class="flag ${f.severity === "expert_review" ? "" : "review"}"><div class="k">${f.kind === "transcription" ? "Possible transcription discrepancy" : f.kind === "consistency" ? "Documentation consistency" : "Documentation"}</div>
        <div>${esc(f.text)}</div>${f.source_quote ? `<div class="small" style="margin-top:4px">Source: ${citeHTML({ doc_id: f.source_doc, doc_title: f.source_title, quote: f.source_quote })} "${esc(f.source_quote)}"</div><div class="small muted">Expert review required. The agent flags the difference; it does not decide which value is correct.</div>` : ""}</div>`).join("")}
      ${b.adjudication.value_checks.filter((v) => v.result === "consistent").map((v) => `<div class="small"><span class="chip c-ok">✓</span> ${esc(v.value_as_written)} matches the source</div>`).join("")}</div>`).join("")}
  </div><div>
    <div class="card"><h3>Follow-up tracker <span class="muted small">${allActs.filter((a) => a.status !== "completed").length} open</span></h3>
      ${allActs.map(actionHTML).join("") || '<div class="muted small">No actions.</div>'}
      ${st.next_review ? `<div class="stagebox"><b>Next Tumour Board review:</b> ${fmtDate(st.next_review.date)}</div>` : ""}</div>
    <div class="card"><h3>Longitudinal Case File</h3><div class="timeline">${S.data.timeline.map((e) => `<div class="tev ${e.kind}"><div class="d">${fmtDate(e.date)}</div>${e.doc_id ? `<span class="cite" data-doc="${esc(e.doc_id)}">${esc(e.title)}</span> <span class="chip ${["FINAL", "AMENDED", "CORRECTED"].includes(e.status) ? "c-ok" : "c-bad"}">${esc(e.status)}</span>` : esc(e.title)}${e.kind === "action" ? ` <span class="chip c-mute">${esc(e.status)}</span>` : ""}</div>`).join("")}</div></div>
  </div></div>`;
  const addRow = (d = "", t = "", due = "") => $("#b-acts").insertAdjacentHTML("beforeend", `<div class="arow"><select>${depts.map((x) => `<option ${x === d ? "selected" : ""}>${x}</option>`).join("")}</select><input placeholder="Task" value="${esc(t)}"><input type="date" value="${due}"><button class="ghost sm" data-rmrow>×</button></div>`);
  if ($("#b-acts")) addRow();
  if ($("#b-add")) $("#b-add").onclick = () => addRow();
  if ($("#b-save")) $("#b-save").onclick = async () => {
    const actions = $$("#b-acts .arow").map((r) => ({ department: r.children[0].value, task: r.children[1].value, due: r.children[2].value })).filter((a) => a.task);
    const body = { board_date: $("#b-date").value, decision_text: $("#b-text").value, recorded_by: $("#b-by").value, participants: $("#b-part").value,
      report_corrections_raised: $("#b-corr").value, divergent_opinions: $("#b-div").value, actions, next_review: $("#b-next").value };
    $("#b-save").innerHTML = `<span class="spin"></span> Adjudicating...`;
    await api(`/cases/${S.caseId}/board-records`, { json: body });
    S.data = await api("/cases/" + S.caseId); renderBoard(); toast("Tumour Board record saved and checked");
  };
  bindActions($("#tab-board"));
}

// ------------------------------------------------------------------ tab: audit
async function renderAudit() {
  const ev = (await api(`/cases/${S.caseId}/audit`)).events.reverse();
  const llm = ev.filter((e) => e.kind === "llm_call");
  $("#tab-audit").innerHTML = `<div class="card"><h3>Audit log <span class="muted small">${ev.length} events · ${llm.length} model calls · ${llm.reduce((a, e) => a + (e.completion_tokens || 0), 0)} tokens generated</span></h3>
    <div class="muted small" style="margin-bottom:8px">Append-only record of every AI call (model, purpose, time, prompt hash), every verification and guardrail decision, and every human action.</div>
    <table class="t"><thead><tr><th>Time</th><th>Event</th><th>Detail</th></tr></thead><tbody>
    ${ev.slice(0, 400).map((e) => { const { ts, kind, ...rest } = e; return `<tr><td class="small">${esc(ts.replace("T", " "))}</td><td><span class="chip ${/guardrail|error|unverified/.test(kind) ? "c-rev" : kind === "llm_call" ? "c-mute" : "c-info"}">${esc(kind)}</span></td><td class="small">${esc(JSON.stringify(rest)).slice(0, 300)}</td></tr>`; }).join("")}
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

// ------------------------------------------------------------------ new case
async function newCase() {
  const ps = S.protocols;
  $("#modal-body").innerHTML = `<h2 style="color:#1f2933;margin-top:0">New Tumour Board Case File</h2><div class="form">
    <label>Case File ID</label><input id="n-id" placeholder="e.g. TB-2026-0142">
    <label>Patient name</label><input id="n-name"><label>UHID / MRN</label><input id="n-mrn"><label>Age / Sex</label><input id="n-agesex" placeholder="62 Y / M">
    <label>Protocol</label><select id="n-prot">${ps.map((p) => `<option value="${esc(p.id)}">${esc(p.label)} (v${esc(p.version)})</option>`).join("")}</select>
    <label>NCG setting (as recorded in the signed reports, chosen by the clinician)</label><select id="n-setting"></select>
    <label>Hospital level (NCG tiers)</label><select id="n-level"><option value="essential">Essential</option><option value="optimal">Optimal</option></select>
    <label>Board date</label><input type="date" id="n-date">
    <div style="margin-top:14px;display:flex;gap:8px;justify-content:flex-end"><button class="ghost" data-closemodal>Cancel</button><button class="primary" id="n-go">Create</button></div></div>`;
  $("#modal").classList.remove("hidden");
  const fillSettings = () => { const p = ps.find((x) => x.id === $("#n-prot").value); $("#n-setting").innerHTML = `<option value="">Not chosen yet</option>` + (p?.settings || []).map((x) => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join(""); };
  fillSettings(); $("#n-prot").onchange = fillSettings; $("#n-level").value = S.org?.hospital?.level || "essential";
  $("#n-go").onclick = async () => {
    try {
      const c = await api("/cases", { json: { case_id: $("#n-id").value.trim(), protocol: $("#n-prot").value, board_date: $("#n-date").value, setting: $("#n-setting").value, hospital_level: $("#n-level").value,
        patient: { name: $("#n-name").value, mrn: $("#n-mrn").value, agesex: $("#n-agesex").value } } });
      $("#modal").classList.add("hidden"); S.tab = "ready"; await openCase(c.case_id);
    } catch (e) { toast(e.message); }
  };
}


// ------------------------------------------------------------------ hospital, departments, users (admin) · V1 item 2.1
const deptName = (id) => (S.org?.departments || []).find((d) => d.id === id)?.name || id || "";
async function loadOrg() {
  try { S.org = await api("/org"); S.me = S.org.me; } catch (e) { S.org = null; S.me = null; }
  $("#btn-org").classList.toggle("hidden", !S.me?.admin);
  $("#btn-new").classList.toggle("hidden", !meCan("create_case"));
}
async function showOrg() {
  const o = await api("/org");
  const slug = (t) => t.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const users = {}; (o.vaidyx_users || []).forEach((u) => (users[u.username] = { departments: {}, coordinator: false, is_admin: u.is_admin, ...(o.users[u.username] || {}) }));
  Object.entries(o.users || {}).forEach(([u, v]) => { if (!users[u]) users[u] = { departments: {}, coordinator: false, ...v, missing: true }; });
  const deptRow = (d) => `<tr class="orow" data-id="${esc(d.id)}"><td><input class="o-name" value="${esc(d.name)}"></td><td><input class="o-alias" value="${esc((d.aliases || []).join(", "))}" placeholder="Other names used in protocols and reports"></td><td class="small muted">${esc(d.id)}</td><td><button class="ghost sm" data-rmrow title="Remove department">×</button></td></tr>`;
  const roleSel = (u, v) => `<div class="urow" data-user="${esc(u)}"><label class="small"><input type="checkbox" class="u-coord" ${v.coordinator ? "checked" : ""}> Coordinator</label>
      <div class="u-depts">${Object.entries(v.departments || {}).map(([d, r]) => `<span class="chip c-info" data-dept="${esc(d)}" data-role="${esc(r)}">${esc(deptName(d))} · ${esc(r)} <button class="x" data-rmchip aria-label="remove">×</button></span>`).join("")}</div>
      <div class="u-add"><select class="u-dept">${(o.departments || []).map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("")}</select><select class="u-role"><option value="member">member</option><option value="head">head</option></select><button class="ghost sm" data-addrole>Add</button></div></div>`;
  $("#modal-body").innerHTML = `<h2 style="color:#1f2933;margin-top:0">Hospital and departments</h2>
    <div class="muted small">One hospital. Logins are the Vaidyx accounts (created under the main app's admin settings); here each account is placed in departments with a role. Vaidyx admins are Tumour Board admins. Saved changes are recorded in the audit log.</div>
    <div class="form"><div class="grid3">
      <div><label>Hospital name</label><input id="o-hname" value="${esc(o.hospital?.name || "")}"></div>
      <div><label>Hospital level (NCG tiers)</label><select id="o-level"><option value="essential" ${o.hospital?.level !== "optimal" ? "selected" : ""}>Essential</option><option value="optimal" ${o.hospital?.level === "optimal" ? "selected" : ""}>Optimal</option></select></div>
      <div><label>Hospital type (PM-JAY paperwork)</label><select id="o-type"><option value="" ${!o.hospital?.type ? "selected" : ""}>Not set</option><option value="public" ${o.hospital?.type === "public" ? "selected" : ""}>Public</option><option value="private" ${o.hospital?.type === "private" ? "selected" : ""}>Private</option></select></div></div></div>
    <h3 style="margin:16px 0 6px">Departments <button class="ghost sm" id="o-adddept">+ Department</button></h3>
    <table class="t"><thead><tr><th>Name</th><th>Also known as</th><th>Id</th><th></th></tr></thead><tbody id="o-depts">${(o.departments || []).map(deptRow).join("")}</tbody></table>
    <h3 style="margin:16px 0 6px">Users and roles</h3>
    <div class="muted small" style="margin-bottom:6px">Member: upload for the department, see its inbox, confirm its documents. Head: also waive a requirement for the department. Coordinator: list Case Files, run matching, run board sessions.</div>
    <table class="t"><thead><tr><th>Account</th><th>Roles</th></tr></thead><tbody id="o-users">${Object.entries(users).sort().map(([u, v]) => `<tr><td><b>${esc(u)}</b>${v.is_admin ? ' <span class="chip c-ok">Vaidyx admin</span>' : ""}${v.missing ? ' <span class="chip c-warn" title="No Vaidyx account with this name">no account</span>' : ""}</td><td>${roleSel(u, v)}</td></tr>`).join("") || `<tr><td colspan="2" class="muted">No accounts.</td></tr>`}</tbody></table>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px"><button class="ghost" data-closemodal>Cancel</button><button class="primary" id="o-save">Save</button></div>`;
  $("#modal").classList.remove("hidden");
  $("#o-adddept").onclick = () => { const name = prompt("Department name (as the hospital calls it):"); if (!name) return; $("#o-depts").insertAdjacentHTML("beforeend", deptRow({ id: slug(name), name, aliases: [] })); };
  $("#modal-body").addEventListener("click", (e) => {
    if (e.target.closest("[data-rmchip]")) e.target.closest(".chip").remove();
    const add = e.target.closest("[data-addrole]");
    if (add) { const row = add.closest(".urow"); const d = row.querySelector(".u-dept").value, r = row.querySelector(".u-role").value;
      const box = row.querySelector(".u-depts"); const old = box.querySelector(`[data-dept="${d}"]`); if (old) old.remove();
      box.insertAdjacentHTML("beforeend", `<span class="chip c-info" data-dept="${esc(d)}" data-role="${esc(r)}">${esc(deptName(d))} · ${esc(r)} <button class="x" data-rmchip aria-label="remove">×</button></span>`); }
  });
  $("#o-save").onclick = async () => {
    const departments = $$("#o-depts tr.orow").map((tr) => ({ id: tr.dataset.id, name: $(".o-name", tr).value.trim(), aliases: $(".o-alias", tr).value.split(",").map((x) => x.trim()).filter(Boolean) }));
    const users = {};
    $$("#o-users .urow").forEach((row) => { const deps = {}; $$(".chip[data-dept]", row).forEach((c) => (deps[c.dataset.dept] = c.dataset.role));
      const coord = $(".u-coord", row).checked; if (Object.keys(deps).length || coord) users[row.dataset.user] = { departments: deps, coordinator: coord }; });
    try {
      await api("/org", { method: "PUT", json: { hospital: { name: $("#o-hname").value.trim(), level: $("#o-level").value, type: $("#o-type").value }, departments, users, admins: o.admins || [] } });
      $("#modal").classList.add("hidden"); toast("Hospital set-up saved"); await loadOrg(); if (S.caseId) openCase(S.caseId, true);
    } catch (e) { toast(e.message, 7000); }
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
  if (!S.me) return;
  try { const q = await api("/intake"); S.queue = q; const n = q.documents.filter((d) => d.state !== "filed").length;
    $("#queue-count").textContent = n; $("#queue-count").classList.toggle("hidden", !n); } catch (e) {}
}
function bindIntakeUpload() {
  const my = S.org?.my_departments || [];
  $("#side-intake").classList.toggle("hidden", !my.length);
  if (!my.length) return;
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
  $("#welcome").classList.add("hidden"); $("#case").classList.add("hidden"); $("#inbox").classList.add("hidden"); $("#intake").classList.remove("hidden");
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
const NKIND = { request: ["c-warn", "Request"], request_closed: ["c-ok", "Request closed"], case_ready: ["c-ok", "Case File ready"] };
async function loadNotifications() {
  if (!S.me) return;
  try { const r = await api("/notifications?limit=80"); S.notifications = r.notifications; S.unread = r.unread;
    $("#btn-bell").classList.remove("hidden"); $("#bell-count").textContent = r.unread; $("#bell-count").classList.toggle("hidden", !r.unread); } catch (e) {}
}
function showNotifications() {
  const list = S.notifications || [];
  const row = (n) => { const k = NKIND[n.kind] || ["c-mute", n.kind]; return `<div class="ntf ${n.read ? "read" : ""}" data-ntf="${esc(n.id)}" data-case="${esc(n.case_id || "")}" title="Open the Case File">
      <div class="h"><span class="chip ${k[0]}">${esc(k[1])}</span> <b>${esc(n.title)}</b>${n.level_label ? ` <span class="chip c-lvl">${esc(n.level_label)}</span>` : ""}${n.read ? "" : ' <span class="chip c-info">new</span>'}</div>
      ${n.text ? `<div class="small">${esc(n.text)}</div>` : ""}<div class="small muted">${esc((n.ts || "").slice(0, 16).replace("T", " "))}${n.due ? " · due " + fmtDate(n.due) : ""}${n.to?.department ? " · to " + esc(deptName(n.to.department)) : n.to?.role ? " · to the coordinator" : ""}</div></div>`; };
  $("#modal-body").innerHTML = `<h3 style="color:#1f2933;margin-top:0">Notifications <span class="muted small" style="font-weight:400">${S.unread || 0} unread</span></h3>
    <div class="small muted">In-app only. The Pre-Authorization check sends each gap to the Responsible Department (Level 1) or to the department that uploaded the record (Level 2); a request closes by itself when the record arrives; the coordinator hears when a Case File is ready for the board.</div>
    <div style="margin:8px 0;display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap">${(S.org?.inbox_departments || []).length ? `<button class="ghost sm" id="nt-inbox">Open the department inbox</button>` : ""}${list.some((n) => !n.read) ? `<button class="ghost sm" id="nt-readall">Mark all read</button>` : ""}<button class="ghost sm" data-closemodal>Close</button></div>
    ${list.length ? list.map(row).join("") : `<div class="muted">Nothing yet.</div>`}`;
  $("#modal").classList.remove("hidden");
  if ($("#nt-readall")) $("#nt-readall").onclick = async () => { await api("/notifications/read", { json: { all: true } }); await loadNotifications(); showNotifications(); };
  if ($("#nt-inbox")) $("#nt-inbox").onclick = () => { $("#modal").classList.add("hidden"); showInbox(); };
  $$("[data-ntf]").forEach((el) => (el.onclick = async () => { try { await api("/notifications/read", { json: { ids: [el.dataset.ntf] } }); } catch (e) {} $("#modal").classList.add("hidden"); loadNotifications(); if (el.dataset.case) { S.tab = "ready"; try { await openCase(el.dataset.case); } catch (e) { toast("That Case File no longer exists", 6000); } } }));
}
async function refreshInboxCount() {
  const show = (S.org?.inbox_departments || []).length > 0;
  $("#btn-inbox").classList.toggle("hidden", !show);
  if (!show) return;
  try { const ib = await api("/inbox"); $("#inbox-count").textContent = ib.open; $("#inbox-count").classList.toggle("hidden", !ib.open); } catch (e) {}
}
async function showInbox() {
  const ib = await api("/inbox"); S.inbox = ib;
  $("#welcome").classList.add("hidden"); $("#case").classList.add("hidden"); $("#intake").classList.add("hidden"); $("#inbox").classList.remove("hidden");
  $$(".citem").forEach((el) => el.classList.remove("on"));
  const chip = (q) => q.status === "completed" ? `<span class="chip c-ok">Closed</span>` : q.overdue ? `<span class="chip c-bad">Overdue ${q.days_overdue} d</span>` : `<span class="chip c-warn">Pending</span>`;
  const row = (q) => `<tr class="click" data-case="${esc(q.case_id)}"><td><b>${esc(q.patient?.name || q.case_id)}</b><div class="small muted">${esc(q.case_id)}${q.patient?.mrn ? " · UHID / MRN " + esc(q.patient.mrn) : ""}${q.patient?.agesex ? " · " + esc(q.patient.agesex) : ""}${q.board_date ? " · board " + fmtDate(q.board_date) : ""}</div></td>
      <td><b>${esc(q.label)}</b>${q.level_label ? `<div><span class="chip c-lvl">${esc(q.level_label)}</span></div>` : ""}</td><td class="small">${esc(q.what)}</td><td class="small">${fmtDate(q.due)}</td><td>${chip(q)}${q.completed ? `<div class="small muted">${esc(q.completed.slice(0, 16).replace("T", " "))}</div>` : ""}</td></tr>`;
  $("#inbox").innerHTML = `<div class="case-head"><div><div class="eyebrow">Department inbox</div><h1>Requests to ${ib.departments.length === 1 ? esc(ib.departments[0].name) : "my departments"}</h1>
      <div class="muted">Every gap the Pre-Authorization check routed to your department across the Tumour Board Case Files: the Case File, the record needed, what is missing, the due date and the status. A request closes by itself when the record arrives and the Case File is re-checked; requests closed in the last 7 days stay listed. Overdue is worked out when this page is shown.</div></div>
      <div class="readiness"><div class="rtext"><b>${ib.open} open</b><span>${ib.overdue} overdue</span></div></div></div>
    ${ib.departments.map((d) => `<div class="card"><h3>${esc(d.name)} <span class="muted small">${d.open} open · ${d.overdue} overdue</span></h3>
      ${d.requests.length ? `<table class="t"><thead><tr><th>Case File</th><th>Record needed</th><th>What is missing</th><th>Due</th><th>Status</th></tr></thead><tbody>${d.requests.map(row).join("")}</tbody></table>` : `<div class="muted small">No requests.</div>`}</div>`).join("") || `<div class="card"><div class="muted">Your account is not placed in a department with an inbox.</div></div>`}`;
  $$("#inbox tr[data-case]").forEach((tr) => (tr.onclick = async () => { S.tab = "ready"; try { await openCase(tr.dataset.case); } catch (e) { toast("That Case File no longer exists", 6000); } }));
  $("#inbox-count").textContent = ib.open; $("#inbox-count").classList.toggle("hidden", !ib.open);
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

// ------------------------------------------------------------------ boot
$$("#tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
$("#btn-new").onclick = newCase;
$("#btn-cards").onclick = showCards;
$("#btn-org").onclick = showOrg;
$("#btn-queue").onclick = showIntake;
$("#btn-inbox").onclick = showInbox;
$("#btn-bell").onclick = showNotifications;
(async () => {
  const pr = await api("/protocols"); S.protocols = pr.protocols; S.facts = pr.facts;
  await loadOrg(); bindIntakeUpload(); refreshQueueCount(); refreshInboxCount(); loadNotifications();
  await loadCases(); loadModels(); setInterval(loadModels, 30000); setInterval(() => { loadNotifications(); refreshInboxCount(); }, 30000);
  const m = location.hash.match(/case=([\w.-]+)/); if (m) openCase(m[1]);
})();

// small screens: the case list is a slide-over panel
(function () {
  const btn = document.getElementById("btn-side"); if (!btn) return;
  const set = (on) => { document.body.classList.toggle("side-open", on); btn.setAttribute("aria-expanded", on ? "true" : "false"); };
  btn.addEventListener("click", () => set(!document.body.classList.contains("side-open")));
  document.addEventListener("click", (e) => {
    if (!document.body.classList.contains("side-open")) return;
    if (e.target.closest(".side .citem, .side [data-demo], .side #btn-new, .side #btn-queue") || (!e.target.closest(".side") && !e.target.closest("#btn-side"))) set(false);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") set(false); });
  window.addEventListener("resize", () => { if (innerWidth > 860) set(false); });
})();
