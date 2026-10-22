// Fixtures and routes for the Case File and meeting screenshot specs (e2e/shots/casefile.spec.ts, meetings.spec.ts).
// SYNTHETIC only: f2/case.json, slots.json and slides.json were built from a scratch copy of the demo Case File
// TB-DEMO-P19 ("Priya Venkatesan (SYNTHETIC)", Vaidyx Demo Hospital) by the backend's own slots.build and
// meetings.slides. Every route of the Case File and meeting pages is answered here, in mock and real mode alike, so the
// shots do not depend on what the running server has loaded; the shell (/me, the bell) comes from support/helpers.ts.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Page, Route, WebSocketRoute } from "@playwright/test";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const load = <T = any>(f: string): T => JSON.parse(fs.readFileSync(path.join(HERE, "f2", f), "utf8")); // eslint-disable-line @typescript-eslint/no-explicit-any
const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));

export const CID = "TB-DEMO-P19";
export const MID = "M-1";
export const baseCase = load("case.json");
export const baseSlots = load("slots.json");
export const baseSlides = load("slides.json");

const now = new Date();
const iso = (minutesAgo: number) => new Date(now.getTime() - minutesAgo * 60_000).toISOString();
const dayIso = (daysAhead: number) => { const d = new Date(now); d.setDate(d.getDate() + daysAhead); return d.toISOString().slice(0, 10); };

// ---- the Case File -------------------------------------------------------------------------------------------------------
/** The Case File as GET /cases/{id} answers it; the owner is the breast surgery team of the treating login in fixtures.ts. */
export function caseFile(over: Record<string, unknown> = {}) {
  const c = clone(baseCase);
  c.case.urgency = undefined;
  return { ...c, ...over };
}

type Slot = { id: string; status: string; [k: string]: unknown };
function patchSlot(slots: any, id: string, fn: (s: Slot) => void) { // eslint-disable-line @typescript-eslint/no-explicit-any
  for (const sec of slots.sections) for (const s of sec.slots) if (s.id === id) fn(s);
}

/** The real slots answer, plus one line in each state the page can show (waiting, entered, not found, needs confirmation). */
export function slotsAllStates() {
  const s = clone(baseSlots);
  patchSlot(s, "record:mri_breast", (x) => {
    x.status = "waiting";
    x.note = "No mri breast in the Case File";
    x.request = { action_id: "A7cecec", department: "Radiology", department_id: "radiology", department_label: "Radiology", sent_at: iso(60 * 26), sent_by: "rao@vxh.example", due: dayIso(1), due_label: "", status: "pending", reminders: 1, what: "MRI breast report, final and signed" };
    x.actions = [{ kind: "remind", label: "Remind", action_id: "A7cecec", department: "Radiology" }, { kind: "not_needed", label: "Not needed", reason_required: true }];
  });
  patchSlot(s, "fact:weight", (x) => {
    x.status = "entered"; x.value = "64"; x.unit = "kg"; x.typed_by = "rao@vxh.example"; x.typed_by_name = "Lakshmi Rao"; x.typed_at = iso(90);
    x.note = "entered by Lakshmi Rao, no report"; x.actions = [{ kind: "enter_value", label: "Change the value", fact_id: "weight" }];
  });
  s.left_before_board = 3;
  return s;
}

/** Before the ready mark: the narrative is a placeholder line and the prose block waits. */
export function slotsBeforeReady() {
  const s = slotsAllStates();
  s.prose = { status: "none", paragraphs: [], points_for_review: [], reviewed: false, label: "Written at the ready mark", generated: null, model: "", stale_reason: "", preparing: false };
  s.sections[0].slots.unshift({ id: "prose:history", kind: "prose", label: "History narrative (AI draft)", section: "presenting", required: false, status: "pending_ready", value: "", quote: null, request: null, confirmation: null, actions: [], note: "Written at the ready mark from the verified records; labelled AI draft until reviewed" });
  s.board_ready = null;
  return s;
}

export const chats = {
  threads: [
    {
      id: "T2", by: "asha@vxh.example", by_name: "Asha Menon", at: iso(35), question: "What did the HPE report say about the grade?", status: "answered", pinned: true, stale: false, seconds: 14,
      statements: [{ text: "The histopathology report records Grade 2 (Nottingham score 6).", citations: [{ doc_id: "D8a2c165d", doc_title: "HISTOPATHOLOGY REPORT", page: 0, quote: "Grade: Grade 2 (Nottingham score 6)" }] }],
    },
    {
      id: "T1", by: "rao@vxh.example", by_name: "Lakshmi Rao", at: iso(60 * 20), question: "Is a CT chest documented?", status: "not_documented", pinned: false, stale: true, seconds: 9, statements: [],
      message: "Not documented in the records of this Case File.",
    },
  ],
};

