// What GET /cases/{id}/steps answers (tumour_board/steps.py): the guided Case File, six sections in working order with their status,
// the next action behind Continue, To do and Waiting, warnings, the patient at a glance and every document's check.
import type { PickedValue, SlotConfirmation, SlotQuote, SlotRequest, SlotsResponse } from "../types";

export type SectionId = "overview" | "question" | "reports" | "check" | "pre_authorization" | "summary";
export type SectionStatus = "home" | "done" | "todo" | "waiting" | "overdue" | "not_started" | "working" | "empty" | "not_needed";

export interface StepSection { id: SectionId; label: string; status: SectionStatus; detail: string; count?: number | null }

export interface Department { name: string; label: string; id: string; action_id?: string | null; phone?: string }

export interface StepAction {
  kind: "go" | "ask_department" | "open_report" | "check" | "remind" | "signoffs" | "change_cancer" | "dismiss";
  label: string;
  department?: Department;
  slot_ids?: string[];
  slot_id?: string;
  doc_id?: string;
  action_id?: string | null;
}

export interface StepRow {
  slot_id: string;
  fact_id?: string | null;
  label: string;
  status: string;
  value: string;
  unit?: string;
  as_of?: string | null;
  quote?: SlotQuote | null;
  note?: string;
  required?: boolean;
  entered_by?: string;
  entered_at?: string | null;
  report_value?: { value: string; quote?: SlotQuote; as_of?: string | null };
  corrected_by?: string;
  /** Only in a report not final and signed: the value, its line and the mark ("not signed", "preliminary"), never counted (2 Nov 2026). */
  unsigned?: { value: string; word: string; quote?: SlotQuote | null };
}

export interface TodoItem { id: string; section: SectionId; label: string; why?: string; action: StepAction }
export interface WaitingItem { id: string; section: SectionId; label: string; department: Department | null; request: SlotRequest & { overdue?: boolean }; action: StepAction }

export interface Warning {
  id: string;
  kind: "cancer_mismatch" | "identity" | "preliminary" | string;
  section: SectionId;
  severity: "warn" | "bad";
  text: string;
  doc_id?: string;
  fixes: Array<{ kind: string; label: string; doc_id?: string; slot_id?: string; department?: string }>;
}

export interface DocCheck { status: "checked" | "please_check" | "reading" | "failed" | "dismissed"; reasons: string[]; values: Array<{ fact_id: string; label: string; value: string; quote: string; page?: number | null; confirmed_by?: string }> }
export interface FinalStatus { final: boolean; signed: boolean; preliminary: boolean; status: string; label: string; warn: boolean }
export interface StepDocument {
  doc_id: string; title: string; doc_type: string; group: "pathology" | "imaging" | "labs" | "notes" | "other" | "outside" | string; date: string;
  department: string; accession: string; final: FinalStatus; check: DocCheck; images: boolean; outside: boolean; state?: string;
  earlier: Array<{ doc_id: string; title: string; version?: number | null; status: string }>;
}

/** A pick for the board that no longer matches its report (the report was replaced, dismissed or now reads another value): the line says
 *  "Your pick of 4.6 cm from the CT report no longer matches the report: pick again" until the doctor picks again or notes it. */
export interface StalePick { doc_id: string; doc_title?: string; value: string; by?: string; by_name?: string; at?: string; confirmation?: string }

export interface CheckItem extends StepRow {
  kind: "problem" | "key"; confirmation?: SlotConfirmation | null; why?: string; detail?: string; confirmed?: boolean; confirmed_by?: string; confirmed_at?: string | null;
  /** Two reports differ and a doctor picked the value the board uses (night-v3 item 1.7): still listed, settled, never counted as left. */
  picked?: PickedValue | null; resolved?: boolean;
  /** The doctor's earlier pick no longer matches its report: `why` says "... no longer matches the report: pick again". */
  pick_stale?: StalePick | null;
}

