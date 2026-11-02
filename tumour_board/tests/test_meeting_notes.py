"""The meeting recorder that keeps no audio and the AI notes per Case File (meetings-v2 items 5.1 and 5.3): the recorder's states
(coordinator only, in session only, audited, sent on the socket; ending the meeting stops it), the chunk route (coordinator only,
recorder on only, 4 MiB and 60 s caps, a known speaker, the audio service stubbed with an httpx mock transport: the text stored with the
speaker's name and the Case File on the floor; empty text or a failure stores nothing; no audio on disk, no temporary file), the notes
(the reasoner stubbed: a quote not in its segment, a number not in the quote, a name that is not the speaker's and advice in Vaidyx's
own words are dropped and counted; edit and review by the coordinator; a rebuild keeps the edits), who reads them (the meeting's
members; an outside expert only with consent; the Case File route for full readers only) and the background builder (one at a time
per meeting). Synthetic Case Files only (TB-001..003 fixtures)."""
import asyncio
import json
import os
import stat
import tempfile

import pytest
from fastapi.testclient import TestClient

from tumour_board import audio_proxy as ap, board, llm, meeting_notes as mn, meetings, store
from tumour_board.api import meeting_notes as api_mn
from tumour_board.tests.test_audio_routes import TOKEN, stub  # noqa: F401 (fixture)
from tumour_board.tests.test_nik_meetings import As, app, join_and_admit, owned, started, with_agenda  # noqa: F401 (fixtures)

AUDIO = b"\x1aE\xdf\xa3 synthetic webm chunk VX-AUDIO-MARKER"
SAID_1 = "The CT thorax report shows a 3.5 cm mass in the right upper lobe with two enlarged hilar nodes."
SAID_2 = "I would recommend a lobectomy if the PET-CT shows no distant disease."
SAID_3 = "Can pathology confirm the EGFR status before the next meeting?"
AUDIO_SUFFIXES = (".webm", ".wav", ".ogg", ".oga", ".opus", ".mp3", ".m4a", ".mp4", ".aac", ".flac", ".weba")


@pytest.fixture
def tc(app, monkeypatch):  # noqa: F811
    api_mn.TRANSCRIBE_LIMIT._hits.clear(); api_mn.BUILD_LIMIT._hits.clear()
    with mn._bg_lock:
        mn._PENDING.clear(); mn._RUNNING.clear()
    mn._BG_TASKS.clear()
    with TestClient(app) as c:
        owned()
        yield c
    api_mn.TRANSCRIBE_LIMIT._hits.clear(); api_mn.BUILD_LIMIT._hits.clear()


@pytest.fixture
def sent(monkeypatch):
    """Every event the meeting code sends on the socket."""
    out = []
    real = meetings._send

    def rec(s, ev):
        out.append(ev)
        return real(s, ev)
    monkeypatch.setattr(meetings, "_send", rec)
    return out


def recording(tc, mid, action, user="anil"):
    return As(tc, user).post(f"/meetings/{mid}/recording", json={"action": action})


def chunk(tc, mid, user="anil", audio=AUDIO, speaker="room", **fields):
    As(tc, user)._c()
    return tc.post(f"/api/tb/meetings/{mid}/transcribe", files={"audio": ("chunk.webm", audio, "audio/webm")},
                   data={"speaker": speaker, **{k: str(v) for k, v in fields.items()}})


def say(tc, stub, mid, speaker, text, duration=18.0, **fields):  # noqa: F811
    stub.stt = (200, {"text": text, "segments": [{"start": 0.0, "end": duration, "text": text}], "language": "en", "duration": duration,
                      "speech_seconds": duration, "engine": "whisper-large-v3-turbo", "device": "cuda", "took_ms": 300, "code": None})
    r = chunk(tc, mid, speaker=speaker, **fields)
    assert r.status_code == 200, r.text
    return r.json()


def session_kinds(mid):
    return [e["kind"] for e in board.read_audit(5000) if e.get("session") == mid]


def recording_meeting(tc):
    """A meeting in session (TB-001 on the floor) with Dr Suresh (Radiology head) and Dr Lata (Surgical Oncology head) admitted and the
    recorder on."""
    mid = started(tc)
    join_and_admit(tc, mid, "suresh")
    join_and_admit(tc, mid, "lata")
    assert recording(tc, mid, "start").status_code == 200
    return mid


