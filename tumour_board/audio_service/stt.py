"""Speech to text: Silero VAD first, then faster-whisper large-v3-turbo (fp16 on the GPU, as shipped) or Parakeet-TDT-0.6B-v2
(fp32 ONNX, CPU) as the fallback. Audio stays in memory; nothing is written. Cohere stays off (engine_unavailable)."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import numpy as np

from . import limits, text_norm

WHISPER_REPO = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
PARAKEET_REPO = "istupakov/parakeet-tdt-0.6b-v2-onnx"
WHISPER_NAME = "whisper-large-v3-turbo"
PARAKEET_NAME = "parakeet-tdt-0.6b-v2"
FALLBACK_LABEL = "parakeet-v2-cpu"
VAD_PARAMS = {"threshold": 0.5, "min_silence_duration_ms": 500, "min_speech_duration_ms": 250, "speech_pad_ms": 400}
ENGINES = ("whisper", "parakeet", "cohere")


class Unavailable(Exception):
    """The engine cannot run (load failed, or switched off)."""


class Loading(Exception):
    """The engine is being loaded by another request."""


def hub_snapshot(repo: str) -> Path:
    """The local snapshot folder of a cached Hugging Face repo. Never downloads."""
    hub = Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME") or Path.home() / ".cache/huggingface") / "hub")
    base = hub / ("models--" + repo.replace("/", "--"))
    ref = base / "refs" / "main"
    if ref.is_file():
        snap = base / "snapshots" / ref.read_text(encoding="utf-8").strip()
        if snap.is_dir():
            return snap
    snaps = sorted((base / "snapshots").glob("*"), key=lambda p: p.stat().st_mtime) if (base / "snapshots").is_dir() else []
    if not snaps:
        raise FileNotFoundError(f"model {repo} is not in the local cache")
    return snaps[-1]


def keep_segment(no_speech_prob: float, avg_logprob: float) -> bool:
    """Whisper's silence guard: drop a segment that is probably not speech and decoded with low confidence."""
    return not (no_speech_prob > 0.6 and avg_logprob < -1.0)


class SileroVad:
    """The Silero VAD bundled with faster-whisper (CPU, about 2 MB)."""

    def __init__(self):
        from faster_whisper.vad import VadOptions, get_speech_timestamps, get_vad_model
        get_vad_model()
        self._opts = VadOptions(**VAD_PARAMS)
        self._ts = get_speech_timestamps

    def speech_seconds(self, audio: np.ndarray) -> float:
        if audio.size == 0:
            return 0.0
        spans = self._ts(audio, self._opts, sampling_rate=limits.STT_SAMPLE_RATE)
        return sum(s["end"] - s["start"] for s in spans) / limits.STT_SAMPLE_RATE


class WhisperEngine:
    name = WHISPER_NAME

    def __init__(self, device: str):
        from faster_whisper import WhisperModel
        self.device = device
        self.precision = "float16" if device == "cuda" else "float32"
        self.model = WhisperModel(str(hub_snapshot(WHISPER_REPO)), device=device, compute_type=self.precision,
                                  cpu_threads=limits.CPU_THREADS if device == "cpu" else 0)
        if device == "cuda":  # one tiny decode so a missing CUDA library shows now, not at the first dictation
            segs, _ = self.model.transcribe(np.zeros(limits.STT_SAMPLE_RATE, dtype=np.float32), language="en", beam_size=1,
                                            vad_filter=False, without_timestamps=True)
            list(segs)

    def run(self, audio: np.ndarray, words: bool, prompt: str) -> list[dict]:
        segments, _info = self.model.transcribe(
            audio, language="en", beam_size=5, condition_on_previous_text=False, vad_filter=True,
            vad_parameters=dict(VAD_PARAMS), initial_prompt=prompt, word_timestamps=words, no_speech_threshold=0.6,
            log_prob_threshold=-1.0)
        out = []
        for s in segments:
            if not keep_segment(s.no_speech_prob, s.avg_logprob):
                continue
            seg = {"start": round(float(s.start), 2), "end": round(float(s.end), 2), "text": s.text.strip()}
            if words and s.words:
                seg["words"] = [{"start": round(float(w.start), 2), "end": round(float(w.end), 2), "word": w.word.strip(),
                                 "probability": round(float(w.probability), 3)} for w in s.words]
            out.append(seg)
        return out


class ParakeetEngine:
    name = PARAKEET_NAME
    device = "cpu"
    precision = "float32"

    def __init__(self):
        import onnx_asr
        self.model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v2", str(hub_snapshot(PARAKEET_REPO)),
                                         providers=["CPUExecutionProvider"])

    def run(self, audio: np.ndarray, words: bool, prompt: str) -> list[dict]:
        text = str(self.model.recognize(audio, sample_rate=limits.STT_SAMPLE_RATE)).strip()
        if not text:
            return []
        return [{"start": 0.0, "end": round(audio.size / limits.STT_SAMPLE_RATE, 2), "text": text}]


# Factories: the unit tests replace these with stubs.
def load_vad():
    return SileroVad()


def load_whisper(device: str):
    return WhisperEngine(device)


def load_parakeet():
    return ParakeetEngine()