export const helpers = {
  heads: ["radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology"],
  helpers: [
    { role: "radiology", label: "Radiology support", department: "radiology", head: true, brief: { status: "none", at: null, sections: [], points_for_review: [], not_documented: [] }, thread_count: 0, prepare_allowed: true },
    { role: "pathology", label: "Pathology support", department: "pathology", head: true, brief: { status: "ready", at: iso(60 * 30), sections: baseCase.state.artefacts.brief_pathology.sections, points_for_review: baseCase.state.artefacts.brief_pathology.points_for_review, not_documented: baseCase.state.artefacts.brief_pathology.not_documented, model: "gemma-4-31b", label: "AI draft, not reviewed" }, thread_count: 2, prepare_allowed: true },
    { role: "medical_oncology", label: "Medical Oncology support", department: "medical_oncology", head: true, brief: { status: "preparing", at: null, sections: [], points_for_review: [], not_documented: [] }, thread_count: 0, prepare_allowed: true },
    { role: "surgical_oncology", label: "Surgical Oncology support", department: "surgical_oncology", head: true, brief: { status: "stale", at: iso(60 * 50), sections: [], points_for_review: [], not_documented: [], stale_reason: "A new report arrived" }, thread_count: 1, prepare_allowed: true },
    { role: "radiation_oncology", label: "Radiation Oncology support", department: "radiation_oncology", head: true, brief: { status: "none", at: null, sections: [], points_for_review: [], not_documented: [] }, thread_count: 0, prepare_allowed: true },
    { role: "nuclear_medicine", label: "Nuclear Medicine support", department: "nuclear_medicine", head: false, brief: { status: "none", at: null, sections: [], points_for_review: [], not_documented: [] }, thread_count: 0, prepare_allowed: true },
  ],
};

export const helperChat = {
  role: "pathology", label: "Pathology support",
  messages: [{ id: "H1", role: "pathology", by: "rao@vxh.example", by_name: "Lakshmi Rao", at: iso(40), question: "Are ER and PR reported with Allred scores?", status: "answered", stale: false,
    statements: [{ text: "ER is positive with Allred score 8/8 and PR positive with Allred score 5/8.", citations: [{ doc_id: "D6b012d3d", doc_title: "IMMUNOHISTOCHEMISTRY REPORT (ER, PR, HER2, Ki-67)", page: 0, quote: "ER: Positive (Allred score 8/8)" }] }] }],
};

export const published = {
  label: "Published case, not advice for this patient",
  searches: [{ by: "rao@vxh.example", at: iso(300), terms: "early breast cancer breast conserving surgery", counts: { local: 1, pubmed: 3 } }],
  items: [{
    id: "P1a2b3c4", title: "Breast-conserving surgery in early breast cancer: a case series from a tertiary centre (SYNTHETIC example)", authors: "Iyer S, Raman K", journal: "Indian Journal of Surgical Oncology (example)", year: 2024,
    doi: "", url: "https://example.org/paper", source: "local", peer_reviewed: true, kind: "paper", added_by: "rao@vxh.example", by_name: "Lakshmi Rao", at: iso(280),
    quotes: [{ text: "Breast-conserving surgery with sentinel node biopsy was performed in all patients.", where: "Methods, page 3" }],
  }],
};

export const publishedResults = {
  results: [
    { title: "Sentinel node biopsy after a negative axillary ultrasound (SYNTHETIC example)", authors: "Das P, Menon A", journal: "Breast (example)", year: 2023, doi: "10.0000/example.1", url: "https://example.org/a", source: "pubmed", peer_reviewed: true, kind: "paper" },
    { title: "Hypofractionated whole-breast radiotherapy: a preprint (SYNTHETIC example)", authors: "Rao V", journal: "medRxiv (example)", year: 2025, doi: "", url: "https://example.org/b", source: "europepmc", peer_reviewed: false, kind: "preprint" },
  ],
  counts: { local: 0, pubmed: 1, europepmc: 1 },
};

