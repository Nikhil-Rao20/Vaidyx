"""Voice routes (night-v3 item 4.2): GET /audio/status, POST /audio/stt and POST /audio/tts, served under /api/tb/audio/ behind the login,
the Origin check and the idle rule of the Tumour Board router; each also needs a placed account (need_known). The app talks to the local
audio service (tumour_board/audio_proxy.py); the browser never does. Speech to text only fills the person's own text box; text to speech
reads a saved statement by reference (the screen's own check first) or text already on screen (at most 1,000 characters). Rate limits per
user: status 60 a minute, dictation 40, saved statements 240 sentences and on-screen text 60 per 10 minutes. Audited without content.
Everything degrades to text: voice off, down or busy is a plain refusal the interface shows beside the text box."""
from fastapi import Request
from fastapi.responses import Response

from tumour_board import audio_proxy as ap

from . import common

router = common.make_router(["tumour-board-audio"])
STATUS_LIMIT = common.RateLimit(60, 60)
STT_LIMIT = common.RateLimit(40, 600)
REF_LIMIT = common.RateLimit(240, 600)
TEXT_LIMIT = common.RateLimit(60, 600)
WAIT = "Too many voice requests. Wait a minute, or type."


def _placed(request):
    u = common.user(request); rl = common.roles(request); common.need_known(rl)
    return u, rl


def _on():
    if not ap.enabled():
        common.fail(503, ap.UNAVAILABLE, "voice_unavailable")


def _service_failed(e: ap.ServiceError):
    common.fail(*ap.error_for(e.status, e.code))


@router.get("/audio/status")
async def audio_status(request: Request):
    """{enabled, stt, tts: ready|loading|down|off, limits{stt_seconds, stt_bytes, tts_chars}, cohere, voices}; never fails on the service."""
    _placed(request)
    STATUS_LIMIT.check(common.client_key(request), WAIT)
    return await ap.status()


async def _capped_body(request, cap: int) -> bytes:
    """The request body, refused with 413 as soon as it passes `cap` (a body without Content-Length is counted as it is read)."""
    chunks, n = [], 0
    async for chunk in request.stream():
        n += len(chunk)
        if n > cap:
            common.fail(413, ap.TOO_BIG, "too_big")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/audio/stt")
async def audio_stt(request: Request):
    """Multipart {audio, screen, case_id?, context?, engine?} -> {text, segments, duration, engine, took_ms, code}. At most 4 MiB and one
    minute. The case_id is kept for the audit only when the user may open that Case File; otherwise it is dropped without a word."""
    u, rl = _placed(request)
    _on()
    if not (request.headers.get("content-type") or "").lower().startswith("multipart/form-data"):
        common.fail(400, "Send the recording as a form upload.", "bad_request")
    STT_LIMIT.check(common.client_key(request), WAIT)
    cap = ap.STT_MAX_BYTES + ap.STT_BODY_SLACK
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            too_big = int(cl) > cap
        except ValueError:
            common.fail(400, "The request has a bad Content-Length.", "bad_request")
        if too_big:
            common.fail(413, ap.TOO_BIG, "too_big")
    request._body = await _capped_body(request, cap)  # Starlette's form() then reads this copy
    try:
        form = await request.form(max_files=1, max_fields=10)
    except Exception:
        common.fail(400, "The form upload could not be read.", "bad_request")
    try:
        audio = form.get("audio")
        if audio is None or isinstance(audio, str) or not hasattr(audio, "read"):
            common.fail(400, "Attach the recording.", "bad_request")
        data = await audio.read()
        ctype = str(getattr(audio, "content_type", "") or "")
        screen = str(form.get("screen") or "")
        case_id = str(form.get("case_id") or "").strip()
        context = str(form.get("context") or "")
        engine = "parakeet" if str(form.get("engine") or "") == "parakeet" else "whisper"
    finally:
        await form.close()
    if not ap.valid_screen(screen):
        common.fail(400, "Say which box the recording is for.", "bad_screen")
    if len(data) > ap.STT_MAX_BYTES:
        common.fail(413, ap.TOO_BIG, "too_big")
    if not data:
        common.fail(400, "The recording is empty.", "bad_request")
    if case_id and ap.case_scope(rl, case_id) is None:
        case_id = ""  # only fills the person's own box: no refusal, no line in a Case File the user cannot open
    try:
        out = await ap.transcribe(data, ctype, engine, context if context in ap.CONTEXTS else "")
    except ap.ServiceError as e:
        _service_failed(e)
    seconds = out.get("duration")
    ap.audit_transcribed(u, screen, case_id, seconds, out.get("engine") or engine, out.get("took_ms"), len(out.get("text") or ""))
    return out


