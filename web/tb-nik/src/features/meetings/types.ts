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
export interface DecisionBody {
  outcome: Outcome;
  decision_text: string;
  rationale?: string;
  intent_as_stated?: string;
  responsible_doctor?: string;
  next_step?: string;
  next_step_date?: string;
  awaited?: string;
  awaited_from?: string;
  referred_to?: string;
  members_present: string[];
  concerns: Array<{ by: string; text: string }>;
}

export interface JoinResponse { meeting_id: string; status: "admitted" | "waiting" | string; meeting?: MeetingInfo }

export interface MemberCard { user: string; name?: string; agree: boolean; note?: string; at?: string; department?: string; head?: boolean }
/** GET /meetings/{mid}/cards: per Case File, the cards given and who is still expected. */
export interface CardsResponse { cards: Record<string, { cards: MemberCard[]; expected: string[]; missing: string[]; concerns: number }>; expected: string[] }

/** The old board sessions (GET /sessions), shown read-only when meetings.py is not on the server. */
export interface OldSession { id: string; date: string; title?: string; status: string; cases?: number; agenda?: unknown[]; created?: string; created_by?: string }
