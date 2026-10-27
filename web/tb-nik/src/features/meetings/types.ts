// Shapes for the meeting pages (docs/ui/build/SPEC-API.md, meetings.py, live.py, video.py; checked against
// tumour_board/meetings.py). The live state lives in src/lib/live.ts so the WebSocket hook and the pages share it.
export type { AgendaRow, Attendee, MeetingQuestion, MeetingState, LiveEvent, LiveStatus, MeetingInfo, MeetingTimer, Opened, AgentState, MeetingOutcome } from "@/lib/live";
import type { MeetingInfo } from "@/lib/live";

export type MeetingRow = MeetingInfo;

export interface MeetingsResponse { meetings: MeetingRow[]; can_manage: boolean }

export interface NewMeeting { date: string; time: string; room?: string; video: boolean; minutes_per_case?: number }

// ---- slides (GET /meetings/{mid}/cases/{cid}/slides) ---------------------------------------------------------------------
export interface SlideCitation { doc_id: string; doc_title?: string; page?: number | null; quote?: string }
export interface SlideSentence { text: string; citations?: SlideCitation[] }
export interface SlideValue { id: string; label: string; value: string; quote?: string; doc_id?: string; doc_title?: string; date?: string; verification?: string; final?: boolean; page?: number | null }
export interface SlideGap { id: string; label: string; department?: string; status: string; problems?: string[]; level?: number }
export interface SlideWaiver { requirement: string; by?: string; at?: string; reason?: string }
export interface SlideDoc { doc_id: string; title: string; doc_type?: string; date?: string; status?: string; signed?: string; department?: string; superseded?: boolean; outside?: boolean; images?: boolean; viewer_available?: boolean; modality?: string | null; facts?: Array<{ id: string; label: string; value: string; quote?: string }> }
export interface SlidePoint { source?: string; role?: string | null; label?: string; text: string; citations?: SlideCitation[]; reviewed?: boolean }

export interface SlideContentMap {
  from?: "summary" | "gate";
  sections?: Array<{ id?: string; title?: string; heading?: string; sentences?: Array<SlideSentence | string>; items?: Array<SlideSentence | string>; text?: string }>;
  label?: string;
  reviewed?: boolean;
  stale?: string;
  stage_as_recorded?: unknown;
  patient_line?: string;
  protocol?: string;
  setting?: string;
  board_question?: string;
  readiness?: number;
  satisfied?: number;
  total?: number;
  passed?: boolean;
  requirements?: Array<{ id: string; label: string; department?: string; status: string }>;
  values?: SlideValue[];
  gaps?: SlideGap[];
  waivers?: SlideWaiver[];
  documents?: SlideDoc[];
  points?: SlidePoint[];
  items?: Array<{ id?: string; title: string; authors?: string; journal?: string; year?: string | number; url?: string; doi?: string; peer_reviewed?: boolean; quotes?: Array<{ text: string; where?: string }> }>;
  paragraphs?: string[];
  note?: string;
}

export type SlideKind = "summary" | "values" | "gaps" | "imaging" | "pathology" | "points" | "published" | string;
export interface Slide {
  id: string;
  title: string;
  kind: SlideKind;
  content: SlideContentMap | string | string[] | null;
}
export interface SlidesResponse { case_id?: string; slides: Slide[] }

// ---- decisions and cards ---------------------------------------------------------------------------------------------
export type Outcome = "decision" | "deferred" | "referred" | "not_discussed" | "noted";
/** One investigation the board asked for: each row becomes a board action for its department (night-v3 3.1). */
export interface DecisionInvestigation { item: string; department: string; due?: string }
/** One referral: a row with a department becomes a board action of kind referral. `kind` is an id of choices.referral_kind. */
export interface DecisionReferral { kind: string; department: string; note?: string }
export interface DecisionConcern { by: string; text: string }

/** The coordinator's decision form (POST /meetings/{mid}/cases/{cid}/decision). The keys and their limits are those of
 * decision_fields.json (tumour_board/decision_record.py spec()); dates are ISO YYYY-MM-DD or "". */
export interface DecisionBody {
  outcome: Outcome;
  decision_text: string;
  // step 1: outcome
  awaited?: string;
  awaited_from?: string;
  referred_to?: string;
  not_discussed_reason?: string;
  // step 2: the board's recommendation
  rationale?: string;
  intent?: string;
  intent_as_stated?: string;
  modalities?: string[];
  sequence?: string;
  alternatives_discussed?: string;
  concerns?: DecisionConcern[];
  stage_as_agreed?: string;
  stage_source?: string;
  report_corrections_raised?: string;
  // step 3: what the board considered (yn fields: "", yes, no, not_applicable, not_stated)
  patient_preference?: string;
  patient_preference_note?: string;
  fitness_considered?: string;
  trial_considered?: string;
  trial_name?: string;
  genomic_considered?: string;
  supportive_needs?: string[];
  consent_recorded?: string;
  // step 4: what happens next
  investigations?: DecisionInvestigation[];
  referrals?: DecisionReferral[];
  next_step?: string;
  next_step_date?: string;
  next_review?: string;
  next_review_trigger?: string;
  // step 5: responsibility and telling the patient
  responsible_doctor?: string;
  key_worker?: string;
  informed_by?: string;
  inform_by_date?: string;
  patient_informed_date?: string;
  gp_informed_date?: string;
  // step 6: PM-JAY and attendance
  pmjay_plan_approval?: string;
  pmjay_plan_note?: string;
  members_present?: string[];
}

// ---- the decision record's field table (decision_fields.json, written by tumour_board/decision_record.py spec()) -----------
export type DecisionFieldKind = "choice" | "multi" | "short" | "long" | "date" | "person" | "dept" | "yn" | "people" | "concerns" | "investigations" | "referrals";
export interface DecisionChoice { id: string; label: string }
export interface DecisionField {
  key: string;
  label: string;
  kind: DecisionFieldKind | string;
  step: string;
  /** A character limit; for the list kinds one limit per part ({by, text}, {item, department}, {note, department}). */
  limit?: number | Record<string, number>;
  /** The name of a list in `choices`. */
  choices?: string;
  /** The outcome ids for which the field must be filled. */
  required?: string[];
  /** Usually filled after the meeting. */
  after?: boolean;
  /** A later correction of this field needs a reason. */
  reason?: boolean;
  hint?: string;
  source?: string;
}
export interface DecisionSpec {
  outcomes: Array<{ id: Outcome | string; label: string; hint?: string }>;
  steps: Array<{ id: string; title: string }>;
  fields: DecisionField[];
  choices: Record<string, DecisionChoice[]>;
  limits: Record<string, number>;
  yn: DecisionChoice[];
}

export interface JoinResponse { meeting_id: string; status: "admitted" | "waiting" | string; meeting?: MeetingInfo }

export interface MemberCard { user: string; name?: string; agree: boolean; note?: string; at?: string; department?: string; head?: boolean }
/** GET /meetings/{mid}/cards: per Case File, the cards given and who is still expected. */
export interface CardsResponse { cards: Record<string, { cards: MemberCard[]; expected: string[]; missing: string[]; concerns: number }>; expected: string[] }

/** The old board sessions (GET /sessions), shown read-only when meetings.py is not on the server. */
export interface OldSession { id: string; date: string; title?: string; status: string; cases?: number; agenda?: unknown[]; created?: string; created_by?: string }
