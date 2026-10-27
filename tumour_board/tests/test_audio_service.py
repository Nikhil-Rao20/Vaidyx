"""The audio service (night-v3 item 4.1): routes, caps, sniffing, the "nothing stored" rule, the text normaliser and the
STT clean-up. The engines are stubbed, so this runs in the app venv (no PyAV, no models, no GPU). Synthetic audio only."""
import asyncio
import builtins
import io
import json
import logging
import os
import re
import struct
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from tumour_board.audio_service import __main__ as audio_main
from tumour_board.audio_service import audio_io, limits, server, stt, text_norm, tts

TOKEN = "a1" * 24
HDR = {"X-Audio-Token": TOKEN}
PKG_DIR = Path(server.__file__).resolve().parent


# ------------------------------------------------------------------------------------------------------------ helpers

def make_wav(x, rate=16000, bits=16, channels=1, tag=1, extensible=False) -> bytes:
    """A WAV in memory from float samples in [-1, 1] (mono; repeated per channel)."""
    x = np.asarray(x, dtype=np.float64)
    if channels > 1:
        x = np.repeat(x[:, None], channels, axis=1).reshape(-1)
    if tag == 3:
        body = x.astype("<f4" if bits == 32 else "<f8").tobytes()
    elif bits == 8:
        body = (np.clip(x, -1, 1) * 127 + 128).astype(np.uint8).tobytes()
    elif bits == 16:
        body = (np.clip(x, -1, 1) * 32767).astype("<i2").tobytes()
    elif bits == 24:
        v = (np.clip(x, -1, 1) * (2 ** 23 - 1)).astype("<i4")
        body = b"".join(int(s).to_bytes(4, "little", signed=True)[:3] for s in v)
    else:
        body = (np.clip(x, -1, 1) * (2 ** 31 - 1)).astype("<i4").tobytes()
    block = channels * bits // 8
    if extensible:
        fmt = struct.pack("<HHIIHHHHI", 0xFFFE, channels, rate, rate * block, block, bits, 22, bits, 0)
        fmt += struct.pack("<H", tag) + b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"
    else:
        fmt = struct.pack("<HHIIHH", tag, channels, rate, rate * block, block, bits)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(body)) + body
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


def tone(seconds, freq=220.0, rate=16000, amp=0.4):
    t = np.arange(int(seconds * rate)) / rate
    return amp * np.sin(2 * np.pi * freq * t)


def noise(seconds, rate=16000):
    return np.random.default_rng(7).normal(0, 0.3, int(seconds * rate)).clip(-1, 1)


