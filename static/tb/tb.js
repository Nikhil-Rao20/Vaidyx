// Vaidyx-TB frontend. Vanilla JS, same-origin only (CSP). All document-derived text is escaped before rendering.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { caseId: null, data: null, tab: "ready", cards: null, roles: null, protocols: null, chat: [], briefs: {} };

async function api(path, opts = {}) {
  const o = { credentials: "same-origin", ...opts };
  if (o.json !== undefined) { o.method = o.method || "POST"; o.headers = { "Content-Type": "application/json" }; o.body = JSON.stringify(o.json); delete o.json; }
  const r = await fetch("/api/tb" + path, o);
  if (r.status === 401) { location.href = "/login"; throw new Error("not logged in"); }
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  return r.json();
}
function toast(msg, ms = 3500) { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), ms); }
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
  $("#case-list").innerHTML = d.cases.length ? d.cases.map((c) => `
    <div class="citem ${c.case_id === S.caseId ? "on" : ""}" data-case="${esc(c.case_id)}">
      <div class="t"><span>${esc(c.patient?.name || c.case_id)}</span>${c.gate_passed ? '<span class="chip c-ok">Ready</span>' : c.readiness != null ? `<span class="chip c-warn">${c.readiness}%</span>` : ""}</div>
      <div class="s">${esc(c.case_id)} · ${esc(c.protocol)} · ${c.documents} documents${c.open_actions ? ` · ${c.open_actions} open actions` : ""}</div>
    </div>`).join("") : `<div class="muted small">No Case Files yet.</div>`;
  $$(".citem").forEach((el) => (el.onclick = () => openCase(el.dataset.case)));
  $("#demo-list").innerHTML = d.demo.map((c) => `<div class="demo"><b>${esc(c.case_id)}</b> ${esc(c.patient?.name)}<br><span class="muted">${esc(c.protocol)} · ${c.files} files${c.has_arrivals ? " · has later arrivals" : ""}</span><br>
      <button class="ghost sm" data-demo="${esc(c.case_id)}" style="margin-top:6px">Load as new Case File</button></div>`).join("") || `<div class="muted small">No demo corpus found.</div>`;
  $$("[data-demo]").forEach((b) => (b.onclick = async () => {
    if (!confirm(`Load synthetic case ${b.dataset.demo}? Any existing Case File with this id is replaced.`)) return;
    const j = await api("/demo/" + b.dataset.demo, { method: "POST" });
    S.caseId = b.dataset.demo; await openCase(S.caseId); watchJob(j.job);
  }));
}

async function openCase(id, keepTab) {
  if (id !== S.caseId) { S.tab = "ready"; S.chat = []; }
  S.caseId = id; S.data = await api("/cases/" + encodeURIComponent(id));
  $("#welcome").classList.add("hidden"); $("#case").classList.remove("hidden");
  const c = S.data.case, p = c.patient || {};
  $("#c-protocol").textContent = (S.protocols?.find((x) => x.id === c.protocol)?.label || c.protocol) + " · Tumour Board Case File";
  $("#c-title").textContent = p.name || c.case_id;
  $("#c-meta").textContent = [c.case_id, p.mrn && "UHID / MRN " + p.mrn, p.agesex, c.board_date && "Board " + fmtDate(c.board_date)].filter(Boolean).join(" · ");
  renderReadiness();
  if (!keepTab) S.tab = S.tab || "ready";
  showTab(S.tab);
  loadCases();
}

