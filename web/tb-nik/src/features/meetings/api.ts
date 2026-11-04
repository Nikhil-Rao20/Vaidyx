// Every call the meeting pages make (meetings.py, checked against tumour_board/api/meetings.py). The old /sessions
// routes are the read-only fallback when the new routes are not on the server.
import { api, TB } from "@/lib/api";
import { routeMissing, type AgentInfo, type BoardTab, type BoardViewState, type ChatMessage, type MeetingInfo, type MeetingQuestion, type MeetingState, type MeetingTimer, type Opened } from "@/lib/live";
import type { CardsResponse, DecisionBody, DecisionSpec, JoinResponse, MeetingsResponse, MemberCard, NewMeeting, OldSession, SlidesResponse } from "./types";
import type { CaseListItem } from "@/lib/types";
import type { ListKey, NewSeries, Series, SeriesList } from "./planner/types";

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
/** Put a Case File on the floor (the Board view starts on its Summary for everyone). */
export const setCurrent = (mid: string, case_id: string) => api.post(`${mUrl(mid)}/current`, { case_id });
/** The Board view's follow state (meetings-v2 2.2 / 2.4): the coordinator, or the presenter of the Case File on the floor, moves every
 *  follower to a tab, a report at a page with its line highlighted, or the images (the server grants the admitted members the viewer).
 *  Refusals: 409 not_in_session, no_current, moved_on; 403 not_member, forbidden; 400 bad_tab, bad_record, bad_page, bad_quote; 404
 *  no_record, no_images; 429. */
export const setView = (mid: string, b: { tab: BoardTab; doc_id?: string | null; page?: number | null; quote?: string }) =>
  api.post<{ view: BoardViewState }>(`${mUrl(mid)}/view`, {
    tab: b.tab,
    ...(b.doc_id ? { doc_id: b.doc_id } : {}),
    ...(b.doc_id && typeof b.page === "number" ? { page: b.page } : {}),
    ...(b.quote ? { quote: b.quote } : {}),
  });
