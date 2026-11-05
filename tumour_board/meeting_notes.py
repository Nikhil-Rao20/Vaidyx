"""The meeting recorder that keeps no audio and the AI notes per Case File (meetings-v2 items 5.1 and 5.3; owner decisions D11 to D13,
technical decisions T3 and T4; spec docs/meetings-v2/research/07_phase5_spec.md).

Recorder (5.1). The MDT Coordinator starts, pauses, resumes and stops it while the meeting is in session; the state lives in the meeting
record as `recording = {state: off|on|paused, by, by_name, started_at, started_by, paused_at, resumed_at, stopped_at, chunks, segments,
last_chunk_at}`, each change audited (recording_started, _paused, _resumed, _stopped) and sent on the meeting socket as
{"type": "recording", "recording": recording_view(s)}. The coordinator's browser posts chunks of about 20 s per audio track; each chunk is
passed IN MEMORY to the audio service (audio_proxy.transcribe: English, the token read in code) and dropped. NO AUDIO IS EVER WRITTEN:
no file, no temporary file, nothing in the meeting record. Only the text is kept, one JSON line per segment in the meeting's transcript
file next to its session file (sessions/<mid>.transcript.jsonl, mode 600): {id, at, started_ms, speaker, speaker_name, case_id, text},
case_id being the Case File on the floor when the chunk arrived. An empty or failed transcription stores nothing. Nothing serves the
transcript as a whole: one segment's words are served only as the "said" of a note line, to a member of that meeting.

Notes (5.3). build_notes(mid, case_id) gives that Case File's segments, in the order spoken, with the speakers, to the reasoner
(Gemma-4-31B, non-medical) and keeps only the lines that pass every check (verify_lines): the segment exists for that Case File, the
quote is in its text word for word (whitespace and case relaxed only) and long enough to stand for it, every number of the line is in the
quote, every capitalised name or term of the line's own words is in the quote or is the speaker's name or department (so a line cannot
put words in another person's or department's mouth), and the advice guardrail (guardrails.scan_output) finds nothing in the line's own
words outside its quote: Vaidyx never advises, diagnoses or stages in its own voice; what a doctor said stays attributed to them behind
the "said" chip. A line that fails is dropped and counted by reason. Stored per Case File in the meeting record:
notes[case_id] = {lines: [{id, text, said: {segment_id, speaker, speaker_name, at, quote}, edited?}], model, model_line, generated_at,
trigger, signature, segments, dropped, dropped_reasons, review: {status: draft|reviewed, by, by_name, at}, reviews[], edits[]}, labelled
"AI draft, not reviewed". The coordinator may edit a line (shown as edited by them; the "said" stays) and mark the notes reviewed; a
rebuild carries the edited lines forward and puts the review back to draft (the earlier review stays in reviews[]).

Every write is a fresh read-modify-write of the meeting record (meetings.need, then meetings._save with no await in between), so a copy
is never held across a model or audio-service call (code review finding 1). The hooks the meeting code calls: on_case_ended,
on_meeting_ended, recording_view (see each docstring)."""
import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime

from . import audio_proxy as ap
from . import board, config, grounding, guardrails, llm, meetings, org, store

log = logging.getLogger(__name__)

MeetingError = meetings.MeetingError

STATES = ("off", "on", "paused")
ACTIONS = {"start": (("off",), "on"), "pause": (("on",), "paused"), "resume": (("paused",), "on"), "stop": (("on", "paused"), "off")}
AUDIT_KINDS = {"start": "recording_started", "pause": "recording_paused", "resume": "recording_resumed", "stop": "recording_stopped"}
REFUSED = {"start": "The recorder is already on or paused.", "pause": "The recorder is not on.", "resume": "The recorder is not paused.",
           "stop": "The recorder is not on."}
BADGE = "Recording: text only, no audio kept"
PAUSED_BADGE = "Recording paused: text only, no audio kept"
JOIN_NOTICE = "This meeting is being recorded as text (no audio is kept)"
ROOM = "room"
ROOM_NAME = "Board room"

MAX_AUDIO_BYTES = ap.STT_MAX_BYTES            # 4 MiB, the audio service's own cap
MAX_SECONDS = ap.LIMITS["stt_seconds"]        # 60 s
MAX_SEGMENT_CHARS = 4000                      # one chunk of about 20 s is a few hundred characters

DRAFT_LABEL = "AI draft, not reviewed"
REVIEW_STATUSES = ("draft", "reviewed")
MAX_LINE = 300          # characters of a note line (model or coordinator)
MAX_QUOTE = 600         # characters of a quote
MIN_QUOTE_WORDS = 3     # unless the quote is the whole segment
MAX_LINES = 60          # lines kept per Case File
CONTEXT_BUDGET = 40000  # characters of transcript per model call; a longer discussion goes in parts
DROP_REASONS = {"empty": "no text or no quote", "too_long": "the line or its quote is too long", "no_segment": "the segment is not one of this Case File's",
                "quote_not_found": "the quote is not word for word in the segment", "quote_too_short": "the quote is too short to stand for the segment",
                "numbers": "a number of the line is not in its quote", "names": "a name or term of the line is not in its quote and is not the speaker's",
                "advice": "advice, diagnosis or stage in Vaidyx's own words", "duplicate": "the same quote twice", "too_many": "more lines than are kept"}