def three_segments(tc, stub, mid):  # noqa: F811
    """Three segments while TB-001 is on the floor and one while TB-002 is; returns their ids."""
    a = say(tc, stub, mid, "suresh", SAID_1, started_ms=1762070000000)["segment"]["id"]
    b = say(tc, stub, mid, "lata", SAID_2, started_ms=1762070020000)["segment"]["id"]
    c = say(tc, stub, mid, "room", SAID_3, started_ms=1762070040000)["segment"]["id"]
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"})
    d = say(tc, stub, mid, "suresh", "The mammogram report notes a spiculated lesion in the upper outer quadrant.", started_ms=1762070100000)["segment"]["id"]
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-001"})
    return a, b, c, d


def fake_reasoner(monkeypatch, lines_for):
    """llm.chat replaced: `lines_for(messages)` gives the lines; every call is kept."""
    calls = []

    async def chat(role, msgs, **kw):
        calls.append({"role": role, "messages": msgs, **kw})
        return {"lines": lines_for(msgs)}
    monkeypatch.setattr(llm, "chat", chat)
    return calls


# ---- the recorder ----------------------------------------------------------------------------------------------------------------

def test_recording_states_coordinator_only_in_session_audited_and_sent(tc, sent):
    planned = with_agenda(tc)
    r = recording(tc, planned, "start")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_in_session"
    mid = started(tc)
    join_and_admit(tc, mid, "ravi")
    assert recording(tc, mid, "start", user="priya").status_code == 403   # a doctor
    assert recording(tc, mid, "start", user="ravi").status_code == 403    # an admitted member
    assert recording(tc, mid, "start", user="admin").status_code == 403   # the Vaidyx admin never runs a meeting
    assert recording(tc, mid, "dance").json()["detail"]["code"] == "bad_action"
    assert recording(tc, mid, "pause").json()["detail"]["code"] == "bad_state"   # not on yet
    r = recording(tc, mid, "start")
    assert r.status_code == 200
    v = r.json()["recording"]
    assert v["state"] == "on" and v["by"] == "anil" and v["by_name"] == "Anil Kumar" and v["label"] == "Recording: text only, no audio kept"
    assert v["notice"] == "This meeting is being recorded as text (no audio is kept)"
    assert recording(tc, mid, "start").json()["detail"]["code"] == "bad_state"
    assert recording(tc, mid, "resume").json()["detail"]["code"] == "bad_state"
    assert recording(tc, mid, "pause").json()["recording"]["state"] == "paused"
    assert recording(tc, mid, "pause").status_code == 409
    assert recording(tc, mid, "resume").json()["recording"]["state"] == "on"
    v = recording(tc, mid, "stop").json()["recording"]
    assert v["state"] == "off" and v["stopped_at"] and v["label"] == "" and v["notice"] == ""
    assert recording(tc, mid, "stop").json()["detail"]["code"] == "bad_state"
    assert meetings.get(mid)["recording"]["state"] == "off"
    kinds = [k for k in session_kinds(mid) if k.startswith("recording_")]
    assert kinds == ["recording_started", "recording_paused", "recording_resumed", "recording_stopped"]
    events = [e for e in sent if e.get("type") == "recording"]
    assert [e["recording"]["state"] for e in events] == ["on", "paused", "on", "off"]


def test_ending_the_meeting_stops_the_recorder(tc, sent):
    mid = started(tc)
    recording(tc, mid, "start")
    recording(tc, mid, "pause")
    assert As(tc, "anil").post(f"/meetings/{mid}/end").status_code == 200
    assert mn.recording_view(meetings.get(mid))["state"] == "off"  # a closed meeting never shows the recorder on
    out = mn.on_meeting_ended(mid, "anil")  # the hook (a no-op when meetings.end already called it)
    assert meetings.get(mid)["recording"]["state"] == "off" and out["scheduled"] == []
    stops = [e for e in board.read_audit(5000) if e.get("session") == mid and e["kind"] == "recording_stopped"]
    assert len(stops) == 1 and stops[0]["reason"] == "meeting_ended"
    assert mn.on_meeting_ended(mid, "anil")["stopped"] is False  # idempotent
    assert recording(tc, mid, "start").json()["detail"]["code"] == "not_in_session"


# ---- the chunks --------------------------------------------------------------------------------------------------------------------

