// Shapes the Case File page reads. The new ones follow docs/ui/build/SPEC-API.md (slots.py, chats.py, helpers.py,
// published.py, team.py); the old ones are what GET /cases/{id} answers today (routes/tumour_board_routes.py).
// Every field the backend may leave out is optional, so a missing piece shows an honest blank, never a crash.

// ---- slots.py ----------------------------------------------------------------------------------------------------
export type SlotStatus = "found" | "not_found" | "waiting" | "needs_confirmation" | "entered" | "not_needed" | "pending_ready";

export interface SlotQuote {
  text: string;
  doc_id: string;
  doc_title: string;
  /** 0-based page; null when the record has no pages (shown as page 1). */
  page: number | null;
  fact_id?: string | null;
  date?: string | null;
  status?: string | null;
  scan?: boolean;
  confirmed_by?: string;
}

export interface SlotRequest {
  action_id: string;
  department: string;
  department_id?: string | null;
  department_label: string;
  sent_at?: string | null;
  sent_by?: string | null;
  due?: string | null;
  due_label?: string;
  status?: string;
  reminders?: number;
  what?: string;
  accession?: string | null;
}

export type SlotActionKind = "ask_department" | "not_needed" | "enter_value" | "review" | "remind" | "open_source";

export interface SlotAction {
  kind: SlotActionKind;
  label: string;
  department?: string;
  department_id?: string | null;
  department_label?: string;
  action_id?: string | null;
  fact_id?: string | null;
  doc_id?: string;
  page?: number | null;
  reason_required?: boolean;
}

/** The value a doctor picked for the board when two reports differ (a board_uses confirmation, night-v3 item 1.7). */
export interface PickedValue { doc_id: string; doc_title?: string; value: string; by?: string; by_name?: string; at?: string; confirmation: string }

/** One side of a difference between two reports (discord.py): the quote plus the value as that report writes it. */
export type DiscordCitation = Citation & { value?: string; date?: string | null; status?: string | null; final?: boolean; confirmed_by?: string };

export interface SlotConfirmation {
  type: string;
  key: string;
  doc_id?: string;
  doc_title?: string;
  fact_id?: string;
  value?: string;
  page?: number | null;
  why?: string;
  kind_label?: string;
  citations?: DiscordCitation[];
  /** Two reports differ and a doctor picked the value the board uses: the line is settled, the difference stays shown. */
  picked?: PickedValue | null;
}

export interface Slot {
  id: string;
  label: string;
  status: SlotStatus;
  value?: string | null;
  unit?: string;
  as_of?: string;
  quote?: SlotQuote | null;
  request?: SlotRequest | null;
  confirmation?: SlotConfirmation | null;
  actions?: SlotAction[];
  typed_by?: string;
  typed_by_name?: string;
  typed_at?: string;
  note?: string;
  /** Which typed value this slot accepts (ecog, weight, height, menopausal_status, clinical_question, or any "typable" fact). */
  fact_id?: string | null;
  typable?: boolean;
  kind?: "record" | "fact" | "prose" | string;
  required?: boolean;
  department?: string;
  /** A report that is there but not final yet (the line still waits for the final, signed one). */
  draft?: { doc_id?: string; doc_title?: string; status?: string; signed?: string; value?: string } | null;
  pending?: boolean;
  waiver?: { by?: string; by_name?: string; at?: string; reason?: string } | null;
  picked?: PickedValue | null;
}

export interface SlotSection {
  id: string;
  label: string;
  slots: Slot[];
}

export interface SlotsResponse {
  case_id?: string;
  protocol?: string;
  protocol_label?: string;
  setting?: string;
  signature?: string;
  sections: SlotSection[];
  left_before_board: number;
  blockers: Array<{ slot_id: string; why: string }>;
  ready_allowed: boolean;
  prose: {
    status: "none" | "pending" | "ready" | "stale";
    /** slots.py sends sections {id, title, sentences[{text, citations}]}; the old summary gave plain paragraphs. */
    paragraphs: Array<string | ProseSection>;
    reviewed: boolean;
    reviewed_by?: string | null;
    at?: string;
    label?: string;
    generated?: string | null;
    model?: string;
    stale_reason?: string;
    preparing?: boolean;
    points_for_review?: Array<{ text: string; citations?: Citation[] }>;
  };
  permissions?: { enter_value?: boolean; not_needed?: boolean; ask_department?: boolean; remind?: boolean; review?: boolean; mark_ready?: boolean };
  listed?: boolean;
  message?: string;
  board_ready?: { by?: string; at?: string; note?: string } | null;
  /** The Pre-Authorization gate as evaluated: readiness in percent, satisfied of total. */
  gate?: { passed?: boolean | null; readiness?: number; satisfied?: number; total?: number; evaluated?: string } | null;
  /** Set by the page when the slots came from the old checklist instead of slots.py. */
  derived?: boolean;
}

