// Fixtures and routes for the one-page planner spec (e2e/shots/meetings-planner.spec.ts, meetings-v2 3.3 and 4.1): a planned meeting
// of a weekly series with its agenda in urgency order, the series, the other open meetings, and every planner call answered from one
// state the spec can read back (the agenda order, the code, the cancel). SYNTHETIC only: the demo patients of f2.ts and fixtures.ts.
// Register after f2.routeMeetings(): the last route registered answers first; anything not handled here falls back to it.
import type { Page, Route } from "@playwright/test";
import { CID, MID, meetingState } from "./f2";

type AnyObj = any; // eslint-disable-line @typescript-eslint/no-explicit-any

/** A date in the browser's time zone (the config runs the browser in Asia/Kolkata), `n` days from today. */
export function istDay(n = 0): string {
  const d = new Date(Date.now() + n * 864e5);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}
/** The server's weekday (0 = Monday) of a YYYY-MM-DD date. */
export const weekdayOf = (iso: string) => (new Date(`${iso}T12:00:00Z`).getUTCDay() + 6) % 7;
export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
/** "07/11/2026" */
export const dmy = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;

export const SID = "W1a2b3c4d";
export const NEXT = "M-2";

const sent = (minutesAgo: number) => new Date(Date.now() - minutesAgo * 60_000).toISOString();

/** The meeting of the weekly series in 3 days: For discussion in urgency order (5, 4, 3), one for noting, one not ready, the code made. */
export function plannerState(over: AnyObj = {}): AnyObj {
  const s: AnyObj = meetingState("planned");
  const date = over.date ?? istDay(3);
  s.meeting = { ...s.meeting, date, time: "16:00", room: "Seminar hall 2", series_id: SID, series_date: date, agenda_sent_at: null };
  const [p19, fatima, kamala] = s.agenda.discussion;
  s.agenda.discussion = [
    { ...fatima, urgency: 5, sent_at: sent(60 * 30), new: false, presenter: { user: "rao@vxh.example", name: "Lakshmi Rao" } },
    { ...p19, urgency: 4, sent_at: sent(60 * 20), new: false, presenter: { user: "asha@vxh.example", name: "Asha Menon" } },
    { ...kamala, urgency: 3, sent_at: sent(60 * 10), new: false },
  ];
  s.agenda.noting = s.agenda.noting.map((r: AnyObj) => ({ ...r, urgency: 1, sent_at: sent(60 * 40), new: false }));
  s.agenda_order = { discussion: "urgency", noting: "urgency" };
  s.attendance = [];
  s.heads = [
    { id: "radiology", name: "Radiology", role: "radiology" }, { id: "pathology", name: "Pathology", role: "pathology" },
    { id: "medical_oncology", name: "Medical Oncology", role: "medical_oncology" }, { id: "surgical_oncology", name: "Surgical Oncology", role: "surgical_oncology" },
    { id: "radiation_oncology", name: "Radiation Oncology", role: "radiation_oncology" },
  ];
  delete over.date;
  return { ...s, ...over, meeting: { ...s.meeting, ...(over.meeting ?? {}) } };
}

/** The same meeting after the coordinator arranged For discussion by hand, with a Case File sent since, at the end and marked New. */
export function plannerHandState(): AnyObj {
  const s = plannerState();
  const [fatima, p19, kamala] = s.agenda.discussion;
  s.agenda.discussion = [p19, fatima, kamala, {
    ...kamala, case_id: "TB-2026-0031", patient_line: "Lakshmi R., 58 F, UHID VXH/2026/000123", protocol: "breast", owner_name: "Lakshmi Rao", owner_department: "breast_surgery",
    owner_department_name: "Breast Surgery", presenter_name: "Lakshmi Rao", presenter: null, board_question: "Upfront surgery or neoadjuvant therapy as the board decides", left_before_board: 2, urgency: 5, sent_at: sent(15), new: true,
  }];
  s.agenda_order = { discussion: "hand", noting: "urgency" };
  return s;
}

export function series(over: AnyObj = {}): AnyObj {
  const date = istDay(3);
  const wd = weekdayOf(date);
  return { id: SID, title: "", weekday: wd, weekday_name: WEEKDAYS[wd], time: "16:00", room: "Seminar hall 2", video: false, minutes_per_case: 10, active: true, paused: null, stopped: null,
    status: "active", label: `Every week on ${WEEKDAYS[wd]} at 16:00`, created_by: "mdt@vxh.example", created_at: sent(60 * 24 * 7), updated_at: sent(60 * 24 * 7),
    meetings: [{ id: MID, date, time: "16:00", room: "Seminar hall 2", status: "planned", series_id: SID, series_date: date, counts: { discussion: 3, noting: 1, not_ready: 1 } },
      { id: NEXT, date: istDay(10), time: "16:00", room: "Seminar hall 2", status: "planned", series_id: SID, series_date: istDay(10), counts: { discussion: 0, noting: 0, not_ready: 0 } }], ...over };
}

