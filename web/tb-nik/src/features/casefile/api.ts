// Every call the Case File page makes. New endpoints (SPEC-API) first; where one answers 404 the page falls back
// to what the old routes already carry, and says so.
import { api, ApiError, TB } from "@/lib/api";
import { errorCode, routeMissing } from "@/lib/live";
import type {
  CaseFile, SlotsResponse, Slot, SlotSection, QuoteBoxes, ChatThread, Helper, HelperMessage, PublishedResult, PublishedSearch, Team, Proposal,
  Urgency, Job, RequestDraft, GateRequirement, CaseAction,
} from "./types";

const enc = encodeURIComponent;
export const caseUrl = (id: string) => `${TB}/cases/${enc(id)}`;

/** True when the server answered 404 for a route that is not built yet (as opposed to a missing Case File). */
export function notBuiltYet(e: unknown): boolean {
  return routeMissing(e);
}
export { errorCode };

// ---- the Case File itself ---------------------------------------------------------------------------------------
export const getCase = (id: string, signal?: AbortSignal) => api.get<CaseFile>(caseUrl(id), { signal });
export const getJob = (jobId: string) => api.get<Job>(`${TB}/jobs/${enc(jobId)}`);

// ---- slots -------------------------------------------------------------------------------------------------------
export const getSlots = (id: string) => api.get<SlotsResponse>(`${caseUrl(id)}/slots`);
export const setSlotValue = (id: string, slot: string, value: string, note?: string) => api.post<Slot>(`${caseUrl(id)}/slots/${enc(slot)}/value`, { value, note });
export const clearSlotValue = (id: string, slot: string) => api.del<Slot>(`${caseUrl(id)}/slots/${enc(slot)}/value`);
export const slotNotNeeded = (id: string, slot: string, reason: string) => api.post<Slot>(`${caseUrl(id)}/slots/${enc(slot)}/not-needed`, { reason });
export const slotAskDepartment = (id: string, slot: string, message?: string, due?: string) => api.post<{ slot: Slot; request: unknown }>(`${caseUrl(id)}/slots/${enc(slot)}/ask-department`, { message, due });
export const getQuoteBoxes = (id: string, doc: string, q: { fact?: string; text?: string }) => {
  const qs = q.fact ? `fact=${enc(q.fact)}` : `text=${enc(q.text ?? "")}`;
  return api.get<QuoteBoxes>(`${caseUrl(id)}/documents/${enc(doc)}/quote?${qs}`);
};

// ---- old routes the page still uses -----------------------------------------------------------------------------
// The server's draft names the internal checklist level ("(Level 1: Case File)"); the department does not need it.
const noLevel = (t?: string) => (t ?? "").replace(/\s*\(Level \d+[^)]*\)/g, "");
export const getRequestDraft = async (id: string, action: string): Promise<RequestDraft> => {
  const d = await api.get<RequestDraft>(`${caseUrl(id)}/requests/${enc(action)}/draft`);
  return { ...d, body: noLevel(d.body), subject: noLevel(d.subject) };
};
export const sendRequest = (id: string, action: string, body: { message?: string; due?: string; subject?: string }) => api.post(`${caseUrl(id)}/requests/${enc(action)}/send`, body);
export const remindRequest = (id: string, action: string) => api.post(`${caseUrl(id)}/requests/${enc(action)}/remind`, {});
export const createFreeRequest = (id: string, body: { department: string; label: string; what?: string; message?: string; due?: string }) => api.post(`${caseUrl(id)}/requests`, body);
export const postConfirmation = (id: string, body: { type: string; key: string; fields?: Record<string, unknown>; reason?: string }) =>
  api.post<{ confirmation: { id: string }; state: unknown }>(`${caseUrl(id)}/confirmations`, body);
