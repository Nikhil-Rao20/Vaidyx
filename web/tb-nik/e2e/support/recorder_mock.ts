// Routes for the meeting recorder, the discussion notes and the Case File taken up during the meeting (meetings-v2 3.4, 5.1 to 5.3), on
// top of f2.routeMeetings (register after it: Playwright runs the routes registered last first). SYNTHETIC: the notes quote a scripted
// synthetic discussion; no audio is ever kept here either: a posted chunk is read for its speaker, its type and its size, then dropped.
import type { Page, Route } from "@playwright/test";
import { CID, MID, caseFile, routeCaseFile, stepsAfterSend } from "./f2";

type AnyObj = any; // eslint-disable-line @typescript-eslint/no-explicit-any

/** The server's local time without a zone (store.now_iso), in India (the browser runs in Asia/Kolkata, playwright.config.ts). */
const localIso = (d = new Date()) => new Date(d.getTime() + 330 * 60_000).toISOString().slice(0, 19);
const today = localIso().slice(0, 10);
const at = (hm: string) => `${today}T${hm}`;

/** The recorder's view as the server sends it (meeting_notes.recording_view). */
export function recordingView(state: "off" | "on" | "paused", over: Record<string, unknown> = {}) {
  return {
    state, by: state === "off" ? null : "mdt@vxh.example", by_name: state === "off" ? "" : "Priya Nair", started_at: state === "off" ? null : localIso(new Date(Date.now() - 95_000)),
    paused_at: state === "paused" ? localIso() : null, stopped_at: null, chunks: 0, segments: 0,
    label: state === "on" ? "Recording: text only, no audio kept" : state === "paused" ? "Recording paused: text only, no audio kept" : "",
    notice: state === "off" ? "" : "This meeting is being recorded as text (no audio is kept)", ...over,
  };
}

export const NOTES_AT = at("16:42:10");

/** GET /meetings/{mid}/notes: the Case File on the floor with three lines from the synthetic discussion, an AI draft. */
export function meetingNotes(over: Record<string, unknown> = {}) {
  return {
    meeting_id: MID, label: "AI draft, not reviewed", building: [], recording: recordingView("on"),
    cases: [{
      case_id: CID, withheld: false, generated_at: NOTES_AT, model: "gemma-4-31b", model_line: "Written by Gemma-4-31B (non-medical)", segments: 6, dropped: 1,
      dropped_reasons: { quote_not_found: 1 }, review: { status: "draft", by: null, by_name: "", at: null }, label: "AI draft, not reviewed", edits: 0,
      lines: [
        { id: "L1", text: "Radiology noted that the axillary ultrasound shows no suspicious nodes.", edited: null,
          said: { segment_id: "g1", speaker: "shanthi@vxh.example", speaker_name: "Shanthi Raman", at: at("16:31:05"), quote: "the axillary ultrasound shows no suspicious nodes" } },
        { id: "L2", text: "In the room, someone asked whether the final histopathology report is signed.", edited: null,
          said: { segment_id: "g2", speaker: "room", speaker_name: "Board room", at: at("16:33:40"), quote: "is the final histopathology report signed" } },
        { id: "L3", text: "Thomas Joseph asked for the Ki-67 value to be read out.", edited: null,
          said: { segment_id: "g3", speaker: "joseph@vxh.example", speaker_name: "Thomas Joseph", at: at("16:35:12"), quote: "can someone read out the Ki-67 value" } },
      ],
    }],
    ...over,
  };
}

/** A Case File that may be taken up (fixtures.caseList TB-2026-0031), as its agenda row once added. */
export const TAKE_UP = { case_id: "TB-2026-0031", name: "Lakshmi R.", patient_line: "Lakshmi R. (SYNTHETIC), 58 F, UHID VXH/2026/000123" };

export interface RecorderCall { method: string; path: string; body?: AnyObj; speaker?: string; contentType?: string; size?: number }