def test_transcribe_stores_text_with_speaker_and_the_case_on_the_floor(tc, stub, data_root):  # noqa: F811
    mid = started(tc)
    join_and_admit(tc, mid, "suresh")
    r = chunk(tc, mid)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_recording"  # nothing runs before Record
    recording(tc, mid, "start")
    assert chunk(tc, mid, user="priya").status_code == 403
    assert chunk(tc, mid, user="suresh").status_code == 403  # a member never posts chunks
    assert chunk(tc, mid, speaker="mohan").json()["detail"]["code"] == "bad_speaker"  # not in the meeting
    assert chunk(tc, mid, speaker="").json()["detail"]["code"] == "bad_speaker"
    assert stub.paths() == []  # nothing reached the service
    out = say(tc, stub, mid, "suresh", SAID_1, started_ms=1762070000000)
    assert out["stored"] is True and out["seconds"] == 18.0
    seg = out["segment"]
    assert seg["speaker"] == "suresh" and seg["speaker_name"] == "Dr Suresh" and seg["case_id"] == "TB-001" and seg["chars"] == len(SAID_1)
    assert "text" not in seg and "CT thorax" not in json.dumps(out)  # the words are never sent back
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"})
    seg2 = say(tc, stub, mid, "room", SAID_3)["segment"]
    assert seg2["speaker"] == "room" and seg2["speaker_name"] == "Board room" and seg2["case_id"] == "TB-002"
    stt = [c for c in stub.calls if c.url.path == "/stt"]
    assert len(stt) == 2 and all(c.headers["x-audio-token"] == TOKEN for c in stt) and b"VX-AUDIO-MARKER" in stt[0].content
    assert b'name="language"' in stt[0].content and b"en" in stt[0].content
    p = mn.transcript_path(mid)
    assert p.parent == board.sessions_dir() and p.name == f"{mid}.transcript.jsonl"
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    assert [(x["speaker"], x["speaker_name"], x["case_id"], x["text"]) for x in rows] == [
        ("suresh", "Dr Suresh", "TB-001", SAID_1), ("room", "Board room", "TB-002", SAID_3)]
    assert rows[0]["started_ms"] == 1762070000000 and rows[1]["started_ms"] is None
    rec = meetings.get(mid)["recording"]
    assert rec["chunks"] == 2 and rec["segments"] == 2
    lines = [e for e in board.read_audit(5000) if e.get("session") == mid and e["kind"] == "recording_chunk"]
    assert len(lines) == 2 and lines[0]["stored"] is True and lines[0]["chars"] == len(SAID_1) and lines[0]["speaker"] == "suresh"
    assert "CT thorax" not in json.dumps(board.read_audit(5000)) and "CT thorax" not in json.dumps(store.read_audit("TB-001"))
    assert "CT thorax" not in As(tc, "anil").get(f"/meetings/{mid}").text  # the meeting view never carries the transcript
    recording(tc, mid, "pause")
    assert chunk(tc, mid).json()["detail"]["code"] == "not_recording"


def test_transcribe_caps_and_failures_store_nothing(tc, stub):  # noqa: F811
    mid = started(tc)
    recording(tc, mid, "start")
    r = chunk(tc, mid, audio=b"\x00" * (ap.STT_MAX_BYTES + 1))
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_big"
    assert chunk(tc, mid, audio=b"").json()["detail"]["code"] == "bad_request"
    assert stub.paths() == []
    stub.stt = (200, {"text": SAID_1, "segments": [], "duration": 75.0, "engine": "whisper", "took_ms": 900, "code": None})
    r = chunk(tc, mid)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_long"  # over 60 s
    stub.stt = (413, {"code": "too_long", "message": "longer than 60 s"})
    assert chunk(tc, mid).json()["detail"]["code"] == "too_long"
    stub.stt = (500, {"code": "failed"})
    assert chunk(tc, mid).status_code == 502
    stub.down = True
    assert chunk(tc, mid).status_code == 503
    stub.down = False
    stub.stt = (200, {"text": "   ", "segments": [], "duration": 20.0, "engine": "whisper", "took_ms": 100, "code": None})
    assert chunk(tc, mid).json() == {"stored": False, "seconds": 20.0, "segment": None}
    stub.stt = (200, {"text": "Thank you.", "segments": [], "duration": 20.0, "engine": "whisper", "took_ms": 100, "code": "no_speech"})
    assert chunk(tc, mid).json()["stored"] is False
    assert not mn.transcript_path(mid).exists() and mn.segments(mid) == []
    rec = meetings.get(mid)["recording"]
    assert rec["chunks"] == 2 and rec["segments"] == 0
    failed = [e["code"] for e in board.read_audit(5000) if e.get("session") == mid and e["kind"] == "recording_chunk_failed"]
    assert failed == ["too_long", "too_long", "voice_failed", "voice_unavailable"]
    r = tc.post(f"/api/tb/meetings/{mid}/transcribe", json={"audio": "x"})
    assert r.status_code == 400  # a form upload only