export const undoConfirmation = (id: string, conf: string) => api.post(`${caseUrl(id)}/confirmations/${enc(conf)}/undo`, {});
export const markReady = (id: string, ready: boolean, note?: string) => api.post(`${caseUrl(id)}/ready`, { ready, note });
export const buildSummary = (id: string, force = false) => api.post<Record<string, unknown>>(`${caseUrl(id)}/summary`, { force });
export const reviewArtefact = (id: string, artefact: string, status = "reviewed", comment = "") => api.post(`${caseUrl(id)}/review`, { artefact, status, comment });
export const refetchHis = (id: string) => api.post<{ job: string; total: number }>(`${caseUrl(id)}/his/refetch`, {});
export const uploadDocuments = (id: string, files: File[], outside: boolean) => {
  const form = new FormData();
  files.forEach((f) => form.append("files", f, f.name));
  form.append("paths", JSON.stringify(files.map((f) => f.name)));
  form.append("outside", outside ? "1" : "0");
  return api.upload<{ job: string; total: number; warnings?: string[] }>(`${caseUrl(id)}/documents`, form);
};
export const openImages = (id: string, doc: string) => api.post<{ available: boolean; viewer_url?: string; reason?: string; modality?: string; instances?: number }>(`${caseUrl(id)}/documents/${enc(doc)}/images`, {});
export const docFileUrl = (id: string, doc: string, page?: number) => `${caseUrl(id)}/documents/${enc(doc)}/file` + (page !== undefined ? `?render=1&page=${page}` : "");
export const exportVtbUrl = (id: string) => `${caseUrl(id)}/export/vtb`;
export const askOld = (id: string, question: string) => api.post<{ status: string; statements: Array<{ text: string; citations: Array<{ doc_id: string; doc_title?: string; title?: string; page?: number; quote?: string }> }>; message?: string; seconds?: number }>(`${caseUrl(id)}/ask`, { question });

// ---- chats ---------------------------------------------------------------------------------------------------------
export const getChats = (id: string) => api.get<{ threads: ChatThread[] }>(`${caseUrl(id)}/chats`);
export const postChat = (id: string, question: string) => api.post<ChatThread>(`${caseUrl(id)}/chats`, { question });
export const pinChat = (id: string, tid: string, pinned: boolean) => api.post<ChatThread>(`${caseUrl(id)}/chats/${enc(tid)}/pin`, { pinned });

// ---- helpers -------------------------------------------------------------------------------------------------------
export const getHelpers = (id: string) => api.get<{ helpers: Helper[]; heads?: string[] }>(`${caseUrl(id)}/helpers`);
/** helpers.py answers {job, status, reused}; job is the job id (or a job object on an older draft). */
export const prepareHelper = async (id: string, role: string, refresh = false) => {
  const r = await api.post<{ job?: string | { id: string } | null; status?: string; reused?: boolean }>(`${caseUrl(id)}/helpers/${enc(role)}/prepare`, { refresh });
  const job = typeof r.job === "string" ? r.job : r.job && typeof r.job === "object" ? r.job.id : null;
  return { job, status: r.status, reused: !!r.reused };
};
export const getHelperChat = (id: string, role: string) => api.get<{ messages: HelperMessage[] }>(`${caseUrl(id)}/helpers/${enc(role)}/chat`);
export const postHelperChat = (id: string, role: string, question: string) => api.post<HelperMessage>(`${caseUrl(id)}/helpers/${enc(role)}/chat`, { question });
export const askAgentOld = (id: string, role: string, question: string) => api.post<HelperMessage>(`${caseUrl(id)}/agents/${enc(role)}/ask`, { question });
export const getRoles = () => api.get<Record<string, { label: string; department?: string; focus?: string }>>(`${TB}/roles`);
/** The old brief preparation streams NDJSON events {type: start|step|brief|error}; used when helpers.py is not on the server. */
export async function streamAgentOld(id: string, role: string, onEvent: (ev: { type: string; text?: string; step?: string; [k: string]: unknown }) => void, signal?: AbortSignal): Promise<void> {
  const res = await fetch(`${caseUrl(id)}/agents/${enc(role)}`, { method: "POST", credentials: "same-origin", headers: { "X-Requested-With": "tb-nik", "Content-Type": "application/json", Accept: "application/x-ndjson" }, body: "{}", signal });
  if (!res.ok || !res.body) throw new ApiError(res.status, res.status === 403 ? "You do not have permission for this." : "The helper could not start.");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line) continue;
      try { onEvent(JSON.parse(line)); } catch { /* a partial line */ }
    }
  }
}