SYSTEM = (
    "You take the discussion notes of a hospital Tumour Board meeting for one Case File. You are given the transcript of what was said "
    "while that Case File was on the floor, cut into segments, each with its id, the time and the speaker. You write short note lines of "
    "what people said and asked. You are a note taker: you never decide, advise, diagnose, stage, judge or conclude anything yourself.\n\n"
    "Rules for every line:\n"
    "1. One line reports one segment. Give that segment's id in segment_id.\n"
    "2. quote: copy a part of that segment's text word for word (the same words in the same order, nothing added and nothing left out in "
    "between), at least three words and at most forty: the part that shows what the line reports.\n"
    "3. text: one short sentence that says who said or asked what, for example \"Radiology noted the size of the mass in the CT report.\" "
    "or \"The board asked Pathology to review the margins.\" or \"Dr Rao asked whether the PET-CT report is signed.\"\n"
    "4. Name the speaker as the segment gives it (the person's name or department). A segment from the Board room microphone has no known "
    "speaker: write \"In the room, it was said that ...\" or \"In the room, someone asked ...\", and name a person or department only when "
    "the quote itself names them.\n"
    "5. Use only plain reporting verbs: said, noted, asked, reported, raised, mentioned, agreed, read out, gave their view. Never write in "
    "your own words that something is recommended, advised, indicated, suitable, needed, likely, best or should be done; when a speaker "
    "said such a thing, write that they gave their view and let the quote carry their exact words.\n"
    "6. Never add a fact, number, date, name, drug, stage, diagnosis or decision that is not in the quote. Write a number only exactly as "
    "the quote has it.\n"
    "7. Skip greetings, small talk and anything not about this Case File. If nothing about the Case File was said, return an empty list.\n"
    "8. Plain English. No em dashes. Do not write the patient's name.")
SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "lines": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "text": {"type": "string"}, "segment_id": {"type": "string"}, "quote": {"type": "string"}},
        "required": ["text", "segment_id", "quote"]}}},
    "required": ["lines"]}


def _now() -> str:
    return store.now_iso()


def _fold(s) -> str:
    return " ".join(str(s if s is not None else "").split())


def _dmy(iso) -> str:
    return board._ddmmyyyy(str(iso or "")[:10]) if iso else ""


def _name(user) -> str:
    try:
        return meetings.display_name(user) or str(user or "")
    except Exception:
        return str(user or "")


# ---- the recorder ----------------------------------------------------------------------------------------------------------------

def _rec(s: dict) -> dict:
    r = s.get("recording") if isinstance(s.get("recording"), dict) else {}
    r = dict(r)
    if r.get("state") not in STATES:
        r["state"] = "off"
    return r


def recording_view(s: dict) -> dict:
    """What every screen shows (the meeting view and the socket event): {state, by, by_name, started_at, paused_at, stopped_at, chunks,
    segments, label, notice}. A meeting that is not in session never shows the recorder on (a stale state after an end the hook missed)."""
    r = _rec(s or {})
    state = r["state"] if (s or {}).get("status") == "in_session" else "off"
    return {"state": state, "by": r.get("by") or None, "by_name": r.get("by_name") or "", "started_at": r.get("started_at"),
            "paused_at": r.get("paused_at") if state == "paused" else None, "stopped_at": r.get("stopped_at"),
            "chunks": int(r.get("chunks") or 0), "segments": int(r.get("segments") or 0),
            "label": BADGE if state == "on" else PAUSED_BADGE if state == "paused" else "",
            "notice": JOIN_NOTICE if state in ("on", "paused") else ""}


def set_recording(mid: str, by: str, action: str, reason: str = "") -> dict:
    """start (off to on), pause (on to paused), resume (paused to on), stop (on or paused to off). Start, pause and resume only while the
    meeting is in session; stop whenever the recorder is on or paused (stopping is always safe). Audited; sent on the socket. The route
    checks that `by` is the MDT Coordinator. Returns recording_view."""
    if action not in ACTIONS:
        raise MeetingError("The action must be start, pause, resume or stop.", 400, "bad_action")
    s = meetings.need(mid)
    if action != "stop" and s.get("status") != "in_session":
        raise MeetingError("The recorder works only while the meeting is in session.", 409, "not_in_session")
    r = _rec(s)
    allowed, nxt = ACTIONS[action]
    if r["state"] not in allowed:
        raise MeetingError(REFUSED[action], 409, "bad_state")
    now = _now()
    r.update(state=nxt, by=by, by_name=_name(by), changed_at=now)
    if action == "start":
        r.update(started_at=now, started_by=by, paused_at=None, resumed_at=None, stopped_at=None)
    elif action == "pause":
        r["paused_at"] = now
    elif action == "resume":
        r.update(paused_at=None, resumed_at=now)
    else:
        r.update(stopped_at=now, paused_at=None)
    s["recording"] = r
    meetings._save(s)
    board.audit_event(s["id"], AUDIT_KINDS[action], by, **({"reason": reason} if reason else {}))
    view = recording_view(s)
    meetings._send(s, {"type": "recording", "recording": view})
    return view