def test_transcribe_rate_limit(tc, stub):  # noqa: F811
    mid = started(tc)
    recording(tc, mid, "start")
    stub.stt = (200, {"text": "", "segments": [], "duration": 1.0, "engine": "whisper", "took_ms": 5, "code": None})
    codes = [chunk(tc, mid).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


def test_no_audio_is_written_anywhere(tc, stub, data_root, monkeypatch):  # noqa: F811
    """A chunk over 1 MiB (where Starlette's form parser would spool to a temporary file) goes to the service from memory: no temporary
    file is made, no file under the data folders holds the audio or has an audio name, the transcript holds text only."""
    mid = recording_meeting(tc)
    import starlette.formparsers as sfp
    made = []
    for mod, name in ((tempfile, "TemporaryFile"), (tempfile, "NamedTemporaryFile"), (tempfile, "SpooledTemporaryFile"), (tempfile, "mkstemp"),
                      (sfp, "SpooledTemporaryFile")):  # Starlette's form parser binds its own name (request.form() is never used)
        real = getattr(mod, name)

        def spy(*a, _real=real, _name=f"{mod.__name__}.{name}", **k):
            made.append(_name)
            return _real(*a, **k)
        monkeypatch.setattr(mod, name, spy)
    marker = b"VX-NO-AUDIO-ON-DISK-" + os.urandom(16).hex().encode()
    big = marker + os.urandom(1536 * 1024) + marker
    stub.stt = (200, {"text": SAID_1, "segments": [], "duration": 19.5, "engine": "whisper", "took_ms": 400, "code": None})
    r = chunk(tc, mid, audio=big, speaker="suresh")
    assert r.status_code == 200 and r.json()["stored"] is True
    assert marker in stub.calls[-1].content  # the bytes reached the service, from memory
    assert made == []
    for root in {str(data_root), str(board.sessions_dir())}:
        for dirpath, _, files in os.walk(root):
            for f in files:
                path = os.path.join(dirpath, f)
                assert not f.lower().endswith(AUDIO_SUFFIXES), path
                with open(path, "rb") as fh:
                    assert marker not in fh.read(), path
    assert all(set(x) <= {"id", "at", "started_ms", "speaker", "speaker_name", "department", "case_id", "text"} for x in mn.segments(mid))
    assert "audio" not in json.dumps(meetings.get(mid).get("recording"))


# ---- the notes -----------------------------------------------------------------------------------------------------------------------

def test_notes_keep_only_verified_lines(tc, stub, monkeypatch):  # noqa: F811
    mid = recording_meeting(tc)
    a, b, c, d = three_segments(tc, stub, mid)
    wanted = [
        {"text": "Dr Suresh noted the size of the mass in the CT thorax report.", "segment_id": a, "quote": "the CT thorax report shows a 3.5 cm mass"},
        {"text": "Dr Suresh noted the nodes.", "segment_id": a, "quote": "three enlarged nodes in the mediastinum"},          # not in the segment
        {"text": "Dr Suresh noted the lesion.", "segment_id": d, "quote": "a spiculated lesion in the upper outer quadrant"},  # TB-002's segment
        {"text": "Surgery is recommended for this patient.", "segment_id": b, "quote": "I would recommend a lobectomy"},        # advice, own words
        {"text": "Dr Lata gave their view on surgery: \"I would recommend a lobectomy if the PET-CT shows no distant disease\".", "segment_id": b,
         "quote": "I would recommend a lobectomy if the PET-CT shows no distant disease"},                                    # attributed: kept
        {"text": "Dr Suresh noted a 4 cm mass.", "segment_id": a, "quote": "a 3.5 cm mass in the right upper lobe"},          # a number not quoted
        {"text": "Pathology noted the hilar nodes.", "segment_id": a, "quote": "with two enlarged hilar nodes"},              # not the speaker
        {"text": "In the room, someone asked whether Pathology can confirm the EGFR status.", "segment_id": c,
         "quote": "Can pathology confirm the EGFR status"},                                                                 # kept
        {"text": "Dr Suresh said \"the patient should start chemotherapy\".", "segment_id": a, "quote": "a 3.5 cm mass"},       # advice in marks
        {"text": "Dr Suresh noted the size of the mass in the CT thorax report.", "segment_id": a, "quote": "The CT thorax report shows a 3.5 cm mass"},  # the same again
        {"text": "Radiology noted the lesion.", "segment_id": a, "quote": "mass"},                                            # too short
    ]
    calls = fake_reasoner(monkeypatch, lambda msgs: wanted)
    assert As(tc, "suresh").post(f"/meetings/{mid}/cases/TB-001/notes/build").status_code == 403
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/notes/build")
    assert r.status_code == 200, r.text
    n = r.json()
    assert n["status"] == "built" and n["label"] == "AI draft, not reviewed" and n["review"]["status"] == "draft" and n["segments"] == 3
    assert [x["text"] for x in n["lines"]] == [wanted[0]["text"], wanted[4]["text"], wanted[7]["text"]]
    said = n["lines"][0]["said"]
    assert said == {"segment_id": a, "speaker": "suresh", "speaker_name": "Dr Suresh", "at": said["at"], "quote": wanted[0]["quote"]} and said["at"]
    assert n["lines"][2]["said"]["speaker_name"] == "Board room" and n["lines"][1]["said"]["speaker_name"] == "Dr Lata"
    assert n["dropped"] == 8 and n["dropped_reasons"] == {"quote_not_found": 1, "no_segment": 1, "advice": 2, "numbers": 1, "names": 1,
                                                          "duplicate": 1, "quote_too_short": 1}
    assert "non-medical" in n["model_line"]
    assert len(calls) == 1 and calls[0]["role"] == "reasoner" and calls[0]["json_schema"] == mn.SCHEMA
    prompt = calls[0]["messages"][1]["content"]
    assert f"[{a}]" in prompt and f"[{b}]" in prompt and f"[{c}]" in prompt and f"[{d}]" not in prompt  # only this Case File's segments
    assert "Dr Suresh (Radiology): " + SAID_1 in prompt and "Board room microphone (speaker not known)" in prompt
    assert prompt.index(f"[{a}]") < prompt.index(f"[{b}]") < prompt.index(f"[{c}]")  # in the order spoken
    assert "never decide, advise, diagnose, stage" in calls[0]["messages"][0]["content"]
    assert "notes_built" in session_kinds(mid)
    assert any(e["kind"] == "board_session_notes_built" and e["lines"] == 3 for e in store.read_audit("TB-001"))
    stored = meetings.get(mid)["notes"]["TB-001"]
    assert len(stored["lines"]) == 3 and stored["signature"].startswith("3:")
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-003/notes/build")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "nothing_recorded"


def test_model_down_keeps_the_old_notes(tc, stub, monkeypatch):  # noqa: F811
    mid = recording_meeting(tc)
    a, *_ = three_segments(tc, stub, mid)
    fake_reasoner(monkeypatch, lambda msgs: [{"text": "Dr Suresh noted the CT thorax report.", "segment_id": a, "quote": "The CT thorax report shows"}])
    assert As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/notes/build").status_code == 200

    async def down(*a_, **k):
        raise llm.LLMError("reasoner unreachable")
    monkeypatch.setattr(llm, "chat", down)
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/notes/build")
    assert r.status_code == 502 and r.json()["detail"]["code"] == "model_unavailable"
    assert len(meetings.get(mid)["notes"]["TB-001"]["lines"]) == 1


def test_edit_review_and_rebuild_keeps_the_edit(tc, stub, monkeypatch):  # noqa: F811
    mid = recording_meeting(tc)
    a, b, c, d = three_segments(tc, stub, mid)
    model = [{"text": "Dr Suresh noted the size of the mass in the CT thorax report.", "segment_id": a, "quote": "the CT thorax report shows a 3.5 cm mass"},
             {"text": "In the room, someone asked about the EGFR status.", "segment_id": c, "quote": "Can pathology confirm the EGFR status"}]
    fake_reasoner(monkeypatch, lambda msgs: model)
    n = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/notes/build").json()
    lid = n["lines"][0]["id"]
    path = f"/meetings/{mid}/cases/TB-001/notes/lines/{lid}"
    assert As(tc, "suresh").put(path, json={"text": "x"}).status_code == 403
    assert As(tc, "anil").put(path, json={"text": "  "}).json()["detail"]["code"] == "bad_text"
    assert As(tc, "anil").put(f"/meetings/{mid}/cases/TB-001/notes/lines/nope", json={"text": "x"}).json()["detail"]["code"] == "no_line"
    assert As(tc, "anil").put(f"/meetings/{mid}/cases/TB-002/notes/lines/{lid}", json={"text": "x"}).json()["detail"]["code"] == "no_notes"
    r = As(tc, "anil").put(path, json={"text": "Dr Suresh read out the CT thorax report — a 3.5 cm mass."})
    assert r.status_code == 200
    ln = r.json()
    assert ln["text"] == "Dr Suresh read out the CT thorax report - a 3.5 cm mass." and ln["edited"]["by"] == "anil" and ln["edited"]["checked"] is True
    assert ln["said"]["quote"] == model[0]["quote"] and ln["said"]["speaker_name"] == "Dr Suresh"  # the "said" stays
    ln = As(tc, "anil").put(path, json={"text": "Dr Suresh noted a 5 cm mass."}).json()
    assert ln["edited"]["checked"] is False  # a number the quote does not hold: shown as not checked
    assert As(tc, "suresh").post(f"/meetings/{mid}/cases/TB-001/notes/review", json={"status": "reviewed"}).status_code == 403
    assert As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/notes/review", json={"status": "done"}).json()["detail"]["code"] == "bad_status"
    v = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/notes/review", json={"status": "reviewed"}).json()
    assert v["review"]["status"] == "reviewed" and v["label"].startswith("AI notes, reviewed by Anil Kumar on ")
    assert v["edits"] == 2
    kinds = session_kinds(mid)
    assert kinds.count("notes_line_edited") == 2 and "notes_reviewed" in kinds
    assert "5 cm mass" not in json.dumps(board.read_audit(5000))  # audited without the text
    n2 = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/notes/build").json()  # the model writes the same line again
    assert [x["text"] for x in n2["lines"]] == ["Dr Suresh noted a 5 cm mass.", model[1]["text"]] and n2["lines"][0]["edited"]["by"] == "anil"
    assert n2["review"]["status"] == "draft" and n2["label"] == "AI draft, not reviewed" and n2["edits"] == 2
    assert meetings.get(mid)["notes"]["TB-001"]["reviews"][0]["status"] == "reviewed"


def test_who_reads_the_notes(tc, stub, monkeypatch):  # noqa: F811
    mid = recording_meeting(tc)
    a, b, c, d = three_segments(tc, stub, mid)
    code = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "guest").post("/meetings/join", json={"code": code})
    As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "guest"})

    def lines(msgs):
        u = msgs[1]["content"]
        if f"[{d}]" in u:
            return [{"text": "Dr Suresh noted the lesion in the mammogram report.", "segment_id": d, "quote": "The mammogram report notes a spiculated lesion"}]
        return [{"text": "Dr Suresh noted the size of the mass in the CT thorax report.", "segment_id": a, "quote": "the CT thorax report shows a 3.5 cm mass"}]
    fake_reasoner(monkeypatch, lines)
    for cid in ("TB-001", "TB-002"):
        assert As(tc, "anil").post(f"/meetings/{mid}/cases/{cid}/notes/build").status_code == 200
    v = As(tc, "suresh").get(f"/meetings/{mid}/notes").json()  # an admitted member
    assert [x["case_id"] for x in v["cases"]] == ["TB-001", "TB-002"] and all(not x["withheld"] for x in v["cases"])
    assert v["cases"][1]["lines"][0]["said"]["quote"] == "The mammogram report notes a spiculated lesion" and v["recording"]["state"] == "on"
    assert As(tc, "anil").get(f"/meetings/{mid}/notes").status_code == 200
    assert As(tc, "ravi").get(f"/meetings/{mid}/notes").status_code == 403    # radiology on the sheet, never admitted
    assert As(tc, "priya").get(f"/meetings/{mid}/notes").status_code == 403   # the owner of TB-002, not in the meeting
    g = As(tc, "guest").get(f"/meetings/{mid}/notes").json()                   # an outside expert without consent
    assert [(x["case_id"], x["withheld"]) for x in g["cases"]] == [("TB-001", True), ("TB-002", True)] and "lines" not in g["cases"][0]
    c2 = store.get_case("TB-002"); c2["consent"] = {"outside_discussion": True}; store.save_case(c2)
    g = As(tc, "guest").get(f"/meetings/{mid}/notes").json()
    assert [(x["case_id"], x["withheld"]) for x in g["cases"]] == [("TB-001", True), ("TB-002", False)] and g["cases"][1]["lines"]
    assert session_kinds(mid).count("notes_read") == 4
    # the Case File route: readers of the whole Case File only
    r = As(tc, "priya").get("/cases/TB-002/meeting-notes")
    assert r.status_code == 200
    rows = r.json()["meetings"]
    assert len(rows) == 1 and rows[0]["meeting_id"] == mid and rows[0]["lines"][0]["said"]["speaker_name"] == "Dr Suresh"
    assert any(e["kind"] == "meeting_notes_read" and e["by"] == "priya" for e in store.read_audit("TB-002"))
    assert As(tc, "anil").get("/cases/TB-001/meeting-notes").json()["meetings"][0]["lines"][0]["text"].startswith("Dr Suresh noted")
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-002"})
    r = As(tc, "suresh").get("/cases/TB-002/meeting-notes")  # the meeting window reads the Case File on the floor, not its notes route
    assert r.status_code == 403
    assert As(tc, "ravi").get("/cases/TB-002/meeting-notes").status_code == 403
    assert As(tc, "guest").get("/cases/TB-002/meeting-notes").status_code == 403