// ---- published cases -----------------------------------------------------------------------------------------------
export const getPublished = (id: string) => api.get<{ items: PublishedResult[]; searches: Array<PublishedSearch | string>; label?: string }>(`${caseUrl(id)}/published`);
export const searchPublished = (id: string, terms: string) => api.post<{ results: PublishedResult[]; error?: string }>(`${caseUrl(id)}/published/search`, { terms });
export const addPublished = (id: string, result: PublishedResult, quotes?: PublishedResult["quotes"]) => api.post<PublishedResult>(`${caseUrl(id)}/published`, { result, quotes });
export const removePublished = (id: string, pid: string) => api.del(`${caseUrl(id)}/published/${enc(pid)}`);

// ---- team, proposals, urgency ----------------------------------------------------------------------------------------
export const getTeam = (id: string) => api.get<Team>(`${caseUrl(id)}/team`);
export const newJoinCode = (id: string) => api.post<{ code: string; expires_at: string }>(`${caseUrl(id)}/team/code`, {});
export const dropJoinCode = (id: string) => api.del(`${caseUrl(id)}/team/code`);
export const approveJoin = (id: string, user: string, note?: string) => api.post(`${caseUrl(id)}/team/pending/${enc(user)}/approve`, { note });
export const rejectJoin = (id: string, user: string, note?: string) => api.post(`${caseUrl(id)}/team/pending/${enc(user)}/reject`, { note });
export const removeResident = (id: string, user: string) => api.del(`${caseUrl(id)}/team/residents/${enc(user)}`);
export const getProposals = (id: string) => api.get<{ proposals: Proposal[] }>(`${caseUrl(id)}/proposals`);
export const postProposal = (id: string, action: string, payload: Record<string, unknown>, note?: string) => api.post<{ proposal: Proposal }>(`${caseUrl(id)}/proposals`, { action, payload, note });
export const approveProposal = (id: string, pid: string, note?: string) => api.post(`${caseUrl(id)}/proposals/${enc(pid)}/approve`, { note });
export const returnProposal = (id: string, pid: string, note: string) => api.post(`${caseUrl(id)}/proposals/${enc(pid)}/return`, { note });
export const setUrgency = (id: string, level: number, note?: string) => api.put<{ urgency?: Urgency; proposal?: Proposal }>(`${caseUrl(id)}/urgency`, { level, note });
export const archiveCase = (id: string, reason: string) => api.post(`${caseUrl(id)}/archive`, { reason });
export const unarchiveCase = (id: string) => api.post(`${caseUrl(id)}/unarchive`, {});

// ---- fallback: the fill-in summary derived from the old checklist ----------------------------------------------------
// When slots.py is not on the server yet, the page builds the same lines from state.gate.requirements, the resolved
// facts and the requests, so the doctor still sees what is found, what is waiting and what is not in the file.
const SECTION_OF: Array<{ id: string; label: string; match: RegExp }> = [
  { id: "history", label: "Presenting history and performance status", match: /history|ecog|performance|karnofsky|menopaus|weight|height|comorbid|presenting|symptom|clinical note|opd|referral/i },
  { id: "pathology", label: "Pathology", match: /histo|patholog|biops|hpe|ihc|immuno|er\b|pr\b|her2|ki.?67|grade|molecular|egfr|alk|ros1|pd-?l1|met\b|kras|braf|msi|specimen|cytolog|fnac/i },
  { id: "imaging", label: "Imaging", match: /ct\b|mri|pet|mammo|ultrasound|usg|x-?ray|imaging|scan|radiolog|bone scan|echo/i },
  { id: "labs", label: "Labs and tumour markers", match: /cbc|blood|lft|rft|kft|creatinine|haemoglobin|hemoglobin|platelet|marker|cea|ca\s?-?\s?125|ca\s?-?\s?19|psa|afp|ldh|hba1c|urea|electrolyte|hbs|hiv|hcv|bilirubin|biochem|serum/i },
  { id: "staging", label: "Staging data as recorded", match: /stag|tnm|metast|nodal|node|size|laterality|figo|extent/i },
  { id: "prior", label: "Prior treatment", match: /prior|previous|treatment|chemo|radiat|surgery|operat|therapy|regimen/i },
  { id: "question", label: "Board question", match: /question|clinical_question|board/i },
];
const SECTION_ORDER = SECTION_OF.map((s) => s.id);