class _Holder:
    def __init__(self):
        self.state = "not_loaded"
        self.obj = None
        self.lock = asyncio.Lock()


class SttService:
    """Lazy, load-once engines. The server holds the one-job slot; this class only loads and runs."""

    def __init__(self, device_pref: str = "auto", log=None):
        self.device_pref = device_pref
        self.log = log
        self.vad, self.whisper, self.parakeet = _Holder(), _Holder(), _Holder()
        self.primary = "whisper"        # becomes "parakeet" when Whisper cannot go on the GPU
        self.fallback_reason: str | None = None
        self.whisper_device = "cpu" if device_pref == "cpu" else "cuda"

    def _holder(self, name: str) -> _Holder:
        return {"vad": self.vad, "whisper": self.whisper, "parakeet": self.parakeet}[name]

    def _pick_whisper_device(self) -> str | None:
        """'cuda' or 'cpu' for Whisper, or None when Parakeet should take over (no GPU room in auto mode)."""
        if self.device_pref == "cpu":
            return "cpu"
        if self.device_pref == "cuda":
            return "cuda"
        free = limits.gpu_free_mib()
        if free is not None and free >= limits.STT_GPU_MIN_MIB:
            return "cuda"
        self.fallback_reason = "no_gpu" if free is None else "low_gpu_memory"
        return None

    def _load_sync(self, name: str):
        if name == "vad":
            return load_vad()
        if name == "parakeet":
            return load_parakeet()
        device = self._pick_whisper_device()
        if device is None:
            raise Unavailable(self.fallback_reason or "no_gpu")
        self.whisper_device = device
        return load_whisper(device)

    async def ensure(self, name: str) -> None:
        h = self._holder(name)
        if h.state == "ready":
            return
        async with h.lock:
            if h.state == "ready":
                return
            if h.state == "error" and name != "whisper":
                raise Unavailable(name)
            h.state = "loading"
            try:
                h.obj = await asyncio.get_running_loop().run_in_executor(None, self._load_sync, name)
                h.state = "ready"
                if self.log:
                    self.log.info("loaded engine=%s device=%s", name, getattr(h.obj, "device", "cpu"))
            except Exception as e:
                h.state, h.obj = "error", None
                if self.log:
                    self.log.warning("load failed engine=%s error=%s", name, type(e).__name__)
                if name == "whisper":
                    if not isinstance(e, Unavailable):
                        self.fallback_reason = "gpu_load_failed"
                    self.primary = "parakeet"
                    raise Unavailable(name) from None
                raise Unavailable(name) from None

    async def ensure_primary(self) -> str:
        """Load the default engine (Whisper, or Parakeet when Whisper cannot load); returns its name."""
        if self.primary == "whisper":
            try:
                await self.ensure("whisper")
                return "whisper"
            except Unavailable:
                pass
        await self.ensure("parakeet")
        return "parakeet"

    async def warm(self) -> None:
        for step in (lambda: self.ensure("vad"), self.ensure_primary):
            try:
                await step()
            except Unavailable:
                pass

    def check_not_loading(self, engine: str) -> None:
        name = "parakeet" if engine == "parakeet" else self.primary
        if self._holder(name).state == "loading" or self.vad.state == "loading":
            raise Loading()

    async def transcribe(self, audio: np.ndarray, duration: float, engine: str, words: bool, context: str | None) -> dict:
        """VAD, then the engine, then the clean-up. Runs inside the server's STT slot."""
        loop = asyncio.get_running_loop()
        await self.ensure("vad")
        speech = await loop.run_in_executor(None, self.vad.obj.speech_seconds, audio)
        result = {"text": "", "segments": [], "language": "en", "duration": round(duration, 2),
                  "speech_seconds": round(speech, 2), "engine": None, "device": None, "code": None}
        if speech < limits.MIN_SPEECH_SECONDS:
            result["code"] = "no_speech"
            return result
        if engine == "parakeet":
            await self.ensure("parakeet")
            name = "parakeet"
        else:
            name = await self.ensure_primary()
        eng = self._holder(name).obj
        result["engine"], result["device"] = eng.name, eng.device
        segments = await loop.run_in_executor(None, eng.run, audio, words, text_norm.prompt_for(context))
        tidy = []
        for seg in segments:
            t = seg["text"]
            if name == "parakeet":
                t = text_norm.inverse_numbers(t)
            t = text_norm.clean_transcript(t)
            if t:
                tidy.append({**seg, "text": t})
        text = " ".join(s["text"] for s in tidy).strip()
        if not text or text_norm.is_repetitive(text):
            result["code"] = "no_speech"
            return result
        result["text"], result["segments"] = text, tidy
        return result

    def health(self) -> dict:
        if self.primary == "whisper":
            dev = self.whisper_device
            out = {"engine": WHISPER_NAME, "state": self.whisper.state, "device": dev,
                   "precision": "float16" if dev == "cuda" else "float32", "fallback": FALLBACK_LABEL}
        else:
            out = {"engine": PARAKEET_NAME, "state": self.parakeet.state, "device": "cpu", "precision": "float32",
                   "fallback": FALLBACK_LABEL, "fallback_reason": self.fallback_reason}
        return out

    def engines(self) -> dict:
        return {"cohere": "unavailable", "parakeet": self.parakeet.state}
