// What GET /cases/{id}/steps answers (tumour_board/steps.py): the guided Case File, six sections in working order with their status,
// the next action behind Continue, To do and Waiting, warnings, the patient at a glance and every document's check.
import type { SlotConfirmation, SlotQuote, SlotRequest, SlotsResponse } from "../types";

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

export interface CheckItem extends StepRow { kind: "problem" | "key"; confirmation?: SlotConfirmation | null; why?: string; detail?: string; confirmed?: boolean; confirmed_by?: string; confirmed_at?: string | null }

export interface MissingItem extends StepRow {
  kind: "record" | "fact" | string;
  department: Department | null;
  typable: boolean;
  can_not_needed: boolean;
  draft?: { doc_id?: string; doc_title?: string; status?: string; value?: string } | null;
  pending?: boolean;
  request?: SlotRequest & { overdue?: boolean };
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
  summary: { prose: SlotsResponse["prose"]; sent: { by?: string; at?: string; note?: string } | null };
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