def _voice(b):
    voice = b.get("voice", ap.DEFAULT_VOICE)
    if voice is None:
        voice = ap.DEFAULT_VOICE
    if voice not in ap.VOICES:
        common.fail(400, "Choose one of the offered voices.", "bad_voice")
    speed = b.get("speed", 1.0)
    if speed is None:
        speed = 1.0
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not ap.SPEED_MIN <= float(speed) <= ap.SPEED_MAX:
        common.fail(400, "The reading speed must be between 0.8 and 1.25.", "bad_speed")
    return voice, float(speed)


def _wav(audio: bytes, headers: dict, parts: int, part: int) -> Response:
    h = {k: v for k, v in headers.items() if k.lower() != "content-type"}
    h.update({"X-Parts": str(parts), "X-Part": str(part), "Cache-Control": "no-store"})
    ctype = next((v for k, v in headers.items() if k.lower() == "content-type"), "audio/wav")
    return Response(audio, media_type=ctype, headers=h)


@router.post("/audio/tts")
async def audio_tts(request: Request):
    """A saved statement by reference {ref{kind, case_id, id, index, meeting_id?, role?}, part?} or on-screen text {text, screen}, with
    voice? and speed?. Returns one sentence as a WAV with X-Parts (sentences in the statement), X-Part and X-Took-Ms."""
    u, rl = _placed(request)
    _on()
    b = await common.body(request)
    voice, speed = _voice(b)
    screen = b.get("screen") if ap.valid_screen(b.get("screen")) else ""
    ref = b.get("ref")
    if ref is not None:
        if not isinstance(ref, dict) or ref.get("kind") not in ap.RESOLVERS:
            common.fail(400, "Say what to read.", "bad_request")
        part = b.get("part", 0)
        if isinstance(part, bool) or not isinstance(part, int) or part < 0:
            common.fail(400, "The part must be a whole number.", "bad_request")
        REF_LIMIT.check(common.client_key(request), WAIT)
        kind = ref["kind"]
        text = ap.resolve(rl, ref)
        if not text:
            ap.audit_refused(u, ref)
            common.fail(404, ap.NOTHING, "not_found")
        sentences = ap.split_sentences(text)
        if part >= len(sentences):
            common.fail(404, ap.NOTHING, "not_found")
        try:
            audio, headers = await ap.speak(sentences[part], voice, speed)
        except ap.ServiceError as e:
            _service_failed(e)
        ap.audit_spoken(u, screen, ap.ref_key(ref), len(sentences), len(text), voice, ap.took_ms(headers),
                        case_id=ap.audit_case_id(ref) if kind in ap.CASE_KINDS else "", part=part)
        return _wav(audio, headers, len(sentences), part)
    if screen not in ap.TEXT_SCREENS:  # on-screen text is read back only from the boxes that offer it (the decision text)
        common.fail(400, "Say which box the text is from.", "bad_screen")
    text = " ".join(str(b.get("text") or "").split())
    if not text:
        common.fail(400, "There is no text to read.", "empty_text")
    if len(text) > ap.TEXT_MAX:
        common.fail(413, ap.TEXT_TOO_LONG, "text_too_long")
    TEXT_LIMIT.check(common.client_key(request), WAIT)
    try:
        audio, headers = await ap.speak(text, voice, speed)
    except ap.ServiceError as e:
        _service_failed(e)
    ap.audit_spoken(u, screen, "", 1, len(text), voice, ap.took_ms(headers))
    return _wav(audio, headers, 1, 0)
