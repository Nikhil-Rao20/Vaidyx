"""Voice routes (night-v3 item 4.2): /api/tb/audio/{status,stt,tts} through the app, the audio service stubbed with an httpx mock
transport (no real service is ever called). Off, down (cached), ready; dictation with its size cap, error mapping and audit without
content; reading a saved statement by reference only after the screen's own check (404 otherwise, nothing loaded), on-screen text up to
1,000 characters; the rate limits; the sentence rule. Synthetic Case Files only (TB-001..003 fixtures)."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from tumour_board import access, audio_proxy as ap, board, chats, config, helpers, meetings, org, store
from tumour_board.api import audio as api_audio, common
from tumour_board.tests import test_nik_meetings as M
from tumour_board.tests.test_nik_meetings import As, app, join_and_admit, owned, started  # noqa: F401 (fixtures)

URL = "http://127.0.0.1:7120"
TOKEN = "synthetic-audio-token-for-tests-only"
CASE = "TB-002"
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 28
HEALTH = {"status": "ok", "version": "1", "limits": {"stt_seconds": 60, "stt_bytes": 4194304, "tts_chars": 2000},
          "stt": {"engine": "whisper-large-v3-turbo", "state": "ready", "device": "cuda", "precision": "float16", "fallback": "parakeet-v2-cpu"},
          "tts": {"engine": "kokoro-82m", "state": "ready", "device": "cuda", "sample_rate": 24000, "voices": ["af_heart", "bf_emma", "am_michael"]},
          "engines": {"cohere": "unavailable", "parakeet": "ready"}, "gpu_free_mib": 1000}
SPOKEN = "Patient reports cough for three months and weight loss"


class Stub:
    """The audio service: records every request; answers set per test (status, body) or raises a connection error."""

    def __init__(self):
        self.calls = []
        self.health = (200, HEALTH)
        self.stt = (200, {"text": SPOKEN, "segments": [{"start": 0.0, "end": 3.2, "text": SPOKEN}], "language": "en", "duration": 7.4,
                          "speech_seconds": 6.9, "engine": "whisper-large-v3-turbo", "device": "cuda", "took_ms": 210, "code": None})
        self.tts = (200, WAV)
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        path = request.url.path
        if path == "/health":
            st, body = self.health
            return httpx.Response(st, json=body)
        if path == "/stt":
            st, body = self.stt
            return httpx.Response(st, json=body)
        if path == "/tts":
            st, body = self.tts
            if st != 200:
                return httpx.Response(st, json=body)
            return httpx.Response(200, content=body, headers={"content-type": "audio/wav", "x-took-ms": "95", "x-sample-rate": "24000",
                                                              "set-cookie": "s=1", "x-internal": "no"})
        return httpx.Response(404, json={"code": "not_found", "message": "no"})

    def paths(self):
        return [c.url.path for c in self.calls]


def _clear_limits():
    for lim in (api_audio.STATUS_LIMIT, api_audio.STT_LIMIT, api_audio.REF_LIMIT, api_audio.TEXT_LIMIT):
        lim._hits.clear()


@pytest.fixture
def stub(data_root, monkeypatch):
    s = Stub()
    (data_root / "audio_token.json").write_text(json.dumps({"token": TOKEN}))
    monkeypatch.setattr(config, "AUDIO_URL", URL)
    monkeypatch.setattr(config, "AUDIO_TOKEN_FILE", str(data_root / "audio_token.json"))
    monkeypatch.setattr(ap, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(s.handler)))
    ap.reset(); _clear_limits()
    yield s
    ap.reset(); _clear_limits()


@pytest.fixture
def tc(app, monkeypatch):  # noqa: F811
    """The Tumour Board API with the audio router (added here when the start-up list does not carry it yet); TB-002 owned by priya."""
    monkeypatch.setitem(M.TOKENS, "tok-stranger", "stranger")
    if not any(getattr(r, "path", "") == "/api/tb/audio/status" for r in app.routes):
        app.include_router(api_audio.router, prefix="/api/tb")
    with TestClient(app) as c:
        owned()
        yield c


def stt(tc, user, audio=b"\x1aE\xdf\xa3 synthetic webm bytes", **fields):
    As(tc, user)._c()
    data = {"screen": "ask", **fields}
    return tc.post("/api/tb/audio/stt", files={"audio": ("dictation.webm", audio, "audio/webm")}, data=data)


def tts(tc, user, body):
    return As(tc, user).post("/audio/tts", json=body)


def org_lines(kind):
    return [e for e in org.read_audit(1000) if e.get("kind") == kind]


def case_lines(case_id, kind):
    return [e for e in store.read_audit(case_id) if e.get("kind") == kind]


def seed_chat(case_id=CASE):
    chats.save(case_id, {"threads": [
        {"id": "T1", "by": "priya", "by_name": "Dr Priya Nair", "at": "2026-10-20T10:00:00", "question": "What size is the mass?", "status": "answered",
         "statements": [{"text": "The CECT of 2026-10-01 reports a 5.2 x 4.1 cm mass.", "citations": [{"doc_id": "D1", "quote": "5.2 x 4.1 cm", "doc_title": "CECT THORAX REPORT"}]},
                        {"text": "Dr. Rao recorded ECOG 1.", "citations": [{"doc_id": "D2", "quote": "ECOG 1", "doc_title": "OPD NOTE"}]}],
         "message": "", "pinned": False},
        {"id": "T2", "by": "priya", "at": "2026-10-19T10:00:00", "question": "Any PET?", "status": "not_documented", "statements": [],
         "message": "The records do not mention a PET/CT.", "pinned": False}]})


# ---- the sentence rule -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Mass seen. Nodes clear.", ["Mass seen.", "Nodes clear."]),
    ("Mass seen. nodes clear.", ["Mass seen. nodes clear."]),
    ("Is it T2? Yes! 3 nodes.", ["Is it T2?", "Yes!", "3 nodes."]),
    ("Seen by Dr. Rao. Next visit.", ["Seen by Dr. Rao.", "Next visit."]),
    ("Reg. No. 123 is listed. Mr. Kumar and Mrs. Devi came.", ["Reg. No. 123 is listed.", "Mr. Kumar and Mrs. Devi came."]),
    ("Markers, e.g. CEA and i.e. CA 19-9, vs. CT findings. Done.", ["Markers, e.g. CEA and i.e. CA 19-9, vs. CT findings.", "Done."]),
    ("(Dr. Nair) agreed. The size is 5.2 cm. Hb 11.8 g/dL.", ["(Dr. Nair) agreed.", "The size is 5.2 cm.", "Hb 11.8 g/dL."]),
    ('Outcome as recorded: "Surgery first." Tumour Board of 01/10/2026.', ['Outcome as recorded: "Surgery first."', "Tumour Board of 01/10/2026."]),
    ("Seen. (Repeat CT due.) \"Quoted\" line.", ["Seen.", "(Repeat CT due.)", "\"Quoted\" line."]),
    ("First line\n\n  second   line  \nThird. Fourth.", ["First line", "second line", "Third.", "Fourth."]),
    ("", []),
])
def test_split_sentences(text, expected):
    assert ap.split_sentences(text) == expected


def test_split_long_pieces():
    long = "word " * 70 + "and then, " + "more " * 40  # no sentence end; a comma after character 300
    parts = ap.split_sentences(long.strip())
    assert len(parts) == 2 and parts[0].endswith("then,") and len(parts[0]) > 300 and " ".join(parts) == " ".join(long.split())
    no_comma = "word " * 120
    parts = ap.split_sentences(no_comma)
    assert all(len(p) <= 400 for p in parts) and len(parts) == 2 and " ".join(parts) == no_comma.strip()
    blob = "x" * 900
    assert [len(p) for p in ap.split_sentences(blob)] == [400, 400, 100]


# ---- off, down, ready --------------------------------------------------------------------------------------------------------------

def test_off_makes_no_call(tc, data_root, monkeypatch):
    calls = []
    monkeypatch.setattr(config, "AUDIO_URL", "")
    monkeypatch.setattr(ap, "_client", lambda: calls.append(1))
    ap.reset()
    r = As(tc, "priya").get("/audio/status")
    assert r.status_code == 200 and r.json()["enabled"] is False and r.json()["stt"] == "off" and r.json()["tts"] == "off"
    r = stt(tc, "priya")
    assert r.status_code == 503 and r.json()["detail"] == {"message": ap.UNAVAILABLE, "code": "voice_unavailable"}
    r = tts(tc, "priya", {"screen": "decision", "text": "Read this back."})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "voice_unavailable"
    assert calls == []


def test_down_is_cached(tc, stub):
    stub.down = True
    a = As(tc, "priya").get("/audio/status").json()
    assert a["enabled"] is True and a["stt"] == "down" and a["tts"] == "down" and a["voices"] == []
    assert As(tc, "anil").get("/audio/status").json()["stt"] == "down"
    assert stub.paths() == ["/health"]  # the second call within 15 s asked nothing
    ap._status["at"] -= 16  # 15 s later the service is asked again
    stub.down = False
    assert As(tc, "priya").get("/audio/status").json()["stt"] == "ready" and stub.paths() == ["/health", "/health"]


def test_ready_with_limits_and_voices(tc, stub):
    r = As(tc, "priya").get("/audio/status")
    assert r.status_code == 200, r.text
    assert r.json() == {"enabled": True, "stt": "ready", "tts": "ready", "limits": {"stt_seconds": 60, "stt_bytes": 4194304, "tts_chars": 2000},
                        "cohere": False, "voices": ["af_heart", "bf_emma", "am_michael"]}
    assert "x-audio-token" not in {k.lower() for k in stub.calls[0].headers}  # /health takes no token
    assert TOKEN not in r.text


def test_status_states_and_a_missing_token(tc, stub, data_root):
    stub.health = (200, {**HEALTH, "stt": {"state": "not_loaded"}, "tts": {"state": "error"}})
    s = As(tc, "priya").get("/audio/status").json()
    assert s["stt"] == "ready" and s["tts"] == "down"  # not_loaded loads on the first request, so the buttons stay usable (review N1)
    ap.reset(); stub.health = (500, {"code": "failed"})
    assert As(tc, "priya").get("/audio/status").json()["stt"] == "down"
    ap.reset(); (data_root / "audio_token.json").unlink()
    stub.health = (200, HEALTH)
    assert As(tc, "priya").get("/audio/status").json()["stt"] == "down"  # the service would refuse every request


def test_a_user_not_placed_is_refused(tc, stub):
    assert As(tc, "stranger").get("/audio/status").status_code == 403
    assert stt(tc, "stranger").status_code == 403
    assert tts(tc, "stranger", {"text": "Read this."}).status_code == 403
    assert stub.calls == []


# ---- dictation ---------------------------------------------------------------------------------------------------------------------

def test_stt_happy_path_and_audit_without_text(tc, stub):
    r = stt(tc, "priya", context="question")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out == {"text": SPOKEN, "segments": [{"start": 0.0, "end": 3.2, "text": SPOKEN}], "duration": 7.4, "engine": "whisper-large-v3-turbo",
                   "took_ms": 210, "code": None}
    req = stub.calls[-1]
    assert req.url.path == "/stt" and req.headers["x-audio-token"] == TOKEN
    assert "cookie" not in {k.lower() for k in req.headers} and "authorization" not in {k.lower() for k in req.headers}
    body = req.content
    assert b'name="engine"\r\n\r\nwhisper' in body and b'name="language"\r\n\r\nen' in body and b'name="context"\r\n\r\nquestion' in body
    assert b"dictation.webm" not in body  # the file name never leaves the app
    line = org_lines("audio_transcribed")[0]
    assert line["by"] == "priya" and line["screen"] == "ask" and line["case_id"] == "" and line["chars"] == len(SPOKEN) and line["seconds"] == 7.4
    assert line["engine"] == "whisper-large-v3-turbo" and line["took_ms"] == 210
    raw = (config.DATA_ROOT / "org_audit.jsonl").read_text()
    assert SPOKEN not in raw and TOKEN not in raw and "dictation" not in raw


def test_stt_parakeet_on_request(tc, stub):
    assert stt(tc, "priya", engine="parakeet", context="banana").status_code == 200
    body = stub.calls[-1].content
    assert b'name="engine"\r\n\r\nparakeet' in body and b"banana" not in body


def test_stt_case_id_of_a_case_file_the_user_cannot_open(tc, stub):
    assert access.scope(org.roles("ravi"), store.get_case(CASE)) is None
    before = len(store.read_audit(CASE))
    r = stt(tc, "ravi", case_id=CASE)
    assert r.status_code == 200 and r.json()["text"] == SPOKEN
    assert len(store.read_audit(CASE)) == before and not case_lines(CASE, "audio_transcribed")
    assert org_lines("audio_transcribed")[0]["case_id"] == ""
    r = stt(tc, "ravi", case_id="TB-NOPE")  # an unknown id: the same
    assert r.status_code == 200 and org_lines("audio_transcribed")[0]["case_id"] == ""


def test_stt_case_id_allowed_writes_both_lines(tc, stub):
    r = stt(tc, "priya", case_id=CASE, screen="decision", context="decision")
    assert r.status_code == 200, r.text
    c = case_lines(CASE, "audio_transcribed")
    assert len(c) == 1 and c[0]["by"] == "priya" and c[0]["screen"] == "decision" and c[0]["chars"] == len(SPOKEN) and c[0]["seconds"] == 7.4
    assert org_lines("audio_transcribed")[0]["case_id"] == CASE
    assert SPOKEN not in json.dumps(store.read_audit(CASE))


def test_stt_size_cap_before_any_call(tc, stub):
    r = stt(tc, "priya", audio=b"\0" * (4 * 1024 * 1024 + 1))
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_big"
    r = stt(tc, "priya", audio=b"\0" * (4 * 1024 * 1024 + 100 * 1024))  # refused on the Content-Length
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_big"
    assert stub.calls == []


def test_stt_needs_a_form_upload_and_a_screen(tc, stub):
    As(tc, "priya")._c()
    r = tc.post("/api/tb/audio/stt", content=b"RIFFraw", headers={"content-type": "audio/wav"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_request"
    r = As(tc, "priya").post("/audio/stt", json={"audio": "x", "screen": "ask"})
    assert r.status_code == 400
    assert stt(tc, "priya", screen="not a screen!").status_code == 400
    assert stt(tc, "priya", screen="x" * 41).status_code == 400
    r = tc.post("/api/tb/audio/stt", files={"other": ("a", b"x", "audio/webm")}, data={"screen": "ask"})
    assert r.status_code == 400 and r.json()["detail"]["message"] == "Attach the recording."
    assert stub.calls == []


@pytest.mark.parametrize("status,body,want,code", [
    (413, {"code": "too_long", "message": "x"}, 413, "too_long"),
    (429, {"code": "busy", "message": "x"}, 429, "busy"),
    (503, {"code": "loading", "message": "x"}, 503, "voice_unavailable"),
    (415, {"code": "unsupported_audio", "message": "x"}, 415, "unsupported_audio"),
    (500, {"code": "failed", "message": "x"}, 502, "voice_failed"),
    (401, {"code": "no_token", "message": "x"}, 502, "voice_failed"),
])
def test_stt_service_errors_map(tc, stub, status, body, want, code):
    stub.stt = (status, body)
    r = stt(tc, "priya")
    assert r.status_code == want and r.json()["detail"]["code"] == code
    assert r.json()["detail"]["message"] == {413: ap.TOO_LONG, 429: ap.BUSY, 503: ap.UNAVAILABLE, 415: ap.UNREADABLE, 502: ap.UNAVAILABLE}[want]
    assert not org_lines("audio_transcribed")


def test_stt_service_down(tc, stub):
    stub.down = True
    r = stt(tc, "priya")
    assert r.status_code == 503 and r.json()["detail"] == {"message": "Voice is not available right now. You can type instead.", "code": "voice_unavailable"}


# ---- reading a saved statement ------------------------------------------------------------------------------------------------------

@pytest.fixture
def spy(monkeypatch):
    loaded = []
    real = ap.statement_text
    monkeypatch.setattr(ap, "statement_text", lambda kind, ref, roles=None: loaded.append(kind) or real(kind, ref, roles))
    return loaded


@pytest.mark.parametrize("kind", ["chat", "agent", "summary", "points"])
def test_reference_refused_without_full_scope(tc, stub, spy, monkeypatch, kind):
    seed_chat()
    ref = {"kind": kind, "case_id": CASE, "id": "T1" if kind == "chat" else "presentation", "role": "radiology", "index": 0}
    r = tts(tc, "ravi", {"ref": ref})  # no scope at all
    assert r.status_code == 404 and r.json()["detail"] == {"message": "Nothing to read here.", "code": "not_found"}
    monkeypatch.setattr(access, "scope", lambda r_, c, state=None: access.REQUESTS)  # a department that was only asked
    r = tts(tc, "priya", {"ref": ref})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"
    assert spy == [] and stub.calls == []
    lines = org_lines("audio_refused")
    assert len(lines) == 2 and lines[0]["ref_kind"] == kind and lines[0]["case_id"] == CASE and set(lines[0]) == {"ts", "by", "kind", "ref_kind", "case_id"}
    assert not case_lines(CASE, "audio_spoken")


def test_unknown_reference_is_the_same_404(tc, stub):
    seed_chat()
    for ref in ({"kind": "chat", "case_id": CASE, "id": "T999"}, {"kind": "chat", "case_id": "TB-NOPE", "id": "T1"},
                {"kind": "summary", "case_id": CASE, "id": "presentation"}, {"kind": "agent", "case_id": CASE, "role": "cardiology", "index": 0}):
        r = tts(tc, "priya", {"ref": ref})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found", ref
    assert tts(tc, "priya", {"ref": {"kind": "secret", "case_id": CASE}}).status_code == 400
    assert stub.calls == []


def test_chat_reference_speaks_one_sentence_per_part(tc, stub):
    seed_chat()
    ref = {"kind": "chat", "case_id": CASE, "id": "T1", "index": 0}
    r = tts(tc, "priya", {"ref": ref, "screen": "ask", "voice": "bf_emma", "speed": 1.1})
    assert r.status_code == 200, r.text
    assert r.content == WAV and r.headers["content-type"] == "audio/wav"
    assert r.headers["x-parts"] == "2" and r.headers["x-part"] == "0" and r.headers["x-took-ms"] == "95" and r.headers["x-sample-rate"] == "24000"
    assert "set-cookie" not in r.headers and "x-internal" not in r.headers
    sent = json.loads(stub.calls[-1].content)
    assert sent == {"text": "The CECT of 01/10/2026 reports a 5.2 x 4.1 cm mass.", "voice": "bf_emma", "speed": 1.1, "normalise": True, "format": "wav"}
    req = stub.calls[-1]
    assert req.headers["x-audio-token"] == TOKEN and "cookie" not in {k.lower() for k in req.headers} and "authorization" not in {k.lower() for k in req.headers}
    r = tts(tc, "priya", {"ref": ref, "part": 1})
    assert r.status_code == 200 and r.headers["x-part"] == "1" and json.loads(stub.calls[-1].content)["text"] == "Dr. Rao recorded ECOG 1."
    assert tts(tc, "priya", {"ref": ref, "part": 2}).status_code == 404
    assert tts(tc, "priya", {"ref": ref, "part": -1}).status_code == 400
    lines = org_lines("audio_spoken")  # newest first: the part 1 request (no screen, the default voice), then the part 0 request
    assert len(lines) == 2 and lines[1]["ref"] == f"chat:{CASE}:T1:0" and lines[1]["parts"] == 2 and lines[1]["voice"] == "bf_emma" and lines[1]["took_ms"] == 95
    assert lines[1]["part"] == 0 and lines[0]["part"] == 1 and lines[0]["ref"] == lines[1]["ref"]  # every part leaves a line (review N3)
    assert lines[1]["screen"] == "ask" and lines[1]["chars"] == len("The CECT of 01/10/2026 reports a 5.2 x 4.1 cm mass. Dr. Rao recorded ECOG 1.")
    c = case_lines(CASE, "audio_spoken")
    assert len(c) == 1 and c[0]["ref"] == f"chat:{CASE}:T1:0" and c[0]["parts"] == 2
    raw = (config.DATA_ROOT / "org_audit.jsonl").read_text() + json.dumps(store.read_audit(CASE))
    assert "CECT of" not in raw and TOKEN not in raw
    # a "not found in the records" answer reads as the screen shows it; by its place in the list too
    r = tts(tc, "priya", {"ref": {"kind": "chat", "case_id": CASE, "index": 1}})
    assert r.status_code == 200 and json.loads(stub.calls[-1].content)["text"] == "The records do not mention a PET/CT."


def test_chat_is_for_the_treating_team(tc, stub, monkeypatch):
    seed_chat()
    c = store.get_case(CASE); c["participants"] = [{"department": "radiology", "since": store.now_iso(), "by": "priya"}]; store.save_case(c)
    assert access.scope(org.roles("ravi"), store.get_case(CASE)) == access.FULL  # a supporting participant reads the Case File
    assert tts(tc, "ravi", {"ref": {"kind": "chat", "case_id": CASE, "id": "T1"}}).status_code == 404  # but never the team chat
    assert tts(tc, "anil", {"ref": {"kind": "chat", "case_id": CASE, "id": "T1"}}).status_code == 200  # the MDT Coordinator does


def test_agent_reference(tc, stub):
    helpers.save_chats(CASE, {"radiology": [
        {"id": "H1", "role": "radiology", "by": "priya", "at": "2026-10-20T10:00:00", "question": "Nodes?", "status": "answered",
         "statements": [{"text": "The CECT reports two nodes.", "citations": [{"doc_id": "D1", "quote": "two nodes"}]}], "references": [{"org": "ICRI / IRIA"}],
         "message": "", "model": "Gemma-4-31B"},
        {"id": "H2", "role": "radiology", "by": "priya", "at": "2026-10-20T10:01:00", "question": "PET?", "status": "not_documented", "statements": [], "message": ""}]})
    r = tts(tc, "priya", {"ref": {"kind": "agent", "case_id": CASE, "role": "radiology", "id": "H1"}})
    assert r.status_code == 200 and r.headers["x-parts"] == "1" and json.loads(stub.calls[-1].content)["text"] == "The CECT reports two nodes."
    r = tts(tc, "priya", {"ref": {"kind": "agent", "case_id": CASE, "role": "radiology", "index": 1}})
    assert r.status_code == 200 and json.loads(stub.calls[-1].content)["text"] == "Nothing in the records answers this."
    assert org_lines("audio_spoken")[0]["ref"] == f"agent:{CASE}:radiology:1"
    assert tts(tc, "priya", {"ref": {"kind": "agent", "case_id": CASE, "role": "pathology", "index": 0}}).status_code == 404


def test_summary_and_points_references(tc, stub):
    st = store.get_state(CASE)
    st.setdefault("artefacts", {})["summary"] = {"sections": [{"id": "presentation", "title": "Presentation", "sentences": [{"text": "Cough since 2026-07-01.", "citations": []}]}],
                                                 "points_for_review": [{"text": "Is the PET/CT stage the one to quote?", "citations": [{"doc_id": "D1", "quote": "x"}]},
                                                                       {"text": "Is the HER2 report final", "citations": []}]}
    store.save_state(CASE, st)
    r = tts(tc, "priya", {"ref": {"kind": "points", "case_id": CASE}})
    assert r.status_code == 200 and r.headers["x-parts"] == "2" and json.loads(stub.calls[-1].content)["text"] == "Is the PET/CT stage the one to quote?"
    r = tts(tc, "priya", {"ref": {"kind": "points", "case_id": CASE}, "part": 1})
    assert json.loads(stub.calls[-1].content)["text"] == "Is the HER2 report final"
    # before the first decision the summary is the pre-board one
    r = tts(tc, "priya", {"ref": {"kind": "summary", "case_id": CASE, "id": "presentation"}})
    assert r.status_code == 200 and json.loads(stub.calls[-1].content)["text"] == "Cough since 01/07/2026."
    # after it, the Case summary's current version, blocks included, the consultant's edit as shown
    st = store.get_state(CASE)
    st["artefacts"]["case_summary"] = {"current": 2, "case_id": CASE, "versions": [
        {"n": 1, "sections": [{"id": "presentation", "title": "Presentation and diagnosis", "sentences": [{"id": "p1", "text": "Old version.", "citations": []}]}]},
        {"n": 2, "sections": [
            {"id": "presentation", "title": "Presentation and diagnosis", "sentences": [
                {"id": "p1", "text": "Cough for three months, edited.", "citations": [{"doc_id": "D1", "quote": "cough"}], "edited": {"by": "priya", "vaidyx_text": "Cough."}},
                {"id": "p2", "text": "Biopsy on 2026-09-12 showed carcinoma.", "citations": []}]},
            {"id": "rounds", "title": "Board rounds", "blocks": [{"record": "B1", "sentences": [{"id": "rB1-date", "text": "Tumour Board of 01/10/2026.", "code": True},
                                                                                              {"id": "rB1-outcome", "text": "Outcome as recorded: Decision.", "code": True}]}]}]}]}
    store.save_state(CASE, st)
    r = tts(tc, "priya", {"ref": {"kind": "summary", "case_id": CASE, "id": "presentation"}})
    assert r.status_code == 200 and r.headers["x-parts"] == "2" and json.loads(stub.calls[-1].content)["text"] == "Cough for three months, edited."
    r = tts(tc, "priya", {"ref": {"kind": "summary", "case_id": CASE, "id": "presentation"}, "part": 1})
    assert json.loads(stub.calls[-1].content)["text"] == "Biopsy on 12/09/2026 showed carcinoma."
    r = tts(tc, "priya", {"ref": {"kind": "summary", "case_id": CASE, "id": "rounds"}})
    assert r.headers["x-parts"] == "2" and json.loads(stub.calls[-1].content)["text"] == "Tumour Board of 01/10/2026."
    r = tts(tc, "priya", {"ref": {"kind": "summary", "case_id": CASE, "id": "presentation", "source": "pre_board"}})
    assert json.loads(stub.calls[-1].content)["text"] == "Cough since 01/07/2026."
    assert len(case_lines(CASE, "audio_spoken")) == 5  # one per statement (part 0 only)


def _meeting_with_answer(tc):
    mid = started(tc)
    join_and_admit(tc, mid, "priya")
    e = board.log_answer(mid, CASE, "pathology", "What is the HER2 status?",
                         {"status": "answered", "statements": [{"text": "HER2 is 3+ on IHC. The report is final.", "citations": [{"doc_id": "D1", "quote": "3+"}]}], "label": "Pathology", "model": "Gemma-4-31B"})
    s = meetings.need(mid)
    s.setdefault("questions", []).append({"id": "Q1", "by": "priya", "text": "HER2?", "case_id": CASE, "role": "pathology",
                                          "answer": {"status": "answered", "text": "HER2 is 3+ on IHC.", "statements": []}})
    board.save_session(s)
    return mid, e["id"]


def test_meeting_answer_for_members_only(tc, stub, spy):
    mid, eid = _meeting_with_answer(tc)
    s = meetings.need(mid)
    assert meetings.may_view(org.roles("mohan"), s) is False
    for user in ("mohan", "ravi"):  # mohan may not open the meeting; ravi is not admitted, so the questions are not on his screen
        r = tts(tc, user, {"ref": {"kind": "meeting_answer", "meeting_id": mid, "id": eid}})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"
    assert tts(tc, "priya", {"ref": {"kind": "meeting_answer", "meeting_id": "S20991231-zzzz", "id": eid}}).status_code == 404
    assert spy == [] and stub.calls == []
    assert org_lines("audio_refused")[0]["case_id"] == "S20991231-zzzz"
    r = tts(tc, "priya", {"ref": {"kind": "meeting_answer", "meeting_id": mid, "id": eid}, "screen": "meeting"})
    assert r.status_code == 200 and r.headers["x-parts"] == "2" and json.loads(stub.calls[-1].content)["text"] == "HER2 is 3+ on IHC."
    r = tts(tc, "priya", {"ref": {"kind": "meeting_answer", "meeting_id": mid, "id": "Q1"}})
    assert r.status_code == 200 and r.headers["x-parts"] == "1"
    lines = org_lines("audio_spoken")
    assert lines[-1]["ref"] == f"meeting_answer:{mid}:{eid}:" and lines[-1]["screen"] == "meeting"
    assert not case_lines(CASE, "audio_spoken")  # a meeting answer is audited on the organisation log


# ---- on-screen text --------------------------------------------------------------------------------------------------------------

def test_on_screen_text(tc, stub):
    r = tts(tc, "priya", {"text": "x" * 1001, "screen": "decision"})
    assert r.status_code == 413 and r.json()["detail"]["code"] == "text_too_long"
    assert tts(tc, "priya", {"text": "   ", "screen": "decision"}).status_code == 400
    assert stub.calls == []
    text = "Plan agreed as typed, for the board to read back. " + "y" * 50
    assert len(text) == 100
    r = tts(tc, "priya", {"text": "  " + text.replace(" ", "   ") + "\n", "screen": "decision"})
    assert r.status_code == 200 and r.content == WAV and r.headers["x-parts"] == "1" and r.headers["x-part"] == "0"
    assert len(stub.calls) == 1 and json.loads(stub.calls[0].content)["text"] == text
    line = org_lines("audio_spoken")[0]
    assert line["ref"] == "" and line["parts"] == 1 and line["chars"] == 100 and line["screen"] == "decision" and line["voice"] == "af_heart"
    assert "Plan agreed" not in (config.DATA_ROOT / "org_audit.jsonl").read_text()


def test_voice_and_speed_are_checked(tc, stub):
    r = tts(tc, "priya", {"screen": "decision", "text": "Read this.", "voice": "en_evil"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_voice"
    assert tts(tc, "priya", {"screen": "decision", "text": "Read this.", "speed": 3}).status_code == 400
    assert tts(tc, "priya", {"screen": "decision", "text": "Read this.", "speed": "fast"}).status_code == 400
    assert stub.calls == []
    assert tts(tc, "priya", {"screen": "decision", "text": "Read this.", "voice": "am_michael", "speed": 0.8}).status_code == 200


@pytest.mark.parametrize("status,code,want,want_code", [(503, "loading", 503, "voice_unavailable"), (429, "busy", 429, "busy"),
                                                        (413, "text_too_long", 413, "text_too_long"), (400, "bad_voice", 502, "voice_failed")])
def test_tts_service_errors_map(tc, stub, status, code, want, want_code):
    stub.tts = (status, {"code": code, "message": "x"})
    r = tts(tc, "priya", {"screen": "decision", "text": "Read this."})
    assert r.status_code == want and r.json()["detail"]["code"] == want_code
    assert not org_lines("audio_spoken")


def test_tts_service_down(tc, stub):
    stub.down = True
    r = tts(tc, "priya", {"screen": "decision", "text": "Read this."})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "voice_unavailable"


# ---- rate limits ---------------------------------------------------------------------------------------------------------------------

def test_rate_limits(tc, stub, monkeypatch):
    seed_chat()
    monkeypatch.setattr(api_audio, "STATUS_LIMIT", common.RateLimit(2, 60))
    monkeypatch.setattr(api_audio, "STT_LIMIT", common.RateLimit(1, 600))
    monkeypatch.setattr(api_audio, "TEXT_LIMIT", common.RateLimit(1, 600))
    monkeypatch.setattr(api_audio, "REF_LIMIT", common.RateLimit(2, 600))
    assert As(tc, "priya").get("/audio/status").status_code == 200 and As(tc, "priya").get("/audio/status").status_code == 200
    r = As(tc, "priya").get("/audio/status")
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    assert stt(tc, "priya").status_code == 200
    r = stt(tc, "priya")
    assert r.status_code == 429 and r.json()["detail"] == {"message": "Too many voice requests. Wait a minute, or type.", "code": "rate_limited"}
    assert tts(tc, "priya", {"screen": "decision", "text": "One."}).status_code == 200
    assert tts(tc, "priya", {"screen": "decision", "text": "Two."}).status_code == 429
    ref = {"kind": "chat", "case_id": CASE, "id": "T1"}
    assert tts(tc, "priya", {"ref": ref}).status_code == 200  # a separate limiter from on-screen text
    assert tts(tc, "priya", {"ref": ref, "part": 1}).status_code == 200
    assert tts(tc, "priya", {"ref": ref}).json()["detail"]["code"] == "rate_limited"
    assert stt(tc, "anil").status_code == 200  # per user


def test_token_is_read_once_and_never_shown(tc, stub, data_root):
    assert ap.token() == TOKEN
    (data_root / "audio_token.json").write_text(json.dumps({"token": "changed"}))
    assert ap.token() == TOKEN  # cached
    ap.reset()
    assert ap.token() == "changed"
    (data_root / "audio_token.json").write_text("{bad json")
    ap.reset()
    assert ap.token() == ""


# ---- the Phase 4 review fixes -------------------------------------------------------------------------------------------------

def test_every_helper_role_is_a_valid_screen_id():
    """The helper chats send screen="helper-<role>"; four roles carry an underscore (review S1)."""
    for role in helpers.ROLES:
        assert ap.valid_screen(f"helper-{role}"), role
    assert not ap.valid_screen("helper/pathology") and not ap.valid_screen("x" * 41)


def test_meeting_log_entry_needs_full_scope_on_its_case_file(tc, stub, spy):
    """A member admitted to the meeting without FULL scope on the Case File hears the question's answer on the screen but not the
    Board room's logged agent answer about that file (review M1)."""
    mid, eid = _meeting_with_answer(tc)
    join_and_admit(tc, mid, "ravi")
    s = meetings.need(mid)
    assert meetings.may_view(org.roles("ravi"), s) and meetings.is_member(org.roles("ravi"), s)
    assert access.scope(org.roles("ravi"), store.get_case(CASE)) != access.FULL
    r = tts(tc, "ravi", {"ref": {"kind": "meeting_answer", "meeting_id": mid, "id": eid}})
    assert r.status_code == 404 and stub.calls == []
    assert tts(tc, "ravi", {"ref": {"kind": "meeting_answer", "meeting_id": mid, "id": "Q1"}}).status_code == 200
    assert tts(tc, "priya", {"ref": {"kind": "meeting_answer", "meeting_id": mid, "id": eid}}).status_code == 200