# ---- background builds and the hooks -------------------------------------------------------------------------------------------------

def test_background_builds_one_at_a_time(tc, stub, monkeypatch):  # noqa: F811
    mid = recording_meeting(tc)
    a, b, c, d = three_segments(tc, stub, mid)
    assert mn.on_case_ended(mid, "TB-001", "anil") == {"scheduled": False, "how": "off"}  # TB_SCHEDULER=0 in the unit suite
    monkeypatch.setenv("TB_SCHEDULER", "1")
    live, peak, order = [0], [0], []

    async def chat(role, msgs, **kw):
        live[0] += 1; peak[0] = max(peak[0], live[0])
        await asyncio.sleep(0.02)
        live[0] -= 1
        u = msgs[1]["content"]
        order.append("TB-002" if f"[{d}]" in u else "TB-001")
        if f"[{d}]" in u:
            return {"lines": [{"text": "Dr Suresh noted the lesion.", "segment_id": d, "quote": "a spiculated lesion in the upper outer quadrant"}]}
        return {"lines": [{"text": "Dr Suresh noted the CT thorax report.", "segment_id": a, "quote": "The CT thorax report shows"}]}
    monkeypatch.setattr(llm, "chat", chat)

    async def go():
        r1 = mn.on_case_ended(mid, "TB-001", "anil")
        r2 = mn.on_case_ended(mid, "TB-002", "anil")
        r3 = mn.on_case_ended(mid, "TB-001", "anil")  # already waiting: not queued twice
        queued = mn.building(mid)
        while mn._BG_TASKS:
            await asyncio.gather(*list(mn._BG_TASKS))
        return r1, r2, r3, queued
    r1, r2, r3, queued = asyncio.run(go())
    assert r1 == {"scheduled": True, "how": "loop"} and r2["how"] == "queued" and r3["how"] == "queued"
    assert queued == ["TB-001", "TB-002"] and order == ["TB-001", "TB-002"] and peak[0] == 1
    notes = meetings.get(mid)["notes"]
    assert set(notes) == {"TB-001", "TB-002"} and notes["TB-001"]["trigger"] == "case_ended" and notes["TB-001"]["built_by"] == "anil"
    assert mn.building(mid) == []
    assert mn.on_case_ended(mid, "TB-001", "anil") == {"scheduled": False, "how": "nothing_new"}  # nothing said since
    As(tc, "anil").post(f"/meetings/{mid}/end")

    async def end():
        out = mn.on_meeting_ended(mid, "anil")
        while mn._BG_TASKS:
            await asyncio.gather(*list(mn._BG_TASKS))
        return out
    out = asyncio.run(end())
    assert out["scheduled"] == [] and meetings.get(mid)["recording"]["state"] == "off"  # notes current, the recorder stopped
    assert mn.on_case_ended("S-none", "TB-001", "anil")["scheduled"] is False  # never raises