export interface MissingItem extends StepRow {
  kind: "record" | "fact" | string;
  department: Department | null;
  typable: boolean;
  can_not_needed: boolean;
  draft?: { doc_id?: string; doc_title?: string; status?: string; value?: string } | null;
  pending?: boolean;
  request?: SlotRequest & { overdue?: boolean };
}

// ---- the Case summary (night-v3 3.3 / 3.4; tumour_board/case_summary.py view) ----------------------------------------------------
/** A record line as today, or a field of a board record, an action, the stage confirmation or a member's card (the stored text). */
export type CaseCitation =
  | { kind?: undefined; doc_id: string; quote: string; page?: number | null; doc_title?: string; date?: string; status?: string }
  | { kind: "board"; board_record: string; version?: number; field: string; label?: string; quote: string; board_date?: string }
  | { kind: "action"; action?: string; board_record?: string; field: string; label?: string; quote: string; at?: string }
  | { kind: "staging"; field: string; quote: string; by?: string; at?: string }
  | { kind: "card"; meeting?: string; user?: string; field: string; quote: string; board_date?: string }
  /** A line of the board's discussion notes (meetings-v2 5.4): who said it, when, and the exact words (verified against the notes). */
  | SaidCitation;

/** What was said at the board: a note line of the meeting's AI discussion notes, with the speaker's exact words ("room" is the Board room
 *  microphone, no speaker known). No audio is ever kept. */
export interface SaidCitation { kind: "said"; meeting_id?: string; line_id?: string; speaker?: string; speaker_name?: string; department?: string; at?: string; board_date?: string; quote: string }

/** GET /cases/{id}/meeting-notes (meeting_notes.case_view): the Case File's AI discussion notes from every meeting, newest first; whoever
 *  reads the whole Case File. Read-only here: the MDT Coordinator edits and reviews them on the meeting page. */
export interface NoteLine {
  id: string; text: string;
  said: { segment_id?: string; speaker?: string; speaker_name?: string; at?: string; quote?: string };
  edited?: { by?: string; by_name?: string; at?: string; checked?: boolean } | null;
}
export interface MeetingNotesRow {
  meeting_id: string; date?: string; time?: string; title?: string; status?: string; label_meeting?: string;
  lines: NoteLine[]; generated_at?: string; model?: string; model_line?: string; label?: string;
  review?: { status?: "draft" | "reviewed" | string; by?: string | null; by_name?: string; at?: string | null };
}
export interface CaseMeetingNotes { case_id: string; label?: string; meetings: MeetingNotesRow[] }

/** What the model wrote for an edited sentence on a later rebuild (case_summary._carry_edits); never written over the edit. */
export interface SuggestedSentence { text: string; citations?: CaseCitation[] }

export interface SentenceEdit {
  by: string; by_name?: string; at: string; checked: boolean; records_changed?: boolean;
  /** An object from the server; a plain string is accepted too. */
  suggested?: SuggestedSentence | string | null;
  vaidyx_text?: string;
  /** Carried from an earlier version: no sentence of the current version matches the edit, so it sits at the end of its section. */
  unmatched?: boolean;
}

export interface CaseSentence {
  id: string;
  text: string;
  citations: CaseCitation[];
  /** Written by code from the stored fields: no AI mark, not editable. */
  code?: boolean;
  /** The fixed sentence when nothing is documented. */
  fixed?: boolean;
  from_fields?: boolean;
  approximate?: boolean;
  edited?: SentenceEdit | null;
}

export interface CaseSummarySection {
  id: "presentation" | "stage" | "rounds" | "since" | "status" | string;
  title: string;
  built_by?: "model" | "code" | string;
  context?: string | Record<string, unknown>;
  /** A plain line under the title ("What was said at the board": from the AI discussion notes, never the board's decision). */
  note?: string;
  sentences?: CaseSentence[];
  /** The board rounds: one block per board record, oldest first. */
  blocks?: Array<{ record: string; version?: number; date?: string; outcome?: string; sentences: CaseSentence[] }>;
}