export interface ProseSection { id?: string; title?: string; sentences?: Array<string | { text: string; citations?: Citation[] }> }

export interface QuoteBoxes {
  page: number | null;
  /** quote_boxes.py sends [x0, y0, x1, y1] fractions of the page; an older draft sent {x, y, w, h}. */
  boxes: Array<[number, number, number, number] | number[] | { x: number; y: number; w: number; h: number }>;
  found: boolean;
  reason?: string;
}

// ---- chats.py ----------------------------------------------------------------------------------------------------
export interface Citation { doc_id: string; doc_title: string; page: number | null; quote: string }
export interface ChatStatement { text: string; citations: Citation[] }
export interface ChatThread {
  id: string;
  by: string;
  by_name?: string;
  at: string;
  question: string;
  status: "answered" | "not_documented" | "out_of_scope" | "pending" | "error" | string;
  statements: ChatStatement[];
  message?: string;
  pinned?: boolean;
  stale?: boolean;
  seconds?: number;
  /** The model that wrote the answer (review 9 C, S3); empty when no model was called (a request refused by the scope check). */
  model?: string | null;
  /** Set by the page when the answer came from the old /ask route and is not saved. */
  unsaved?: boolean;
  /** Nothing in the records and the question reads as a general one: the screen offers "Ask PubMed?" (docs/pubmed-ask section 8). */
  suggest_pubmed?: boolean;
}

// ---- helpers.py --------------------------------------------------------------------------------------------------
export type HelperRole = "radiology" | "pathology" | "medical_oncology" | "surgical_oncology" | "radiation_oncology" | "nuclear_medicine";
export interface HelperBrief {
  status: "none" | "preparing" | "ready" | "stale";
  at?: string | null;
  /** Set while the ready mark's run still has to reach this head (status "preparing"). */
  queued?: boolean;
  message?: string;
  stale_reason?: string;
  sections?: Array<{ heading?: string; title?: string; items?: Array<{ text: string; citations?: Citation[] }>; text?: string }>;
  points_for_review?: Array<{ text: string; citations?: Citation[] }>;
  not_documented?: string[];
  reviewed_by?: string;
  /** The reviewer's display name beside the login (review 9 C, M11). */
  reviewed_by_name?: string;
  /** The doctor who flagged the brief for correction, and their display name (Phase 9 review E, I2). */
  flagged_by?: string;
  flagged_by_name?: string;
  /** The review status of the brief: "reviewed", "flagged", "ai_draft" or "". */
  review?: string;
  label?: string;
  model?: string;
}
export interface Helper {
  role: HelperRole | string;
  label: string;
  department?: string;
  brief: HelperBrief;
  thread_count: number;
  prepare_allowed: boolean;
  head?: boolean;
  /** The brief's job while it is prepared (poll GET /jobs/{id}). */
  job?: string | null;
  // night-v3 item 6.5: the "Specialty agents" (owner decision D2: AI agent, support only, never a member of the board)
  /** "<Department>, AI agent". */
  title?: string;
  points_count?: number;
  not_documented_count?: number;
  /** How many exchanges on the shared thread were asked in a board meeting. */
  meeting_exchanges?: number;
  prepared_at?: string | null;
}
export interface HelperMessage {
  id?: string;
  role?: string;
  by?: string;
  by_name?: string;
  at?: string;
  question: string;
  answer?: string;
  statements?: ChatStatement[];
  status?: string;
  message?: string;
  /** "case" or "meeting:<meeting id>": the one thread per Case File and role is shared with the board meetings (night-v3 item 6.3). */
  source?: string;
  /** The date of the board meeting the question was asked in (YYYY-MM-DD), for a meeting exchange. */
  meeting_date?: string | null;
  model?: string | null;
  /** The records changed after this answer. */
  stale?: boolean;
  kind?: string;
}

