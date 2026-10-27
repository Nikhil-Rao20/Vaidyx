"""The aiohttp app of the audio service: GET /health, POST /stt, POST /tts (docs/night-v3/research/08_voice.md section 4).

Nothing is stored: the audio and the text live in memory for the length of the request. One log line per /stt and /tts request
with time, route, status, audio seconds, engine, device, took_ms and byte count; never text, never a filename."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time

from aiohttp import BodyPartReader, web

from . import audio_io, limits, text_norm
from .stt import ENGINES, Loading, SttService, Unavailable
from .tts import VOICES, EmptyText, TtsService

VERSION = "1"
LOG = logging.getLogger("tb.audio")
MULTIPART_SLACK = 64 * 1024
TOKEN_KEY = web.AppKey("token", str)
STT_KEY = web.AppKey("stt", SttService)
TTS_KEY = web.AppKey("tts", TtsService)
STT_SLOT_KEY = web.AppKey("stt_slot", object)
TTS_SLOT_KEY = web.AppKey("tts_slot", object)
GPU_KEY = web.AppKey("gpu", object)
WARM_KEY = web.AppKey("warm_task", object)
META_KEY = web.RequestKey("meta", dict)
DRAIN_MAX = 64 * 1024 * 1024

MESSAGES = {
    "bad_request": "The request is not valid.",
    "no_token": "The audio token is missing or wrong.",
    "too_big": "The upload is too big (4 MB at most).",
    "too_long": "The recording is longer than 60 seconds.",
    "unsupported_audio": "The audio could not be decoded.",
    "busy": "The audio service is busy. Try again in a moment.",
    "loading": "The speech model is still loading. Try again in a few seconds.",
    "engine_unavailable": "This speech engine is not available.",
    "failed": "The audio could not be processed.",
    "text_too_long": "The text is longer than 2,000 characters.",
    "bad_voice": "This voice is not available.",
    "empty_text": "There is no text to read.",
    "not_found": "Not found.",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str | None = None):
        super().__init__(code)
        self.status, self.code, self.message = status, code, message or MESSAGES[code]


def _error_response(status: int, code: str, message: str | None = None) -> web.Response:
    return web.json_response({"code": code, "message": message or MESSAGES[code]}, status=status,
                             headers={"Cache-Control": "no-store"})


class Slot:
    """One job at a time; at most QUEUE_MAX waiting, each for at most WAIT_SECONDS, else 429 busy."""

    def __init__(self):
        self.sem = asyncio.Semaphore(1)
        self.waiting = 0

    async def __aenter__(self):
        if self.waiting >= limits.QUEUE_MAX:
            raise ApiError(429, "busy")
        self.waiting += 1
        try:
            task = asyncio.ensure_future(self.sem.acquire())
            done, _ = await asyncio.wait({task}, timeout=limits.WAIT_SECONDS)
            if not done:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                else:
                    self.sem.release()  # acquired while being cancelled: give it back
                raise ApiError(429, "busy")
        finally:
            self.waiting -= 1
        return self

    async def __aexit__(self, *exc):
        self.sem.release()
        return False


class GpuProbe:
    """Free GPU memory for /health, refreshed in the background so /health never waits on nvidia-smi."""

    def __init__(self, max_age: float = 10.0):
        self.value: int | None = None
        self.at = -1e9
        self.max_age = max_age
        self.task: asyncio.Task | None = None

    async def refresh(self) -> None:
        loop = asyncio.get_running_loop()
        self.value = await loop.run_in_executor(None, limits.gpu_free_mib)
        self.at = loop.time()

    def read(self) -> int | None:
        loop = asyncio.get_running_loop()
        if loop.time() - self.at > self.max_age and (self.task is None or self.task.done()):
            self.task = loop.create_task(self.refresh())
        return self.value


def _check_token(request: web.Request) -> None:
    given = request.headers.get("X-Audio-Token", "")
    if not given or not hmac.compare_digest(given.encode("utf-8"), request.app[TOKEN_KEY].encode("utf-8")):
        raise ApiError(401, "no_token")


async def _drain(request: web.Request) -> None:
    seen = 0
    while seen < DRAIN_MAX:
        chunk = await request.content.readany()
        if not chunk:
            break
        seen += len(chunk)


async def _read_capped(read, cap: int, code: str = "too_big") -> bytes:
    buf = bytearray()
    while True:
        chunk = await read()
        if not chunk:
            return bytes(buf)
        buf += chunk
        if len(buf) > cap:
            raise ApiError(413, code)


async def _read_stt_request(request: web.Request) -> tuple[bytes, dict]:
    if request.content_length is not None and request.content_length > limits.STT_BYTES + MULTIPART_SLACK:
        await _drain(request)
        raise ApiError(413, "too_big")
    params = {k: v for k, v in request.query.items() if k in ("engine", "language", "context", "words")}
    ctype = request.content_type.lower()
    if ctype.startswith("multipart/"):
        data = None
        reader = await request.multipart()
        while True:
            part = await reader.next()
            if part is None:
                break
            if not isinstance(part, BodyPartReader):
                raise ApiError(400, "bad_request")
            if part.name == "audio":
                data = await _read_capped(lambda: part.read_chunk(65536), limits.STT_BYTES)
            elif part.name in ("engine", "language", "context", "words"):
                raw = await _read_capped(lambda: part.read_chunk(256), 64, "bad_request")
                params[part.name] = raw.decode("utf-8", "replace").strip()
            else:
                await part.release()
        if data is None:
            raise ApiError(400, "bad_request", "The request needs an audio part.")
        return data, params
    if ctype.startswith("audio/") or ctype in ("video/webm", "video/mp4", "application/octet-stream"):
        return await _read_capped(lambda: request.content.read(65536), limits.STT_BYTES), params
    raise ApiError(400, "bad_request", "Send the audio as multipart form data with a part named audio.")


async def health(request: web.Request) -> web.Response:
    app = request.app
    stt, tts, gpu = app[STT_KEY], app[TTS_KEY], app[GPU_KEY]
    if request.query.get("warm") in ("1", "true"):
        await asyncio.gather(stt.warm(), tts.warm())
        await gpu.refresh()
    body = {
        "status": "ok", "version": VERSION,
        "limits": {"stt_seconds": limits.STT_SECONDS, "stt_bytes": limits.STT_BYTES, "tts_chars": limits.TTS_CHARS},
        "stt": stt.health(), "tts": tts.health(), "engines": stt.engines(), "gpu_free_mib": gpu.read(),
    }
    return web.json_response(body, headers={"Cache-Control": "no-store"})


async def stt_route(request: web.Request) -> web.Response:
    meta = request[META_KEY]
    _check_token(request)
    data, params = await _read_stt_request(request)
    meta["bytes"] = len(data)
    engine = (params.get("engine") or "whisper").lower()
    if engine not in ENGINES:
        raise ApiError(400, "bad_request", "Unknown engine.")
    if (params.get("language") or "en").lower() != "en":
        raise ApiError(400, "bad_request", "Only English (en) is supported.")
    context = (params.get("context") or "").lower() or None
    if context is not None and context not in text_norm.CONTEXTS:
        raise ApiError(400, "bad_request", "Unknown context.")
    words = (params.get("words") or "0").lower() in ("1", "true")
    meta["engine"] = engine
    if engine == "cohere":
        raise ApiError(503, "engine_unavailable")
    t0 = time.perf_counter()
    if audio_io.sniff(data) is None:
        raise ApiError(415, "unsupported_audio")
    loop = asyncio.get_running_loop()
    try:
        audio, duration = await loop.run_in_executor(None, audio_io.decode, data)
    except audio_io.TooLong:
        raise ApiError(413, "too_long") from None
    except audio_io.DecodeError:
        raise ApiError(415, "unsupported_audio") from None
    meta["audio_s"] = round(duration, 2)
    svc: SttService = request.app[STT_KEY]
    try:
        svc.check_not_loading(engine)
    except Loading:
        raise ApiError(503, "loading") from None
    async with request.app[STT_SLOT_KEY]:
        try:
            result = await svc.transcribe(audio, duration, engine, words, context)
        except Unavailable:
            raise ApiError(503, "engine_unavailable") from None
    if result["engine"] is None:  # the engine was not run (no speech): name the one that would have run
        h = svc.health() if engine != "parakeet" else {"engine": "parakeet-tdt-0.6b-v2", "device": "cpu"}
        result["engine"], result["device"] = h["engine"], h["device"]
    took = int((time.perf_counter() - t0) * 1000)
    meta["engine"], meta["device"] = result["engine"], result["device"]
    body = {k: result[k] for k in ("text", "segments", "language", "duration", "speech_seconds", "engine", "device")}
    body["took_ms"] = took
    body["code"] = result["code"]
    return web.json_response(body, headers={"Cache-Control": "no-store"})


async def tts_route(request: web.Request) -> web.Response:
    meta = request[META_KEY]
    _check_token(request)
    if request.content_length is not None and request.content_length > limits.TTS_BODY_BYTES:
        await _drain(request)
        raise ApiError(413, "too_big")
    raw = await _read_capped(lambda: request.content.read(65536), limits.TTS_BODY_BYTES)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ApiError(400, "bad_request", "The body must be JSON.") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("text", ""), str):
        raise ApiError(400, "bad_request")
    text = payload.get("text", "")
    if not text.strip():
        raise ApiError(400, "empty_text")
    if len(text) > limits.TTS_CHARS:
        raise ApiError(413, "text_too_long")
    voice = payload.get("voice") or "af_heart"
    if voice not in VOICES:
        raise ApiError(400, "bad_voice")
    speed = payload.get("speed", 1.0)
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not limits.SPEEDS[0] <= speed <= limits.SPEEDS[1]:
        raise ApiError(400, "bad_request", "Speed must be between 0.8 and 1.25.")
    normalise = payload.get("normalise", True)
    if not isinstance(normalise, bool) or payload.get("format", "wav") != "wav":
        raise ApiError(400, "bad_request")
    svc: TtsService = request.app[TTS_KEY]
    meta["engine"] = "kokoro"
    if svc.state == "loading":
        raise ApiError(503, "loading")
    t0 = time.perf_counter()
    async with request.app[TTS_SLOT_KEY]:
        try:
            wav, seconds = await svc.synthesise(text, voice, float(speed), normalise)
        except Unavailable:
            raise ApiError(503, "engine_unavailable") from None
        except EmptyText:
            raise ApiError(400, "empty_text") from None
    took = int((time.perf_counter() - t0) * 1000)
    meta.update(audio_s=round(seconds, 2), device=svc.device, bytes=len(wav))
    return web.Response(body=wav, content_type="audio/wav",
                        headers={"X-Took-Ms": str(took), "X-Sample-Rate": str(limits.TTS_SAMPLE_RATE),
                                 "Cache-Control": "no-store"})


@web.middleware
async def middleware(request: web.Request, handler):
    request[META_KEY] = meta = {"audio_s": None, "engine": None, "device": None, "bytes": 0}
    t0 = time.perf_counter()
    status = 500
    try:
        resp = await handler(request)
        status = resp.status
        return resp
    except ApiError as e:
        status = e.status
        return _error_response(e.status, e.code, e.message)
    except web.HTTPException as e:
        status = e.status
        if e.status == 404:
            return _error_response(404, "not_found")
        if e.status >= 400:
            return _error_response(e.status, "bad_request")
        raise
    except asyncio.CancelledError:
        status = 499
        raise
    except Exception as e:
        LOG.error("route=%s error=%s", request.path, type(e).__name__)  # the class name only, never the content
        status = 500
        return _error_response(500, "failed")
    finally:
        if request.path in ("/stt", "/tts"):
            LOG.info("route=%s status=%d audio_s=%s engine=%s device=%s took_ms=%d bytes=%d", request.path, status,
                     meta["audio_s"], meta["engine"], meta["device"], int((time.perf_counter() - t0) * 1000),
                     meta["bytes"])


def make_app(token: str, device: str = "auto", warm: bool = False, stt_service: SttService | None = None,
             tts_service: TtsService | None = None) -> web.Application:
    if not token:
        raise ValueError("a token is required")
    app = web.Application(client_max_size=limits.STT_BYTES + MULTIPART_SLACK, middlewares=[middleware])
    app[TOKEN_KEY] = token
    app[STT_KEY] = stt_service or SttService(device, LOG)
    app[TTS_KEY] = tts_service or TtsService(device, LOG)
    app[STT_SLOT_KEY], app[TTS_SLOT_KEY] = Slot(), Slot()
    app[GPU_KEY] = GpuProbe()
    app.router.add_get("/health", health)
    app.router.add_post("/stt", stt_route)
    app.router.add_post("/tts", tts_route)

    async def start_warm(app):
        async def go():
            await asyncio.gather(app[STT_KEY].warm(), app[TTS_KEY].warm())
        app[WARM_KEY] = asyncio.create_task(go())

    async def stop_warm(app):
        t = app.get(WARM_KEY)
        if t and not t.done():
            t.cancel()

    if warm:
        app.on_startup.append(start_warm)
        app.on_cleanup.append(stop_warm)
    return app