function renderReadiness() {
  const g = S.data.state.gate;
  if (!g) { $("#c-ready").innerHTML = ""; return; }
  const pct = g.readiness, r = 26, C = 2 * Math.PI * r, col = g.passed ? "#2f7d55" : pct >= 60 ? "#a96e0a" : "#b23a2f";
  $("#c-ready").innerHTML = `<svg class="ring" viewBox="0 0 64 64"><circle cx="32" cy="32" r="${r}" fill="none" stroke="#e2e8f0" stroke-width="7"/>
    <circle cx="32" cy="32" r="${r}" fill="none" stroke="${col}" stroke-width="7" stroke-linecap="round" stroke-dasharray="${C * pct / 100} ${C}" transform="rotate(-90 32 32)"/>
    <text x="32" y="37" text-anchor="middle" font-size="15" font-weight="600" fill="#00183c">${pct}%</text></svg>
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
  needs_confirmation: ["c-warn", "Confirm final version", "i-warn", "?"], waived: ["c-mute", "Waived for this Case File", "i-na", "–"],
};
const FINALISH = (c) => ["FINAL", "AMENDED", "CORRECTED"].includes(c.status) && c.signed !== "no";
const statusChip = (c) => { if (!c || !c.status) return ""; const ok = FINALISH(c); const un = c.status === "UNSTATED" && c.signed !== "no";
  return `<span class="chip ${ok || (un && c.signed === "yes") ? "c-ok" : un ? "c-warn" : "c-bad"}" title="${esc((c.status_notes || []).join("; "))}">${un ? (c.signed === "yes" ? "Signed, status not stated" : "Status not stated") : esc(c.status)}${c.signed === "no" ? " · unsigned" : c.signed === "yes" && !un ? " · signed" : ""}</span>`; };

// ------------------------------------------------------------------ tab: Pre-Authorization
function renderReady() {
  const { state } = S.data, g = state.gate;
  const reqs = g ? g.requirements.map((r) => {
    const s = STATUS[r.status] || STATUS.needs_review;
    const ev = r.evidence.filter((e) => e.doc_id).map((e) => {
      const d = S.data.documents.find((x) => x.doc_id === e.doc_id); const cl = d?.classification || {};
      return `<span class="cite" data-doc="${esc(e.doc_id)}" title="${esc(e.quote || "")}">${esc(e.value ? `${S.facts?.[e.fact]?.label || e.fact}: ${e.value}` : (cl.title || e.doc_id))}${cl.report_date_iso ? " · " + fmtDate(cl.report_date_iso) : ""}</span>`;
    }).join("");
    const attest = r.status === "needs_confirmation" && r.evidence[0]?.doc_id ? `<button class="ghost sm" data-attest="${esc(r.evidence[0].doc_id)}">Attest: final, signed</button>` : "";
    const waive = r.status === "waived" ? `<button class="ghost sm" data-unwaive="${esc(r.id)}">Remove waiver</button>` : (r.status !== "satisfied" && r.status !== "not_applicable") ? `<button class="ghost sm" data-waive="${esc(r.id)}" title="Clinical decision that this record is not required for this Case File (audited)">Waive</button>` : "";
    return `<div class="req"><div class="icon ${s[2]}">${s[3]}</div><div style="flex:1">
      <div style="display:flex;justify-content:space-between;gap:8px"><span class="lbl">${esc(r.label)}</span><span style="display:flex;gap:4px;align-items:center">${attest}${waive}<span class="chip ${s[0]}">${s[1]}</span></span></div>
      <div class="dept">Responsible Department: ${esc(r.department)}</div>
      ${r.problems.map((p) => `<div class="prob">${esc(p)}</div>`).join("")}${(r.notes || []).map((p) => `<div class="prob muted">${esc(p)}</div>`).join("")}<div class="ev">${ev}</div></div></div>`;
  }).join("") : `<div class="muted">Not evaluated yet. Add documents to start.</div>`;
  const opt = g ? g.optional.map((o) => `<span class="chip ${o.available ? "c-info" : "c-mute"}" style="margin:2px">${o.available ? "✓ " : ""}${esc(o.label)}</span>`).join("") : "";
  const acts = (state.actions || []).filter((a) => a.source === "pre_authorization");
  const actHTML = acts.length ? acts.sort((a, b) => (a.status === "completed") - (b.status === "completed")).map(actionHTML).join("") : `<div class="muted small">No gaps routed.</div>`;
  const docs = g?.documents || {};
  $("#tab-ready").innerHTML = `<div class="grid2"><div>
    <div class="card"><h3>Pre-Authorization check <span><button class="ghost sm" id="btn-recheck">Re-check now</button></span></h3>
      <div class="muted small" style="margin-bottom:6px">Mandatory records for this protocol (configurable per Case File). A record counts only when it is the final, signed version and its required primary fields are found with a verified source quote. Document exists ≠ Document is ready.</div>
      ${reqs}</div>
    ${g?.core_data?.length ? `<div class="card"><h3>MDT minimum core data <span class="muted small">${g.core_data.filter((c) => c.present).length} of ${g.core_data.length} documented</span></h3>
      <div class="muted small" style="margin-bottom:6px">Informational checklist (not part of the gate). Source: ${esc(g.core_data_source || "")}.</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">${g.core_data.map((c) => c.present ? `<span class="cite" data-doc="${esc(c.evidence[0]?.doc_id || "")}" title="${esc((c.evidence[0]?.value || "") + " | " + (c.evidence[0]?.quote || ""))}">✓ ${esc(c.label)}</span>` : `<span class="chip c-mute">– ${esc(c.label)}</span>`).join("")}</div></div>` : ""}
    <div class="card"><h3>Optional records available</h3><div>${opt || '<span class="muted small">None</span>'}</div></div>
    ${g?.policy_basis ? `<div class="card"><h3>Why a Pre-Authorization gate</h3><div class="small" style="color:#475569">${esc(g.policy_basis)}</div></div>` : ""}
  </div><div>
    <div class="card"><h3>Routed actions <span class="muted small">${acts.filter((a) => a.status !== "completed").length} open</span></h3>
      <div class="muted small" style="margin-bottom:8px">The agent identifies and routes the gap. It does not perform the missing clinical task.</div>${actHTML}</div>
    <div class="card"><h3>Add documents</h3>
      <div class="drop" id="drop">Drop files or a whole folder here<br><span class="small">PDF, scanned images (PNG / JPG / TIFF), text and Office files</span><br>
      <button class="ghost sm" id="pick-files" style="margin-top:8px">Choose files</button> <button class="ghost sm" id="pick-folder">Choose folder</button></div>
      <input type="file" id="f-files" multiple class="hidden"><input type="file" id="f-folder" webkitdirectory multiple class="hidden">
      <div id="job"></div>
      ${(S.demoList || []).some((x) => x.case_id === S.caseId && x.has_arrivals) ? `<button class="ghost sm" id="btn-arrivals" style="margin-top:10px">Demo: new reports arrive from departments</button>` : ""}
      <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">${docs.errors ? `<button class="ghost sm" id="btn-reproc-err">Re-process ${docs.errors} failed</button>` : ""}<button class="ghost sm" id="btn-reproc-all" title="Re-read, re-classify and re-extract every document (after a protocol or model change)">Re-process all documents</button><a class="ghost sm" href="/api/tb/cases/${esc(S.caseId)}/export">Export Case File record</a></div>
      <div class="muted small" style="margin-top:10px">${docs.total || 0} documents · ${docs.ready || 0} processed${docs.processing ? ` · ${docs.processing} processing` : ""}${docs.errors ? ` · ${docs.errors} errors` : ""}${docs.identity_flags?.length ? ` · <b style="color:#b23a2f">${docs.identity_flags.length} identity flags</b>` : ""}</div>
    </div></div></div>`;
  $("#btn-recheck").onclick = async () => { const st = await api(`/cases/${S.caseId}/recheck`, { method: "POST" }); await openCase(S.caseId, true); const r = st.recheck || {};
    toast(`Re-checked ${r.documents_checked} processed document(s) against the protocol: ${r.satisfied}/${r.total} satisfied${r.processing ? `, ${r.processing} still processing` : ""}${r.errors ? `, ${r.errors} failed to read` : ""}. ${r.changed?.length ? "Changed: " + r.changed.join(", ") + "." : "No change."} Documents are not re-read by a re-check; use Re-process for that.`, 9000); };
  const reproc = async (which) => { const j = await api(`/cases/${S.caseId}/reprocess`, { json: { which } }); watchJob(j.job); };
  if ($("#btn-reproc-err")) $("#btn-reproc-err").onclick = () => reproc("errors");
  $("#btn-reproc-all").onclick = () => { if (confirm("Re-read, re-classify and re-extract every document in this Case File?")) reproc("all"); };
  $$("[data-waive]", $("#tab-ready")).forEach((b) => (b.onclick = async () => { const reason = prompt("Reason for waiving this record for this Case File (recorded in the audit log):"); if (reason === null) return;
    await api(`/cases/${S.caseId}/overrides`, { json: { kind: "requirements", key: b.dataset.waive, value: { waived: true, reason } } }); await openCase(S.caseId, true); toast("Requirement waived and recorded"); }));
  $$("[data-unwaive]", $("#tab-ready")).forEach((b) => (b.onclick = async () => { await api(`/cases/${S.caseId}/overrides`, { json: { kind: "requirements", key: b.dataset.unwaive, value: null } }); await openCase(S.caseId, true); }));
  $$("[data-attest]", $("#tab-ready")).forEach((b) => (b.onclick = () => attestDoc(b.dataset.attest)));
  bindUpload();
  const arr = $("#btn-arrivals");
  if (arr) arr.onclick = async () => { try { const j = await api(`/cases/${S.caseId}/demo-arrivals`, { method: "POST" }); watchJob(j.job); } catch (e) { toast(e.message); } };
  bindActions($("#tab-ready"));
}

async function attestDoc(docId) {
  const reason = prompt("Confirm that this document is the final, signed version (your name is recorded with this attestation). Note (optional):");
  if (reason === null) return;
  await api(`/cases/${S.caseId}/overrides`, { json: { kind: "documents", key: docId, value: { attested_final: true, reason } } });
  await openCase(S.caseId, true); toast("Attestation recorded in the audit log");
}
function actionHTML(a) {
  return `<div class="action ${a.status}"><div class="h"><span>${esc(a.label)}</span><span class="chip ${a.status === "completed" ? "c-ok" : a.status === "overdue" ? "c-bad" : "c-warn"}">${a.status === "completed" ? "Completed" : a.status === "overdue" ? "Overdue" : "Pending"}</span></div>
    <div class="w">${esc(a.what)}</div>
    <div class="f"><span>Responsible Department: <b>${esc(a.department)}</b> · due ${fmtDate(a.due)}</span>
    ${a.status !== "completed" ? `<span><button class="ghost sm" data-req="${a.id}">Request message</button> <button class="ghost sm" data-act="${a.id}" data-st="completed">Mark completed</button></span>` : `<span>${a.completed ? "closed " + esc(a.completed.slice(0, 16).replace("T", " ")) : ""}</span>`}</div>
    ${a.history?.length > 1 ? `<details class="small muted"><summary>History</summary>${a.history.map((h) => `<div>${esc(h.ts.slice(0, 16).replace("T", " "))} ${esc(h.event)}</div>`).join("")}</details>` : ""}</div>`;
}
function requestText(a) {
  const c = S.data.case, p = c.patient || {};
  return `Tumour Board Case File ${c.case_id}: ${p.name || ""}${p.mrn ? ", UHID " + p.mrn : ""}${p.agesex ? ", " + p.agesex : ""}
To: ${a.department}
Required before the Tumour Board${c.board_date ? " on " + fmtDate(c.board_date) : ""}: ${a.label}
Details: ${a.what}
Please upload the final, signed report to the Case File by ${fmtDate(a.due)}. The Case File is re-checked automatically when it arrives.
(Generated by Vaidyx Tumour Board assistant, action ${a.id})`;
}
function bindActions(root) {
  $$("[data-req]", root).forEach((b) => (b.onclick = () => {
    const a = (S.data.state.actions || []).find((x) => x.id === b.dataset.req);
    $("#modal-body").innerHTML = `<h3 style="color:#00183c;margin-top:0">Request to ${esc(a.department)}</h3><textarea id="reqtxt" style="width:100%;min-height:190px;padding:10px;border:1px solid #e2e8f0;border-radius:8px">${esc(requestText(a))}</textarea>
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
  watchJob((await r.json()).job);
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
      const extra = [j.skipped_duplicates?.length ? `${j.skipped_duplicates.length} identical file(s) already in the Case File were skipped` : "", j.unsupported?.length ? `${j.unsupported.length} file(s) not read: ` + j.unsupported.map(u => `${u.file} (${u.reason})`).join(", ") : ""].filter(Boolean).join("; ");
      toast(`Processed ${j.total} documents in ${j.seconds} s. Pre-Authorization re-checked: ${j.gate.satisfied}/${j.gate.total} satisfied.${extra ? " " + extra + "." : ""}`, 7000);
      await openCase(S.caseId, true); break;
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
    const st = d.state !== "ready" ? `<span class="chip ${d.state === "error" ? "c-bad" : "c-info"}" title="${esc(d.error || "")}">${esc(d.state)}</span>` : statusChip(c) + (att?.attested_final ? ` <span class="chip c-ok" title="${esc(att.reason || "")}">attested final by ${esc(att.by)}</span>` : "");
    const unst = d.state === "ready" && c.status === "UNSTATED" && c.signed !== "no" && !att?.attested_final;
    return `<tr class="click" data-doc="${esc(d.doc_id)}"><td><b>${esc(c.title || d.filename)}</b><div class="small muted">${esc(d.rel_path)}${d.identity === "mismatch_or_missing" ? ' · <span style="color:#b23a2f">patient ID not found</span>' : d.identity === "name_match" ? ' · <span style="color:#a96e0a">matched by name only</span>' : ""}</div></td>
      <td>${esc(DT[c.doc_type] || c.doc_type || "")}</td><td>${fmtDate(c.report_date_iso)}</td><td>${st}</td>
      <td class="small">${(d.methods || []).map((m) => (m === "vision-transcription" ? "Vision reader (scan)" : m === "text-layer" ? "PDF text layer" : m)).join(", ")}</td>
      <td>${nf.filter((f) => f.verification === "verified").length} verified${nf.filter((f) => f.verification !== "verified").length ? ` · <span class="chip c-rev">${nf.filter((f) => f.verification !== "verified").length} not verified</span>` : ""}
      <div style="margin-top:4px;display:flex;gap:4px">${unst ? `<button class="ghost sm" data-attest-doc="${esc(d.doc_id)}">Attest final</button>` : ""}<button class="ghost sm" data-del-doc="${esc(d.doc_id)}" title="Remove this document from the Case File (audited)">Remove</button></div></td></tr>`; }).join("")}
  </tbody></table></div>
  <div class="card"><h3>Primary fields across the Case File</h3><div class="muted small" style="margin-bottom:8px">Current value = most recent verified value from a final, signed document. Every value links to its source quote.</div>
  <table class="t"><thead><tr><th>Field</th><th>Current value</th><th>Source</th><th>History</th></tr></thead><tbody>
  ${Object.entries(S.data.facts).map(([k, f]) => { const c = f.current;
    return `<tr><td>${esc(f.label)}</td><td><b>${esc(c.value)}</b> ${c.state === "pending" ? '<span class="chip c-warn">pending</span>' : ""}${c.verification !== "verified" ? '<span class="chip c-rev">' + esc(c.verification) + "</span>" : ""}${!c.doc_final ? '<span class="chip c-bad">non-final doc</span>' : ""}</td>
      <td>${citeHTML({ ...c.location, doc_id: c.doc_id, doc_title: c.doc_title, date: c.date, quote: c.quote })}</td>
      <td class="small muted">${f.history.length > 1 ? f.history.map((h) => `${esc(h.value)} (${fmtDate(h.date)})`).join(" → ") : ""}</td></tr>`; }).join("")}
  </tbody></table></div>`;
  $$("tr[data-doc]").forEach((tr) => (tr.onclick = (e) => { if (!e.target.closest("button")) openDoc(tr.dataset.doc); }));
  $$("[data-attest-doc]").forEach((b) => (b.onclick = () => attestDoc(b.dataset.attestDoc)));
  $$("[data-del-doc]").forEach((b) => (b.onclick = async () => { if (!confirm("Remove this document from the Case File? The removal is recorded in the audit log.")) return;
    await api(`/cases/${S.caseId}/documents/${b.dataset.delDoc}`, { method: "DELETE" }); await openCase(S.caseId, true); toast("Document removed; Pre-Authorization re-checked"); }));
}

async function openDoc(docId, focus) {
  const d = await api(`/cases/${S.caseId}/documents/${docId}`);
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
  const preview = isImg ? `<img class="orig" src="/api/tb/cases/${S.caseId}/documents/${docId}/file">` :
    isPdf ? `<img class="orig" id="pdfimg" src="/api/tb/cases/${S.caseId}/documents/${docId}/file?render=1&page=${pg}">` : `<div class="muted">No image preview for this format.</div>`;
  $("#drawer-body").innerHTML = `<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
    <div><div class="eyebrow">${esc(DT[c.doc_type] || c.doc_type || "")} · ${esc(c.department || "")}</div><h2 style="margin:4px 0;color:#00183c">${esc(c.title || d.filename)}</h2>
    <div class="muted small">${esc(d.rel_path)} · ${fmtDate(c.report_date_iso)} · ${statusChip(c)}${(c.status_notes || []).length ? ` <span class="chip c-warn">${esc(c.status_notes.join("; "))}</span>` : ""}</div></div>
    <div><a class="ghost" href="/api/tb/cases/${S.caseId}/documents/${docId}/file" target="_blank">Open original</a> <button class="ghost" data-close>Close</button></div></div>
    <div class="kv" style="margin:12px 0"><div>Status line</div><div>${esc(c.status_quote || "not found")}</div><div>Signature</div><div>${esc(c.signature_quote || c.signer || "not found")}</div>
    <div>Patient ID check</div><div>${d.identity === "match" ? "UHID / MRN matches the Case File patient" : d.identity === "name_match" ? "Patient name matches (identifier not found in the document)" : "Not found in document: verify it belongs to this patient"}</div>
    <div>Read by</div><div>${esc([...new Set(pages.map((p) => p.method))].join(", "))}${pages.some((p) => p.ocr_reads) ? " (two independent reads per scanned page; numbers compared)" : ""}</div></div>
    <div class="docview"><div>${preview}</div><div>
      ${pages.length > 1 ? `<div style="margin-bottom:6px">${pages.map((p, i) => `<button class="ghost sm" data-pg="${i}">Page ${i + 1}</button>`).join(" ")}</div>` : ""}
      <div class="doctext" id="doctext">${marks(pg)}</div>
      <h4 style="color:#00183c">Fields found in this document</h4>
      <table class="t"><tbody>${Object.entries(d.facts || {}).map(([k, f]) => `<tr><td>${esc(k)}</td><td><b>${esc(f.value)}</b>${f.state === "pending" ? ' <span class="chip c-warn">pending</span>' : ""}</td>
        <td><span class="chip ${f.verification === "verified" ? "c-ok" : "c-rev"}" title="${esc(f.reason || "")}">${esc(f.verification)}</span>${f.polarity === "negated" ? ' <span class="chip c-mute" title="The value is a negative finding (no / not / negative / absent)">negated</span>' : ""}</td><td class="small muted">"${esc(f.quote)}"</td></tr>`).join("") || '<tr><td class="muted">None</td></tr>'}</tbody></table>
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
      <div style="display:flex;gap:6px"><input placeholder="Optional focus question" id="focus-${k}" style="flex:1;padding:6px 8px;border:1px solid #e2e8f0;border-radius:8px;font-size:12px">
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
  box.innerHTML = `<h3>${esc(b.label)} <span>${rv.status === "reviewed" ? `<span class="chip c-ok">Reviewed by ${esc(rv.by)}</span>` : rv.status === "flagged" ? `<span class="chip c-bad">Flagged for correction</span>` : `<span class="chip c-rev">AI draft · awaiting expert review</span>`}</span></h3>
    <div class="small muted">${esc(b.generated?.replace("T", " "))} · ${b.seconds} s · ${esc(b.model)}${b.dropped_unverified ? ` · ${b.dropped_unverified} unverified item(s) removed` : ""}${b.guardrail_removed ? ` · ${b.guardrail_removed} removed by scope guardrail` : ""}</div>
    ${b.sections.map((s) => `<h4>${esc(s.heading)}</h4><ul>${s.items.map((it) => `<li>${esc(it.text)} ${it.citations.map(citeHTML).join("")}${flagHTML(it)}</li>`).join("")}</ul>`).join("")}
    ${b.points_for_review.length ? `<h4>Points for review (not treatment recommendations)</h4><ul>${b.points_for_review.map((it) => `<li>${esc(it.text)} ${it.citations.map(citeHTML).join("")}</li>`).join("")}</ul>` : ""}
    ${b.not_documented.length ? `<h4>Not documented</h4><ul>${b.not_documented.map((x) => `<li class="muted">${esc(x)}</li>`).join("")}</ul>` : ""}
    ${reviewBar("brief_" + role, rv)}`;
  bindReview(box);
}
function reviewBar(art, rv) {
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
    <div style="margin-top:10px;display:flex;gap:8px"><button class="primary" id="sum" ${g?.passed ? "" : "disabled"}>${s ? "Regenerate" : "Compile Case File summary"}</button>
    ${g?.passed ? "" : `<button class="ghost" id="sum-force">Compile draft anyway (marked incomplete)</button>`}${s ? `<button class="ghost" id="sum-print">Print</button>` : ""}</div></div>
    <div id="sumout" class="card summary ${s ? "" : "hidden"}"></div>
    <div class="card"><h3>Guideline references for this Case File <button class="ghost sm" id="gl-case">Find relevant sections</button></h3>
      <div class="muted small">Reference text retrieved from the guideline library for the board to consult, India first (National Cancer Grid, ICMR), then international. Not a recommendation for this patient.</div><div id="glout"></div></div>`;
  const go = async (force) => { $("#sumout").classList.remove("hidden"); $("#sumout").innerHTML = `<span class="spin"></span> Compiling from the signed records...`;
    const r = await api(`/cases/${S.caseId}/summary`, { json: { force } }); if (r.status === "gate_not_met") { $("#sumout").innerHTML = esc(r.message); return; }
    S.data = await api("/cases/" + S.caseId); showSummary(r); };
  $("#gl-case").onclick = async () => { $("#glout").innerHTML = `<span class="spin"></span> Searching the guideline library...`;
    const r = await api(`/cases/${S.caseId}/guidelines`); $("#glout").innerHTML = r.queries.map((q) => `<h4 style="color:#00183c;margin:14px 0 4px">${esc(q.query)}</h4>` + glHTML(q)).join(""); };
  $("#sum").onclick = () => go(false); if ($("#sum-force")) $("#sum-force").onclick = () => go(true);
  if ($("#sum-print")) $("#sum-print").onclick = () => { document.body.classList.add("print-summary"); window.print(); setTimeout(() => document.body.classList.remove("print-summary"), 500); };
  if (s) showSummary(s);
}
function showSummary(s) {
  const p = S.data.case.patient || {};
  const rv = s.review || {};
  $("#sumout").innerHTML = `<div class="eyebrow">Automated Case File summary${s.status !== "ready" ? " · INCOMPLETE: Pre-Authorization not met" : ""}</div>
    <h2 style="color:#00183c;margin:4px 0 12px">${esc(p.name)} · ${esc(p.agesex || "")}</h2>
    ${s.structure ? `<div class="muted small" style="margin-bottom:8px">Structure: ${esc(s.structure)}</div>` : ""}
    ${(s.sections || []).length ? s.sections.map((sec) => `<h4 style="color:#00183c;margin:12px 0 4px">${esc(sec.title)}</h4>${sec.sentences.length ? `<p>${sec.sentences.map((x) => `<span ${x.from_fields ? 'title="Added from the verified primary fields (no model text)" style="color:#334155"' : ""}>${esc(x.text)}</span> ${x.citations.map(citeHTML).join("")}${flagHTML(x)}`).join(" ")}</p>` : `<p class="muted small">Nothing verified for this section in the Case File.</p>`}`).join("")
      : s.paragraphs.map((para) => `<p>${para.map((x) => `${esc(x.text)} ${x.citations.map(citeHTML).join("")}${flagHTML(x)}`).join(" ")}</p>`).join("")}
    ${s.stage_as_recorded ? `<div class="stagebox"><b>Stage, as recorded in the ${esc(s.stage_as_recorded.doc_title)}:</b> ${esc(s.stage_as_recorded.value)} ${citeHTML({ ...s.stage_as_recorded, quote: s.stage_as_recorded.quote })}<div class="small muted">Extracted from the signed source report. The agent does not derive or assign stage.</div></div>` : ""}
    ${s.points_for_review.length ? `<h4 style="color:#00183c">Points for review</h4><ul>${s.points_for_review.map((x) => `<li>${esc(x.text)} ${x.citations.map(citeHTML).join("")}</li>`).join("")}</ul>` : ""}
    <div class="small muted">${esc(s.generated?.replace("T", " "))} · ${s.seconds} s · ${esc(s.model)}${s.dropped_unverified ? ` · ${s.dropped_unverified} unverified sentence(s) removed` : ""}${s.filled_from_fields ? ` · ${s.filled_from_fields} sentence(s) added from verified fields` : ""}</div>
    ${reviewBar("summary", rv)}`;
  bindReview($("#sumout"));
}

function glHTML(r) {
  const one = (h) => `<div class="hit"><div class="small"><span class="chip ${h.region === "India" ? "c-ok" : h.region === "US" ? "c-mute" : "c-info"}">${esc(h.region)}</span> <b>${esc(h.org)}</b> · ${esc(h.title)} · page ${h.page}
    <a href="/api/tb/guidelines/file?path=${encodeURIComponent(h.file)}#page=${h.page}" target="_blank">open</a></div><div style="margin-top:4px">${esc(h.text.slice(0, 520))}${h.text.length > 520 ? "..." : ""}</div></div>`;
  return (r.india.length ? r.india.map(one).join("") : `<div class="small muted">No Indian guideline passage matched.</div>`) + r.international.map(one).join("");
}

// ------------------------------------------------------------------ tab: board & follow-up
function renderBoard() {
  const st = S.data.state;
  const depts = ["Medical Oncology", "Surgical Oncology", "Radiation Oncology", "Radiology", "Pathology", "Molecular Pathology", "Nuclear Medicine", "Laboratory Medicine", "GI Oncology", "Gastroenterology", "Pulmonology", "Tumour Board coordinator"];
  const records = (st.board_records || []).slice().reverse();
  const allActs = (st.actions || []).slice().sort((a, b) => (a.status === "completed") - (b.status === "completed") || a.due.localeCompare(b.due));
  $("#tab-board").innerHTML = `<div class="grid2"><div>
    <div class="card form"><h3>Record the Tumour Board decision</h3><div class="muted small">Entered by the clinical team. The agent then checks the record (AI-assisted adjudication): documentation completeness, values against the signed sources, open Pre-Authorization items. It does not judge the clinical decision.</div>
      <label>Board date</label><input type="date" id="b-date" value="${new Date().toISOString().slice(0, 10)}">
      <label>Decision recorded by the board</label><textarea id="b-text" placeholder="As decided and dictated by the board"></textarea>
      <label>Recorded by</label><input id="b-by" placeholder="Name, role">
      <label>Participants present (names and specialties)</label><input id="b-part" placeholder="e.g. Dr A (Med Onc), Dr B (Surg Onc), Dr C (Radiology), Dr D (Pathology)">
      <label>Report corrections or discrepancies raised at the meeting (if any)</label><input id="b-corr" placeholder="e.g. Pathology to issue addendum correcting PD-L1 TPS">
      <label>Divergent opinions / dissenting clinicians (if any)</label><input id="b-div" placeholder="Recorded verbatim, with names">
      <label>Actions (Responsible Department · task · due)</label><div id="b-acts"></div><button class="ghost sm" id="b-add">+ Action</button>
      <label>Next Tumour Board review</label><input type="date" id="b-next">
      <div style="margin-top:12px"><button class="primary" id="b-save">Save record and run adjudication</button></div></div>
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
  addRow();
  $("#b-add").onclick = () => addRow();
  $("#b-save").onclick = async () => {
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
  $("#modal-body").innerHTML = `<h2 style="color:#00183c;margin-top:0">Model and data cards</h2>
    <p class="muted small">Every model and data asset used by the system ships with a published card: source, version, intended use, provenance, limitations.</p>
    ${r.cards.map((c) => `<div class="card"><h3>${esc(c.name)} <span>${(c.tags || []).map((t) => `<span class="chip ${/chin/i.test(t) ? "c-cn" : /non-medical/i.test(t) ? "c-nm" : "c-info"}">${esc(t)}</span>`).join(" ")}</span></h3>
      <div class="kv">${Object.entries(c.fields || {}).map(([k, v]) => `<div>${esc(k)}</div><div>${esc(v)}</div>`).join("")}</div></div>`).join("")}
    <div style="text-align:right;margin-top:12px"><button class="ghost" data-closemodal>Close</button></div>`;
  $("#modal").classList.remove("hidden");
}

// ------------------------------------------------------------------ new case
async function newCase() {
  const ps = S.protocols;
  $("#modal-body").innerHTML = `<h2 style="color:#00183c;margin-top:0">New Tumour Board Case File</h2><div class="form">
    <label>Case File ID</label><input id="n-id" placeholder="e.g. TB-2026-0142">
    <label>Patient name</label><input id="n-name"><label>UHID / MRN</label><input id="n-mrn"><label>Age / Sex</label><input id="n-agesex" placeholder="62 Y / M">
    <label>Protocol</label><select id="n-prot">${ps.map((p) => `<option value="${esc(p.id)}">${esc(p.label)} (v${esc(p.version)})</option>`).join("")}</select>
    <label>Board date</label><input type="date" id="n-date">
    <div style="margin-top:14px;display:flex;gap:8px;justify-content:flex-end"><button class="ghost" data-closemodal>Cancel</button><button class="primary" id="n-go">Create</button></div></div>`;
  $("#modal").classList.remove("hidden");
  $("#n-go").onclick = async () => {
    try {
      const c = await api("/cases", { json: { case_id: $("#n-id").value.trim(), protocol: $("#n-prot").value, board_date: $("#n-date").value,
        patient: { name: $("#n-name").value, mrn: $("#n-mrn").value, agesex: $("#n-agesex").value } } });
      $("#modal").classList.add("hidden"); S.tab = "ready"; await openCase(c.case_id);
    } catch (e) { toast(e.message); }
  };
}

// ------------------------------------------------------------------ boot
$$("#tabs button").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
$("#btn-new").onclick = newCase;
$("#btn-cards").onclick = showCards;
(async () => {
  const pr = await api("/protocols"); S.protocols = pr.protocols; S.facts = pr.facts;
  await loadCases(); loadModels(); setInterval(loadModels, 30000);
  const m = location.hash.match(/case=([\w.-]+)/); if (m) openCase(m[1]);
})();

// small screens: the case list is a slide-over panel
(function () {
  const btn = document.getElementById("btn-side"); if (!btn) return;
  const set = (on) => { document.body.classList.toggle("side-open", on); btn.setAttribute("aria-expanded", on ? "true" : "false"); };
  btn.addEventListener("click", () => set(!document.body.classList.contains("side-open")));
  document.addEventListener("click", (e) => {
    if (!document.body.classList.contains("side-open")) return;
    if (e.target.closest(".side .citem, .side [data-demo], .side #btn-new") || (!e.target.closest(".side") && !e.target.closest("#btn-side"))) set(false);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") set(false); });
  window.addEventListener("resize", () => { if (innerWidth > 860) set(false); });
})();