def test_every_part_is_audited_and_the_case_line_once(tc, stub):
    """A part asked for on its own leaves an organisation line; the Case File's log gets one line per statement (review N3)."""
    seed_chat(); tid = "T1"
    before, cb = len(org_lines("audio_spoken")), len(case_lines(CASE, "audio_spoken"))
    r = tts(tc, "priya", {"ref": {"kind": "chat", "case_id": CASE, "id": tid}, "part": 1, "screen": "ask"})
    assert r.status_code == 200 and r.headers["x-part"] == "1"
    lines = org_lines("audio_spoken")
    assert len(lines) == before + 1 and lines[0]["part"] == 1  # newest first
    assert len(case_lines(CASE, "audio_spoken")) == cb  # the Case File's log gets its line with part 0 only
    assert tts(tc, "priya", {"ref": {"kind": "chat", "case_id": CASE, "id": tid}, "part": 0, "screen": "ask"}).status_code == 200
    assert len(case_lines(CASE, "audio_spoken")) == cb + 1 and org_lines("audio_spoken")[0]["part"] == 0


def test_padded_case_id_never_makes_a_new_folder(tc, stub):
    """The audit uses the stored id of the Case File, never the raw field (review N4)."""
    seed_chat(); tid = "T1"
    cases = store.CASES_DIR if hasattr(store, "CASES_DIR") else config.CASES_DIR
    dirs_before = {d.name for d in cases.iterdir()} if cases.exists() else set()
    r = tts(tc, "priya", {"ref": {"kind": "chat", "case_id": CASE + " " * 70 + "Z", "id": tid}, "screen": "ask"})
    assert r.status_code in (200, 404)
    dirs_after = {d.name for d in cases.iterdir()} if cases.exists() else set()
    assert dirs_after == dirs_before
    if r.status_code == 200:
        assert case_lines(CASE, "audio_spoken")


def test_on_screen_text_only_from_the_boxes_that_offer_it(tc, stub):
    """Mode (b) is for the decision text's Read back; any other or no screen is refused before the service is called (review N5)."""
    for body in ({"text": "Read this please."}, {"text": "Read this please.", "screen": "ask"}, {"text": "Read this please.", "screen": "helper-pathology"}):
        r = tts(tc, "priya", body)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_screen"
    assert stub.calls == []
    assert tts(tc, "priya", {"text": "Read this please.", "screen": "decision"}).status_code == 200


def test_empty_token_is_not_cached(stub, monkeypatch, tmp_path):
    """The app may start before the token file exists; once it appears, the next call reads it (review N2)."""
    f = tmp_path / "later" / "audio_token.json"  # not the stub's file: this one does not exist yet
    monkeypatch.setattr(config, "AUDIO_TOKEN_FILE", str(f))
    ap.reset()
    assert ap.token() == ""
    f.parent.mkdir()
    f.write_text(json.dumps({"token": "t" * 48}))
    assert ap.token() == "t" * 48
    ap.reset()