class StubVad:
    """Stands in for Silero: 20 ms frames that are loud and tonal (low spectral flatness) count as speech, so silence and white
    noise give no speech while a tone does."""

    def speech_seconds(self, audio):
        n = 320
        frames = audio[: audio.size // n * n].reshape(-1, n) if audio.size >= n else np.zeros((0, n))
        speech = 0
        for f in frames:
            if np.sqrt(np.mean(f ** 2)) < 0.01:
                continue
            p = np.abs(np.fft.rfft(f)) ** 2 + 1e-12
            if np.exp(np.mean(np.log(p))) / np.mean(p) < 0.1:
                speech += 1
        return speech * n / 16000


class StubSttEngine:
    text = "Stub transcript."
    delay = 0.0

    def __init__(self, name, device, calls):
        self.name, self.device, self.calls = name, device, calls
        self.precision = "float16" if device == "cuda" else "float32"

    def run(self, audio, words, prompt):
        self.calls["run"].append({"engine": self.name, "words": words, "prompt": prompt})
        if self.delay:
            time.sleep(self.delay)
        return [{"start": 0.0, "end": round(audio.size / 16000, 2), "text": type(self).text}]


class StubKokoro:
    fallback_on = True

    def __init__(self, device, calls):
        self.device, self.calls = device, calls

    def render(self, chunk, voice, speed):
        self.calls["chunks"].append(chunk)
        return np.full(len(chunk) * 240, 0.1, dtype=np.float32)  # 10 ms per character


@pytest.fixture
def calls(monkeypatch):
    c = {"vad": 0, "whisper": 0, "parakeet": 0, "kokoro": 0, "run": [], "chunks": []}

    def load_vad():
        c["vad"] += 1
        return StubVad()

    def load_whisper(device):
        c["whisper"] += 1
        return StubSttEngine(stt.WHISPER_NAME, device, c)

    def load_parakeet():
        c["parakeet"] += 1
        return StubSttEngine(stt.PARAKEET_NAME, "cpu", c)

    def load_kokoro(device):
        c["kokoro"] += 1
        return StubKokoro(device, c)

    monkeypatch.setattr(stt, "load_vad", load_vad)
    monkeypatch.setattr(stt, "load_whisper", load_whisper)
    monkeypatch.setattr(stt, "load_parakeet", load_parakeet)
    monkeypatch.setattr(tts, "load_kokoro", load_kokoro)
    monkeypatch.setattr(limits, "gpu_free_mib", lambda: 20000)
    monkeypatch.setattr(StubSttEngine, "text", "Stub transcript.")
    monkeypatch.setattr(StubSttEngine, "delay", 0.0)
    return c


@pytest.fixture
async def client(calls):
    async with TestClient(TestServer(server.make_app(TOKEN))) as c:
        yield c


async def post_stt(client, data, params=None, headers=HDR, ctype="audio/wav"):
    return await client.post("/stt", data=data, params=params or {}, headers={**headers, "Content-Type": ctype})


def assert_error(body, code):
    assert set(body) == {"code", "message"}
    assert body["code"] == code
    assert body["message"] and "\u2014" not in body["message"]


# ------------------------------------------------------------------------------------------------------------ /health

async def test_health_shape_and_loads_nothing(client, calls):
    t0 = time.perf_counter()
    r = await client.get("/health")
    elapsed = time.perf_counter() - t0
    assert r.status == 200
    h = await r.json()
    assert h["status"] == "ok" and h["version"] == "1"
    assert h["limits"] == {"stt_seconds": 60, "stt_bytes": 4194304, "tts_chars": 2000}
    assert h["stt"]["engine"] == "whisper-large-v3-turbo" and h["stt"]["state"] == "not_loaded"
    assert h["stt"]["precision"] == "float16" and h["stt"]["device"] == "cuda" and h["stt"]["fallback"] == "parakeet-v2-cpu"
    assert h["tts"]["engine"] == "kokoro-82m" and h["tts"]["state"] == "not_loaded" and h["tts"]["sample_rate"] == 24000
    assert h["tts"]["voices"] == ["af_heart", "bf_emma", "am_michael"]
    assert h["engines"] == {"cohere": "unavailable", "parakeet": "not_loaded"}
    assert "gpu_free_mib" in h
    assert (calls["vad"], calls["whisper"], calls["parakeet"], calls["kokoro"]) == (0, 0, 0, 0)
    assert elapsed < 0.5


async def test_health_warm_loads_both_engines(client, calls):
    h = await (await client.get("/health", params={"warm": "1"})).json()
    assert h["stt"]["state"] == "ready" and h["stt"]["device"] == "cuda"
    assert h["tts"]["state"] == "ready" and h["tts"]["device"] == "cuda" and h["tts"]["espeak_fallback"] == "on"
    assert h["gpu_free_mib"] == 20000
    assert (calls["whisper"], calls["kokoro"], calls["parakeet"]) == (1, 1, 0)


async def test_low_gpu_memory_loads_on_the_cpu(client, calls, monkeypatch):
    monkeypatch.setattr(limits, "gpu_free_mib", lambda: 1000)
    h = await (await client.get("/health", params={"warm": "1"})).json()
    assert h["stt"]["engine"] == "parakeet-tdt-0.6b-v2" and h["stt"]["device"] == "cpu"
    assert h["stt"]["fallback_reason"] == "low_gpu_memory"
    assert h["tts"]["device"] == "cpu" and h["engines"]["parakeet"] == "ready"
    assert calls["whisper"] == 0


async def test_whisper_gpu_failure_falls_back_to_parakeet(client, calls, monkeypatch):
    def broken(device):
        raise RuntimeError("cuDNN missing")
    monkeypatch.setattr(stt, "load_whisper", broken)
    r = await post_stt(client, make_wav(tone(2)))
    body = await r.json()
    assert r.status == 200 and body["engine"] == "parakeet-tdt-0.6b-v2" and body["device"] == "cpu"
    h = await (await client.get("/health")).json()
    assert h["stt"]["fallback_reason"] == "gpu_load_failed"


# ------------------------------------------------------------------------------------------------------------ token

async def test_token_required(client, calls):
    wav = make_wav(tone(1))
    r = await post_stt(client, wav, headers={})
    assert r.status == 401
    assert_error(await r.json(), "no_token")
    r = await post_stt(client, wav, headers={"X-Audio-Token": "wrong" * 10})
    assert r.status == 401
    r = await client.post("/tts", json={"text": "Hello."})
    assert r.status == 401
    assert_error(await r.json(), "no_token")
    assert calls["run"] == [] and calls["chunks"] == []
    assert (await post_stt(client, wav)).status == 200
    assert (await client.post("/tts", json={"text": "Hello."}, headers=HDR)).status == 200


def test_main_refuses_a_missing_token_file_and_names_the_path_only(tmp_path, capsys):
    missing = tmp_path / "nope.json"
    assert audio_main.main(["--port", "7199", "--token-file", str(missing)]) == 2
    err = capsys.readouterr().err
    assert str(missing) in err


def test_main_binds_loopback_only(capsys):
    assert audio_main.main(["--host", "0.0.0.0"]) == 2


def test_read_token(tmp_path):
    good = tmp_path / "t.json"
    good.write_text(json.dumps({"token": TOKEN}))
    assert audio_main.read_token(str(good)) == TOKEN
    bad = tmp_path / "b.json"
    bad.write_text("{not json")
    assert audio_main.read_token(str(bad)) is None
    short = tmp_path / "s.json"
    short.write_text(json.dumps({"token": "abc"}))
    assert audio_main.read_token(str(short)) is None


# ------------------------------------------------------------------------------------------------------------ caps

async def test_61_second_tone_is_too_long_and_no_engine_runs(client, calls):
    r = await post_stt(client, make_wav(tone(61)))
    assert r.status == 413
    assert_error(await r.json(), "too_long")
    assert calls["vad"] == 0 and calls["run"] == []


async def test_59_second_tone_is_accepted(client, calls):
    r = await post_stt(client, make_wav(tone(59, rate=8000), rate=8000))
    assert r.status == 200
    assert (await r.json())["duration"] == pytest.approx(59, abs=0.01)


async def test_5_mb_body_is_too_big(client, calls):
    r = await post_stt(client, b"RIFF" + os.urandom(5 * 1024 * 1024))
    assert r.status == 413
    assert_error(await r.json(), "too_big")
    assert calls["run"] == []


async def test_5_mb_multipart_part_is_too_big(client, calls):
    form = FormData()
    form.add_field("audio", b"\x1a\x45\xdf\xa3" + bytes(5 * 1024 * 1024), filename="clip.webm", content_type="audio/webm")
    r = await client.post("/stt", data=form, headers=HDR)
    assert r.status == 413
    assert_error(await r.json(), "too_big")


async def test_random_bytes_are_unsupported(client, calls):
    r = await post_stt(client, bytes(range(7, 250)) * 40)
    assert r.status == 415
    assert_error(await r.json(), "unsupported_audio")


async def test_a_known_container_that_does_not_decode_is_unsupported(client, calls):
    r = await post_stt(client, b"\x1a\x45\xdf\xa3" + b"\x00garbage" * 50, ctype="audio/webm")
    assert r.status == 415
    assert calls["run"] == []


# ------------------------------------------------------------------------------------------------------------ sniffing and decoding

@pytest.mark.parametrize("head,kind", [
    (b"RIFF\x24\x00\x00\x00WAVEfmt ", "wav"),
    (b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81", "webm"),
    (b"\x00\x00\x00\x20ftypM4A ", "mp4"),
    (b"\x00\x00\x00\x1cftypisom", "mp4"),
    (b"OggS\x00\x02\x00\x00", "ogg"),
    (b"ID3\x04\x00\x00\x00\x00", "mp3"),
    (b"\xff\xfb\x90\x64\x00\x00", "mp3"),
    (b"fLaC\x00\x00\x00\x22", "flac"),
    (b"RIFF\x24\x00\x00\x00AVI LIST", None),
    (b"%PDF-1.7", None),
    (b"\x00\x01", None),
])
def test_sniff_by_first_bytes(head, kind):
    assert audio_io.sniff(head) == kind


@pytest.mark.parametrize("bits,tag", [(8, 1), (16, 1), (24, 1), (32, 1), (32, 3), (64, 3)])
def test_decode_wav_sample_formats(bits, tag):
    x = tone(0.5)
    y, dur = audio_io.decode(make_wav(x, bits=bits, tag=tag))
    assert dur == pytest.approx(0.5) and y.dtype == np.float32 and y.size == x.size
    assert np.max(np.abs(y - x)) < (0.02 if bits == 8 else 1e-3)


def test_decode_wav_stereo_resampled_and_extensible():
    x = tone(1.0, rate=44100)
    y, dur = audio_io.decode(make_wav(x, rate=44100, channels=2, extensible=True))
    assert dur == pytest.approx(1.0, abs=1e-3)
    assert y.size == 16000
    assert np.max(np.abs(y)) == pytest.approx(0.4, abs=0.01)


def test_decode_rejects_a_broken_wav():
    with pytest.raises(audio_io.DecodeError):
        audio_io.decode(b"RIFF\x10\x00\x00\x00WAVEjunkjunkjunk")


def test_wav_bytes_round_trip():
    data = audio_io.wav_bytes(np.full(2400, 0.5, dtype=np.float32), 24000)
    with wave.open(io.BytesIO(data)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 24000, 2400)


# ------------------------------------------------------------------------------------------------------------ /stt

async def test_silence_gives_no_speech_and_the_engine_is_never_called(client, calls):
    r = await post_stt(client, make_wav(np.zeros(16000 * 3)))
    body = await r.json()
    assert r.status == 200 and body["text"] == "" and body["code"] == "no_speech" and body["segments"] == []
    assert calls["run"] == [] and calls["whisper"] == 0


async def test_white_noise_gives_no_speech_and_the_engine_is_never_called(client, calls):
    r = await post_stt(client, make_wav(noise(3)))
    body = await r.json()
    assert r.status == 200 and body["text"] == "" and body["code"] == "no_speech"
    assert calls["run"] == [] and calls["whisper"] == 0


async def test_speech_is_transcribed_and_cleaned(client, calls, monkeypatch):
    monkeypatch.setattr(StubSttEngine, "text", "Staged MRT3BN1, Ki-67 40 per cent, Hb 9.8 g d l.")
    r = await post_stt(client, make_wav(tone(4)))
    body = await r.json()
    assert r.status == 200
    assert body["text"] == "Staged mrT3b N1, Ki-67 40%, Hb 9.8 g/dL."
    assert list(body) == ["text", "segments", "language", "duration", "speech_seconds", "engine", "device", "took_ms", "code"]
    assert body["code"] is None and body["language"] == "en" and body["engine"] == "whisper-large-v3-turbo"
    assert body["duration"] == pytest.approx(4.0) and body["speech_seconds"] > 3
    assert isinstance(body["took_ms"], int)
    assert calls["run"][0]["prompt"] == text_norm.prompt_for(None)


async def test_multipart_with_fields(client, calls):
    form = FormData()
    form.add_field("audio", make_wav(tone(2)), filename="clip.wav", content_type="audio/webm")
    form.add_field("engine", "whisper")
    form.add_field("language", "en")
    form.add_field("context", "decision")
    form.add_field("words", "1")
    r = await client.post("/stt", data=form, headers=HDR)
    assert r.status == 200
    assert calls["run"][0]["words"] is True
    assert calls["run"][0]["prompt"] == text_norm.prompt_for("decision")


async def test_parakeet_engine_turns_spoken_numbers_into_digits(client, calls, monkeypatch):
    monkeypatch.setattr(StubSttEngine, "text", "haemoglobin eleven point eight platelets two hundred forty five thousand")
    r = await post_stt(client, make_wav(tone(2)), params={"engine": "parakeet"})
    body = await r.json()
    assert body["engine"] == "parakeet-tdt-0.6b-v2" and body["device"] == "cpu"
    assert body["text"] == "haemoglobin 11.8 platelets 245,000"


async def test_a_repeated_loop_is_dropped(client, calls, monkeypatch):
    monkeypatch.setattr(StubSttEngine, "text", "thank you so thank you so thank you so thank you so")
    body = await (await post_stt(client, make_wav(tone(2)))).json()
    assert body["text"] == "" and body["code"] == "no_speech"


@pytest.mark.parametrize("params,status,code", [
    ({"language": "hi"}, 400, "bad_request"),
    ({"engine": "google"}, 400, "bad_request"),
    ({"context": "diagnosis"}, 400, "bad_request"),
    ({"engine": "cohere"}, 503, "engine_unavailable"),
])
async def test_bad_parameters(client, calls, params, status, code):
    r = await post_stt(client, make_wav(tone(1)), params=params)
    assert r.status == status
    assert_error(await r.json(), code)
    assert calls["run"] == []


async def test_multipart_without_an_audio_part(client, calls):
    form = FormData()
    form.add_field("engine", "whisper")
    r = await client.post("/stt", data=form, headers=HDR)
    assert r.status == 400
    assert_error(await r.json(), "bad_request")


async def test_json_body_is_refused(client, calls):
    r = await client.post("/stt", json={"audio": "x"}, headers=HDR)
    assert r.status == 400


async def test_loading_answers_503(client, calls):
    client.server.app[server.STT_KEY].whisper.state = "loading"
    r = await post_stt(client, make_wav(tone(1)))
    assert r.status == 503
    assert_error(await r.json(), "loading")


async def test_unknown_route_is_json(client, calls):
    r = await client.get("/nope")
    assert r.status == 404
    assert_error(await r.json(), "not_found")


# ------------------------------------------------------------------------------------------------------------ concurrency

async def test_busy_when_more_than_four_wait(client, calls, monkeypatch):
    monkeypatch.setattr(StubSttEngine, "delay", 0.3)
    wav = make_wav(tone(1))
    first = asyncio.create_task(post_stt(client, wav))
    while not calls["run"]:
        await asyncio.sleep(0.01)
    rest = [asyncio.create_task(post_stt(client, wav)) for _ in range(5)]
    responses = [await first] + [await t for t in rest]
    statuses = sorted(r.status for r in responses)
    assert statuses == [200] * 5 + [429]
    busy = [r for r in responses if r.status == 429][0]
    assert_error(await busy.json(), "busy")


async def test_busy_after_waiting_too_long(client, calls, monkeypatch):
    monkeypatch.setattr(StubSttEngine, "delay", 1.0)
    monkeypatch.setattr(limits, "WAIT_SECONDS", 0.2)
    wav = make_wav(tone(1))
    first = asyncio.create_task(post_stt(client, wav))
    while not calls["run"]:
        await asyncio.sleep(0.01)
    second = await post_stt(client, wav)
    assert second.status == 429
    assert (await first).status == 200
    assert (await post_stt(client, make_wav(tone(1)))).status in (200, 429)  # the slot was given back


# ------------------------------------------------------------------------------------------------------------ /tts

async def test_tts_returns_a_wav_and_reads_the_normalised_text(client, calls):
    r = await client.post("/tts", json={"text": "Haemoglobin 11.8 g/dL. Dr Kavita.", "voice": "bf_emma", "speed": 1.1},
                          headers=HDR)
    assert r.status == 200 and r.content_type == "audio/wav"
    assert r.headers["X-Sample-Rate"] == "24000" and int(r.headers["X-Took-Ms"]) >= 0
    with wave.open(io.BytesIO(await r.read())) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        assert w.getnframes() > 0
    assert calls["chunks"] == ["Haemoglobin eleven point eight grams per decilitre.", "Doctor Kavita."]


async def test_tts_normalise_false_reads_the_text_as_given(client, calls):
    r = await client.post("/tts", json={"text": "11.8 g/dL", "normalise": False}, headers=HDR)
    assert r.status == 200 and calls["chunks"] == ["11.8 g/dL"]


async def test_tts_long_text_is_split_under_the_phoneme_limit(client, calls):
    text = ("Capecitabine and oxaliplatin were discussed with the Responsible Department, " * 40)[:1990] + "."
    r = await client.post("/tts", json={"text": text}, headers=HDR)
    assert r.status == 200
    assert len(calls["chunks"]) > 5
    assert all(len(c) <= tts.CHUNK_CHARS for c in calls["chunks"])
    assert all(len(c) * 1.5 < 510 for c in calls["chunks"])  # a generous character-to-phoneme proxy


@pytest.mark.parametrize("payload,status,code", [
    ({"text": "   "}, 400, "empty_text"),
    ({"text": "x" * 2001}, 413, "text_too_long"),
    ({"text": "Hello.", "voice": "af_bella"}, 400, "bad_voice"),
    ({"text": "Hello.", "speed": 2.0}, 400, "bad_request"),
    ({"text": "Hello.", "speed": True}, 400, "bad_request"),
    ({"text": "Hello.", "format": "mp3"}, 400, "bad_request"),
    ({"text": 42}, 400, "bad_request"),
])
async def test_tts_errors(client, calls, payload, status, code):
    r = await client.post("/tts", json=payload, headers=HDR)
    assert r.status == status
    assert_error(await r.json(), code)
    assert calls["chunks"] == []


async def test_tts_bad_json(client, calls):
    r = await client.post("/tts", data=b"{not json", headers={**HDR, "Content-Type": "application/json"})
    assert r.status == 400
    assert_error(await r.json(), "bad_request")


# ------------------------------------------------------------------------------------------------------------ nothing stored

SECRET = "Zephyrine Quillborough asked about capecitabine 7461"


async def test_log_line_holds_no_text_and_no_filename(client, calls, monkeypatch, tmp_path):
    monkeypatch.setattr(StubSttEngine, "text", SECRET)
    log_file = tmp_path / "audio.log"
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    lg = logging.getLogger("tb.audio")
    lg.addHandler(handler)
    old = lg.level
    lg.setLevel(logging.INFO)
    try:
        form = FormData()
        form.add_field("audio", make_wav(tone(2)), filename="Quillborough_secret_clip.wav", content_type="audio/wav")
        r = await client.post("/stt", data=form, headers=HDR)
        assert (await r.json())["text"] == SECRET
        assert (await client.post("/tts", json={"text": SECRET}, headers=HDR)).status == 200
        assert (await client.post("/tts", json={"text": SECRET, "voice": "nobody"}, headers=HDR)).status == 400
    finally:
        lg.removeHandler(handler)
        lg.setLevel(old)
        handler.close()
    log = log_file.read_text(encoding="utf-8")
    lines = [l for l in log.splitlines() if "route=" in l]
    assert len(lines) == 3
    assert "route=/stt status=200" in lines[0] and "engine=whisper-large-v3-turbo" in lines[0] and "took_ms=" in lines[0]
    assert "route=/tts status=200" in lines[1] and "bytes=" in lines[1] and "audio_s=" in lines[1]
    for word in ("Zephyrine", "Quillborough", "capecitabine", "7461", "secret_clip", ".wav"):
        assert word not in log


async def test_nothing_is_written_to_disk(client, calls, monkeypatch, tmp_path):
    monkeypatch.setattr(StubSttEngine, "text", SECRET)
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)

    def refuse(*a, **k):
        raise AssertionError("the audio service tried to write a file")

    real_open, real_os_open = builtins.open, os.open

    def guarded_open(file, mode="r", *a, **k):
        if any(c in mode for c in "wax+"):
            refuse()
        return real_open(file, mode, *a, **k)

    def guarded_os_open(path, flags, *a, **k):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC):
            refuse()
        return real_os_open(path, flags, *a, **k)

    for name in ("NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile", "mkstemp", "mkdtemp", "TemporaryDirectory"):
        monkeypatch.setattr(tempfile, name, refuse)
    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_open)
    monkeypatch.setattr(os, "open", guarded_os_open)
    form = FormData()
    form.add_field("audio", make_wav(tone(2)), filename="clip.wav", content_type="audio/wav")
    r1 = await client.post("/stt", data=form, headers=HDR)
    r2 = await client.post("/tts", json={"text": SECRET}, headers=HDR)
    monkeypatch.undo()
    assert r1.status == 200 and (await r1.json())["text"] == SECRET
    assert r2.status == 200
    assert list(work.iterdir()) == []
    for path in PKG_DIR.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes(), path


