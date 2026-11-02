"""Sniffing and decoding of browser audio, in memory only (no temporary file, no disk).

A RIFF/WAVE body is decoded with the standard library and numpy (so the unit tests run without PyAV); every other container
goes through PyAV from a BytesIO. The result is float32 mono at 16 kHz."""
from __future__ import annotations

import io
import struct

import numpy as np

from . import limits

RATE = limits.STT_SAMPLE_RATE


class DecodeError(Exception):
    """The audio could not be decoded."""


class TooLong(Exception):
    """The audio is longer than the cap."""


def sniff(data: bytes) -> str | None:
    """The container type from the first bytes ('wav', 'webm', 'mp4', 'ogg', 'mp3', 'flac'), or None. Headers are not trusted."""
    if len(data) < 4:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if data[4:8] == b"ftyp":
        return "mp4"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:4] == b"fLaC":
        return "flac"
    if data[:3] == b"ID3" or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "mp3"
    return None


def _resample(x: np.ndarray, rate: int) -> np.ndarray:
    if rate == RATE or x.size == 0:
        return x.astype(np.float32, copy=False)
    n = int(round(x.size * RATE / rate))
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    src = np.arange(x.size, dtype=np.float64) / rate
    dst = np.arange(n, dtype=np.float64) / RATE
    return np.interp(dst, src, x).astype(np.float32)


def _decode_wav(data: bytes, max_seconds: float) -> tuple[np.ndarray, float]:
    pos, fmt, body = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        start = pos + 8
        if cid == b"fmt ":
            if size < 16 or start + 16 > len(data):
                raise DecodeError("bad fmt chunk")
            tag, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", data, start)
            if tag == 0xFFFE and size >= 40 and start + 26 <= len(data):
                tag = struct.unpack_from("<H", data, start + 24)[0]  # first two bytes of the sub-format GUID
            fmt = (tag, channels, rate, bits)
        elif cid == b"data":
            body = data[start:min(len(data), start + size)]  # a streamed WAV may declare a size past the end
            break
        pos = start + size + (size & 1)
    if fmt is None or body is None:
        raise DecodeError("no fmt or data chunk")
    tag, channels, rate, bits = fmt
    if not (1 <= channels <= 8 and 1000 <= rate <= 384000):
        raise DecodeError("bad channels or rate")
    width = bits // 8
    if bits % 8 or width not in (1, 2, 3, 4, 8):
        raise DecodeError("bad sample width")
    frames = len(body) // (width * channels)
    duration = frames / rate
    if duration >= max_seconds:
        raise TooLong()
    body = body[:frames * width * channels]
    if tag == 1 and width == 1:
        x = (np.frombuffer(body, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif tag == 1 and width == 2:
        x = np.frombuffer(body, dtype="<i2").astype(np.float32) / 32768.0
    elif tag == 1 and width == 3:
        b = np.frombuffer(body, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        x = v.astype(np.float32) / float(1 << 23)
    elif tag == 1 and width == 4:
        x = np.frombuffer(body, dtype="<i4").astype(np.float32) / float(1 << 31)
    elif tag == 3 and width == 4:
        x = np.frombuffer(body, dtype="<f4").astype(np.float32)
    elif tag == 3 and width == 8:
        x = np.frombuffer(body, dtype="<f8").astype(np.float32)
    else:
        raise DecodeError("unsupported WAV encoding")
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    return _resample(x, rate), duration


def _decode_av(data: bytes, max_seconds: float) -> tuple[np.ndarray, float]:
    try:
        import av  # PyAV, in the audio venv only
    except ImportError as e:
        raise DecodeError("no decoder for this container") from e
    limit = int(max_seconds * RATE)
    parts: list[np.ndarray] = []
    total = 0
    try:
        with av.open(io.BytesIO(data), mode="r") as container:
            if not container.streams.audio:
                raise DecodeError("no audio stream")
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="flt", layout="mono", rate=RATE)
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    arr = out.to_ndarray().reshape(-1).astype(np.float32, copy=False)
                    parts.append(arr)
                    total += arr.size
                if total >= limit:
                    raise TooLong()
            for out in resampler.resample(None):
                arr = out.to_ndarray().reshape(-1).astype(np.float32, copy=False)
                parts.append(arr)
                total += arr.size
    except (TooLong, DecodeError):
        raise
    except Exception as e:
        raise DecodeError(type(e).__name__) from e
    if total >= limit:
        raise TooLong()
    x = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    return x, x.size / RATE


def decode(data: bytes, max_seconds: float | None = None) -> tuple[np.ndarray, float]:
    """(float32 mono 16 kHz samples, duration in seconds). Raises DecodeError, or TooLong at 61 s or more (no engine is run
    for either)."""
    max_seconds = limits.STT_TOLERANCE_SECONDS if max_seconds is None else max_seconds
    kind = sniff(data)
    if kind is None:
        raise DecodeError("unknown container")
    if kind == "wav":
        return _decode_wav(data, max_seconds)
    return _decode_av(data, max_seconds)


def wav_bytes(samples: np.ndarray, rate: int) -> bytes:
    """A mono 16-bit PCM WAV in memory from float samples in [-1, 1]."""
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ", 16, 1, 1, rate, rate * 2, 2, 16,
                         b"data", len(pcm))
    return header + pcm