export interface CaseSummaryReview { status?: "reviewed" | "flagged" | "ai_draft" | string; by?: string; by_name?: string; at?: string; comment?: string }

export interface CaseSummaryVersionRow { n: number; built_at?: string; trigger?: { kind?: string }; review?: CaseSummaryReview; edits?: number; sentences?: number }

export interface CaseSummaryView {
  status: "building" | "ready" | "stale" | "reviewed";
  current: number;
  /** "Summary after the board" (meetings-v2 5.4, D14), beside "Summary before the board" (the pre-board summary). */
  title?: string;
  before_title?: string;
  /** The latest board's date (ISO) the summary is after. */
  last_board_date?: string | null;
  built_at?: string;
  trigger?: { kind?: string; by?: string };
  model_line?: string;
  label?: string;
  stale_reason?: string;
  review?: CaseSummaryReview | null;
  sections: CaseSummarySection[];
  /** Sentences dropped because they could not be checked (a count here; a stored version keeps the list). */
  removed?: number | unknown[];
  edits?: number | unknown[];
  first_board_date?: string;
  versions: CaseSummaryVersionRow[];
  can: { build?: boolean; review?: boolean; edit?: boolean };
}

/** One pre-board summary (summary.history): the archived ones first, the live one last. */
export interface PreBoardVersion {
  generated?: string;
  archived_at?: string;
  review?: { status?: string; by?: string; at?: string } | null;
  model?: string;
  paragraphs?: Array<{ id?: string; title?: string; sentences?: Array<string | { text: string; citations?: Array<{ doc_id: string; doc_title: string; page: number | null; quote: string }> }> }>;
  points_for_review?: Array<{ text: string }>;
  stage_as_recorded?: unknown;
  live?: boolean;
  /** false: only the date and the review are sent (older archived versions); no paragraphs to show. */
  full?: boolean;
}

export interface Steps {
  case_id: string;
  mode: "prepare" | "read";
  role: "consultant" | "resident" | "reader";
  sections: StepSection[];
  next: { section: SectionId; label: string; target?: string; done?: boolean; send?: boolean } | null;
  todo: TodoItem[];
  waiting: WaitingItem[];
  warnings: Warning[];
  question: {
    text: string; by?: string; at?: string | null; note_text?: string;
    reason?: { value: string; label: string; by?: string; at?: string } | null;
    urgency?: { level?: number | null } | null;
    extras: StepRow[];
  };
  glance: Array<{ id: string; label: string; rows: StepRow[] }>;
  documents: StepDocument[];
  check: { problems: CheckItem[]; keys: CheckItem[] };
  pre_authorization: { groups: Array<{ department: Department; items: MissingItem[] }>; waiting: MissingItem[]; optional: MissingItem[] };
  summary: {
    prose: SlotsResponse["prose"]; sent: { by?: string; at?: string; note?: string } | null;
    /** After the first board decision: the main summary (night-v3 3.4). */
    case_summary?: CaseSummaryView | null;
    /** Every pre-board summary, the live one last. */
    history?: PreBoardVersion[];
  };
  left: number;
  permissions: SlotsResponse["permissions"];
  signoffs: number;
  protocol: string;
  protocol_label: string;
  reasons: Array<{ id: string; label: string }>;
  blockers: Array<{ slot_id: string; why: string }>;
}

/** The address of a section: /cases/:id/<slug>. */
export const SLUG: Record<SectionId, string> = { overview: "overview", question: "question", reports: "reports", check: "check", pre_authorization: "pre-authorization", summary: "summary" };
export const fromSlug = (s?: string): SectionId | null => (Object.entries(SLUG).find(([, v]) => v === s)?.[0] as SectionId | undefined) ?? null;