def recording_on(s: dict) -> None:
    """The chunk route's state check: the meeting in session and the recorder on (paused takes no chunk)."""
    if s.get("status") != "in_session":
        raise MeetingError("The recorder works only while the meeting is in session.", 409, "not_in_session")
    if _rec(s)["state"] != "on":
        raise MeetingError("The recorder is not on.", 409, "not_recording")


def speaker_of(s: dict, speaker) -> dict:
    """{speaker, speaker_name, department}: `room` (the coordinator's laptop microphone, the Board room), or a login admitted to this
    meeting (present or remote); anything else is refused."""
    sp = str(speaker or "").strip()
    if sp == ROOM:
        return {"speaker": ROOM, "speaker_name": ROOM_NAME, "department": ""}
    p = (s.get("people") or {}).get(sp)
    if not sp or not isinstance(p, dict) or p.get("status") not in meetings.ADMITTED:
        raise MeetingError("The speaker must be the Board room or a member admitted to this meeting.", 400, "bad_speaker")
    dept = str(p.get("department") or "")
    return {"speaker": sp, "speaker_name": str(p.get("name") or "") or _name(sp), "department": dept,
            "outside_expert": bool(p.get("outside_expert"))}


def _started_ms(v):
    """The client's time of the chunk's start (milliseconds since 1970), or None."""
    if v in (None, "") or isinstance(v, bool):
        return None
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 10 ** 14 else None


# ---- the transcript (text only, mode 600, never served whole) ----------------------------------------------------------------------

_file_lock = threading.Lock()


def transcript_path(mid: str):
    """Next to the meeting's own session file: sessions/<mid>.transcript.jsonl (board.all_sessions reads S*.json only)."""
    return board.sessions_dir() / f"{store.safe_id(mid)}.transcript.jsonl"


def _append(mid: str, seg: dict) -> None:
    p = transcript_path(mid)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(seg, ensure_ascii=False) + "\n").encode("utf-8")
    with _file_lock:
        fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.fchmod(fd, 0o600)
            os.write(fd, line)
        finally:
            os.close(fd)


def _order_key(seg: dict):
    ms = seg.get("started_ms")
    if isinstance(ms, int) and not isinstance(ms, bool):
        return (ms, str(seg.get("at") or ""))
    try:
        return (int(datetime.fromisoformat(str(seg.get("at") or "")).timestamp() * 1000), str(seg.get("at") or ""))
    except ValueError:
        return (0, str(seg.get("at") or ""))


def segments(mid: str, case_id: str | None = None) -> list[dict]:
    """The stored segments of the meeting (of one Case File when given), in the order spoken (the client's start time, else arrival).
    For this module only: nothing serves this list."""
    try:
        raw = transcript_path(mid).read_text(encoding="utf-8")
    except (FileNotFoundError, ValueError):
        return []
    out = []
    for ln in raw.splitlines():
        try:
            x = json.loads(ln)
        except ValueError:
            continue
        if isinstance(x, dict) and x.get("id") and isinstance(x.get("text"), str) and (case_id is None or x.get("case_id") == case_id):
            out.append(x)
    out.sort(key=_order_key)
    return out


async def transcribe_chunk(mid: str, by: str, audio: bytes, content_type: str, speaker, started_ms=None) -> dict:
    """One chunk of one audio track: checked (in session, recorder on, a known speaker), passed in memory to the audio service, dropped.
    The Case File on the floor is taken when the chunk arrives. Text stored as one segment; empty text (or no speech) stores nothing; a
    refusal or failure of the service stores nothing (MeetingError with the app's message). Audited without the text. Returns
    {stored, segment: {id, at, speaker, speaker_name, case_id, chars} | None, seconds}; never the words."""
    if not audio:
        raise MeetingError("The recording is empty.", 400, "bad_request")
    if len(audio) > MAX_AUDIO_BYTES:
        raise MeetingError(ap.TOO_BIG, 413, "too_big")
    s = meetings.need(mid)
    recording_on(s)
    who = speaker_of(s, speaker)
    case_id = str(s.get("current") or "")
    ms = _started_ms(started_ms)
    t0 = time.time()
    try:
        out = await ap.transcribe(audio, content_type or "", "whisper", "")
    except ap.ServiceError as e:
        status, message, code = ap.error_for(e.status, e.code)
        board.audit_event(mid, "recording_chunk_failed", by, speaker=who["speaker"], code=code)
        raise MeetingError(message, status, code)
    seconds = out.get("duration")
    seconds = round(float(seconds), 1) if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) else None
    if seconds is not None and seconds > MAX_SECONDS:
        board.audit_event(mid, "recording_chunk_failed", by, speaker=who["speaker"], code="too_long", seconds=seconds)
        raise MeetingError(ap.TOO_LONG, 413, "too_long")
    text = _fold(out.get("text"))[:MAX_SEGMENT_CHARS]
    if out.get("code") == "no_speech":
        text = ""
    seg = None
    if text:
        seg = {"id": "g" + uuid.uuid4().hex[:10], "at": _now(), "started_ms": ms, "speaker": who["speaker"], "speaker_name": who["speaker_name"],
               "department": who["department"], "case_id": case_id or None, "text": text}
        _append(mid, seg)
    s = meetings.need(mid)  # read again after the await, change only the counters
    r = _rec(s)
    r["chunks"] = int(r.get("chunks") or 0) + 1
    r["segments"] = int(r.get("segments") or 0) + (1 if seg else 0)
    r["last_chunk_at"] = _now()
    s["recording"] = r
    meetings._save(s)
    board.audit_event(mid, "recording_chunk", by, speaker=who["speaker"], case_id=case_id or None, seconds=seconds, chars=len(text),
                      stored=bool(seg), took_ms=int((time.time() - t0) * 1000))
    return {"stored": bool(seg), "seconds": seconds,
            "segment": {k: seg[k] for k in ("id", "at", "speaker", "speaker_name", "case_id")} | {"chars": len(text)} if seg else None}


