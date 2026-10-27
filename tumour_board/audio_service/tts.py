"""Text to speech: Kokoro-82M (the shipped kokoro-v1_0.pth, 24 kHz) behind the clinical normaliser and lexicon, espeak-ng as the
catch-all for unknown words, the CPU as the fallback. The audio is built in memory and returned; nothing is written."""
from __future__ import annotations

import asyncio
import os

import numpy as np

from . import audio_io, limits, text_norm
from .stt import Unavailable, hub_snapshot

KOKORO_REPO = "hexgrad/Kokoro-82M"
ENGINE_NAME = "kokoro-82m"
VOICES = ("af_heart", "bf_emma", "am_michael")
ESPEAK_LIB = "/data/vaidyx/tools/espeak-ng/lib64/libespeak-ng.so"
ESPEAK_DATA = "/data/vaidyx/tools/espeak-ng/share/espeak-ng-data"
GAP_SECONDS = 0.12        # a short pause between sentences
CHUNK_CHARS = 300         # characters per Kokoro call (well under its 510 phonemes)


class EmptyText(Exception):
    """Nothing left to read."""


class _ProbeToken:
    def __init__(self, text: str):
        self.text = text


class KokoroEngine:
    name = ENGINE_NAME

    def __init__(self, device: str):
        import misaki.espeak  # noqa: F401  its import points espeak at a wheel library that fails on this glibc
        from phonemizer.backend.espeak.wrapper import EspeakWrapper
        EspeakWrapper.set_library(os.environ.get("PHONEMIZER_ESPEAK_LIBRARY") or ESPEAK_LIB)
        EspeakWrapper.set_data_path(os.environ.get("ESPEAK_DATA_PATH") or ESPEAK_DATA)
        import torch
        from kokoro import KModel, KPipeline
        from loguru import logger
        logger.disable("kokoro")   # kokoro logs the text it reads at debug level: never let it reach the log
        logger.disable("misaki")
        self.device = device
        if device == "cpu":
            torch.set_num_threads(limits.CPU_THREADS)
        snap = hub_snapshot(KOKORO_REPO)
        model = KModel(repo_id=KOKORO_REPO, config=str(snap / "config.json"), model=str(snap / "kokoro-v1_0.pth"))
        model = model.to(device).eval()
        self.pipeline = KPipeline(lang_code="a", repo_id=KOKORO_REPO, model=model)
        for v in VOICES:
            self.pipeline.voices[v] = torch.load(str(snap / "voices" / f"{v}.pt"), weights_only=True)
        golds = self.pipeline.g2p.lexicon.golds
        for word, ps in text_norm.LEXICON.items():
            for key in {word, word.lower(), word.capitalize()}:
                golds[key] = ps
        self.fallback_on = self._probe_fallback()
        self._torch = torch

    def _probe_fallback(self) -> bool:
        fb = getattr(self.pipeline.g2p, "fallback", None)
        if fb is None:
            return False
        try:
            ps, _ = fb(_ProbeToken("zorbitane"))
            return bool(ps)
        except Exception:
            return False

    def render(self, chunk: str, voice: str, speed: float) -> np.ndarray:
        parts = []
        with self._torch.inference_mode():
            for r in self.pipeline(chunk, voice=voice, speed=speed, split_pattern=None):
                if r.audio is not None:
                    parts.append(r.audio.detach().cpu().numpy().astype(np.float32).reshape(-1))
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def load_kokoro(device: str):
    """Factory: the unit tests replace it with a stub."""
    return KokoroEngine(device)


class TtsService:
    def __init__(self, device_pref: str = "auto", log=None):
        self.device_pref = device_pref
        self.log = log
        self.state = "not_loaded"
        self.engine = None
        self.device = "cpu" if device_pref == "cpu" else "cuda"
        self.lock = asyncio.Lock()

    def _load_sync(self):
        device = self.device_pref
        if device == "auto":
            free = limits.gpu_free_mib()
            device = "cuda" if free is not None and free >= limits.TTS_GPU_MIN_MIB else "cpu"
        try:
            eng = load_kokoro(device)
        except Exception:
            if device != "cuda":
                raise
            if self.log:
                self.log.warning("load failed engine=kokoro device=cuda, loading on the CPU")
            device = "cpu"
            eng = load_kokoro(device)
        self.device = device
        return eng

    async def ensure(self) -> None:
        if self.state == "ready":
            return
        async with self.lock:
            if self.state == "ready":
                return
            if self.state == "error":
                raise Unavailable("kokoro")
            self.state = "loading"
            try:
                self.engine = await asyncio.get_running_loop().run_in_executor(None, self._load_sync)
                self.state = "ready"
                if self.log:
                    self.log.info("loaded engine=kokoro device=%s", self.device)
                    self.log.info("espeak-ng fallback: %s", "on" if getattr(self.engine, "fallback_on", False) else "off")
            except Exception as e:
                self.state, self.engine = "error", None
                if self.log:
                    self.log.warning("load failed engine=kokoro error=%s", type(e).__name__)
                raise Unavailable("kokoro") from None

    async def warm(self) -> None:
        try:
            await self.ensure()
        except Unavailable:
            pass

    def _render_all(self, chunks: list[str], voice: str, speed: float) -> np.ndarray:
        gap = np.zeros(int(GAP_SECONDS * limits.TTS_SAMPLE_RATE), dtype=np.float32)
        parts = []
        for chunk in chunks:
            audio = self.engine.render(chunk, voice, speed)
            if audio.size:
                if parts:
                    parts.append(gap)
                parts.append(audio)
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    async def synthesise(self, text: str, voice: str, speed: float, normalise: bool = True) -> tuple[bytes, float]:
        """(WAV bytes, seconds of audio). Runs inside the server's TTS slot."""
        spoken = text_norm.normalise_for_speech(text) if normalise else text
        chunks = text_norm.split_for_tts(spoken, CHUNK_CHARS)
        if not chunks:
            raise EmptyText()
        await self.ensure()
        audio = await asyncio.get_running_loop().run_in_executor(None, self._render_all, chunks, voice, speed)
        if audio.size == 0:
            raise EmptyText()
        return audio_io.wav_bytes(audio, limits.TTS_SAMPLE_RATE), audio.size / limits.TTS_SAMPLE_RATE

    def health(self) -> dict:
        fb = getattr(self.engine, "fallback_on", None)
        return {"engine": ENGINE_NAME, "state": self.state, "device": self.device, "sample_rate": limits.TTS_SAMPLE_RATE,
                "voices": list(VOICES), "espeak_fallback": None if fb is None else ("on" if fb else "off")}