/** The meetings a Case File may go to (GET /meetings/open): this one, the next of the series and an extra meeting. */
export function openMeetings(): AnyObj[] {
  return [
    { id: MID, date: istDay(3), time: "16:00", room: "Seminar hall 2", status: "planned", series_id: SID },
    { id: "M-X", date: istDay(5), time: "11:00", room: "Board room", status: "planned", series_id: "" },
    { id: NEXT, date: istDay(10), time: "16:00", room: "Seminar hall 2", status: "planned", series_id: SID },
  ];
}

export type PlannerCalls = { method: string; path: string; body: AnyObj }[];

/** Answers the planner's calls from `state` (kept up to date, so the page's next GET reads the change) and records every call. */
export async function routePlanner(page: Page, state: AnyObj, o: { series?: AnyObj[]; inSession?: () => AnyObj } = {}): Promise<PlannerCalls> {
  const calls: PlannerCalls = [];
  const seriesRows: AnyObj[] = o.series ?? [series()];
  const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const all = () => [...state.agenda.discussion, ...state.agenda.noting, ...state.agenda.not_ready];
  const drop = (cid: string) => { for (const k of ["discussion", "noting", "not_ready"]) state.agenda[k] = state.agenda[k].filter((r: AnyObj) => r.case_id !== cid); };
  const counts = () => { state.meeting.counts = { discussion: state.agenda.discussion.length, noting: state.agenda.noting.length, not_ready: state.agenda.not_ready.length }; };

  await page.route("**/api/tb/meeting-series**", async (route) => {
    const url = new URL(route.request().url()); const m = route.request().method(); const body = route.request().postDataJSON?.() ?? null;
    calls.push({ method: m, path: url.pathname, body });
    const p = url.pathname.replace("/api/tb/meeting-series", "");
    if (p === "" && m === "GET") return json(route, { series: seriesRows, weekdays: WEEKDAYS });
    if (p === "" && m === "POST") {
      const wd = Number(body?.weekday ?? 4);
      const row = series({ id: "W9", weekday: wd, weekday_name: WEEKDAYS[wd], time: body?.time ?? "16:00", room: body?.room ?? "", label: `Every week on ${WEEKDAYS[wd]} at ${body?.time ?? "16:00"}` });
      seriesRows.push(row);
      return json(route, { series: row, made: [MID, NEXT, "M-3", "M-4"] });
    }
    const ser = seriesRows.find((x) => p.startsWith(`/${x.id}`));
    if (!ser) return json(route, { detail: { message: "Weekly series not found.", code: "not_found" } }, 404);
    if (m === "PUT") {
      Object.assign(ser, body);
      if (body?.weekday !== undefined) ser.weekday_name = WEEKDAYS[body.weekday];
      ser.label = `Every week on ${ser.weekday_name} at ${ser.time}`;
      return json(route, { series: ser, changed: [MID, NEXT], cancelled: [], made: [] });
    }
    if (p.endsWith("/pause")) { Object.assign(ser, { active: false, status: "paused", paused: { by: "mdt@vxh.example", at: sent(0) } }); return json(route, { series: ser }); }
    if (p.endsWith("/resume")) { Object.assign(ser, { active: true, status: "active", paused: null }); return json(route, { series: ser, made: [] }); }
    if (p.endsWith("/stop")) { Object.assign(ser, { active: false, status: "stopped", stopped: { by: "mdt@vxh.example", at: sent(0) } }); return json(route, { series: ser, cancelled: [NEXT], kept: [state.meeting] }); }
    return json(route, { ok: true });
  });

  await page.route("**/api/tb/cases/*/meeting/*", async (route) => {
    const url = new URL(route.request().url()); const body = route.request().postDataJSON?.() ?? {};
    calls.push({ method: route.request().method(), path: url.pathname, body });
    const [, , , , cid, , what] = url.pathname.split("/");
    if (what === "withdraw" && String(body.reason ?? "").trim().length < 3) return json(route, { detail: { message: "Say why it comes off the agenda.", code: "reason_needed" } }, 400);
    drop(decodeURIComponent(cid)); counts();
    return json(route, { case_id: cid, meeting_id: what === "move" ? body.meeting_id : "", board_date: "", board_send: {}, meeting: null });
  });

  await page.route("**/api/tb/meetings/**", async (route) => {
    const url = new URL(route.request().url()); const m = route.request().method(); const p = url.pathname.replace("/api/tb/meetings", "");
    const body = m === "GET" ? null : route.request().postDataJSON?.() ?? null;
    if (p === "/open" && m === "GET") { calls.push({ method: m, path: url.pathname, body }); return json(route, { meetings: openMeetings() }); }
    if (!p.startsWith(`/${MID}`)) return route.fallback();
    const rest = p.slice(MID.length + 1);
    if (m === "GET" && rest === "/pdf") {
      calls.push({ method: m, path: url.pathname, body });
      return route.fulfill({ status: 200, contentType: "application/pdf", headers: { "Content-Disposition": `attachment; filename="Tumour-Board-meeting-${state.meeting.date}.pdf"` }, body: "%PDF-1.7\n% SYNTHETIC test file\n%%EOF\n" });
    }
    if (m === "GET") return route.fallback();
    calls.push({ method: m, path: url.pathname, body });
    if (rest === "" && m === "PUT") { Object.assign(state.meeting, body); return json(route, { meeting: state.meeting }); }
    if (rest === "/agenda" && m === "PUT") {
      const byId = new Map(all().map((r: AnyObj) => [r.case_id, r]));
      const urg = (rows: AnyObj[]) => [...rows].sort((a, b) => (b.urgency ?? 0) - (a.urgency ?? 0) || String(a.sent_at).localeCompare(String(b.sent_at)));
      for (const k of ["discussion", "noting"]) {
        const before = state.agenda[k].map((r: AnyObj) => r.case_id).join(" ");
        let rows = (body[k] ?? []).map((x: string) => byId.get(x)).filter(Boolean).map((r: AnyObj) => ({ ...r, new: false }));
        if ((body.by_urgency ?? []).includes(k)) { rows = urg(rows); state.agenda_order[k] = "urgency"; }
        else if (rows.map((r: AnyObj) => r.case_id).join(" ") !== before && rows.map((r: AnyObj) => r.case_id).join(" ") !== urg(rows).map((r: AnyObj) => r.case_id).join(" ")) state.agenda_order[k] = "hand";
        state.agenda[k] = rows;
      }
      counts();
      return json(route, state);
    }
    if (rest === "/agenda/add" && m === "POST") {
      const row = { ...state.agenda.discussion[state.agenda.discussion.length - 1], case_id: body.case_id, patient_line: "Lakshmi R., 58 F, UHID VXH/2026/000123", urgency: 5, sent_at: sent(1), new: false, presenter: null, presenter_name: "Lakshmi Rao", board_question: "Upfront surgery or neoadjuvant therapy as the board decides", left_before_board: 2 };
      drop(body.case_id);
      state.agenda[body.list === "noting" ? "noting" : "discussion"].unshift(row);
      counts();
      return json(route, state);
    }
    if (rest === "/send-agenda") { state.meeting.agenda_sent_at = new Date().toISOString(); return json(route, { sent_at: state.meeting.agenda_sent_at, sent_to: ["radiology", "pathology", "medical_oncology", "surgical_oncology", "radiation_oncology", "breast_surgery", "gynaecologic_oncology"], cases: 4, new: [] }); }
    if (rest === "/code") { state.code = { value: "482913", expires_at: new Date(Date.now() + 4 * 864e5).toISOString(), attempts: 0 }; return json(route, { value: state.code.value, expires_at: state.code.expires_at }); }
    if (rest === "/start") {
      const next = o.inSession ? o.inSession() : meetingState("in_session");
      for (const k of Object.keys(state)) delete state[k];
      Object.assign(state, next);
      return json(route, { meeting: state.meeting, preparing: 0, current: state.current, view: state.view });
    }
    if (rest === "/cancel") {
      state.meeting.status = "cancelled"; state.status = "cancelled";
      state.meeting.cancelled = { by: "mdt@vxh.example", at: new Date().toISOString(), reason: body?.reason ?? "" };
      state.code = null;
      for (const k of ["discussion", "noting"]) state.agenda[k] = [];
      counts();
      return json(route, { meeting: state.meeting });
    }
    if (rest === "/remind") return json(route, { ok: true });
    return route.fallback();
  });
  return calls;
}

export { CID, MID };