# ---- the notes: checks ---------------------------------------------------------------------------------------------------------------

_MARKS = re.compile(r"[\"“”‘’`]")
_CAPS = re.compile(r"\b[A-Z][A-Za-z0-9+\-/]*")
_ALLOWED_CAPS = {"the", "in", "a", "an", "it", "they", "he", "she", "there", "this", "that", "both", "all", "someone", "members", "member",
                 "board", "tumour", "mdt", "coordinator", "room", "dr", "doctor", "prof", "professor", "i"}


def _relaxed(s) -> str:
    """Whitespace and case relaxed only (the spec's quote rule)."""
    return _fold(s).casefold()


def own_words(text: str, quote: str) -> str:
    """The line's own words: its text with the quote taken out (guardrails.outside_quotes) and every quotation mark removed, so a span
    the model put in quotation marks that is not the verified quote is still checked."""
    return _fold(_MARKS.sub(" ", guardrails.outside_quotes(text, [quote])))


def _speaker_pool(seg: dict) -> str:
    """The speaker's name, and the name and aliases of the speaker's department (Radiology, Radio-diagnosis, Imaging)."""
    dept = str(seg.get("department") or "")
    d = org.department(dept) if dept else None
    names = [str(seg.get("speaker_name") or ""), dept.replace("_", " ")]
    if isinstance(d, dict):
        names += [str(d.get("name") or "")] + [str(a) for a in d.get("aliases") or []]
    return " ".join(x for x in names if x)


def _names_ok(own: str, quote: str, seg: dict) -> bool:
    """Every capitalised word of the line's own words (a name, a department, a marker, a test), the first word included, was said in
    that segment (its quote or the rest of what the speaker said there) or is the speaker's name or department; a few plain words (The,
    In, Board, Dr ...) excepted. So "Pathology noted ..." on a segment Radiology spoke is dropped, and so is a marker or test nobody said.
    An acronym also matches with the spaces and stops speech to text put in it ("MR, I" for MRI). (The evaluation of 2 Nov: lines naming
    the MRI were dropped because the model's shorter quote left the word out.)"""
    said = quote + " " + str(seg.get("text") or "")
    pool = grounding.norm(said + " " + _speaker_pool(seg))
    compact = re.sub(r"[^a-z0-9]", "", said.lower())
    for m in _CAPS.finditer(own):
        w = m.group(0)
        if w.lower() in _ALLOWED_CAPS:
            continue
        if grounding.norm(w) in pool:
            continue
        if w.isupper() and len(w) >= 2 and re.sub(r"[^a-z0-9]", "", w.lower()) in compact:
            continue
        return False
    return True


def _numbers_ok(text: str, quote: str) -> bool:
    have = set(grounding.numbers(quote))
    return all(n in have for n in grounding.numbers(text))


def check_line(item, segs_by_id: dict) -> tuple[dict | None, str]:
    """One model line: (the line to keep, "") or (None, the reason it is dropped). See the module docstring for the checks."""
    if not isinstance(item, dict):
        return None, "empty"
    text = _fold(str(item.get("text") or "").replace("—", "-").replace("–", "-"))
    quote = _fold(item.get("quote"))
    sid = str(item.get("segment_id") or "").strip()
    if not text or not quote:
        return None, "empty"
    if len(text) > MAX_LINE or len(quote) > MAX_QUOTE:
        return None, "too_long"
    seg = segs_by_id.get(sid)
    if not seg:
        return None, "no_segment"
    seg_text = _relaxed(seg.get("text"))
    if _relaxed(quote) not in seg_text:
        return None, "quote_not_found"
    if len(re.findall(r"\w+", quote)) < MIN_QUOTE_WORDS and _relaxed(quote) != seg_text:
        return None, "quote_too_short"
    if not _numbers_ok(text, quote):
        return None, "numbers"
    own = own_words(text, quote)
    if not _names_ok(own, quote, seg):
        return None, "names"
    if guardrails.scan_output(own):
        return None, "advice"
    return {"id": "n" + uuid.uuid4().hex[:8], "text": text,
            "said": {"segment_id": sid, "speaker": seg.get("speaker"), "speaker_name": seg.get("speaker_name") or "", "at": seg.get("at"),
                     "started_ms": seg.get("started_ms"), "department": seg.get("department") or "", "quote": quote}}, ""