def test_source_never_writes_files():
    for path in PKG_DIR.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        for bad in ("tempfile", "write_bytes", "write_text", "mkstemp", "NamedTemporaryFile", "pickle", ".save("):
            assert bad not in src, (path.name, bad)
        for m in re.finditer(r"open\(([^)]*)\)", src):
            assert not re.search(r"""["'][rwab+]*[wa+][rwab+]*["']""", m.group(1)), (path.name, m.group(0))
    main_src = (PKG_DIR / "__main__.py").read_text(encoding="utf-8")
    assert "access_log=None" in main_src
    assert main_src.index('os.environ["HF_HUB_OFFLINE"] = "1"') < main_src.index("from .server import")


# ------------------------------------------------------------------------------------------------------------ TTS normaliser

OCTOBER = "Haemoglobin 11.8 g/dL, platelets 245,000 per microlitre. Capecitabine and oxaliplatin from 14/09/2026, Dr Kavita."


def test_normaliser_october_sentence():
    assert text_norm.normalise_for_speech(OCTOBER) == (
        "Haemoglobin eleven point eight grams per decilitre, platelets two hundred and forty-five thousand per microlitre. "
        "Capecitabine and oxaliplatin from fourteenth of September, twenty twenty-six, Doctor Kavita.")


@pytest.mark.parametrize("src,spoken", [
    ("11.8 g/dL", "eleven point eight grams per decilitre"),
    ("0.9 mg/dL", "zero point nine milligrams per decilitre"),
    ("500 mg twice", "500 milligrams twice"),
    ("dose in mg", "dose in milligrams"),
    ("1 mg", "1 milligram"),
    ("25 mL", "25 millilitres"),
    ("245,000/µL", "two hundred and forty-five thousand per microlitre"),
    ("4,500 per mcL", "four thousand five hundred per microlitre"),
    ("2,45,000", "two lakh forty-five thousand"),
    ("1 cm lesion, 3 x 2 cm", "1 centimetre lesion, 3 by 2 centimetres"),
    ("12 mm", "12 millimetres"),
    ("PD-L1 TPS 60%", "P D L 1 T P S 60 percent"),
    ("SUVmax 12.4", "S U V max twelve point four"),
    ("mrT3b N1", "m r T 3 b, N 1"),
    ("cT3 N2 M0", "c T 3, N 2, M 0"),
    ("ypT2 N0", "y p T 2, N 0"),
    ("T3N2M0", "T 3, N 2, M 0"),
    ("14/09/2026", "fourteenth of September, twenty twenty-six"),
    ("01/10/2005", "first of October, two thousand and five"),
    ("31/02/2026", "31/02/2026"),
    ("ER positive, PR negative, HER2 3+", "E R positive, P R negative, H E R 2 3 plus"),
    ("ER/PR positive", "E R, P R positive"),
    ("ER+", "E R positive"),
    ("the ER team", "the ER team"),
    ("ECOG 1, UHID", "E C O G 1, U H I D"),
    ("PET-CT and MRI, then CT", "pet C T and M R I, then C T"),
    ("HPE and IHC", "H P E and I H C"),
    ("PM-JAY Reg. No. 12", "P M jay registration number 12"),
    ("Dr Kavita and Dr. Venkatesh", "Doctor Kavita and Doctor Venkatesh"),
    ("UHID VXH/2026/00123", "U H I D VXH/2026/00123"),
])
def test_normaliser_cases(src, spoken):
    assert text_norm.normalise_for_speech(src) == spoken