export function team(over: Record<string, unknown> = {}) {
  return {
    owner: { department: "breast_surgery", department_label: "Breast Surgery", doctors: [{ user: "rao@vxh.example", name: "Lakshmi Rao" }] },
    residents: [{ user: "asha@vxh.example", name: "Asha Menon", end_date: dayIso(90), added_by: "rao@vxh.example", since: iso(60 * 24 * 10), expired: false }],
    departments: [{ id: "radiology", label: "Radiology", since: iso(60 * 24 * 3) }, { id: "pathology", label: "Pathology", since: iso(60 * 24 * 3) }],
    join_code: { code: "482913", expires_at: new Date(now.getTime() + 6 * 864e5).toISOString(), uses: 1 },
    pending: [{ user: "kiran@vxh.example", name: "Kiran Shetty", requested_at: iso(25), department: "surgical_oncology", department_label: "Surgical Oncology" }],
    can: { manage: true, leave: false, set_urgency: true, propose: false, archive: true, consent: true },
    urgency: { level: 4, label: "high", set_by: "rao@vxh.example", set_by_name: "Lakshmi Rao", at: iso(200), note: "", proposed: null },
    archived: null, consent: null,
    ...over,
  };
}

export const proposals = {
  proposals: [
    { id: "PR-1", action: "not_needed", payload: { slot: "record:pet_ct", reason: "Early disease; PET/CT not planned" }, note: "", by: "asha@vxh.example", by_name: "Asha Menon", at: iso(50), status: "pending" },
    { id: "PR-2", action: "typed_value", payload: { slot: "fact:height", value: "158" }, note: "From the OPD vitals", by: "asha@vxh.example", by_name: "Asha Menon", at: iso(20), status: "pending" },
  ],
};