def verify_lines(items, segs: list[dict]) -> tuple[list[dict], dict]:
    """The lines that pass, in the order spoken, and the dropped ones counted by reason."""
    by_id = {x["id"]: x for x in segs}
    place = {x["id"]: i for i, x in enumerate(segs)}
    keep, dropped, seen = [], {}, set()
    for i, item in enumerate(items or []):
        line, why = check_line(item, by_id)
        if line:
            key = (line["said"]["segment_id"], _relaxed(line["said"]["quote"]))
            if key in seen:
                line, why = None, "duplicate"
            else:
                seen.add(key)
        if not line:
            dropped[why] = dropped.get(why, 0) + 1
            continue
        keep.append((place[line["said"]["segment_id"]], i, line))
    keep.sort(key=lambda t: (t[0], t[1]))
    lines = [t[2] for t in keep]
    if len(lines) > MAX_LINES:
        dropped["too_many"] = len(lines) - MAX_LINES
        lines = lines[:MAX_LINES]
    return lines, dropped


# ---- the notes: the model ------------------------------------------------------------------------------------------------------------

def _clock(seg: dict) -> str:
    ms = seg.get("started_ms")
    if isinstance(ms, int) and not isinstance(ms, bool):
        try:
            return datetime.fromtimestamp(ms / 1000).strftime("%H:%M:%S")
        except (OverflowError, OSError, ValueError):
            pass
    return str(seg.get("at") or "")[11:19]


def _speaker_label(seg: dict) -> str:
    if seg.get("speaker") == ROOM:
        return "Board room microphone (speaker not known)"
    dept = str(seg.get("department") or "")
    return f"{seg.get('speaker_name') or seg.get('speaker')}" + (f" ({org.department_name(dept)})" if dept else "")


def _batches(segs: list[dict]) -> list[list[dict]]:
    out, cur, n = [], [], 0
    for x in segs:
        size = len(x.get("text") or "") + 80
        if cur and n + size > CONTEXT_BUDGET:
            out.append(cur)
            cur, n = [], 0
        cur.append(x)
        n += size
    if cur:
        out.append(cur)
    return out


def messages(s: dict, case_id: str, segs: list[dict], part: int = 1, parts: int = 1) -> list[dict]:
    rows = "\n".join(f"[{x['id']}] {_clock(x)}, {_speaker_label(x)}: {x.get('text')}" for x in segs)
    where = f" (part {part} of {parts} of the discussion)" if parts > 1 else ""
    user = (f"Case File {case_id}, Tumour Board meeting of {_dmy(s.get('date'))}.\n\nTRANSCRIPT{where}, {len(segs)} segments in the order "
            f"spoken:\n{rows}\n\nWrite the note lines for this Case File.")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def model_label() -> str:
    return config.models().get("reasoner", {}).get("label") or "the reasoner model"


def signature(segs: list[dict]) -> str:
    return f"{len(segs)}:{segs[-1]['id']}" if segs else "0:"


def _carry(old: dict | None, lines: list[dict], segs: list[dict]) -> list[dict]:
    """The coordinator's edited lines survive a rebuild: a new line with the same "said" takes the edited text; an edited line the model
    did not write again stays (its segment is never removed). In the order spoken."""
    edited = [x for x in ((old or {}).get("lines") or []) if isinstance(x, dict) and x.get("edited")]
    if not edited:
        return lines
    key = lambda ln: (ln["said"]["segment_id"], _relaxed(ln["said"]["quote"]))  # noqa: E731
    by_key = {key(x): x for x in edited}
    out, used = [], set()
    for ln in lines:
        k = key(ln)
        if k in by_key:
            out.append(by_key[k]); used.add(k)
        else:
            out.append(ln)
    out += [x for x in edited if key(x) not in used]
    place = {x["id"]: i for i, x in enumerate(segs)}
    return sorted(out, key=lambda ln: place.get(ln["said"]["segment_id"], len(place)))