export const timer = (mid: string, action: "start" | "stop" | "reset", minutes?: number) => api.post<{ timer: MeetingTimer | null }>(`${mUrl(mid)}/timer`, { action, minutes });
/** A question to the board, or to one stand-in agent when `role` names it (night-v3 5.1: the chip row of the Chat panel). */
export const askQuestion = (mid: string, text: string, role?: string) => api.post(`${mUrl(mid)}/questions`, role ? { text, role } : { text });
export const raiseHand = (mid: string, raised: boolean) => api.post(`${mUrl(mid)}/hand`, { raised });
export const decisionLive = (mid: string, text: string) => api.put(`${mUrl(mid)}/decision-live`, { text });
/** Spotlight for everyone (night-v3 5.1): the coordinator, up to three admitted people; [] removes it. */
export const setSpotlight = (mid: string, users: string[]) => api.post<{ spotlight: string[] }>(`${mUrl(mid)}/spotlight`, { users });
/** Screen share (night-v3 5.2): the coordinator allows or withdraws a member's right to present; the sharer records a start or stop. */
export const allowPresent = (mid: string, user: string, allowed: boolean) => api.post<{ present_allowed: string[] }>(`${mUrl(mid)}/present-allow`, { user, allowed });
export const setPresenting = (mid: string, on: boolean) => api.post<{ presenting: string | null; replaced?: string | null }>(`${mUrl(mid)}/presenting`, { on });
/** A meeting chat line (night-v3 5.3): kept with the meeting record, apart from the questions. */
export const sendChat = (mid: string, text: string) => api.post<{ message: ChatMessage }>(`${mUrl(mid)}/chat`, { text });
/** A short reaction (agree, thanks, applause, question): broadcast for a moment, never stored (night-v3 5.1). */
export const sendReaction = (mid: string, kind: "agree" | "thanks" | "applause" | "question") => api.post<{ user: string; kind: string; at: string }>(`${mUrl(mid)}/reaction`, { kind });
// The stand-in agents (night-v3 Phase 6, research/05 section 11.1). Every call is audited by the server.
/** The coordinator adds or removes an agent for the Case File on the floor (409 no_current outside a case). */
export const setAgent = (mid: string, role: string, on: boolean) => api.post<{ agents: AgentInfo[] }>(`${mUrl(mid)}/agents`, { role, on });
/** The coordinator's switch "Members can ask the agents". */
export const setAgentSettings = (mid: string, b: { members_ask: boolean }) => api.put<{ members_ask: boolean }>(`${mUrl(mid)}/agents/settings`, b);
/** My device records a question for this agent (on), or stopped (off); the server shows "Listening to <name>" (expires 65 s). */
export const agentListening = (mid: string, role: string, on: boolean) => api.post(`${mUrl(mid)}/agents/${enc(role)}/listening`, { on });
/** "Present your points": the agent reads its points for review from the brief (built by code, each point with its records). */
export const presentPoints = (mid: string, role: string) => api.post<{ question?: MeetingQuestion }>(`${mUrl(mid)}/agents/${enc(role)}/present`, {});
/** The asker or the coordinator stops the agent's voice for everyone (the text stays). */
export const stopAgent = (mid: string, role: string, question?: string) => api.post(`${mUrl(mid)}/agents/${enc(role)}/stop`, question ? { question } : {});
/** This device plays (true, renewed every 15 s) or stopped playing (false) an answer: the server's "Speaking" follows these reports. */
export const agentAudio = (mid: string, question: string, playing: boolean, device?: string) => api.post(`${mUrl(mid)}/agents/audio`, device ? { question, playing, device } : { question, playing });
export const saveDecision = (mid: string, cid: string, b: DecisionBody) => api.post(`${mUrl(mid)}/cases/${enc(cid)}/decision`, b);
/** The decision record's field table as the server has it (decision_record.spec()); the form uses the bundled decision_fields.json. */
export const getDecisionFields = () => api.get<DecisionSpec>(`${TB}/meetings/decision-fields`);
/** A later correction of a board record (the owning department's consultants, or the MDT Coordinator on the meeting day). */
export const correctBoardRecord = (cid: string, recordId: string, changes: Partial<DecisionBody>, reason = "") => api.post(`${TB}/cases/${enc(cid)}/board-records/${enc(recordId)}/correct`, { changes, reason });
export const endCase = (mid: string, cid: string) => api.post<{ case_id: string; cards_requested: string[] }>(`${mUrl(mid)}/cases/${enc(cid)}/end`, {});
export const sendCard = (mid: string, cid: string, agree: boolean, note?: string) => api.post<{ card: MemberCard }>(`${mUrl(mid)}/cases/${enc(cid)}/card`, { agree, note });
export const getCards = (mid: string) => api.get<CardsResponse>(`${mUrl(mid)}/cards`);
/** The summary of the Case File on the floor with the patient's identity removed, for an outside expert only (security review #9): the
 *  Board view reads the Case File itself for everyone else (meetings-v2 2.6). */
export const getSlides = (mid: string, cid: string) => api.get<SlidesResponse>(`${mUrl(mid)}/cases/${enc(cid)}/slides`);

// Old sessions, read-only.
export const listOldSessions = () => api.get<{ sessions: OldSession[]; can_manage: boolean }>(`${TB}/sessions`);
export const getOldSession = (sid: string) => api.get<{ session: { id: string; date: string; title?: string; status: string; agenda: Array<{ case_id: string; owner_ready?: boolean; status?: string }>; current?: string | null; members?: Array<{ name: string; department?: string }> } }>(`${TB}/sessions/${enc(sid)}`);