// ---- published.py ------------------------------------------------------------------------------------------------
export interface PublishedResult {
  id?: string;
  title: string;
  authors: string;
  journal: string;
  year: number | string;
  doi?: string;
  url?: string;
  source: "local" | "pubmed" | "europepmc" | string;
  peer_reviewed: boolean;
  kind: "paper" | "preprint" | "white_paper" | "book" | string;
  added_by?: string;
  added_by_name?: string;
  by_name?: string;
  at?: string;
  quotes?: Array<{ text: string; where: string }>;
  snippet?: string;
  label?: string;
}

export interface PublishedSearch { by?: string; at?: string; terms: string; counts?: Record<string, number>; errors?: unknown }

// ---- similar.py (night-v3 Phase 7, docs/night-v3/research/07_similar_cases.md 8.3 and 8.4) ------------------------------
/** A quoted line and where it sits: the past file "<doc title>, Mon YYYY" (or "Board record, Mon YYYY", "Case summary, Mon YYYY"),
 *  this file "<doc title>, DD/MM/YYYY". */
/** A quoted line (text and where it sits). A Case summary sentence of the past file (outcome so far) is model-written: `label` says so
 *  ("Case summary, AI draft, not reviewed"), and `quote` with `quote_where` is the verified record line it rests on (Phase 7 review, S1). */
export interface SimilarQuote { text: string; where: string; quote?: string; quote_where?: string; label?: string }
export interface SimilarStage { text: string; kind: "recorded" | "confirmed_draft" | "agreed" | string; label: string; quote?: string; where?: string }
export interface SimilarValue { fact: string; label: string; value: string; quote?: string; where?: string; shared?: boolean }
export interface SimilarDecision {
  record_id: string; when: string; outcome?: string; outcome_label?: string; intent?: string; intent_label?: string;
  text: string; modalities?: string[]; stage_as_agreed?: string;
}
export interface SimilarLine { about?: string; this: SimilarQuote; past: SimilarQuote }
export type SimilarHow = "normal" | "with_reason" | "refused";
/** POST /cases/{id}/similar/open: how this person may open the past file (the server computes access.scope). */
export interface SimilarOpen { how: SimilarHow; scope?: string | null; reason?: string; via?: string; label?: string }
/** One past Case File as the card shows it. No field ranks it: the order of the list is the only order. */
export interface SimilarResult {
  case_id: string; cancer: string; setting?: string; age_band?: string; sex?: string;
  stage: SimilarStage[];
  values: SimilarValue[];
  decisions: SimilarDecision[];
  outcome_so_far: { sentences: SimilarQuote[]; later_records?: string };
  similar: SimilarLine[];
  differs: SimilarLine[];
  matched_by?: string[] | null;
  no_reasons?: boolean;
  open?: { how: SimilarHow; reason?: string; via?: string };
  label?: string;
}
/** POST /cases/{id}/similar/search {words?} */
export interface SimilarResponse {
  label: string; ordered_by: "model" | "text"; order_note: string; model_line: string;
  cancer_group?: string; group_label?: string; words?: string; note?: string;
  results: SimilarResult[]; weaker: SimilarResult[];
}
/** GET /cases/{id}/similar: whether a search is possible here, and the last five searches of this file. */
export interface SimilarInfo {
  available: boolean; reason?: string; label?: string; order_note?: string; model_line?: string; cancer_group?: string; group_label?: string;
  searches?: Array<{ words?: string; at?: string; by_name?: string }>;
}

// ---- team.py -----------------------------------------------------------------------------------------------------
export interface Team {
  owner: { department: string; department_label?: string; doctors: Array<{ user: string; name: string }> };
  residents: Array<{ user: string; name: string; end_date?: string; added_by?: string; since?: string; expired?: boolean }>;
  departments: Array<{ id: string; label: string; since?: string }>;
  join_code: { code: string; expires_at: string; uses?: number } | null;
  pending: Array<{ user: string; name: string; requested_at: string; department?: string; department_label?: string }>;
  can?: { manage?: boolean; leave?: boolean; set_urgency?: boolean; propose?: boolean; archive?: boolean; consent?: boolean };
  urgency?: Urgency | null;
  archived?: { by?: string; at?: string; reason?: string } | null;
  consent?: { outside_discussion?: boolean } | null;
  /** Set by the page when the team came from the old access block. */
  derived?: boolean;
}

