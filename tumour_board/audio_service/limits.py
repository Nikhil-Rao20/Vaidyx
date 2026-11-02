"""Caps of the audio service and the free GPU memory check (docs/night-v3/research/08_voice.md section 4)."""
from __future__ import annotations

import subprocess

STT_SECONDS = 60            # longest clip, after decoding
STT_TOLERANCE_SECONDS = 61  # encoder padding allowance: 61 s or more is too long
STT_BYTES = 4 * 1024 * 1024  # largest upload (the aiohttp client_max_size too)
TTS_CHARS = 2000            # longest text for one /tts call
TTS_BODY_BYTES = 64 * 1024  # largest JSON body for /tts
QUEUE_MAX = 4               # requests allowed to wait for a busy slot
WAIT_SECONDS = 10.0         # longest wait for the slot before 429 busy
MIN_SPEECH_SECONDS = 0.3    # under this much speech the engine is not run
SPEEDS = (0.8, 1.25)        # allowed TTS speed range

STT_GPU_MIN_MIB = 3072      # Whisper loads on the GPU only with this much free
TTS_GPU_MIN_MIB = 1536      # Kokoro loads on the GPU only with this much free

STT_SAMPLE_RATE = 16000
TTS_SAMPLE_RATE = 24000
CPU_THREADS = 16            # the CPU engines share a 64-core server


def gpu_free_mib() -> int | None:
    """Free memory of the first GPU in MiB from nvidia-smi, or None when there is no GPU or the query fails."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, check=True,
        ).stdout
        used, total = (int(float(x)) for x in out.strip().splitlines()[0].split(","))
        return max(0, total - used)
    except Exception:
        return None