def test_meeting_end_builds_what_is_new(tc, stub, monkeypatch):  # noqa: F811
    mid = recording_meeting(tc)
    a, b, c, d = three_segments(tc, stub, mid)
    calls = fake_reasoner(monkeypatch, lambda msgs: [])
    As(tc, "anil").post(f"/meetings/{mid}/end")
    monkeypatch.setenv("TB_SCHEDULER", "1")  # after the end route, so only this call queues the builds

    async def end():
        out = mn.on_meeting_ended(mid, "anil")
        while mn._BG_TASKS:
            await asyncio.gather(*list(mn._BG_TASKS))
        return out
    out = asyncio.run(end())
    assert out["scheduled"] == ["TB-001", "TB-002"] and len(calls) == 2
    notes = meetings.get(mid)["notes"]
    assert notes["TB-001"]["lines"] == [] and notes["TB-001"]["trigger"] == "meeting_ended" and notes["TB-001"]["built_by"] == "anil"


def test_the_old_sessions_route_never_carries_the_notes():
    """The 5.3 agent's finding: board.session_view dropped only the chat, so the old sessions route served the notes' spoken words."""
    from tumour_board import board
    v = board.session_view({"id": "S1", "chat": [{"text": "x"}], "notes": {"TB-001": {"lines": [{"said": {"quote": "spoken words"}}]}}}, None)
    assert "notes" not in v and "chat" not in v