async def build_notes(mid: str, case_id: str, by: str = "", trigger: str = "on_demand") -> dict:
    """Write (again) the notes of one Case File of this meeting from its segments. Returns notes_view of the stored notes, or
    {"status": "nothing_recorded"} when no segment was stored for it (nothing saved). The model is called with no meeting record held;
    the result is saved by a fresh read-modify-write. llm.LLMError propagates (the old notes stay)."""
    if case_id in config.BOARD_HIDDEN:
        raise MeetingError("Notes are never written for a protected Case File.", 403, "protected")
    s = meetings.need(mid)
    segs = segments(mid, case_id)
    if not segs:
        return {"case_id": case_id, "status": "nothing_recorded", "lines": []}
    by = by or meetings.AUTOMATIC

    def au(ev):
        board.audit_session(mid, {**ev, "case_id": case_id, "purpose": "meeting notes"})
    items = []
    groups = _batches(segs)
    for i, group in enumerate(groups):
        out = await llm.chat("reasoner", messages(s, case_id, group, i + 1, len(groups)), json_schema=SCHEMA, max_tokens=2500,
                             purpose="meeting notes", audit=au)
        got = out.get("lines") if isinstance(out, dict) else None
        items += [x for x in got or [] if isinstance(x, dict)]
    lines, dropped = verify_lines(items, segs)
    label = model_label()
    s = meetings.need(mid)  # read again after the model calls: only notes[case_id] changes
    notes = s.get("notes") if isinstance(s.get("notes"), dict) else {}
    old = notes.get(case_id) if isinstance(notes.get(case_id), dict) else None
    lines = _carry(old, lines, segs)
    reviews = list((old or {}).get("reviews") or [])
    entry = {"lines": lines, "model": label, "model_line": f"Written by {board.model_words(label)}", "generated_at": _now(), "trigger": trigger,
             "built_by": by, "signature": signature(segs), "segments": len(segs), "dropped": sum(dropped.values()), "dropped_reasons": dropped,
             "review": {"status": "draft", "by": None, "by_name": "", "at": None}, "reviews": reviews, "edits": list((old or {}).get("edits") or [])}
    notes[case_id] = entry
    s["notes"] = notes
    meetings._save(s)
    board.audit_event(mid, "notes_built", by, case_id, "notes_built", lines=len(lines), dropped=entry["dropped"], segments=len(segs), trigger=trigger)
    meetings._send(s, {"type": "notes", "case_id": case_id, "lines": len(lines), "generated_at": entry["generated_at"], "review": "draft"})
    _summary_after_board(mid, case_id, by, "notes_built")
    return {"case_id": case_id, "status": "built", **notes_view(entry)}


def _summary_after_board(mid: str, case_id: str, by: str, why: str) -> None:
    """The summary after the board cites these notes (item 5.4): it is written again in the background (case_summary.on_notes_changed,
    which never raises)."""
    from . import case_summary
    case_summary.on_notes_changed(mid, case_id, by, why)


# ---- edit and review (the coordinator) -------------------------------------------------------------------------------------------------

def _entry(s: dict, case_id: str) -> dict:
    e = (s.get("notes") or {}).get(case_id) if isinstance(s.get("notes"), dict) else None
    if not isinstance(e, dict):
        raise MeetingError("There are no notes for this Case File in this meeting.", 404, "no_notes")
    return e


def edit_line(mid: str, case_id: str, line_id: str, text, by: str) -> dict:
    """The coordinator changes one line's text; the "said" stays. Kept as edited by them (`edited.checked`: every number and name of the
    new text is still in the quote); back to the Vaidyx text clears the mark. Every edit is kept in edits[]. Audited (no text)."""
    text = _fold(str(text or "").replace("—", "-").replace("–", "-"))
    if not 1 <= len(text) <= MAX_LINE:
        raise MeetingError(f"Write the line (1 to {MAX_LINE} characters).", 400, "bad_text")
    s = meetings.need(mid)
    e = _entry(s, case_id)
    line = next((x for x in e.get("lines") or [] if isinstance(x, dict) and x.get("id") == line_id), None)
    if line is None:
        raise MeetingError("That note line was not found.", 404, "no_line")
    prev = line.get("text") or ""
    if text == prev:
        return line_view(line)
    ed = line.get("edited") if isinstance(line.get("edited"), dict) else {}
    vaidyx_text = ed.get("vaidyx_text") or prev
    now = _now()
    if text == vaidyx_text:
        line.pop("edited", None)
    else:
        quote = str((line.get("said") or {}).get("quote") or "")
        checked = _numbers_ok(text, quote) and _names_ok(own_words(text, quote), quote, line.get("said") or {})
        line["edited"] = {"by": by, "by_name": _name(by), "at": now, "vaidyx_text": vaidyx_text, "checked": bool(checked)}
    line["text"] = text
    e.setdefault("edits", []).append({"line_id": line_id, "text": text, "previous": prev, "by": by, "at": now})
    meetings._save(s)
    board.audit_event(mid, "notes_line_edited", by, case_id, "notes_line_edited", line_id=line_id, chars=len(text))
    meetings._send(s, {"type": "notes", "case_id": case_id, "lines": len(e.get("lines") or []), "generated_at": e.get("generated_at"),
                       "review": (e.get("review") or {}).get("status") or "draft"})
    _summary_after_board(mid, case_id, by, "notes_line_edited")
    return line_view(line)