def test_normaliser_is_deterministic_and_leaves_the_input_alone():
    src = str(OCTOBER)
    assert text_norm.normalise_for_speech(src) == text_norm.normalise_for_speech(src)
    assert src == OCTOBER


def test_lexicon_covers_the_words_kokoro_dropped():
    for word in ("mg", "SUVmax", "Reg", "Kavita", "decilitre", "microlitre", "immunohistochemistry", "capecitabine",
                 "oxaliplatin", "trastuzumab", "pembrolizumab", "osimertinib", "letrozole", "tamoxifen", "paclitaxel",
                 "docetaxel", "carboplatin", "bevacizumab", "temozolomide", "imatinib", "Venkatesh", "Priya",
                 "Thiruvananthapuram", "Visakhapatnam", "Bengaluru", "Guwahati", "Bhubaneswar", "Coimbatore", "Kathua",
                 "Rajouri", "Poonch"):
        assert text_norm.LEXICON.get(word), word
    vocab = set("AIOWYbdfhijklmnpstuvwzæðŋɑɔəɛɜɡɪɹɾʃʊʌʒʤʧˈˌθᵊᵻʔ")  # misaki US_VOCAB
    for word, ps in text_norm.LEXICON.items():
        assert set(ps) <= vocab, word


def test_drug_and_indian_names_pass_the_normaliser_unchanged():
    s = "Kavita from Guwahati: capecitabine, oxaliplatin, trastuzumab, pembrolizumab."
    assert text_norm.normalise_for_speech(s) == s


