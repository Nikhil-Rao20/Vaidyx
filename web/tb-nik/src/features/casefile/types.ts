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
  /** Set by the page when the answer came from the old /ask route and is not saved. */
  unsaved?: boolean;
}

// ---- helpers.py --------------------------------------------------------------------------------------------------
export type HelperRole = "radiology" | "pathology" | "medical_oncology" | "surgical_oncology" | "radiation_oncology" | "nuclear_medicine";
export interface HelperBrief {
  status: "none" | "preparing" | "ready" | "stale";
  at?: string;
  sections?: Array<{ heading?: string; title?: string; items?: Array<{ text: string; citations?: Citation[] }>; text?: string }>;
  points_for_review?: Array<{ text: string; citations?: Citation[] }>;
  not_documented?: string[];
  reviewed_by?: string;
  model?: string;
}
export interface Helper {
  role: HelperRole | string;
  label: string;
  department?: string;
  brief: HelperBrief;
  thread_count: number;
  prepare_allowed: boolean;
}
export interface HelperMessage {
  id?: string;
  by?: string;
  by_name?: string;
  at?: string;
  question: string;
  answer?: string;
  statements?: ChatStatement[];
  status?: string;
  message?: string;
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

export interface CaseDocument {
  doc_id: string;
  filename: string;
  rel_path?: string;
  ext?: string;
  state: "queued" | "reading" | "classifying" | "extracting" | "ready" | "error" | string;
  error?: string;
  dismissed?: { by?: string; reason?: string } | null;
  classification?: DocClassification;
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
  meeting_outcome?: string;
  session?: string;
  recorded_at?: string;
  recorded_by?: string;
  board_date?: string;
}

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
    /** The choices of Send to the board (night-v3 item 1.4); withdrawn when the doctor took it off the agenda (item 1.6). */
    board_send?: BoardSend | null;
    board_record?: BoardRecord | null;
    created?: string;
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