def review(mid: str, case_id: str, status, by: str) -> dict:
    """The coordinator marks the notes reviewed (or back to draft). Kept in review and reviews[]; audited."""
    if status not in REVIEW_STATUSES:
        raise MeetingError("The review status must be reviewed or draft.", 400, "bad_status")
    s = meetings.need(mid)
    e = _entry(s, case_id)
    rv = {"status": status, "by": by, "by_name": _name(by), "at": _now(), "generated_at": e.get("generated_at")}
    e["review"] = rv
    e.setdefault("reviews", []).append(rv)
    meetings._save(s)
    board.audit_event(mid, "notes_reviewed" if status == "reviewed" else "notes_review_cleared", by, case_id, "notes_reviewed", status=status)
    meetings._send(s, {"type": "notes", "case_id": case_id, "lines": len(e.get("lines") or []), "generated_at": e.get("generated_at"), "review": status})
    return notes_view(e)


# ---- views -----------------------------------------------------------------------------------------------------------------------------

def line_view(line: dict) -> dict:
    said = line.get("said") or {}
    ed = line.get("edited") if isinstance(line.get("edited"), dict) else None
    return {"id": line.get("id"), "text": line.get("text") or "",
            "said": {k: said.get(k) for k in ("segment_id", "speaker", "speaker_name", "at", "quote")},
            "edited": {k: ed.get(k) for k in ("by", "by_name", "at", "checked")} if ed else None}


def notes_view(e: dict) -> dict:
    rv = e.get("review") if isinstance(e.get("review"), dict) else {"status": "draft"}
    reviewed = rv.get("status") == "reviewed"
    return {"lines": [line_view(x) for x in e.get("lines") or [] if isinstance(x, dict)], "generated_at": e.get("generated_at"),
            "model": e.get("model") or "", "model_line": e.get("model_line") or "", "segments": int(e.get("segments") or 0),
            "dropped": int(e.get("dropped") or 0), "dropped_reasons": dict(e.get("dropped_reasons") or {}),
            "review": {k: rv.get(k) for k in ("status", "by", "by_name", "at")},
            "label": f"AI notes, reviewed by {rv.get('by_name') or rv.get('by')} on {_dmy(rv.get('at'))}" if reviewed else DRAFT_LABEL,
            "edits": len(e.get("edits") or [])}


def _agenda_order(s: dict) -> list[str]:
    lists = s.get("agenda_lists") or {}
    out = []
    for k in ("discussion", "noting", "not_ready"):
        for it in lists.get(k) or []:
            cid = (it or {}).get("case_id")
            if cid and cid not in out:
                out.append(cid)
    return out


WITHHELD_NOTE = "Withheld: the patient has not consented to an outside discussion."


def meeting_view(s: dict, r: dict) -> dict:
    """GET /meetings/{mid}/notes for a member (the route checks): every Case File's notes in agenda order, with the "said" words. An
    outside expert gets a Case File's notes only with the owner's recorded consent to an outside discussion (security review #9)."""
    notes = s.get("notes") if isinstance(s.get("notes"), dict) else {}
    order = [c for c in _agenda_order(s) if c in notes] + sorted(c for c in notes if c not in _agenda_order(s))
    cases = []
    for cid in order:
        e = notes.get(cid)
        if not isinstance(e, dict):
            continue
        if r.get("outside_expert") and not meetings.manage(r):
            c = store.get_case(cid) if cid not in config.BOARD_HIDDEN else None
            if not c or meetings.outside_view(r, c):
                cases.append({"case_id": cid, "withheld": True, "note": WITHHELD_NOTE})
                continue
        cases.append({"case_id": cid, "withheld": False, **notes_view(e)})
    return {"meeting_id": s["id"], "meeting": meetings.summary_row(s), "label": DRAFT_LABEL, "cases": cases, "building": building(s["id"]),
            "recording": recording_view(s)}


def case_view(case_id: str) -> dict:
    """GET /cases/{case_id}/meeting-notes for a reader of the whole Case File (the route checks): this Case File's notes from every
    meeting, newest meeting first."""
    rows = []
    for s in board.all_sessions():
        e = (s.get("notes") or {}).get(case_id) if isinstance(s.get("notes"), dict) else None
        if not isinstance(e, dict):
            continue
        rows.append({"meeting_id": s.get("id"), "date": s.get("date"), "time": s.get("time") or "", "title": s.get("title") or "",
                     "status": s.get("status"), "label_meeting": f"Tumour Board {_dmy(s.get('date'))}", **notes_view(e)})
    return {"case_id": case_id, "label": DRAFT_LABEL, "meetings": rows}


# ---- background builds (one at a time per meeting) and the hooks ----------------------------------------------------------------------

_bg_lock = threading.Lock()
_PENDING: dict[str, list] = {}   # mid -> [(case_id, by, trigger)] waiting
_RUNNING: dict[str, str] = {}    # mid -> the case being built now ("" between two)
_BG_TASKS: set = set()