@pytest.mark.parametrize("n,words", [
    (0, "zero"), (7, "seven"), (45, "forty-five"), (100, "one hundred"), (105, "one hundred and five"),
    (1005, "one thousand and five"), (245000, "two hundred and forty-five thousand"),
    (1200000, "one million two hundred thousand"),
])
def test_number_to_words(n, words):
    assert text_norm.number_to_words(n) == words


def test_ordinals_and_years():
    assert [text_norm.ordinal_words(d) for d in (1, 2, 3, 12, 20, 22, 30, 31)] == [
        "first", "second", "third", "twelfth", "twentieth", "twenty-second", "thirtieth", "thirty-first"]
    assert text_norm.year_words(2026) == "twenty twenty-six"
    assert text_norm.year_words(2000) == "two thousand"
    assert text_norm.year_words(1999) == "nineteen ninety-nine"
    assert text_norm.year_words(1905) == "nineteen oh five"
    assert text_norm.number_to_words(12500000, indian=True) == "one crore twenty-five lakh"


def test_split_for_tts_limits():
    text = "One. Two!\n\nThree? " + "word " * 200 + "x" * 700
    chunks = text_norm.split_for_tts(text, 300)
    assert chunks[:3] == ["One.", "Two!", "Three?"]
    assert all(0 < len(c) <= 300 for c in chunks)
    assert "".join(c.replace(" ", "") for c in chunks) == text.replace(" ", "").replace("\n", "")