/** The hospital image viewer for a study, served through the app so the viewer stays same-origin. */
export const ohifUrl = (studyUid: string) => `${TB}/pacs/ohif/viewer?StudyInstanceUIDs=${enc(studyUid)}`;
/** Only a same-origin path is put in an iframe (the Board view's Images tab). */
export function viewerSrc(o: Opened | null | undefined): string | null {
  if (!o) return null;
  const u = o.viewer_url ?? (o.kind === "images" ? o.url : undefined);
  if (u && u.startsWith("/")) return u;
  return o.study_uid ? ohifUrl(o.study_uid) : null;
}

// ---- planning (meetings-v2 3.3): the weekly series, the agenda order, moving a Case File, the PDFs (4.1) -------------------------------
/** The MDT Coordinator's weekly series: {series: [row], weekdays: [Monday .. Sunday]}; a row has its label ("Every week on Friday at
 *  10:00"), its status (active, paused, stopped) and its meetings dated today or later. */
export const listSeries = () => api.get<SeriesList>(`${TB}/meeting-series`);
/** A new weekly series: the next four weeks of meetings are made at once (`made`: their ids, earliest first). 409 duplicate. */
export const createSeries = (b: NewSeries) => api.post<{ series: Series; made: string[] }>(`${TB}/meeting-series`, b);
/** Change the series (only the fields given): its future meetings follow, except a field changed by hand on one meeting. */
export const updateSeries = (sid: string, b: Partial<NewSeries>) => api.put<{ series: Series; changed: string[]; cancelled: string[]; made: string[] }>(`${TB}/meeting-series/${enc(sid)}`, b);
export const pauseSeries = (sid: string) => api.post<{ series: Series }>(`${TB}/meeting-series/${enc(sid)}/pause`, {});
export const resumeSeries = (sid: string) => api.post<{ series: Series; made?: string[] }>(`${TB}/meeting-series/${enc(sid)}/resume`, {});
/** No new meetings; the future meetings with no Case File are cancelled, those with Case Files stay (`kept`). */
export const stopSeries = (sid: string) => api.post<{ series: Series; cancelled: string[]; kept: MeetingInfo[] }>(`${TB}/meeting-series/${enc(sid)}/stop`, {});
/** The coordinator's order of the two lists; `byUrgency` puts those lists back in urgency order (5 first). A list put in an order that
 *  is not the urgency order is arranged by hand from then on: new Case Files go at its end, marked new. */
export const arrangeAgenda = (mid: string, discussion: string[], noting: string[], byUrgency: ListKey[] = []) =>
  api.put<MeetingState>(`${mUrl(mid)}/agenda`, byUrgency.length ? { discussion, noting, by_urgency: byUrgency } : { discussion, noting });
/** The meetings a Case File may still go to (planned, not cancelled, today or later, earliest first). */
export const listOpenMeetings = () => api.get<{ meetings: MeetingInfo[] }>(`${TB}/meetings/open`);
/** Move a Case File sent to the board to another open meeting (same list); 400 not_sent when it was never sent to the board. */
export const moveToMeeting = (cid: string, meetingId: string, reason = "") => api.post(`${TB}/cases/${enc(cid)}/meeting/move`, { meeting_id: meetingId, reason });
/** Take a Case File off the agenda with a reason (3 to 500 characters); it stays marked ready. 400 not_sent when it was never sent. */
export const takeOffAgenda = (cid: string, reason: string) => api.post(`${TB}/cases/${enc(cid)}/meeting/withdraw`, { reason });
/** The Case Files the coordinator may list, matched on the patient's name, UHID or the cancer (GET /case-list?q=). */
export const findCaseFiles = (q: string) => api.get<{ cases: CaseListItem[] }>(`${TB}/case-list?q=${enc(q)}`);
/** The meeting PDF (4.1): the agenda before the meeting, the record with the decisions and the minutes after it. The coordinator and the
 *  admitted members; never an outside expert. */
export const meetingPdfUrl = (mid: string) => `${mUrl(mid)}/pdf`;
/** The board record PDF of one Case File (4.1): its full readers, never in a read-only window; 404 no_board_record before the board. */
export const caseBoardPdfUrl = (cid: string) => `${TB}/cases/${enc(cid)}/board-pdf`;
