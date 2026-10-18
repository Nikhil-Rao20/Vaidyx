// Every call the meeting pages make (meetings.py, checked against tumour_board/api/meetings.py). The old /sessions
// routes are the read-only fallback when the new routes are not on the server.
import { api, TB } from "@/lib/api";
import { routeMissing, type MeetingInfo, type MeetingState, type MeetingTimer, type Opened } from "@/lib/live";
import type { CardsResponse, DecisionBody, JoinResponse, MeetingsResponse, MemberCard, NewMeeting, OldSession, SlidesResponse } from "./types";

const enc = encodeURIComponent;
export const mUrl = (mid: string) => `${TB}/meetings/${enc(mid)}`;
export const notBuiltYet = (e: unknown) => routeMissing(e);

/** POST /meetings and PUT answer {meeting}; an older draft answered the row itself. */
const row = (r: { meeting?: MeetingInfo } & Partial<MeetingInfo>): MeetingInfo => (r.meeting ?? (r as MeetingInfo));

export const listMeetings = () => api.get<MeetingsResponse>(`${TB}/meetings`);
export const createMeeting = async (b: NewMeeting) => row(await api.post<{ meeting?: MeetingInfo } & Partial<MeetingInfo>>(`${TB}/meetings`, b));
export const updateMeeting = async (mid: string, b: Partial<NewMeeting>) => row(await api.put<{ meeting?: MeetingInfo } & Partial<MeetingInfo>>(mUrl(mid), b));
export const cancelMeeting = (mid: string, reason?: string) => api.post(`${mUrl(mid)}/cancel`, { reason });
export const getMeeting = (mid: string) => api.get<MeetingState>(mUrl(mid));

export const putAgenda = (mid: string, discussion: string[], noting: string[]) => api.put<MeetingState>(`${mUrl(mid)}/agenda`, { discussion, noting });
export const addToAgenda = (mid: string, case_id: string, list: "discussion" | "noting", reason?: string) => api.post<MeetingState>(`${mUrl(mid)}/agenda/add`, { case_id, list, reason });
export const sendAgenda = (mid: string) => api.post(`${mUrl(mid)}/send-agenda`, {});
export const remindCase = (mid: string, case_id: string) => api.post(`${mUrl(mid)}/remind`, { case_id });
export const newCode = (mid: string) => api.post<{ value: string; expires_at: string }>(`${mUrl(mid)}/code`, {});
export const joinMeeting = (code: string) => api.post<JoinResponse>(`${TB}/meetings/join`, { code });
export const admit = (mid: string, user: string) => api.post(`${mUrl(mid)}/admit`, { user });
export const present = (mid: string, mode: "room" | "remote") => api.post(`${mUrl(mid)}/present`, { mode });
export const startMeeting = (mid: string) => api.post(`${mUrl(mid)}/start`, {});
export const endMeeting = (mid: string) => api.post(`${mUrl(mid)}/end`, {});
export const setCurrent = (mid: string, case_id: string, slide?: number) => api.post(`${mUrl(mid)}/current`, { case_id, slide });
export const openOnScreen = (mid: string, kind: "record" | "images" | "none", doc_id?: string) => api.post<{ opened: Opened | null }>(`${mUrl(mid)}/open`, { kind, doc_id });
export const timer = (mid: string, action: "start" | "stop" | "reset", minutes?: number) => api.post<{ timer: MeetingTimer | null }>(`${mUrl(mid)}/timer`, { action, minutes });
export const askQuestion = (mid: string, text: string) => api.post(`${mUrl(mid)}/questions`, { text });
export const raiseHand = (mid: string, raised: boolean) => api.post(`${mUrl(mid)}/hand`, { raised });
export const decisionLive = (mid: string, text: string) => api.put(`${mUrl(mid)}/decision-live`, { text });
export const saveDecision = (mid: string, cid: string, b: DecisionBody) => api.post(`${mUrl(mid)}/cases/${enc(cid)}/decision`, b);
export const endCase = (mid: string, cid: string) => api.post<{ case_id: string; cards_requested: string[] }>(`${mUrl(mid)}/cases/${enc(cid)}/end`, {});
export const sendCard = (mid: string, cid: string, agree: boolean, note?: string) => api.post<{ card: MemberCard }>(`${mUrl(mid)}/cases/${enc(cid)}/card`, { agree, note });
export const getCards = (mid: string) => api.get<CardsResponse>(`${mUrl(mid)}/cards`);
export const meetingDeckUrl = (mid: string) => `${mUrl(mid)}/deck`;
export const getSlides = (mid: string, cid: string) => api.get<SlidesResponse>(`${mUrl(mid)}/cases/${enc(cid)}/slides`);

// Old sessions, read-only.
export const listOldSessions = () => api.get<{ sessions: OldSession[]; can_manage: boolean }>(`${TB}/sessions`);
export const getOldSession = (sid: string) => api.get<{ session: { id: string; date: string; title?: string; status: string; agenda: Array<{ case_id: string; owner_ready?: boolean; status?: string }>; current?: string | null; members?: Array<{ name: string; department?: string }> } }>(`${TB}/sessions/${enc(sid)}`);

/** The hospital image viewer for a study, served through the app so the viewer stays same-origin. */
export const ohifUrl = (studyUid: string) => `${TB}/pacs/ohif/viewer?StudyInstanceUIDs=${enc(studyUid)}`;
/** One page of a record as a PNG (pages are 0-based in the API). */
export const recordPageUrl = (cid: string, doc: string, page = 0) => `${TB}/cases/${enc(cid)}/documents/${enc(doc)}/file?render=1&page=${page}`;

/** Only a same-origin path is put in an iframe on the shared screen. */
export function viewerSrc(o: Opened | null | undefined): string | null {
  if (!o) return null;
  const u = o.viewer_url ?? (o.kind === "images" ? o.url : undefined);
  if (u && u.startsWith("/")) return u;
  return o.study_uid ? ohifUrl(o.study_uid) : null;
}
