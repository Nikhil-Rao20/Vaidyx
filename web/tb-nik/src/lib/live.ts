// The live channel of a meeting: WebSocket /api/tb/meetings/{mid}/ws (live.py) with reconnect and backoff, a ping
// every 25 s, typed events, and a fallback poll of GET /meetings/{mid} every 10 s so the screen never goes blind.
// The socket opens only once the first GET answered, so a meeting that does not exist (or a server without the
// meeting routes) is never hammered with reconnects.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, TB } from "@/lib/api";

export type LiveEventType =
  | "state" | "current" | "open" | "timer" | "decision_live" | "question" | "hand" | "presence" | "admit" | "end_case"
  | "card" | "agent_state" | "ended" | "agenda" | "decision" | "meeting" | "pong" | "error"
  // night-v3 Phase 5: the call shell
  | "agents" | "spotlight" | "reaction" | "chat" | "presenting" | "present_allowed";

export interface LiveEvent { type: LiveEventType | string; [k: string]: unknown }

export type LiveStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed" | "unavailable";

export function meetingWsUrl(mid: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${TB}/meetings/${encodeURIComponent(mid)}/ws`;
}

export interface LiveClientOptions {
  onEvent: (ev: LiveEvent) => void;
  onStatus?: (s: LiveStatus, detail?: string) => void;
  pingMs?: number;
  maxBackoffMs?: number;
}

/** A small reconnecting WebSocket. close() stops it for good. */
export class LiveClient {
  private ws: WebSocket | null = null;
  private stopped = false;
  private attempt = 0;
  private pingTimer: number | null = null;
  private reconnectTimer: number | null = null;
  private readonly url: string;
  private readonly opts: LiveClientOptions;
  status: LiveStatus = "idle";

  constructor(url: string, opts: LiveClientOptions) { this.url = url; this.opts = opts; }

  connect() {
    if (this.stopped) return;
    this.setStatus(this.attempt ? "reconnecting" : "connecting");
    let ws: WebSocket;
    try { ws = new WebSocket(this.url); } catch { this.setStatus("unavailable", "The browser could not open the live channel."); return; }
    this.ws = ws;
    ws.onopen = () => { this.attempt = 0; this.setStatus("open"); this.startPing(); };
    ws.onmessage = (m) => {
      let ev: LiveEvent | null = null;
      try { ev = JSON.parse(String(m.data)); } catch { ev = null; }
      if (ev && typeof ev === "object" && typeof ev.type === "string" && ev.type !== "pong") this.opts.onEvent(ev);
    };
    ws.onerror = () => { /* onclose follows */ };
    ws.onclose = (e) => {
      this.stopPing();
      this.ws = null;
      if (this.stopped) { this.setStatus("closed"); return; }
      // 1008 policy violation (no access, wrong origin): do not hammer the server; the 10 s poll keeps the page current.
      if (e.code === 1008 || e.code === 4401 || e.code === 4403) { this.setStatus("unavailable", "The live channel refused the connection; the page checks every 10 seconds instead."); return; }
      this.attempt += 1;
      const wait = Math.min(this.opts.maxBackoffMs ?? 30_000, 1000 * 2 ** Math.min(this.attempt - 1, 5)) + Math.random() * 400;
      this.setStatus(this.attempt > 4 ? "unavailable" : "reconnecting", `Reconnecting in ${Math.round(wait / 1000)} s`);
      this.reconnectTimer = window.setTimeout(() => this.connect(), wait);
    };
  }

  send(obj: Record<string, unknown>): boolean {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) { this.ws.send(JSON.stringify(obj)); return true; }
    return false;
  }

  close() {
    this.stopped = true;
    this.stopPing();
    if (this.reconnectTimer) { window.clearTimeout(this.reconnectTimer); this.reconnectTimer = null; }
    if (this.ws) { try { this.ws.close(1000, "bye"); } catch { /* already closed */ } this.ws = null; }
    this.setStatus("closed");
  }

  private startPing() {
    this.stopPing();
    this.pingTimer = window.setInterval(() => { this.send({ type: "ping" }); }, this.opts.pingMs ?? 25_000);
  }
  private stopPing() { if (this.pingTimer) { window.clearInterval(this.pingTimer); this.pingTimer = null; } }
  private setStatus(s: LiveStatus, detail?: string) { this.status = s; this.opts.onStatus?.(s, detail); }
}

// ---- the meeting state (GET /meetings/{mid}, the first socket message) -----------------------------------------------
export interface AgendaRow {
  case_id: string;
  patient_line: string;
  missing?: boolean;
  protocol?: string;
  owner_name?: string;
  owner_department?: string;
  owner_department_name?: string;
  presenter_name?: string;
  /** The presenter chosen when the Case File was sent to the board (night-v3 1.4); null when the owner presents. */
  presenter?: { user: string; name: string } | null;
  board_question?: string;
  left_before_board?: number | null;
  minutes?: number;
  order?: number;
  reason?: string;
  ready?: boolean;
  status?: string;
  ended?: boolean;
  /** The outcome id (decision, deferred, referred, not_discussed, noted) once the board recorded it. */
  outcome?: string | null;
  outcome_label?: string;
  added_after_send?: boolean;
  /** After sending (night-v3 1.5): a value waits on the treating doctor's check ("waiting on Dr X"); null when nothing waits. */
  waiting_on?: { user: string; name: string; values?: number } | null;
  /** Reports new or changed since the Case File was sent to the board (night-v3 1.5). */
  new_since_sent?: number;
  urgency?: number | null;
  /** Set on the client after a "decision" event. */
  decided?: boolean;
  /** Seconds spent on the case when it ended (night-v3 5.4); null or absent before. */
  elapsed_seconds?: number | null;
}

export interface Attendee {
  user: string;
  name: string;
  department?: string;
  department_name?: string;
  status: "present" | "remote" | "absent" | "waiting" | string;
  mode?: "room" | "remote" | null | string;
  joined_at?: string;
  online?: boolean;
  head?: boolean;
  outside_expert?: boolean;
  hand?: boolean;
  phone?: string;
}

export interface QuestionAnswer {
  status?: string;
  text?: string;
  statements?: Array<{ text: string; citations?: Array<{ doc_id: string; doc_title?: string; page?: number | null; quote?: string }> }>;
  role?: string;
  label?: string;
  model?: string;
  at?: string;
  seconds?: number;
  note?: string;
}

export interface MeetingQuestion {
  id: string;
  by?: string;
  by_name: string;
  text: string;
  at: string;
  case_id?: string;
  /** The stand-in agent's answer (an object from meetings.answer), or a plain text from an older server. */
  answer?: QuestionAnswer | string | null;
  /** The stand-in role the question was routed to, when one is active. */
  role?: string | null;
  agent_label?: string;
}

export interface Opened {
  kind: "record" | "images" | "none" | string;
  doc_id?: string;
  title?: string;
  /** For a record: the file url; for images: the hospital viewer url (same origin). */
  url?: string;
  study_uid?: string;
  viewer_url?: string;
  modality?: string | null;
  page?: number;
  by?: string;
  at?: string;
}

export interface MeetingTimer { seconds_left: number; running: boolean; total?: number }

export interface AgentState {
  active: boolean;
  role?: string | null;
  label?: string;
  state?: "off" | "ready" | "reading_question" | "reading" | "thinking" | "answering" | string;
  roles?: string[];
  question?: string | null;
  note?: string;
}

/** One stand-in agent of the meeting (owner decision D2; meetings.agents_view): a tile and a panel row, never a member. */
export interface AgentInfo {
  role: string;
  label: string;
  department?: string;
  department_name?: string;
  /** ready, reading_question, thinking, answering (true states from the server); Phase 6 adds listening and speaking. */
  state: string;
  question?: string | null;
  note?: string;
  standing_in?: boolean;
  /** Added by the coordinator on demand (Phase 6). */
  added?: boolean;
}

/** The quorum line (night-v3 5.4): heads present as people, the agents standing in, the PM-JAY composition. Information, not a gate. */
export interface QuorumInfo {
  heads: Array<{ id: string; name: string; present: boolean; by?: string | null; agent?: string | null; role?: string | null }>;
  present: number;
  total: number;
  agents: string[];
  pmjay: { surgical?: boolean; radiation?: boolean; medical?: boolean; present: number; total: number; note?: string; not_applicable?: boolean; seat_note?: string; seat_check?: boolean };
}

/** The presenter of the Case File on the floor (night-v3 5.4). */
export interface PresenterInfo { user: string; name: string; department?: string; department_name?: string }

/** A meeting chat line (night-v3 5.3): kept with the meeting record, apart from the questions to the agents. */
export interface ChatMessage { id: string; by: string; by_name: string; text: string; at: string; case_id?: string | null }

/** A reaction as the live channel carries it (night-v3 5.1): shown for a moment, never stored. */
export interface ReactionEvent { user: string; name?: string; kind: "agree" | "thanks" | "applause" | "question" | string; at?: string }

export interface MeetingInfo {
  id: string;
  date: string;
  time?: string;
  room?: string;
  status: "planned" | "in_session" | "closed" | "cancelled" | string;
  video?: boolean;
  minutes_per_case?: number;
  counts?: { discussion: number; noting: number; not_ready: number };
  agenda_sent_at?: string | null;
  title?: string;
  created_by?: string;
  started_at?: string | null;
  closed_at?: string | null;
  cancelled?: { by?: string; at?: string; reason?: string } | null;
  current?: string | null;
  people?: number;
  label?: string;
  /** A number the remote members may call (the room phone), when the hospital set one. */
  phone?: string;
  room_phone?: string;
}

export interface MeetingOutcome { outcome: string; label?: string; record?: string; by?: string; at?: string; decision_text?: string; moved_to?: string | null; flagged?: boolean }

export interface MeetingState {
  meeting: MeetingInfo;
  agenda: { discussion: AgendaRow[]; noting: AgendaRow[]; not_ready: AgendaRow[] };
  code?: { value: string; expires_at: string; attempts?: number } | null;
  attendance: Attendee[];
  current: { case_id?: string | null; slide?: number; opened?: Opened | null; timer?: MeetingTimer | null; presenter?: PresenterInfo | null; elapsed_seconds?: number } | null;
  decision_live?: { text: string; by?: string; at?: string | null; case_id?: string | null; saved?: boolean } | null;
  questions: MeetingQuestion[];
  hands: Array<string | { user: string; name?: string; at?: string }>;
  agent?: AgentState | null;
  can?: { manage?: boolean; record?: boolean; ask?: boolean; card?: boolean; card_required?: boolean; video?: boolean; present?: boolean; chat?: boolean };
  /** Every absent head's stand-in agent (night-v3 5.1, D2); `agent` above stays for older readers. */
  agents?: AgentInfo[];
  /** The people the coordinator spotlighted for everyone (night-v3 5.1). */
  spotlight?: string[];
  quorum?: QuorumInfo | null;
  chat?: ChatMessage[];
  /** Screen share (night-v3 5.2): who may present besides the coordinator and the presenter, and who shares now. */
  present_allowed?: string[];
  presenting?: string | null;
  me?: { user?: string; status?: string | null; mode?: string | null; department?: string; role?: string };
  online?: string[];
  outcomes?: Record<string, MeetingOutcome>;
  ended?: string[];
  cards_given?: Record<string, string[]>;
  heads?: Array<{ id: string; name?: string; role?: string } | string>;
  absent_roles?: string[];
  status?: string;
}

const EMPTY_CURRENT: NonNullable<MeetingState["current"]> = { case_id: null, slide: 0, opened: null, timer: null, presenter: null };

/** One agent's state event merged into the list by role (the event carries the state only). */
function mergeAgent(list: AgentInfo[] | undefined, a: Partial<AgentInfo> & { role?: string | null }): AgentInfo[] | undefined {
  if (!list || !a.role) return list;
  return list.map((x) => (x.role === a.role ? { ...x, state: a.state ?? x.state, question: a.question === undefined ? x.question : a.question } : x));
}

function asTimer(v: unknown): MeetingTimer | null {
  if (!v || typeof v !== "object") return null;
  const t = v as Record<string, unknown>;
  return { seconds_left: Number(t.seconds_left ?? 0), running: !!t.running, total: typeof t.total === "number" ? t.total : undefined };
}

function asOpened(v: unknown): Opened | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Opened;
  return o.kind === "none" ? null : o;
}

/** One live event applied to the state. Unknown events leave the state as it is. */
export function applyLiveEvent(s: MeetingState | null, ev: LiveEvent): MeetingState | null {
  if (ev.type === "state") { const { type: _t, ...rest } = ev; void _t; return rest as unknown as MeetingState; }
  if (!s) return s;
  const cur = s.current ?? EMPTY_CURRENT;
  const next: MeetingState = { ...s, current: { ...cur } };
  switch (ev.type) {
    case "current": {
      const cid = (ev.case_id as string | null | undefined) ?? cur.case_id ?? null;
      const changed = cid !== (cur.case_id ?? null);
      next.current = {
        case_id: cid,
        slide: typeof ev.slide === "number" ? ev.slide : changed ? 0 : cur.slide ?? 0,
        opened: ev.opened !== undefined ? asOpened(ev.opened) : changed ? null : cur.opened ?? null,
        timer: ev.timer !== undefined ? asTimer(ev.timer) : cur.timer ?? null,
        presenter: ev.presenter !== undefined ? (ev.presenter as PresenterInfo | null) : changed ? null : cur.presenter ?? null,
        elapsed_seconds: typeof ev.elapsed_seconds === "number" ? ev.elapsed_seconds : changed ? 0 : cur.elapsed_seconds,
      };
      if (ev.agent && typeof ev.agent === "object") next.agent = ev.agent as AgentState;
      if (Array.isArray(ev.agents)) next.agents = ev.agents as AgentInfo[];
      if (Array.isArray(ev.spotlight)) next.spotlight = ev.spotlight as string[]; else if (changed) next.spotlight = [];
      if (ev.quorum !== undefined) next.quorum = ev.quorum as QuorumInfo | null;
      if (changed) { next.presenting = null; }
      if (ev.status === "in_session" && s.meeting.status !== "in_session") next.meeting = { ...s.meeting, status: "in_session" };
      if (changed) next.decision_live = null;
      return next;
    }
    case "open": {
      // live.py sends {case_id, opened}; an older shape put the fields at the top level.
      const opened = ev.opened !== undefined ? asOpened(ev.opened) : ev.kind ? asOpened({ kind: ev.kind, doc_id: ev.doc_id, study_uid: ev.study_uid, viewer_url: ev.viewer_url, url: ev.url, page: ev.page }) : null;
      next.current = { ...cur, opened };
      return next;
    }
    case "timer": next.current = { ...cur, timer: asTimer(ev.timer ?? ev) }; return next;
    case "decision_live": next.decision_live = { text: String(ev.text ?? ""), by: ev.by as string | undefined, at: ev.at as string | undefined, case_id: ev.case_id as string | undefined, saved: !!ev.saved }; return next;
    case "question": {
      const raw = (ev.question as MeetingQuestion | undefined) ?? { id: String(ev.id ?? Date.now()), by_name: String(ev.by_name ?? ""), text: String(ev.text ?? ""), at: String(ev.at ?? new Date().toISOString()), answer: ev.answer as MeetingQuestion["answer"] };
      const list = [...(s.questions ?? [])];
      const i = list.findIndex((x) => x.id === raw.id);
      if (i >= 0) list[i] = { ...list[i], ...raw }; else list.push(raw);
      next.questions = list;
      return next;
    }
    case "hand": {
      if (Array.isArray(ev.hands)) {
        next.hands = ev.hands as MeetingState["hands"];
      } else {
        const user = String(ev.user ?? "");
        const rest = (s.hands ?? []).filter((h) => (typeof h === "string" ? h : h.user) !== user);
        next.hands = ev.raised ? [...rest, { user, name: ev.name as string | undefined }] : rest;
      }
      return next;
    }
    case "presence": {
      if (Array.isArray(ev.attendance)) next.attendance = ev.attendance as Attendee[];
      if (Array.isArray(ev.online)) next.online = ev.online as string[];
      if (ev.quorum !== undefined) next.quorum = ev.quorum as QuorumInfo | null;
      if (Array.isArray(ev.agents)) next.agents = ev.agents as AgentInfo[];
      return next;
    }
    case "admit": {
      const user = String(ev.user ?? "");
      if (Array.isArray(ev.attendance)) next.attendance = ev.attendance as Attendee[];
      else next.attendance = (s.attendance ?? []).map((a) => (a.user === user ? { ...a, status: String(ev.status ?? "remote") } : a));
      if (s.me?.user && s.me.user === user) next.me = { ...s.me, status: String(ev.status ?? "remote") };
      if (ev.agent && typeof ev.agent === "object") next.agent = ev.agent as AgentState;
      if (Array.isArray(ev.agents)) next.agents = ev.agents as AgentInfo[];
      if (ev.quorum !== undefined) next.quorum = ev.quorum as QuorumInfo | null;
      return next;
    }
    case "agent_state": {
      const a = (ev.agent && typeof ev.agent === "object" ? ev.agent : ev) as AgentState;
      // the event carries the state only; keep the label and note the full state gave
      next.agent = { ...(s.agent ?? { active: true }), ...a, active: a.active !== false };
      next.agents = mergeAgent(s.agents, a as Partial<AgentInfo> & { role?: string | null });
      return next;
    }
    case "agents": if (Array.isArray(ev.agents)) next.agents = ev.agents as AgentInfo[]; return next;
    case "spotlight": next.spotlight = Array.isArray(ev.users) ? (ev.users as string[]) : []; return next;
    case "chat": {
      const m = ev.message as ChatMessage | undefined;
      if (!m || !m.id) return s;
      const list = [...(s.chat ?? [])];
      const i = list.findIndex((x) => x.id === m.id);
      if (i >= 0) list[i] = { ...list[i], ...m }; else list.push(m);
      next.chat = list.slice(-200);
      return next;
    }
    case "presenting": next.presenting = ev.on ? String(ev.user ?? "") || null : null; return next;
    case "present_allowed": next.present_allowed = Array.isArray(ev.users) ? (ev.users as string[]) : []; return next;
    case "reaction": return s;
    case "ended": {
      const m = ev.meeting && typeof ev.meeting === "object" ? (ev.meeting as MeetingInfo) : null;
      next.meeting = m ? { ...s.meeting, ...m } : { ...s.meeting, status: ev.cancelled ? "cancelled" : "closed" };
      next.decision_live = null;
      return next;
    }
    case "meeting": if (ev.meeting && typeof ev.meeting === "object") next.meeting = { ...s.meeting, ...(ev.meeting as MeetingInfo) }; return next;
    case "agenda": {
      if (ev.agenda && typeof ev.agenda === "object") next.agenda = ev.agenda as MeetingState["agenda"];
      if (ev.sent_at) next.meeting = { ...s.meeting, agenda_sent_at: String(ev.sent_at) };
      if (ev.counts && typeof ev.counts === "object") next.meeting = { ...next.meeting, counts: ev.counts as MeetingInfo["counts"] };
      return next;
    }
    case "decision": {
      const cid = String(ev.case_id ?? "");
      const oc = (ev.outcome && typeof ev.outcome === "object" ? ev.outcome : { outcome: String(ev.outcome ?? "decision") }) as MeetingOutcome;
      const mark = (rows: AgendaRow[]) => rows.map((r) => (r.case_id === cid ? { ...r, decided: true, outcome: oc.outcome, outcome_label: oc.label ?? r.outcome_label } : r));
      next.agenda = { discussion: mark(s.agenda.discussion), noting: mark(s.agenda.noting), not_ready: mark(s.agenda.not_ready) };
      next.outcomes = { ...(s.outcomes ?? {}), [cid]: oc };
      next.decision_live = null;
      return next;
    }
    case "end_case": {
      const cid = String(ev.case_id ?? "");
      next.ended = Array.from(new Set([...(s.ended ?? []), cid]));
      if (ev.timer !== undefined && cid === cur.case_id) next.current = { ...cur, timer: asTimer(ev.timer) };
      return next;
    }
    case "card": {
      const cid = String(ev.case_id ?? "");
      if (Array.isArray(ev.cards_given)) next.cards_given = { ...(s.cards_given ?? {}), [cid]: ev.cards_given as string[] };
      return next;
    }
    default: return s;
  }
}

export const meetingUrl = (mid: string) => `${TB}/meetings/${encodeURIComponent(mid)}`;

/** Live state of one meeting: the WebSocket feeds it, the poll every 10 s corrects it, callers get every event. */
export function useMeetingLive(mid: string, opts: { enabled?: boolean; onEvent?: (ev: LiveEvent) => void } = {}) {
  const enabled = opts.enabled ?? true;
  const qc = useQueryClient();
  const [state, setState] = useState<MeetingState | null>(null);
  const [status, setStatus] = useState<LiveStatus>("idle");
  const [statusDetail, setStatusDetail] = useState<string | undefined>();
  const [lastEvent, setLastEvent] = useState<LiveEvent | null>(null);
  const [loaded, setLoaded] = useState(false);
  const onEventRef = useRef(opts.onEvent);
  onEventRef.current = opts.onEvent;
  const client = useRef<LiveClient | null>(null);
  const lastEventAt = useRef(0);

  const poll = useQuery({
    queryKey: ["meeting", mid],
    queryFn: () => api.get<MeetingState>(meetingUrl(mid)),
    enabled: enabled && !!mid,
    refetchInterval: (q) => (q.state.error instanceof ApiError && (q.state.error.status === 404 || q.state.error.status === 403) ? false : 10_000),
    refetchIntervalInBackground: true,
    retry: (n, e) => !(e instanceof ApiError && (e.status === 404 || e.status === 403)) && n < 2,
  });

  // The poll is the truth unless a live event arrived while it was in flight (then the live part stays).
  useEffect(() => {
    if (!poll.data) return;
    setLoaded(true);
    const fresh = poll.data;
    const recentLive = Date.now() - lastEventAt.current < 2500;
    setState((old) => (old && recentLive ? { ...fresh, current: old.current ?? fresh.current, decision_live: old.decision_live ?? fresh.decision_live, questions: old.questions?.length > (fresh.questions?.length ?? 0) ? old.questions : fresh.questions } : fresh));
  }, [poll.data, poll.dataUpdatedAt]);

  useEffect(() => {
    if (!enabled || !mid || !loaded) return;
    const c = new LiveClient(meetingWsUrl(mid), {
      onEvent: (ev) => {
        lastEventAt.current = Date.now();
        setLastEvent(ev);
        setState((s) => applyLiveEvent(s, ev));
        onEventRef.current?.(ev);
        if (ev.type === "decision" || ev.type === "agenda" || ev.type === "ended" || ev.type === "meeting") void qc.invalidateQueries({ queryKey: ["meeting", mid] });
      },
      onStatus: (st, d) => { setStatus(st); setStatusDetail(d); },
    });
    client.current = c;
    c.connect();
    return () => { c.close(); client.current = null; };
  }, [mid, enabled, loaded, qc]);

  const send = useCallback((obj: Record<string, unknown>) => client.current?.send(obj) ?? false, []);
  const refresh = useCallback(() => qc.invalidateQueries({ queryKey: ["meeting", mid] }), [qc, mid]);
  const err = poll.error;
  const notBuilt = poll.isError && routeMissing(err) && !state;
  const missing = poll.isError && err instanceof ApiError && err.status === 404 && !routeMissing(err);
  const forbidden = poll.isError && err instanceof ApiError && err.status === 403;

  return useMemo(() => ({ state, status, statusDetail, lastEvent, send, refresh, error: err, isLoading: poll.isLoading && !state, notBuilt, missing, forbidden, setState }),
    [state, status, statusDetail, lastEvent, send, refresh, err, poll.isLoading, notBuilt, missing, forbidden]);
}

// ---- errors ------------------------------------------------------------------------------------------------------------
/** The server answered 404 because the route itself is not on it (FastAPI's bare {"detail": "Not Found"}), as opposed to
 *  a meeting or Case File that does not exist (those carry a message and a code). */
export function routeMissing(e: unknown): boolean {
  if (!(e instanceof ApiError) || e.status !== 404) return false;
  const d = e.detail as { detail?: unknown } | null;
  return !!d && typeof d === "object" && d.detail === "Not Found";
}

/** The machine code of a refusal: {"detail": {"message", "code"}} from the new routes, or a top-level code. */
export function errorCode(e: unknown): string {
  if (!(e instanceof ApiError)) return "";
  if (e.code) return e.code;
  const d = e.detail as { detail?: { code?: unknown } } | null;
  const inner = d && typeof d === "object" ? d.detail : null;
  return inner && typeof inner === "object" && typeof inner.code === "string" ? inner.code : "";
}

// ---- small readers the pages share ---------------------------------------------------------------------------------------
/** The text of a question's answer, whatever shape the server sent. */
export function answerText(q: MeetingQuestion): string {
  const a = q.answer;
  if (!a) return "";
  if (typeof a === "string") return a;
  return a.text ?? "";
}

export function handUsers(hands: MeetingState["hands"] | undefined): Set<string> {
  return new Set((hands ?? []).map((h) => (typeof h === "string" ? h : h.user)));
}