# ------------------------------------------------------------------------------------------------------------ STT clean-up

@pytest.mark.parametrize("src,clean", [
    ("MRT3BN1", "mrT3b N1"),
    ("MRT3BN1M0", "mrT3b N1 M0"),
    ("c t 3 n 2", "cT3 N2"),
    ("ct3n2m0", "cT3 N2 M0"),
    ("T3N2M0", "T3 N2 M0"),
    ("yp T2 N0", "ypT2 N0"),
    ("MrT3b, N1 on MRI", "mrT3b N1 on MRI"),
    ("staged MRT3B on MRI", "staged mrT3b on MRI"),
    ("CT3 alone", "cT3 alone"),
    ("ECOG1, HER2 equivocal", "ECOG 1, HER2 equivocal"),
    ("the T3 and N1 status", "the T3 and N1 status"),
    ("Ki-67 40 per cent", "Ki-67 40%"),
    ("PD-L1 60 percent", "PD-L1 60%"),
    ("haemoglobin 9.8 g d l", "haemoglobin 9.8 g/dL"),
    ("creatinine 1.1 mg/dl", "creatinine 1.1 mg/dL"),
    ("Haemoglobin 11.8 g/dL, platelets 245,000", "Haemoglobin 11.8 g/dL, platelets 245,000"),
    # learned from the voice check (item 4.5): the engine writes spoken forms the house format does not use
    ("from 14th of September, 2026, Dr. Kavita", "from 14/09/2026, Dr. Kavita"),
    ("seen on 3 March 2026 and 31st October 2025", "seen on 03/03/2026 and 31/10/2025"),
    ("September 2026 alone stays", "September 2026 alone stays"),
    ("under PMJ is pending, EC OG1", "under PM-JAY is pending, ECOG 1"),
    ("PMJAY and PM Jay and EC OG 2", "PM-JAY and PM-JAY and ECOG 2"),
    ("Haemoglobin 11.8 g per deciliter", "Haemoglobin 11.8 g/dL"),
    ("11.8 grams per decilitre, creatinine 1.1 milligrams per decilitre", "11.8 g/dL, creatinine 1.1 mg/dL"),
    ("creatinine 0.9 mg per deciliter", "creatinine 0.9 mg/dL"),
    ("the scan is due by 4-11-2026 and 30-10-2026", "the scan is due by 04/11/2026 and 30/10/2026"),
    ("approved on 2410-2026, imaging 1501-2027", "approved on 24/10/2026, imaging 15/01/2027"),
    ("a lot number 4599-2026 stays", "a lot number 4599-2026 stays"),
    ("HER23 plus on IHC, PDL1TPS 60%, PD L1 negative", "HER2 3+ on IHC, PD-L1 TPS 60%, PD-L1 negative"),
])
def test_clean_transcript(src, clean):
    assert text_norm.clean_transcript(src) == clean