export type ProposalAction = "waive" | "not_needed" | "confirm" | "mark_ready" | "send_request" | "urgency" | "refer" | "typed_value" | "published_case"
  | "key_value" | "reason" | "staging_confirm";
/** What a resident's call answers instead of doing the step (night-v3 item 1.8): the proposal the consultant signs off. */
export interface Proposed { proposal?: Proposal }
export interface Proposal {
  id: string;
  action: ProposalAction | string;
  payload: Record<string, unknown>;
  note?: string;
  by: string;
  by_name?: string;
  at: string;
  status: "pending" | "approved" | "returned" | string;
  decided_by?: string;
  decision_note?: string;
}

export interface Urgency {
  level: number | null;
  label?: string;
  set_by?: string;
  set_by_name?: string;
  set_at?: string;
  at?: string;
  note?: string;
  /** A resident's pending proposal (team.urgency_view). */
  proposed?: { level: number; by: string; by_name?: string; at: string; id?: string } | null;
  proposals?: Array<{ level: number; by: string; by_name?: string; at: string; note?: string }>;
}

// ---- GET /cases/{id} (today's backend) ---------------------------------------------------------------------------
export interface DocClassification {
  title?: string;
  doc_type?: string;
  status?: string;
  signed?: string;
  report_date_iso?: string;
  event_date_iso?: string;
  dates?: unknown[];
  doc_type_disagreement?: { keyword_type?: string; note?: string } | null;
  doc_type_confirmed_by?: string;
  dates_confirmed_by?: string;
  text_status?: string;
  text_signed?: string;
}

export interface DocFact {
  value?: string;
  quote?: string;
  verification?: string;
  state?: string;
  location?: { page?: number; [k: string]: unknown } | null;
  reason?: string;
}

/** Final and signed as the report states it (steps.final_status), on every document of the Case File view. */
export interface DocFinal { final: boolean; signed: boolean; preliminary: boolean; status: string; label: string; warn: boolean }

export interface CaseDocument {
  doc_id: string;
  filename: string;
  rel_path?: string;
  ext?: string;
  state: "queued" | "reading" | "classifying" | "extracting" | "ready" | "error" | string;
  error?: string;
  dismissed?: { by?: string; reason?: string } | null;
  classification?: DocClassification;
  /** Final and signed as the report states it (2 Nov 2026). */
  final?: DocFinal;
  identity?: string;
  added?: string;
  department?: string;
  uploaded_by?: string;
  facts?: Record<string, DocFact>;
  pages?: number;
  methods?: string[];
  scan_pages?: number[];
  page_flags?: string[];
  his?: {
    id?: string;
    version?: number;
    status?: string;
    issued?: string;
    encounter_number?: string;
    encounter_kind?: string;
    accession?: string;
    performer_department?: string;
    reported_by?: string;
    imaging_study_ref?: string;
    signed?: boolean;
    signature?: { signer?: string; signed_at?: string } | null;
    amendment_note?: string;
    title?: string;
  };
  superseded?: { by_doc?: string; version?: number; at?: string } | null;
  outside?: unknown;
  identity_confirmed_by?: string;
}

export interface RecordGroup {
  key: string;
  kind: "OP" | "IP" | "HIS" | "outside" | "upload" | string;
  label: string;
  number?: string;
  department?: string;
  unit?: string;
  start?: string;
  end?: string;
  status?: string;
  consultant?: string;
  pre_admission?: boolean;
  docs: string[];
}

export interface TimelineEvent {
  date: string;
  kind: "document" | "encounter" | "referral" | "board" | "action" | "review" | string;
  title: string;
  status?: string;
  doc_id?: string;
  doc_type?: string;
  end?: string;
  number?: string;
  encounter_kind?: string;
}

export interface GateRequirement {
  id: string;
  label: string;
  department?: string;
  status: "satisfied" | "missing" | "not_applicable" | "waived" | "needs_confirmation" | string;
  problems?: string[];
  evidence?: Array<{ doc_id?: string; quote?: string; value?: string; fact?: string; page?: number }>;
  level?: number;
  source_doc_id?: string;
}