/** Reads a multipart chunk post: the speaker field, the audio part's type and size (the bytes are not kept). */
function readChunk(buf: Buffer | null): { speaker?: string; contentType?: string; size?: number; startedMs?: string } {
  if (!buf) return {};
  const text = buf.toString("latin1");
  const field = (name: string) => new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r]*)`).exec(text)?.[1];
  const audio = /name="audio"; filename="[^"]*"\r\nContent-Type: ([^\r]+)\r\n\r\n/.exec(text);
  let size: number | undefined;
  if (audio) {
    const start = audio.index + audio[0].length;
    const end = text.indexOf("\r\n--", start);
    size = end > start ? end - start : undefined;
  }
  return { speaker: field("speaker"), startedMs: field("started_ms"), contentType: audio?.[1], size };
}

/** Answers the recorder, the notes, the agenda add and the floor change for MID; returns the calls seen (in order). */
export async function routeRecorder(page: Page, live: { push: (ev: Record<string, unknown>) => void }, state: AnyObj, o: { notes?: AnyObj; transcribe?: { status: number; body: unknown } } = {}) {
  const calls: RecorderCall[] = [];
  const notes: AnyObj = o.notes ?? meetingNotes();
  // the Board view of the Case File taken up (the same synthetic fixture under its own patient)
  const cf: AnyObj = caseFile();
  cf.case.case_id = TAKE_UP.case_id;
  cf.case.patient = { ...cf.case.patient, name: "Lakshmi R. (SYNTHETIC)", agesex: "58 Y / F", mrn: "VXH/2026/000123", ids: [{ kind: "uhid", value: "VXH/2026/000123", from: "his" }] };
  const st: AnyObj = stepsAfterSend();
  st.case_id = TAKE_UP.case_id;
  await routeCaseFile(page, { caseId: TAKE_UP.case_id, caseFile: cf, steps: st });

  await page.route(new RegExp(`/api/tb/meetings/${MID}/(recording|transcribe|notes|agenda/add|current|cases/[^/]+/notes/.+)$`), async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    const p = url.pathname.replace(`/api/tb/meetings/${MID}`, "");
    const m = req.method();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    const body = (() => { try { return req.postDataJSON(); } catch { return undefined; } })();
    if (p === "/recording" && m === "POST") {
      calls.push({ method: m, path: p, body });
      const cur = state.recording?.state ?? "off";
      const next = ({ start: cur === "off" ? "on" : null, pause: cur === "on" ? "paused" : null, resume: cur === "paused" ? "on" : null, stop: cur === "off" ? null : "off" } as Record<string, string | null>)[body?.action];
      if (!next) return json({ detail: { message: "The recorder is not on.", code: "bad_state" } }, 409);
      state.recording = recordingView(next as "off" | "on" | "paused", { started_at: cur === "off" ? localIso() : state.recording?.started_at ?? null });
      live.push({ type: "recording", recording: state.recording });
      return json({ recording: state.recording });
    }
    if (p === "/transcribe" && m === "POST") {
      const c = readChunk(req.postDataBuffer());
      calls.push({ method: m, path: p, speaker: c.speaker, contentType: c.contentType, size: c.size });
      if (o.transcribe) return json(o.transcribe.body, o.transcribe.status);
      if (state.recording?.state !== "on") return json({ detail: { message: "The recorder is not on.", code: "not_recording" } }, 409);
      return json({ stored: true, seconds: 3.1, segment: { id: `g${calls.length}`, at: localIso(), speaker: c.speaker, speaker_name: c.speaker === "room" ? "Board room" : c.speaker, case_id: state.current?.case_id ?? null, chars: 42 } });
    }
    if (p === "/notes" && m === "GET") { calls.push({ method: m, path: p }); return json(notes); }
    const line = /^\/cases\/([^/]+)\/notes\/lines\/([^/]+)$/.exec(p);
    if (line && m === "PUT") {
      calls.push({ method: m, path: p, body });
      const cn = notes.cases.find((x: AnyObj) => x.case_id === decodeURIComponent(line[1]));
      const ln = cn?.lines.find((x: AnyObj) => x.id === decodeURIComponent(line[2]));
      if (!ln) return json({ detail: { message: "That note line was not found.", code: "no_line" } }, 404);
      ln.text = body.text;
      ln.edited = { by: "mdt@vxh.example", by_name: "Priya Nair", at: localIso(), checked: true };
      cn.edits += 1;
      live.push({ type: "notes", case_id: cn.case_id, lines: cn.lines.length, generated_at: cn.generated_at, review: cn.review.status });
      return json(ln);
    }
    const review = /^\/cases\/([^/]+)\/notes\/review$/.exec(p);
    if (review && m === "POST") {
      calls.push({ method: m, path: p, body });
      const cn = notes.cases.find((x: AnyObj) => x.case_id === decodeURIComponent(review[1]));
      const d = new Date();
      cn.review = { status: body.status, by: "mdt@vxh.example", by_name: "Priya Nair", at: localIso(d) };
      cn.label = body.status === "reviewed" ? `AI notes, reviewed by Priya Nair on ${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}` : "AI draft, not reviewed";
      live.push({ type: "notes", case_id: cn.case_id, lines: cn.lines.length, generated_at: cn.generated_at, review: body.status });
      return json(cn);
    }
    if (p === "/agenda/add" && m === "POST") {
      calls.push({ method: m, path: p, body });
      const lists = state.agenda;
      for (const k of ["discussion", "noting", "not_ready"]) lists[k] = lists[k].filter((r: AnyObj) => r.case_id !== body.case_id);
      lists.discussion.push({ case_id: body.case_id, patient_line: body.case_id === TAKE_UP.case_id ? TAKE_UP.patient_line : body.case_id, protocol: "breast", owner_name: "Lakshmi Rao", owner_department: "breast_surgery",
        owner_department_name: "Breast Surgery", presenter_name: "Lakshmi Rao", board_question: "Primary management plan", left_before_board: 2, minutes: 10, order: lists.discussion.length + 1, reason: body.reason ?? "",
        ready: false, status: "waiting", ended: false, outcome: null, outcome_label: "", added_after_send: true, urgency: 5 });
      live.push({ type: "agenda", agenda: lists, counts: { discussion: lists.discussion.length, noting: lists.noting.length, not_ready: lists.not_ready.length } });
      return json(state);
    }
    if (p === "/current" && m === "POST") {
      calls.push({ method: m, path: p, body });
      state.current = { ...state.current, case_id: body.case_id, opened: null, timer: { seconds_left: 600, running: true, total: 600 }, presenter: { user: "rao@vxh.example", name: "Lakshmi Rao", department: "breast_surgery", department_name: "Breast Surgery" }, elapsed_seconds: 0 };
      state.view = { case_id: body.case_id, tab: "summary", doc_id: null, page: null, quote: "", opened: null, by: "mdt@vxh.example", by_name: "Priya Nair", at: new Date().toISOString() };
      live.push({ type: "current", case_id: body.case_id, slide: 0, opened: null, timer: state.current.timer, presenter: state.current.presenter, elapsed_seconds: 0 });
      live.push({ type: "view", view: state.view });
      return json({ ok: true });
    }
    return route.fallback();
  });
  return { calls, notes };
}