function sectionFor(label: string, fallback = "history"): string {
  for (const s of SECTION_OF) if (s.match.test(label)) return s.id;
  return fallback;
}

export function deriveSlots(cf: CaseFile): SlotsResponse {
  const reqs: GateRequirement[] = cf.state?.gate?.requirements ?? [];
  const actions: CaseAction[] = cf.state?.actions ?? [];
  const byReq = new Map<string, CaseAction>();
  for (const a of actions) if (a.source === "pre_authorization" && a.requirement && a.status !== "completed") byReq.set(a.requirement, a);
  const docTitle = (docId?: string) => cf.documents.find((d) => d.doc_id === docId)?.classification?.title || cf.documents.find((d) => d.doc_id === docId)?.filename || "record";
  const sections = new Map<string, SlotSection>();
  const push = (sec: string, slot: Slot) => {
    const label = SECTION_OF.find((s) => s.id === sec)?.label ?? sec;
    if (!sections.has(sec)) sections.set(sec, { id: sec, label, slots: [] });
    sections.get(sec)!.slots.push(slot);
  };
  let left = 0;
  const blockers: SlotsResponse["blockers"] = [];
  for (const r of reqs) {
    const act = byReq.get(r.id);
    const ev = (r.evidence ?? [])[0];
    let slot: Slot;
    if (r.status === "satisfied") {
      slot = { id: r.id, label: r.label, status: "found", value: ev?.value ?? "present", quote: ev?.doc_id ? { text: ev.quote ?? "", doc_id: ev.doc_id, doc_title: docTitle(ev.doc_id), page: ev.page ?? 0, fact_id: ev.fact } : (r.source_doc_id ? { text: "", doc_id: r.source_doc_id, doc_title: docTitle(r.source_doc_id), page: 0 } : null), actions: [] };
    } else if (r.status === "waived" || r.status === "not_applicable") {
      slot = { id: r.id, label: r.label, status: "not_needed", note: r.status === "waived" ? "Not needed, recorded by the consultant" : "Not applicable for this cancer and setting", actions: [] };
    } else if (act && (act.status === "pending" || act.status === "overdue")) {
      left += 1;
      slot = { id: r.id, label: r.label, status: "waiting", request: { action_id: act.id, department: act.department_id ?? act.department ?? "", department_label: act.department ?? "", sent_at: act.sent?.at, due: act.due ?? undefined, status: act.status }, actions: [{ kind: "remind", label: "Remind", action_id: act.id }] };
    } else if ((r.problems ?? []).length && (r.evidence ?? []).length) {
      left += 1; blockers.push({ slot_id: r.id, why: r.problems![0] });
      slot = { id: r.id, label: r.label, status: "needs_confirmation", value: ev?.value, quote: ev?.doc_id ? { text: ev.quote ?? "", doc_id: ev.doc_id, doc_title: docTitle(ev.doc_id), page: ev.page ?? 0, fact_id: ev.fact } : null, note: r.problems![0], confirmation: ev?.doc_id ? { type: "confirm_value", key: `${ev.doc_id}:${ev.fact ?? r.id}` } : null, actions: [{ kind: "review", label: "Review" }] };
    } else {
      left += 1; blockers.push({ slot_id: r.id, why: `${r.label}: not found in the file` });
      const acts: Slot["actions"] = [];
      if (act) acts.push({ kind: "ask_department", label: `Ask ${act.department ?? r.department ?? "the department"}`, department: act.department_id ?? act.department, department_label: act.department ?? r.department, action_id: act.id });
      acts.push({ kind: "not_needed", label: "Not needed" });
      slot = { id: r.id, label: r.label, status: "not_found", note: r.problems?.[0], actions: acts };
    }
    push(sectionFor(r.label, (r.department ?? "").match(/patholog/i) ? "pathology" : (r.department ?? "").match(/radiolog|nuclear/i) ? "imaging" : (r.department ?? "").match(/biochem|lab|haemat/i) ? "labs" : "history"), slot);
  }
  // Typed-value facts (ECOG, menopausal status, weight, height) and the board question always have a line.
  const typable: Array<{ id: string; label: string; sec: string }> = [
    { id: "ecog", label: "ECOG performance status", sec: "history" }, { id: "menopausal_status", label: "Menopausal status", sec: "history" },
    { id: "weight", label: "Weight", sec: "history" }, { id: "height", label: "Height", sec: "history" }, { id: "clinical_question", label: "Board question", sec: "question" },
  ];
  const facts = cf.facts ?? {};
  for (const t of typable) {
    const has = [...sections.values()].some((s) => s.slots.some((x) => x.id === t.id || x.label.toLowerCase() === t.label.toLowerCase()));
    if (has) continue;
    const f = facts[t.id];
    if (f?.current?.value) {
      push(t.sec, { id: t.id, label: t.label, status: "found", value: f.current.value, fact_id: t.id, typable: true, quote: f.current.doc_id ? { text: f.current.quote ?? "", doc_id: f.current.doc_id, doc_title: f.current.doc_title ?? docTitle(f.current.doc_id), page: f.current.location?.page ?? 0, fact_id: t.id } : null, actions: [] });
    } else {
      if (t.id === "clinical_question") left += 1;
      push(t.sec, { id: t.id, label: t.label, status: "not_found", fact_id: t.id, typable: true, actions: [{ kind: "enter_value", label: "Enter a value" }, ...(t.id === "clinical_question" ? [] : [{ kind: "not_needed" as const, label: "Not needed" }])] });
    }
  }
  // Every other resolved fact with a verified value is a found line in its section (never AI prose).
  for (const [fid, f] of Object.entries(facts)) {
    if (!f?.current?.value) continue;
    const exists = [...sections.values()].some((s) => s.slots.some((x) => x.quote?.fact_id === fid || x.id === fid));
    if (exists) continue;
    push(sectionFor(f.label || fid), { id: fid, label: f.label || fid, status: f.current.verification === "verified" ? "found" : "needs_confirmation", value: f.current.value, as_of: f.current.date ?? undefined, quote: f.current.doc_id ? { text: f.current.quote ?? "", doc_id: f.current.doc_id, doc_title: f.current.doc_title ?? docTitle(f.current.doc_id), page: f.current.location?.page ?? 0, fact_id: fid } : null, confirmation: f.current.verification !== "verified" && f.current.doc_id ? { type: "confirm_value", key: `${f.current.doc_id}:${fid}` } : null, actions: f.current.verification === "verified" ? [] : [{ kind: "review", label: "Review" }] });
  }
  const summary = cf.state?.artefacts?.summary;
  const prose: SlotsResponse["prose"] = summary
    ? { status: cf.stale?.summary ? "stale" : "ready", paragraphs: summary.paragraphs ?? (summary.sections ?? []).map((s) => s.text ?? (s.sentences ?? []).join(" ")).filter(Boolean), reviewed: summary.review?.status === "reviewed", reviewed_by: summary.review?.by, at: summary.review?.at }
    : { status: cf.case?.board_ready ? "pending" : "none", paragraphs: [], reviewed: false };
  const ordered = [...sections.values()].sort((a, b) => SECTION_ORDER.indexOf(a.id) - SECTION_ORDER.indexOf(b.id));
  return { sections: ordered, left_before_board: left, blockers, ready_allowed: left === 0 && !!cf.permissions?.mark_ready, prose, derived: true };
}

/** The owning department of a Case File as {id, name}, whatever shape the server used. */
export function ownerOf(cf: CaseFile | null | undefined): { id: string; name: string } {
  const o = cf?.access?.owner;
  if (o && typeof o === "object") return { id: o.id, name: o.name || o.id.replace(/_/g, " ") };
  const id = (typeof o === "string" && o) || cf?.case?.department || "";
  return { id, name: id.replace(/_/g, " ") };
}

function deptOf(d: string | { id: string; name?: string }): { id: string; label: string } {
  return typeof d === "string" ? { id: d, label: d.replace(/_/g, " ") } : { id: d.id, label: d.name || d.id.replace(/_/g, " ") };
}

export function deriveTeam(cf: CaseFile): Team {
  const owner = ownerOf(cf);
  return {
    owner: { department: owner.id, department_label: owner.name, doctors: cf.access?.owner_name ? [{ user: cf.access.owner_name, name: cf.access.owner_name }] : [] },
    residents: [], departments: (cf.access?.participants ?? []).map((p) => ({ ...deptOf(p.department), since: p.since })),
    join_code: null, pending: [], derived: true,
  };
}
