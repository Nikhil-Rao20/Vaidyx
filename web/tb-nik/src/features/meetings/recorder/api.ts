// The meeting recorder and the discussion notes (meetings-v2 5.1 to 5.3; tumour_board/api/meeting_notes.py). NO AUDIO IS EVER KEPT:
// a chunk goes from memory to the app, which passes it in memory to the speech service and drops it; only the text is stored. Nothing
// here writes audio anywhere in the browser either (no IndexedDB, no localStorage, no Cache): the Blob is posted and let go.
import { api, whileLeaving } from "@/lib/api";
import type { MeetingInfo, RecordingView } from "@/lib/live";
import { mUrl } from "../api";

const enc = encodeURIComponent;

export type RecordingAction = "start" | "pause" | "resume" | "stop";

/** The coordinator starts, pauses, resumes or stops the recorder. 409 not_in_session or bad_state; 400 bad_action. */
export const setRecording = (mid: string, action: RecordingAction) => api.post<{ recording: RecordingView }>(`${mUrl(mid)}/recording`, { action });

/** While the page is being left (pagehide): "stop" marked keepalive so it reaches the server after the tab is gone. The last unsent
 *  chunk is dropped (a keepalive body is capped at 64 KB, and audio is never kept to send later). */
export function stopOnLeave(mid: string): void {
  whileLeaving(() => { void setRecording(mid, "stop").catch(() => undefined); });
}

/** What the chunk route answers: whether text was stored, the seconds heard, and the segment's id, speaker and case (never the words). */
export interface ChunkAnswer {
  stored: boolean;
  seconds: number | null;
  segment: { id: string; at: string; speaker: string; speaker_name: string; case_id: string | null; chars: number } | null;
}

/** One chunk of one audio track (at most 4 MiB and 60 s), with its speaker (an admitted login, or "room") and its start time. */
export function postChunk(mid: string, audio: Blob, fileName: string, speaker: string, startedMs: number): Promise<ChunkAnswer> {
  const form = new FormData();
  form.append("audio", audio, fileName);
  form.append("speaker", speaker);
  form.append("started_ms", String(Math.round(startedMs)));
  return api.upload<ChunkAnswer>(`${mUrl(mid)}/transcribe`, form);
}

// ---- the discussion notes (5.3) -----------------------------------------------------------------------------------------

/** The exact words behind a note line: the speaker, the time and the quote copied word for word from what was said. */
export interface NoteSaid { segment_id: string; speaker: string; speaker_name: string; at: string; quote: string }

export interface NoteLine {
  id: string;
  text: string;
  said: NoteSaid;
  /** Set when the coordinator changed the line: by whom, when, and whether its numbers and names are still in the quote. */
  edited?: { by: string; by_name?: string; at: string; checked?: boolean } | null;
}

/** One Case File's notes in a meeting (meeting_notes.notes_view); `withheld` for an outside expert without the patient's consent. */
export interface CaseNotes {
  case_id: string;
  withheld?: boolean;
  note?: string;
  lines: NoteLine[];
  generated_at?: string | null;
  model?: string;
  /** "Written by Gemma-4-31B (non-medical)". */
  model_line?: string;
  segments?: number;
  /** Lines the model wrote that failed the word-for-word check and were left out. */
  dropped?: number;
  review?: { status: "draft" | "reviewed" | string; by?: string | null; by_name?: string | null; at?: string | null };
  /** "AI draft, not reviewed", or "AI notes, reviewed by <name> on DD/MM/YYYY". */
  label?: string;
  edits?: number;
}

export interface MeetingNotes {
  meeting_id: string;
  meeting?: MeetingInfo;
  label?: string;
  cases: CaseNotes[];
  /** The Case Files whose notes are being written now. */
  building?: string[];
  recording?: RecordingView;
}

/** Every Case File's notes of this meeting, with the "said" words: the meeting's members (403 not_member otherwise). */
export const getMeetingNotes = (mid: string) => api.get<MeetingNotes>(`${mUrl(mid)}/notes`);
/** The coordinator changes one line's text; the "said" stays. */
export const editNoteLine = (mid: string, cid: string, lineId: string, text: string) => api.put<NoteLine>(`${mUrl(mid)}/cases/${enc(cid)}/notes/lines/${enc(lineId)}`, { text });
/** The coordinator marks a Case File's notes reviewed (or back to draft). */
export const reviewNotes = (mid: string, cid: string, status: "reviewed" | "draft") => api.post<CaseNotes>(`${mUrl(mid)}/cases/${enc(cid)}/notes/review`, { status });