def test_clean_transcript_never_adds_a_word():
    for src in ("MRT3BN1 seen on MRI", "c t 3 n 2 m 0 with nodes", "hemoglobin 9 point 8", "spelling as spoken haemoglobin",
                "the patient is a T2 at most", "ECOG 1 in OPD"):
        out = text_norm.clean_transcript(src)
        assert re.sub(r"[^a-z0-9]", "", out.lower()) == re.sub(r"[^a-z0-9]", "", src.lower())


@pytest.mark.parametrize("src,digits", [
    ("eleven point eight", "11.8"),
    ("two hundred forty five thousand", "245,000"),
    ("two hundred and forty-five thousand platelets", "245,000 platelets"),
    ("three point five centimetres", "3.5 centimetres"),
    ("twenty twenty six", "2026"),
    ("two thousand and twenty six", "2026"),
    ("seventy two", "72"),
    ("two lakh forty five thousand", "245,000"),
    ("ECOG one", "ECOG one"),
    ("zero point nine", "0.9"),
])
def test_inverse_numbers(src, digits):
    assert text_norm.inverse_numbers(src) == digits


def test_is_repetitive():
    assert text_norm.is_repetitive("thank you so thank you so thank you so thank you so")
    assert text_norm.is_repetitive("the the the the")
    assert not text_norm.is_repetitive("cT3 N2 M0 on MRI, discussed at the board, the board agreed.")


def test_prompt_is_short_and_has_no_patient_data():
    for ctx in (None,) + text_norm.CONTEXTS:
        p = text_norm.prompt_for(ctx)
        assert len(p.split()) <= 30
        assert not re.search(r"VXH|UHID ?\d|IP/|OP/|\d{2}/\d{2}/\d{4}", p)
    assert text_norm.prompt_for("question") != text_norm.prompt_for("decision")


def test_keep_segment():
    assert stt.keep_segment(0.1, -0.2)
    assert stt.keep_segment(0.9, -0.5)
    assert stt.keep_segment(0.3, -1.5)
    assert not stt.keep_segment(0.7, -1.2)


def test_hub_snapshot_reads_the_local_cache_only(tmp_path, monkeypatch):
    snap = tmp_path / "models--org--model" / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    (tmp_path / "models--org--model" / "refs").mkdir()
    (tmp_path / "models--org--model" / "refs" / "main").write_text("abc123")
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    assert stt.hub_snapshot("org/model") == snap
    with pytest.raises(FileNotFoundError):
        stt.hub_snapshot("org/missing")


def test_gpu_free_mib_is_none_without_nvidia_smi(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    assert limits.gpu_free_mib() is None
