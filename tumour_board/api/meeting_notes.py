"""The meeting recorder and the AI notes (meetings-v2 items 5.1 and 5.3), served under /api/tb behind the login, the Origin check and the
idle rule of the Tumour Board router. Logic in tumour_board/meeting_notes.py (it audits every change).

    POST /meetings/{mid}/recording                       {action: start|pause|resume|stop} -> {recording}            the MDT Coordinator
    POST /meetings/{mid}/transcribe                      multipart {audio, speaker, started_ms?} -> {stored, segment, seconds}
                                                         the coordinator, recorder on; 4 MiB, 60 s, 30 a minute; parsed in memory
    POST /meetings/{mid}/cases/{cid}/notes/build         -> the Case File's notes                                    the coordinator
    PUT  /meetings/{mid}/cases/{cid}/notes/lines/{lid}   {text} -> the line                                          the coordinator
    POST /meetings/{mid}/cases/{cid}/notes/review        {status: reviewed|draft} -> the Case File's notes           the coordinator
    GET  /meetings/{mid}/notes                           every Case File's notes                                     the members
    GET  /cases/{case_id}/meeting-notes                  this Case File's notes from every meeting                   full readers

No route returns the transcript or a segment's words except as the "said" of a note line. The audio is never written anywhere: the body
is read into memory with a cap and parsed there (api/audio.py's _capped_body and _form_in_memory; never request.form(), which spools a
part over 1 MiB to a temporary file)."""
from fastapi import Request

from tumour_board import access, audio_proxy as ap, board, config, llm, meeting_notes as mn, meetings, store

from . import common
from .audio import _capped_body, _form_in_memory

router = common.make_router(["tumour-board-meeting-notes"])
TRANSCRIBE_LIMIT = common.RateLimit(30, 60)  # per meeting and coordinator: about 30 chunks a minute (spec 5.1)
BUILD_LIMIT = common.RateLimit(20, 600)      # on-demand model calls
BUSY = "Too many recording chunks. Wait a moment."


def _call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except meetings.MeetingError as e:
        common.fail(e.status, str(e), e.code)


async def _acall(coro):
    try:
        return await coro
    except meetings.MeetingError as e:
        common.fail(e.status, str(e), e.code)


def _who(request: Request, guest: bool = False):
    """The user and its roles: a placed account (need_known); with guest=True an outside expert of a meeting passes too (reading only)."""
    rl = common.roles(request)
    if not (guest and rl.get("outside_expert") and not rl.get("disabled")):
        common.need_known(rl)
    return common.user(request), rl


def _coordinator(request: Request):
    u, rl = _who(request)
    common.need(rl, "session")  # the MDT Coordinator (org action "session"; never the Vaidyx admin)
    return u, rl


def _meeting(mid: str) -> dict:
    s = meetings.get(mid)
    if not s:
        common.fail(404, "Meeting not found.", "not_found")
    return s


def _case_id(x) -> str:
    try:
        return store.safe_id(str(x or ""))
    except ValueError:
        common.fail(400, "A Case File id is not valid.", "bad_case")


# ---- the recorder ----------------------------------------------------------------------------------------------------------------------

@router.post("/meetings/{mid}/recording")
async def meetings_recording(mid: str, request: Request):
    """{action: start|pause|resume|stop} -> {recording: {state, by, by_name, started_at, paused_at, stopped_at, chunks, segments, label,
    notice}}. 400 bad_action, 409 not_in_session / bad_state."""
    u, rl = _coordinator(request)
    b = await common.body(request)
    s = _meeting(mid)
    return {"recording": _call(mn.set_recording, s["id"], u, str(b.get("action") or ""))}