export interface CaseAction {
  id: string;
  source: "pre_authorization" | "board" | string;
  requirement?: string;
  label: string;
  department?: string;
  department_id?: string;
  what?: string;
  status: "suggested" | "pending" | "overdue" | "completed" | string;
  due?: string | null;
  created?: string;
  sent?: { at?: string; by?: string; to?: string } | null;
  acknowledged?: { at?: string; by?: string } | null;
  done?: { at?: string; by?: string; note?: string } | null;
  reminders?: Array<{ at: string; by?: string }>;
  accession?: string;
}

export interface ResolvedFact {
  label: string;
  current: {
    value?: string;
    quote?: string;
    verification?: string;
    state?: string;
    doc_id?: string;
    doc_title?: string;
    date?: string | null;
    doc_final?: boolean;
    location?: { page?: number } | null;
  };
  history: Array<{ value?: string; quote?: string; verification?: string; doc_id?: string; doc_title?: string; date?: string | null; doc_status?: string; superseded?: boolean }>;
}

export interface Artefact {
  status?: string;
  sections?: Array<{ title: string; text?: string; sentences?: string[] }>;
  paragraphs?: string[];
  points_for_review?: Array<{ text: string; citations?: Citation[] }>;
  review?: { status?: string; by?: string; at?: string; comment?: string };
  model?: string;
  generated_at?: string;
}

export interface BoardRecord {
  id?: string;
  outcome?: string;
  outcome_type?: string;
  decision_text?: string;
  rationale?: string;
  intent_as_stated?: string;
  intent_as_recorded?: string;
  responsible_doctor?: string;
  next_step?: string;
  next_step_date?: string;
  awaited?: string;
  awaited_from?: string;
  deferred_reason?: string;
  referred_to?: string;
  members_present?: string[];
  /** The old board record keeps a sentence ("Radiology, Medical Oncology; absent: Pathology"); the new one a list. */
  participants?: string[] | string;
  concerns?: Array<{ by: string; text: string }>;
  divergent_opinions?: string;
  meeting_outcome?: string;
  session?: string;
  recorded_at?: string;
  recorded_by?: string;
  board_date?: string;
  // Decision record v2 (night-v3 3.1, tumour_board/decision_record.py): the same keys as the meeting's decision form.
  not_discussed_reason?: string;
  intent?: string;
  modalities?: string[];
  sequence?: string;
  alternatives_discussed?: string;
  stage_as_agreed?: string;
  stage_source?: string;
  report_corrections_raised?: string;
  patient_preference?: string;
  patient_preference_note?: string;
  fitness_considered?: string;
  trial_considered?: string;
  trial_name?: string;
  genomic_considered?: string;
  supportive_needs?: string[];
  consent_recorded?: string;
  investigations?: Array<{ item: string; department: string; due?: string }>;
  referrals?: Array<{ kind: string; department: string; note?: string }>;
  next_review?: string;
  next_review_trigger?: string;
  key_worker?: string;
  informed_by?: string;
  inform_by_date?: string;
  patient_informed_date?: string;
  gp_informed_date?: string;
  pmjay_plan_approval?: string;
  pmjay_plan_note?: string;
  /** Board actions ({task, department, due, kind}); investigations and referrals become rows of kind investigation or referral. */
  actions?: Array<{ task: string; department?: string; due?: string; kind?: string }>;
  /** Set when the owning consultant (or the MDT Coordinator on the meeting day) corrected the record; versions are kept. */
  corrected?: { by: string; by_name?: string; at: string; reason?: string; version: number } | null;
  entered_by?: string;
  /** The current version number; every version is kept in `versions` (version 1 is the decision as recorded). */
  version?: number;
  versions?: BoardRecordVersion[];
}

/** One version of a board record (postboard._versions / _new_version): a correction carries the changed fields and why. */
export interface BoardRecordVersion {
  version: number;
  at?: string;
  by?: string;
  by_name?: string;
  reason?: string;
  /** "correction" for a later correction; absent for version 1. */
  change?: string;
  changed?: Array<{ key: string; old?: unknown; new?: unknown }>;
  decision_text?: string;
  fields?: Record<string, unknown>;
}

export interface SummaryLine { text: string; version?: number; at?: string; by?: string; by_name?: string; edited?: boolean; stale?: boolean; vaidyx_text?: string }