# ---- the summary after the board (item 5.4) -------------------------------------------------------------------------------------------

def test_the_summary_after_the_board_follows_the_notes(tc, stub, monkeypatch):  # noqa: F811
    """Building the notes or editing a line writes the Case summary again (case_summary.on_notes_changed); a review changes no words.
    With a board record of the meeting, the summary built now cites the note line ("said") with the speaker's exact words."""
    from tumour_board import case_summary as cs
    got = []
    real = cs.on_notes_changed
    monkeypatch.setattr(cs, "on_notes_changed", lambda mid, cid, by="", why="": got.append((mid, cid, by, why)) or real(mid, cid, by, why))
    mid = recording_meeting(tc)
    a, *_ = three_segments(tc, stub, mid)
    line = {"text": "Dr Suresh noted the size of the mass in the CT thorax report.", "segment_id": a, "quote": "the CT thorax report shows a 3.5 cm mass"}
    fake_reasoner(monkeypatch, lambda msgs: [line])
    n = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/notes/build").json()
    assert got == [(mid, "TB-001", "anil", "notes_built")]
    assert real(mid, "TB-001", "anil") == {"scheduled": False, "how": "no_board_record"}  # no decision of this meeting yet
    lid = n["lines"][0]["id"]
    As(tc, "anil").put(f"/meetings/{mid}/cases/TB-001/notes/lines/{lid}", json={"text": "Dr Suresh read out the CT thorax report."})
    assert got[-1] == (mid, "TB-001", "anil", "notes_line_edited")
    As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/notes/review", json={"status": "reviewed"})
    assert len(got) == 2
    r = As(tc, "anil").post(f"/meetings/{mid}/cases/TB-001/decision", json={"outcome": "decision", "decision_text": "Surgery first (SYNTHETIC).",
                                                                             "members_present": ["Anil Kumar"], "intent": "curative",
                                                                             "responsible_doctor": "Dr Priya Nair"})
    assert r.status_code == 200, r.text
    assert real(mid, "TB-001", "anil")["how"] == "off"  # a board record of this meeting: scheduled (the scheduler is off in the unit suite)
    said = {"text": "At the board, Dr Suresh noted that the CT thorax report shows a 3.5 cm mass.",
            "citations": [{"note_line": lid, "quote": "the CT thorax report shows a 3.5 cm mass"}]}

    async def chat(role, msgs, **kw):
        return {"sentences": [said] if kw.get("purpose") == "case summary discussion" else [], "claims": []}
    monkeypatch.setattr(llm, "chat", chat)
    v = asyncio.run(cs.build("TB-001", {"kind": "notes", "meeting": mid}, "anil"))
    disc = next(x for x in v["sections"] if x["id"] == "discussion")
    c = disc["sentences"][0]["citations"][0]
    assert disc["sentences"][0]["text"] == said["text"]
    assert {k: c[k] for k in ("kind", "meeting_id", "line_id", "speaker", "speaker_name", "quote")} == {
        "kind": "said", "meeting_id": mid, "line_id": lid, "speaker": "suresh", "speaker_name": "Dr Suresh", "quote": "the CT thorax report shows a 3.5 cm mass"}
    assert cs.verify_said("TB-001", c) and SAID_1 not in json.dumps(v)  # only the quoted words, never the whole segment