/** A synthetic report page (SVG) with the quote boxed where quote_boxes.py says it is. */
export function pageSvg(title: string, lines: string[]) {
  const esc = (t: string) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const rows = lines.map((l, i) => `<text x="60" y="${210 + i * 34}" font-size="20" fill="#1f2933">${esc(l)}</text>`).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="850" height="1100" viewBox="0 0 850 1100"><rect width="850" height="1100" fill="#ffffff"/><rect x="40" y="40" width="770" height="90" fill="#e6f3f7"/><text x="60" y="80" font-size="22" font-weight="bold" fill="#1f2933">Vaidyx Demo Hospital (SYNTHETIC)</text><text x="60" y="112" font-size="18" fill="#3e4c59">${esc(title)}</text>${rows}<text x="60" y="1060" font-size="14" fill="#52606d">SYNTHETIC document for screenshots. Digitally signed: Vaidyx Demo CA.</text></svg>`;
}

function docTitle(docId: string): string {
  const d = baseCase.documents.find((x: { doc_id: string }) => x.doc_id === docId);
  return d?.classification?.title ?? "REPORT";
}

export type CaseRouteOptions = {
  slots?: unknown | { status: number; body?: unknown };
  caseFile?: unknown | { status: number; body?: unknown };
  team?: unknown;
  proposals?: unknown;
  chats?: unknown;
  helpers?: unknown;
  published?: unknown;
  notBuilt?: Array<"slots" | "chats" | "helpers" | "published" | "team" | "proposals">;
  delayMs?: number;
};

const NOT_FOUND = { detail: "Not Found" };
const isReply = (x: unknown): x is { status: number; body?: unknown } => !!x && typeof x === "object" && "status" in (x as object) && typeof (x as { status: unknown }).status === "number" && Object.keys(x as object).length <= 2;

/** Answers every Case File route for CID. Register after helpers.prepare(): the last route registered runs first. */
export async function routeCaseFile(page: Page, o: CaseRouteOptions = {}) {
  const nb = new Set(o.notBuilt ?? []);
  await page.route(`**/api/tb/cases/${CID}**`, async (route: Route) => {
    const url = new URL(route.request().url());
    const m = route.request().method();
    const p = url.pathname.replace(`/api/tb/cases/${CID}`, "");
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    const reply = (x: unknown, fallback: () => unknown) => (isReply(x) ? json(x.body ?? { detail: { message: "The server could not answer (test).", code: "test" } }, x.status) : json(x ?? fallback()));
    if (o.delayMs && m === "GET" && (p === "" || p === "/")) await new Promise((r) => setTimeout(r, o.delayMs));
    if (m === "GET" && (p === "" || p === "/")) return reply(o.caseFile, () => caseFile());
    if (p === "/slots" && m === "GET") return nb.has("slots") ? json(NOT_FOUND, 404) : reply(o.slots, () => clone(baseSlots));
    if (p === "/chats" && m === "GET") return nb.has("chats") ? json(NOT_FOUND, 404) : json(o.chats ?? chats);
    if (p === "/chats" && m === "POST") return json({ ...chats.threads[0], id: "T3", at: new Date().toISOString(), question: JSON.parse(route.request().postData() || "{}").question, pinned: false });
    if (p === "/helpers" && m === "GET") return nb.has("helpers") ? json(NOT_FOUND, 404) : json(o.helpers ?? helpers);
    if (/^\/helpers\/[a-z_]+\/chat$/.test(p) && m === "GET") return json(helperChat);
    if (p === "/published" && m === "GET") return nb.has("published") ? json(NOT_FOUND, 404) : json(o.published ?? published);
    if (p === "/published/search") return json(publishedResults);
    if (p === "/team" && m === "GET") return nb.has("team") ? json(NOT_FOUND, 404) : json(o.team ?? team());
    if (p === "/proposals" && m === "GET") return nb.has("proposals") ? json(NOT_FOUND, 404) : json(o.proposals ?? proposals);
    if (/^\/documents\/[^/]+\/quote$/.test(p)) {
      const q = url.searchParams.get("text") || url.searchParams.get("fact") || "";
      return json({ found: true, page: 0, boxes: q ? [[0.065, 0.215, 0.82, 0.245]] : [], quote: q });
    }
    const file = /^\/documents\/([^/]+)\/file$/.exec(p);
    if (file) {
      const doc = baseCase.documents.find((x: { doc_id: string }) => x.doc_id === file[1]);
      const facts = Object.values((doc?.facts ?? {}) as Record<string, { quote?: string }>).map((f) => f.quote).filter(Boolean) as string[];
      return route.fulfill({ status: 200, contentType: "image/svg+xml", body: pageSvg(docTitle(file[1]), facts.length ? facts.slice(0, 18) : ["Report text (SYNTHETIC)."]) });
    }
    if (/^\/documents\/[^/]+\/images$/.test(p)) return json({ available: false, reason: "The study is not in the image viewer yet (SYNTHETIC test answer)." });
    if (/^\/requests\/[^/]+\/draft$/.test(p)) return json({ action_id: p.split("/")[2], to: "Radiology", subject: "Request for MRI breast report (VXH/26/004219)", body: "Dear colleague,\n\nFor the Tumour Board Case File of the patient below, please share the final, signed MRI breast report.\n\nThank you.", due: dayIso(3), accession: "RAD/26/01021" });
    if (m !== "GET") return json({ ok: true });
    return json(NOT_FOUND, 404);
  });
}

// ---- meetings ---------------------------------------------------------------------------------------------------------
const row = (o: Record<string, unknown>) => ({ owner_department: "breast_surgery", owner_department_name: "Breast Surgery", minutes: 10, reason: "", ready: true, status: "waiting", ended: false, outcome: null, outcome_label: "", added_after_send: false, urgency: null, ...o });

export function meetingState(status: "planned" | "in_session" | "closed" = "planned", over: Record<string, unknown> = {}) {
  const live = status === "in_session";
  return {
    meeting: { id: MID, date: dayIso(status === "closed" ? -4 : live ? 0 : 3), time: "16:00", room: "Seminar hall 2", status, video: false, minutes_per_case: 10, counts: { discussion: 3, noting: 1, not_ready: 1 }, agenda_sent_at: status === "planned" ? null : iso(60 * 30), title: "", created_by: "mdt@vxh.example", started_at: live ? iso(14) : null, closed_at: null, cancelled: null, current: live ? CID : null, people: 5, label: "Tumour Board" },
    agenda: {
      discussion: [
        row({ case_id: CID, patient_line: "Priya Venkatesan (SYNTHETIC), 52 Y / F, UHID VXH/26/004219", protocol: "breast", owner_name: "Lakshmi Rao", presenter_name: "Asha Menon", board_question: "Primary management plan", left_before_board: 0, order: 1, urgency: 4 }),
        row({ case_id: "TB-2026-0030", patient_line: "Fatima B., 46 F, UHID VXH/2026/000118", protocol: "breast", owner_name: "Lakshmi Rao", presenter_name: "Lakshmi Rao", board_question: "Neoadjuvant chemotherapy or upfront surgery as the board decides", left_before_board: 1, order: 2, ready: true, added_after_send: status !== "planned" }),
        row({ case_id: "TB-2026-0029", patient_line: "Kamala S., 61 F, UHID VXH/2026/000102", protocol: "cervix", owner_name: "Radha Devi", owner_department: "gynaecologic_oncology", owner_department_name: "Gynaecologic Oncology", presenter_name: "Radha Devi", board_question: "Chemoradiation plan as recorded; review the MRI pelvis", left_before_board: 0, order: 3 }),
      ],
      noting: [row({ case_id: "TB-2026-0019", patient_line: "Sunita P., 50 F, UHID VXH/2026/000064", protocol: "breast", owner_name: "Lakshmi Rao", presenter_name: "", board_question: "", left_before_board: 0, order: 1, outcome: status === "closed" ? "noted" : null, outcome_label: status === "closed" ? "Noted for information" : "" })],
      not_ready: [row({ case_id: "TB-2026-0024", patient_line: "Venkatesh M., 55 M, UHID VXH/2026/000081", protocol: "oral_cavity", owner_name: "Arun Pillai", owner_department: "ent_head_neck_surgery", owner_department_name: "ENT and Head and Neck Surgery", board_question: "", left_before_board: 4, order: 1, ready: false, reason: "HPE report awaited" })],
    },
    code: status === "closed" ? null : { value: "305718", expires_at: new Date(now.getTime() + 8 * 36e5).toISOString(), attempts: 2 },
    attendance: [
      { user: "mdt@vxh.example", name: "Priya Nair", department: "mdt", department_name: "MDT Coordinator", status: "present", mode: "room", online: true, head: false },
      { user: "rao@vxh.example", name: "Lakshmi Rao", department: "breast_surgery", department_name: "Breast Surgery", status: "present", mode: "room", online: true, head: false },
      { user: "shanthi@vxh.example", name: "Shanthi Raman", department: "radiology", department_name: "Radiology", status: "remote", mode: "remote", online: true, head: true },
      { user: "joseph@vxh.example", name: "Thomas Joseph", department: "medical_oncology", department_name: "Medical Oncology", status: "remote", mode: "remote", online: false, head: true },
      { user: "kiran@vxh.example", name: "Kiran Shetty", department: "surgical_oncology", department_name: "Surgical Oncology", status: "waiting", mode: null, online: true, head: true },
    ],
    current: { case_id: live ? CID : null, slide: live ? 1 : 0, opened: null, timer: live ? { seconds_left: 412, running: true, total: 600 } : null },
    decision_live: { text: live ? "Breast conservation surgery with sentinel node biopsy; adjuvant plan after the final histopathology" : "", by: "mdt@vxh.example", at: iso(1), case_id: live ? CID : null },
    questions: live ? [
      { id: "Q1", by: "shanthi@vxh.example", by_name: "Shanthi Raman", text: "Is the axillary ultrasound final and signed?", at: iso(6), case_id: CID, role: "pathology", agent_label: "Pathology support",
        answer: { status: "answered", text: "", statements: [{ text: "The USG of both breasts and axillae is final and signed and records no suspicious axillary lymph nodes.", citations: [{ doc_id: "D95d20494", doc_title: "USG BOTH BREASTS AND AXILLAE", page: 0, quote: "No suspicious axillary lymph nodes" }] }], role: "pathology", label: "Pathology support", note: "From the records only; the agent is not a member of the board" } },
      { id: "Q2", by: "joseph@vxh.example", by_name: "Thomas Joseph", text: "What was the Ki-67?", at: iso(1), case_id: CID, role: "pathology", agent_label: "Pathology support", answer: null },
    ] : [],
    hands: live ? [{ user: "shanthi@vxh.example", name: "Shanthi Raman", at: iso(2) }] : [],
    agent: live ? { active: true, role: "pathology", label: "Pathology support", state: "thinking", roles: ["pathology"], question: "Q2", note: "AI support: answers from the records only; not a member of the board" } : { active: false, role: null, label: "", state: "off", roles: [], question: null },
    can: { manage: true, record: true, ask: live, card: live, card_required: false, video: false },
    me: { user: "mdt@vxh.example", status: "present", mode: "room", department: "mdt" },
    online: ["mdt@vxh.example", "rao@vxh.example", "shanthi@vxh.example", "kiran@vxh.example"],
    outcomes: status === "closed" ? { [CID]: { outcome: "decision", label: "Decision recorded" } } : {},
    ended: [], cards_given: {},
    heads: [], absent_roles: live ? ["pathology"] : [], status,
    ...over,
  };
}

/** The member's own view of the same meeting (a remote head of Radiology). */
export function memberState(over: Record<string, unknown> = {}) {
  const s = meetingState("in_session") as any; // eslint-disable-line @typescript-eslint/no-explicit-any
  s.code = null;
  s.can = { manage: false, record: false, ask: true, card: true, card_required: true, video: false };
  s.me = { user: "rao@vxh.example", status: "remote", mode: "remote", department: "radiology" };
  return { ...s, ...over };
}

export const cards = { cards: { [CID]: { cards: [{ user: "shanthi@vxh.example", name: "Shanthi Raman", agree: true, note: "", at: iso(1), department: "radiology", head: true }], expected: ["shanthi@vxh.example", "joseph@vxh.example"], missing: ["joseph@vxh.example"], concerns: 0 } }, expected: ["shanthi@vxh.example", "joseph@vxh.example"] };

export type MeetingRouteOptions = { state?: unknown; meetings?: unknown; notBuilt?: boolean; missing?: boolean; join?: { status: number; body: unknown } };

/** Answers the meeting routes for MID (and the list); the live socket is mocked: it sends the state, then whatever the spec pushes. */
export async function routeMeetings(page: Page, o: MeetingRouteOptions = {}): Promise<{ push: (ev: Record<string, unknown>) => void }> {
  let sockets: WebSocketRoute[] = [];
  const state = o.state ?? meetingState("planned");
  await page.route("**/api/tb/meetings**", async (route: Route) => {
    const url = new URL(route.request().url());
    const m = route.request().method();
    const p = url.pathname.replace("/api/tb/meetings", "");
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (o.notBuilt) return json(NOT_FOUND, 404);
    if (p === "" && m === "GET") return json(o.meetings ?? { can_manage: true, meetings: [(state as { meeting: unknown }).meeting, { ...meetingState("closed").meeting, id: "M-0" }] });
    if (p === "/join" && m === "POST") return o.join ? json(o.join.body, o.join.status) : json({ meeting_id: MID, status: "waiting", meeting: (state as { meeting: unknown }).meeting });
    if (o.missing && p.startsWith(`/${MID}`)) return json({ detail: { message: "Meeting not found.", code: "not_found" } }, 404);
    if (p === `/${MID}` && m === "GET") return json(state);
    if (p === `/${MID}/cards`) return json(cards);
    if (p === `/${MID}/cases/${CID}/slides`) return json(baseSlides);
    if (/\/cases\/[^/]+\/slides$/.test(p)) return json({ slides: [{ id: "summary", title: "Summary", kind: "summary", content: { from: "gate", board_question: "", requirements: [], note: "No Case File summary compiled yet." } }] });
    if (p === `/${MID}/video-token`) return json({ detail: { message: "Video is not set up on this server (ask the Vaidyx admin to run scripts/livekit.sh).", code: "video_off" } }, 503);
    if (m !== "GET") return json({ ok: true });
    return json(NOT_FOUND, 404);
  });
  await page.route("**/api/tb/sessions**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(route.request().url().includes("/candidates") ? { cases: [{ case_id: "TB-2026-0031", patient: { name: "Lakshmi R.", agesex: "58 F" }, protocol: "breast", ready: { by: "rao@vxh.example" }, gate: { satisfied: 8, total: 10 } }] } : { can_manage: false, sessions: [{ id: "S20261023-5cf6", date: dayIso(3), title: "Tumour Board demo (SYNTHETIC)", status: "planned", cases: 3, created_by: "mdt@vxh.example" }] }) }));
  await page.routeWebSocket(/\/api\/tb\/meetings\/.+\/ws$/, (ws) => {
    sockets.push(ws);
    ws.send(JSON.stringify({ type: "state", ...(state as object) }));
    ws.onMessage((msg) => { try { const d = JSON.parse(String(msg)); if (d.type === "ping") ws.send(JSON.stringify({ type: "pong" })); } catch { /* not JSON */ } });
    ws.onClose(() => { sockets = sockets.filter((x) => x !== ws); });
  });
  return { push: (ev) => { for (const ws of sockets) ws.send(JSON.stringify(ev)); } };
}