export interface CaseFile {
  case: {
    case_id: string;
    patient: { name: string; mrn: string; agesex: string; ids?: Array<{ kind: string; value: string }> };
    protocol?: string;
    protocol_label?: string;
    setting?: string;
    hospital_level?: string;
    board_date?: string;
    department?: string;
    listing?: { status?: string };
    his?: unknown;
    board_ready?: { by: string; at: string; note?: string } | null;
    urgency?: Urgency | null;
    team?: { owner?: string; residents?: unknown[] };
    meeting_id?: string;
    /** A guest reviewer's private Case File: only its creator sees it; deleted 90 days after creation (5 Nov 2026). */
    private?: boolean;
    /** The choices of Send to the board (night-v3 item 1.4); withdrawn when the doctor took it off the agenda (item 1.6). */
    board_send?: BoardSend | null;
    board_record?: BoardRecord | null;
    created?: string;
    /** The short line under the patient (night-v3 3.4), built from the Case summary; the owner's consultant may edit it. */
    summary_line?: SummaryLine | null;
  };
  state: {
    gate?: { passed?: boolean; readiness?: number; satisfied?: number; total?: number; requirements?: GateRequirement[]; blockers?: unknown[] };
    actions?: CaseAction[];
    confirmations?: Array<{ id: string; type: string; key: string; fields?: Record<string, unknown>; reason?: string; by?: string; at?: string; undone?: boolean }>;
    artefacts?: Record<string, Artefact>;
    board_records?: BoardRecord[];
  };
  documents: CaseDocument[];
  facts: Record<string, ResolvedFact>;
  timeline: TimelineEvent[];
  permissions: {
    upload?: boolean;
    refetch?: boolean;
    review?: boolean;
    mark_ready?: boolean;
    send_request?: boolean;
    create_request?: boolean;
    remind?: boolean;
    waive?: Record<string, boolean>;
    confirm?: Record<string, boolean>;
    board_record?: boolean;
    /** Per board record id: may this login correct it (the owning department's consultants; the MDT Coordinator on the meeting day). */
    correct_board_record?: Record<string, boolean>;
    manage_participants?: boolean;
    refer?: boolean;
  };
  signature?: { hash: string } | null;
  stale?: Record<string, string>;
  his?: { label?: string; uhid?: string; fetched_at?: string; window_label?: string; encounters?: unknown[] } | null;
  requests?: { suggested: number; sent: number; done: number; closed: number };
  groups?: RecordGroup[];
  /** owner is {id, name} on today's server (a bare id on older ones). */
  access?: { owner?: string | { id: string; name?: string } | null; owner_name?: string; participants?: Array<{ department: string | { id: string; name?: string }; since?: string }>; owner_history?: unknown[]; scope?: string };
  referral?: unknown;
}

export interface Job {
  id: string;
  case_id?: string;
  total: number;
  done: number;
  events: Array<{ t: number; doc_id?: string; state?: string; text?: string }>;
  state: "running" | "finished" | "failed" | string;
  error?: string;
  doc_states?: Record<string, string>;
}

export interface RequestDraft {
  action_id: string;
  to: string;
  subject: string;
  body: string;
  due?: string;
  mailto?: string;
  accession?: string;
  uhid?: string;
  free?: boolean;
  sent?: unknown;
  status?: string;
}

export interface BoardSend {
  list?: "discussion" | "noting";
  meeting_id?: string;
  presenter?: string;
  note?: string;
  reason?: string;
  by?: string;
  at?: string;
  withdrawn?: { by: string; at: string; reason: string } | null;
}

/** POST /cases/{id}/meeting/move or /withdraw (night-v3 item 1.6). */
export interface MeetingMoveResult {
  case_id: string;
  meeting_id: string;
  board_date: string;
  board_send?: BoardSend | null;
  meeting?: { id: string; date: string; time?: string; room?: string; label?: string } | null;
}

/** Send to the board (night-v3 item 1.4, design B7): POST /cases/{id}/ready with ready true, or a resident's mark_ready proposal.
 *  meeting_id "" is "not scheduled yet" (the coordinator picks); presenter "" is the consultant who sends it; reason is required by the
 *  server when items are still open. */
export interface SendToBoardBody {
  list: "discussion" | "noting";
  meeting_id: string;
  presenter: string;
  note: string;
  reason: string;
}