def test_a_term_said_in_the_segment_counts_even_outside_the_short_quote():
    """The 2 Nov evaluation: "MRI" was said by Radiology but left out of the model's shorter quote, and speech to text wrote "MR, I"."""
    from tumour_board import meeting_notes as mn
    seg = {"text": "On the MRI pelvis, the lesion measures 2.2 x 1.8 cm, and the parametria are free.", "speaker": "tb-rad-doc",
           "speaker_name": "Dr Radiology (demo)", "department": "radiology"}
    assert mn._names_ok("Radiology noted the lesion measures 2.2 x 1.8 cm on the MRI pelvis.", "the lesion measures 2.2 x 1.8 cm", seg)
    seg2 = {"text": "Could radiology confirm whether the lesion size on MR, I matches the clinical examination?", "speaker": "room", "speaker_name": "Board room"}
    assert mn._names_ok("In the room, someone asked radiology to confirm the lesion size on MRI.", "Could radiology confirm whether the lesion size", seg2)
    assert not mn._names_ok("Pathology noted the lesion measures 2.2 cm.", "the lesion measures 2.2 x 1.8 cm", seg)  # nobody said Pathology
    assert not mn._names_ok("Radiology noted the PET-CT was clear.", "the lesion measures 2.2 x 1.8 cm", seg)  # no PET-CT was said