def enabled() -> bool:
    """TB_SCHEDULER=0 turns the background build off; under pytest it runs only with TB_SCHEDULER=1 (as case_summary.enabled)."""
    raw = os.getenv("TB_SCHEDULER")
    v = str(raw).strip().lower() if raw is not None else ""
    if v in ("0", "false", "no", "off"):
        return False
    return not ("PYTEST_CURRENT_TEST" in os.environ and v != "1")


def building(mid: str) -> list[str]:
    with _bg_lock:
        now = [_RUNNING[mid]] if _RUNNING.get(mid) else []
        return now + [c for c, _, _ in _PENDING.get(mid) or [] if c not in now]


async def _drain(mid: str) -> None:
    done = False
    try:
        while True:
            with _bg_lock:
                q = _PENDING.get(mid) or []
                if not q:  # emptied and released under one lock, so a request arriving now starts a new builder
                    _PENDING.pop(mid, None)
                    _RUNNING.pop(mid, None)
                    done = True
                    return
                cid, by, trigger = q.pop(0)
                _RUNNING[mid] = cid
            try:
                await build_notes(mid, cid, by, trigger)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # the old notes stay; the next case is built
                log.warning("meeting %s: notes for %s not written (%s)", mid, cid, e.__class__.__name__)
                try:
                    board.audit_event(mid, "notes_failed", by or meetings.AUTOMATIC, case_id=cid, trigger=trigger, why=e.__class__.__name__)
                except Exception:
                    pass
            with _bg_lock:
                _RUNNING[mid] = ""
    finally:
        if not done:  # cancelled: the meeting is free for the next request
            with _bg_lock:
                _RUNNING.pop(mid, None)
                _PENDING.pop(mid, None)


def schedule(mid: str, case_id: str, by: str = "", trigger: str = "on_demand") -> dict:
    """Queue the notes of one Case File for the background builder of this meeting (one build at a time per meeting, in the order
    asked; a Case File already waiting is not queued twice). {"scheduled", "how": loop|queued|off|no_loop}."""
    if not enabled():
        return {"scheduled": False, "how": "off"}
    if case_id in config.BOARD_HIDDEN:
        return {"scheduled": False, "how": "off", "reason": "protected Case File"}
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return {"scheduled": False, "how": "no_loop"}  # the meeting code runs on the app's loop; never from a thread (meetings.py rule)
    with _bg_lock:
        q = _PENDING.setdefault(mid, [])
        if not any(c == case_id for c, _, _ in q):
            q.append((case_id, by, trigger))
        if mid in _RUNNING:
            return {"scheduled": True, "how": "queued"}
        _RUNNING[mid] = ""
    t = loop.create_task(_drain(mid))
    _BG_TASKS.add(t)
    t.add_done_callback(_BG_TASKS.discard)
    return {"scheduled": True, "how": "loop"}


def _stale(s: dict, case_id: str) -> bool:
    """True when this Case File has segments and no notes, or notes written from fewer segments than there are now."""
    segs = segments(s["id"], case_id)
    if not segs:
        return False
    e = (s.get("notes") or {}).get(case_id) if isinstance(s.get("notes"), dict) else None
    return not isinstance(e, dict) or e.get("signature") != signature(segs)


def on_case_ended(mid: str, case_id: str, by: str = "") -> dict:
    """HOOK: call after meetings.end_case(mid, cid, by) succeeded. Queues the notes of that Case File when something was recorded for
    it since the last notes. Never raises."""
    try:
        s = meetings.get(mid)
        if not s or not _stale(s, case_id):
            return {"scheduled": False, "how": "nothing_new"}
        return schedule(mid, case_id, by, "case_ended")
    except Exception as e:
        log.warning("meeting %s: notes not queued for %s (%s)", mid, case_id, e.__class__.__name__)
        return {"scheduled": False, "how": "error"}


def on_meeting_ended(mid: str, by: str = "") -> dict:
    """HOOK: call after meetings.end(mid, by) saved the closed meeting. Stops the recorder when it is on or paused (audited
    recording_stopped, reason meeting_ended, socket event), then queues the notes of every Case File with something new recorded, in
    agenda order. Idempotent; never raises."""
    out = {"stopped": False, "scheduled": []}
    try:
        s = meetings.get(mid)
        if not s:
            return out
        if _rec(s)["state"] in ("on", "paused"):
            set_recording(mid, by, "stop", reason="meeting_ended")
            out["stopped"] = True
            s = meetings.get(mid) or s
        seen = {x.get("case_id") for x in segments(mid) if x.get("case_id")}
        order = [c for c in _agenda_order(s) if c in seen] + sorted(c for c in seen if c not in _agenda_order(s))
        for cid in order:
            if cid not in config.BOARD_HIDDEN and _stale(s, cid) and schedule(mid, cid, by, "meeting_ended").get("scheduled"):
                out["scheduled"].append(cid)
    except Exception as e:
        log.warning("meeting %s: end-of-meeting recorder step failed (%s)", mid, e.__class__.__name__)
    return out