@router.post("/meetings/{mid}/transcribe")
async def meetings_transcribe(mid: str, request: Request):
    """Multipart {audio: one chunk (at most 4 MiB and 60 s), speaker: a login admitted to the meeting or "room", started_ms?: the client's
    time of the chunk's start} -> {stored, seconds, segment: {id, at, speaker, speaker_name, case_id, chars} | null}. Never the words."""
    u, rl = _coordinator(request)
    s = _meeting(mid)
    _call(mn.recording_on, s)
    if not ap.enabled():
        common.fail(503, ap.UNAVAILABLE, "voice_unavailable")
    if not (request.headers.get("content-type") or "").lower().startswith("multipart/form-data"):
        common.fail(400, "Send the recording as a form upload.", "bad_request")
    TRANSCRIBE_LIMIT.check(f"{s['id']}:{u}", BUSY)
    cap = ap.STT_MAX_BYTES + ap.STT_BODY_SLACK
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            too_big = int(cl) > cap
        except ValueError:
            common.fail(400, "The request has a bad Content-Length.", "bad_request")
        if too_big:
            common.fail(413, ap.TOO_BIG, "too_big")
    body = await _capped_body(request, cap)
    try:  # in memory only: never request.form()
        form, audio = _form_in_memory(body, request.headers.get("content-type") or "", max_files=1, max_fields=5)
    except Exception:
        common.fail(400, "The form upload could not be read.", "bad_request")
    del body
    if audio is None or audio["name"] != "audio":
        common.fail(400, "Attach the recording.", "bad_request")
    data, ctype = audio["data"], str(audio["content_type"] or "")
    del audio
    return await _acall(mn.transcribe_chunk(s["id"], u, data, ctype, form.get("speaker"), form.get("started_ms")))


# ---- the notes -----------------------------------------------------------------------------------------------------------------------

@router.post("/meetings/{mid}/cases/{cid}/notes/build")
async def meetings_notes_build(mid: str, cid: str, request: Request):
    """Write the notes of one Case File now (the model is called; a minute or so) -> {case_id, status: built, lines, ...} as in GET.
    409 nothing_recorded when no segment was stored for it; 502 when the model is not available (the old notes stay)."""
    u, rl = _coordinator(request)
    s = _meeting(mid)
    cid = _case_id(cid)
    BUILD_LIMIT.check(f"{s['id']}:{u}", "Too many requests to write notes. Wait a few minutes.")
    try:
        out = await _acall(mn.build_notes(s["id"], cid, u, "on_demand"))
    except llm.LLMError:
        common.fail(502, "The notes could not be written now: the model is not available. Try again later.", "model_unavailable")
    if out.get("status") == "nothing_recorded":
        common.fail(409, "Nothing was recorded while this Case File was on the floor.", "nothing_recorded")
    return out


@router.put("/meetings/{mid}/cases/{cid}/notes/lines/{line_id}")
async def meetings_notes_edit(mid: str, cid: str, line_id: str, request: Request):
    """{text} -> {id, text, said, edited: {by, by_name, at, checked}}. The "said" never changes."""
    u, rl = _coordinator(request)
    b = await common.body(request)
    s = _meeting(mid)
    return _call(mn.edit_line, s["id"], _case_id(cid), str(line_id)[:40], b.get("text"), u)


@router.post("/meetings/{mid}/cases/{cid}/notes/review")
async def meetings_notes_review(mid: str, cid: str, request: Request):
    """{status: reviewed|draft} -> the Case File's notes."""
    u, rl = _coordinator(request)
    b = await common.body(request)
    s = _meeting(mid)
    return _call(mn.review, s["id"], _case_id(cid), b.get("status"), u)


@router.get("/meetings/{mid}/notes")
async def meetings_notes(mid: str, request: Request):
    """{meeting_id, meeting, label, cases: [{case_id, withheld, lines: [{id, text, said: {segment_id, speaker, speaker_name, at, quote},
    edited}], generated_at, model, model_line, segments, dropped, dropped_reasons, review, label, edits}], building, recording}. Members
    of that meeting only (admitted, or the coordinator); an outside expert sees a Case File's notes only with the patient's consent."""
    u, rl = _who(request, guest=True)
    s = _meeting(mid)
    if not meetings.is_member(rl, s):
        common.fail(403, "The notes of a meeting are for the members admitted to it.", "not_member")
    out = mn.meeting_view(s, rl)
    board.audit_event(s["id"], "notes_read", u, cases=len(out["cases"]))
    return out


@router.get("/cases/{case_id}/meeting-notes")
async def case_meeting_notes(case_id: str, request: Request):
    """{case_id, label, meetings: [{meeting_id, date, time, title, status, label_meeting, lines, ...}]}: the Case File's notes from every
    meeting, for whoever reads the whole Case File (not a department that was only asked, not a window opened with a reason, not the
    meeting window: a member of that meeting reads them on the meeting's own route)."""
    u, rl = _who(request)
    c = common.case(case_id)
    if common.scope(request) != access.FULL:
        common.fail(403, "The meeting notes are shown to the readers of the whole Case File.", "not_full")
    cid = str(c.get("case_id") or c.get("id") or case_id)
    out = mn.case_view(cid)
    if cid not in config.PROTECTED_CASES:
        store.audit(cid, {"kind": "meeting_notes_read", "by": u, "meetings": len(out["meetings"])})
    return out
