"""The voice check (night-v3 item 4.5, docs/night-v3/research/08_voice.md section 8.1): synthetic clinical sentences spoken by
Kokoro through the audio service's /tts, sent back to its /stt, and the text heard compared with the text written.

    /data/vaidyx/venv/app/bin/python -m tumour_board.eval.audio_eval [--label name] [--voices default|all] [--engines default|all]
                                                                      [--real] [--strict] [--limit n]

Needs the audio service on TB_AUDIO_URL (default http://127.0.0.1:7120); its token is read from tumour_board.config.AUDIO_TOKEN_FILE
and never printed. Only the standard library is used (urllib, wave, random), so no audio library is needed: /tts returns a WAV and
/stt takes it back as a raw audio/wav body.

Logged per sentence: the text heard, the strict word error rate (lower case, punctuation removed), the normalised word error rate
(spelling pairs such as haemoglobin / hemoglobin, "245,000" equal to "245 thousand", staging spacing and hyphens, unit words and
symbols, dates written in words), the exact-token score (the share of the sentence's must_keep tokens present in the service's
cleaned text, compared case-insensitively with hyphens and spaces inside a token ignored) and the latency of /tts and /stt. Also:
10 s of silence and 10 s of white noise must give no text with the code no_speech, a 62 s tone must be refused with 413 too_long,
the free GPU memory before and after, and the p50 / p95 latencies per engine and per voice.

--real sends the Svarah clips (at most 40) and the Common Voice Indian-accent clips (at most 16) already in the Hugging Face cache to
/stt and logs the word error rate per engine. Nothing is downloaded; the parquet files are read as data only (pyarrow; when this
interpreter has none, the audio venv's interpreter reads them in isolated mode).

The thresholds (strict WER at most 0.12, exact tokens at least 0.90, no text on silence or noise) are checks on a synthetic set
spoken by a synthetic voice. They are not an accuracy claim about real speech, real people or real recordings. They are printed as
pass or fail and only change the exit code with --strict.

Output: data/tumour_board/eval/audio_eval_<label>.json and one summary line starting "AUDIO:".
"""
from __future__ import annotations

import argparse
import base64
import glob
import io
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tumour_board import config  # noqa: E402
from tumour_board.audio_service.text_norm import clean_transcript, inverse_numbers  # noqa: E402  (pure, standard library only)

HERE = Path(__file__).resolve().parent
SENTENCES = HERE / "audio_sentences.json"
DEFAULT_URL = "http://127.0.0.1:7120"
VOICES = {"default": ["af_heart"], "all": ["af_heart", "bf_emma"]}
ENGINES = {"default": ["whisper"], "all": ["whisper", "parakeet", "cohere"]}
THRESHOLDS = {"strict_wer_max": 0.12, "exact_tokens_min": 0.90}
AUDIO_PY = "/data/vaidyx/venv/audio/bin/python"
HF_HUB = Path(os.environ.get("HF_HUB_CACHE") or Path.home() / ".cache/huggingface/hub")
REAL_SETS = {  # name: (snapshot glob, audio column, text column, filter column, filter text, at most)
    "svarah": ("datasets--ai4bharat--Svarah/snapshots/*/data/*.parquet", "audio_filepath", "text", None, None, 40),
    "commonvoice_indian": ("datasets--ishands--commonvoice-indian_accent/snapshots/*/data/*.parquet", "audio", "sentence", "accents",
                           "India", 16),
}

# ------------------------------------------------------------------------------------------------------------- words

_TOKEN = re.compile(r"[a-z0-9]+(?:[.,/'][a-z0-9]+)*%?|%")


def strict_words(text: str) -> list[str]:
    """Lower case, punctuation removed (a point, comma or slash inside a number or a ratio stays, as in 11.8, 245,000, g/dl)."""
    return _TOKEN.findall((text or "").lower().replace("’", "'"))


def edit_distance(ref: list[str], hyp: list[str]) -> int:
    """Levenshtein distance on word lists (substitutions, deletions and insertions all cost 1)."""
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1]


def wer(ref: list[str], hyp: list[str]) -> float:
    """Word error rate of one pair: edits / reference words (an empty reference gives 0 for an empty hypothesis, else 1)."""
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


# Spelling pairs counted as equal in the normalised rate, the system's form first. A sentence adds its own in "accept".
GLOBAL_ACCEPT = [
    ("haemoglobin", "hemoglobin"), ("tumour", "tumor"), ("tumours", "tumors"), ("leucocyte", "leukocyte"),
    ("microlitre", "microliter"), ("decilitre", "deciliter"), ("millilitre", "milliliter"), ("litre", "liter"),
    ("centimetre", "centimeter"), ("centimetres", "centimeters"), ("millimetre", "millimeter"), ("millimetres", "millimeters"),
    ("millimoles", "millimols"), ("oesophagus", "esophagus"), ("haematology", "hematology"), ("anaemia", "anemia"),
    ("oedema", "edema"), ("keratinising", "keratinizing"), ("randomised", "randomized"), ("versus", "vs"), ("dr", "doctor"),
    ("by", "x"),
    # compounds: the joined form is the canonical one (hyphens become spaces at the end of the normalisation)
    ("pmjay", "pm-jay", "pm jay"), ("pdl1", "pd-l1", "pd l1"), ("ki67", "ki-67", "ki 67"), ("her2", "her 2", "her-2"),
    ("petct", "pet-ct", "pet ct", "pet/ct"), ("followup", "follow-up", "follow up"),
    ("preauthorization", "pre-authorization", "pre-authorisation", "preauthorisation", "pre authorization"),
]
# Unit words to the symbols the records use (after the spelling pairs, so only one spelling is listed).
UNIT_WORDS = [
    (r"(?:grams?|g) per decilitre", "g/dl"), (r"(?:milligrams?|mg) per decilitre", "mg/dl"),
    (r"(?:nanograms?|ng) per millilitre", "ng/ml"), (r"(?:units?|u) per millilitre", "u/ml"), (r"(?:millimoles?|mmol) per litre", "mmol/l"), (r"milligrams?", "mg"), (r"centimetres?", "cm"),
    (r"millimetres?", "mm"), (r"millilitres?", "ml"), (r"(?:percent|per cent)", "%"),
]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
          "december"]
_ORDINALS = {w: i for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth "
    "seventeenth eighteenth nineteenth twentieth".split(), 1)}
_ORDINALS.update({"twenty " + w: 20 + i for w, i in list(_ORDINALS.items()) if i < 10})
_ORDINALS.update({"twenty-" + w: 20 + i for w, i in list(_ORDINALS.items()) if i < 10})
_ORDINALS.update({"thirtieth": 30, "thirty first": 31, "thirty-first": 31})
_MONTH = "(" + "|".join(MONTHS) + ")"
_DAY = r"(\d{1,2}|" + "|".join(sorted((re.escape(w) for w in _ORDINALS), key=len, reverse=True)) + r")(?:st|nd|rd|th)?"
_DATE_DMY = re.compile(r"(?<![\w/])" + _DAY + r"\s+(?:of\s+)?" + _MONTH + r",?\s+(\d{4})(?!\d)")
_DATE_MDY = re.compile(r"(?<![\w/])" + _MONTH + r"\s+" + _DAY + r",?\s+(\d{4})(?!\d)")
_DATE_SEP = re.compile(r"(?<![\d/.\-])(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})(?![\d])")
_STAGE_PRE = r"(?:yp|yc|mr|c|p|r|a|u)?"
_STAGE_GLUE = re.compile(r"(?<![a-z0-9])(" + _STAGE_PRE + r"t(?:is|x|[0-4][a-d]?\d?)(?:mi)?)[\s,\-]+(n(?:x|[0-3][a-c]?)(?:mi)?)"
                         r"(?:[\s,\-]+(m(?:x|[01][a-d]?)))?(?![a-z0-9])")


def _phrase(p: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(p.lower()) + r"(?![a-z0-9])")


def _day(s: str) -> int:
    return int(s) if s.isdigit() else _ORDINALS[s]


def _dmy(d: int, m: int, y: int) -> str:
    return f"{d:02d}/{m:02d}/{y}" if 1 <= d <= 31 and 1 <= m <= 12 else f"{d}/{m}/{y}"


def normalise_text(text: str, accept=()) -> str:
    """The text both sides go through before the normalised rate: the service's own clean-up, lower case, the spelling pairs,
    unit words to symbols, number words to digits, digit-group commas, lakh and thousand, DD/MM/YYYY however written, staging
    tokens glued ("mrT3b N1", "mrt3b-n1" and "MRT3BN1" become one token) and any other hyphen inside a word read as a space
    ("ER-positive" is "er positive")."""
    s = clean_transcript(text or "").lower().replace("’", "'")
    for group in list(GLOBAL_ACCEPT) + [tuple(a) for a in accept or ()]:
        canon = group[0].lower()
        for variant in group[1:]:
            s = _phrase(variant).sub(canon, s)
    for pat, sym in UNIT_WORDS:
        s = re.sub(r"(?<![a-z])" + pat + r"(?![a-z])", sym, s)
    s = re.sub(r"\b(m?g|ng|u|mmol)\s*/\s*(dl|ml|l)\b", r"\1/\2", s)
    s = _DATE_DMY.sub(lambda m: _dmy(_day(m.group(1)), MONTHS.index(m.group(2)) + 1, int(m.group(3))), s)
    s = _DATE_MDY.sub(lambda m: _dmy(_day(m.group(2)), MONTHS.index(m.group(1)) + 1, int(m.group(3))), s)
    s = inverse_numbers(s)
    s = _DATE_DMY.sub(lambda m: _dmy(_day(m.group(1)), MONTHS.index(m.group(2)) + 1, int(m.group(3))), s)  # a year said in words
    s = re.sub(r"(?<=\d),(?=\d)", "", s)
    s = re.sub(r"(\d+(?:\.\d+)?)\s+lakhs?(?:\s+(?:and\s+)?(\d{1,5})(?!\d))?",
               lambda m: str(int(round(float(m.group(1)) * 100000)) + int(m.group(2) or 0)), s)
    s = re.sub(r"(\d+)\s+thousand(?:\s+(?:and\s+)?(\d{1,3})(?!\d))?", lambda m: str(int(m.group(1)) * 1000 + int(m.group(2) or 0)), s)
    s = re.sub(r"(\d)\s+%", r"\1%", s)
    s = _DATE_SEP.sub(lambda m: _dmy(int(m.group(1)), int(m.group(2)), int(m.group(3))), s)
    for _ in range(2):
        s = _STAGE_GLUE.sub(lambda m: "".join(g for g in m.groups() if g), s)
    s = re.sub(r"(?<=[a-z0-9])-(?=[a-z0-9])", " ", s)
    return s


def normalised_words(text: str, accept=()) -> list[str]:
    return strict_words(normalise_text(text, accept))


# ------------------------------------------------------------------------------------------------------- exact tokens

def token_pattern(token: str) -> re.Pattern:
    """A must_keep token as a pattern: case-insensitive, any spaces or hyphens allowed between its characters (none required),
    and whole: "8" does not match inside "8.4" or "18", "11.8" not inside "211.8"."""
    chars = [c for c in token.lower() if c not in " -"]
    body = r"[\s\-]*".join(re.escape(c) for c in chars)
    return re.compile(r"(?<![a-z0-9])(?<!\d[.,/])" + body + r"(?![a-z0-9])(?![.,/]\d)", re.I)


def exact_tokens(must_keep, heard: str, any_form: bool = False, accept=()) -> tuple[int, int, list[str]]:
    """(found, total, missing) of the must_keep tokens in the service's cleaned text. any_form=True compares both after
    normalise_text (a date in words, "g per deciliter" for g/dL): a second number that tells a wrong value from another way of
    writing the right one; the exact score is the one the threshold reads."""
    found, missing = 0, []
    hay = normalise_text(heard or "", accept) if any_form else (heard or "")
    for tok in must_keep or ():
        if token_pattern(normalise_text(tok, accept) if any_form else tok).search(hay):
            found += 1
        else:
            missing.append(tok)
    return found, len(must_keep or ()), missing


# ------------------------------------------------------------------------------------------------------------- audio

def wav_from_samples(samples, rate: int = 16000) -> bytes:
    """A mono 16-bit PCM WAV in memory from integer samples (clipped to the 16-bit range)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(max(-32768, min(32767, int(x))).to_bytes(2, "little", signed=True) for x in samples))
    return buf.getvalue()


def silence_wav(seconds: float = 10.0, rate: int = 16000) -> bytes:
    return wav_from_samples([0] * int(round(seconds * rate)), rate)


def noise_wav(seconds: float = 10.0, rate: int = 16000, amplitude: int = 3000, seed: int = 7) -> bytes:
    rnd = random.Random(seed)
    return wav_from_samples([rnd.randint(-amplitude, amplitude) for _ in range(int(round(seconds * rate)))], rate)


def tone_wav(seconds: float = 62.0, rate: int = 16000, freq: float = 440.0, amplitude: int = 8000) -> bytes:
    n = int(round(seconds * rate))
    step = 2 * math.pi * freq / rate
    return wav_from_samples([amplitude * math.sin(step * i) for i in range(n)], rate)


def wav_seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as w:
        return w.getnframes() / float(w.getframerate())


# ------------------------------------------------------------------------------------------------------------- stats

def percentile(values, q: float):
    """Linear interpolation between the closest ranks (numpy's default); None for no values."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return round(xs[lo] if lo == hi else xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 2)


def aggregate(rows) -> dict:
    """Corpus-level rates of a set of rows: edits summed over reference words summed, tokens found over tokens wanted."""
    rows = [r for r in rows if r.get("heard") is not None]
    ref_s = sum(r["strict_ref_words"] for r in rows)
    ref_n = sum(r["norm_ref_words"] for r in rows)
    tok_t = sum(r["tokens_total"] for r in rows)
    return {
        "n": len(rows),
        "strict_wer": round(sum(r["strict_edits"] for r in rows) / ref_s, 4) if ref_s else None,
        "normalised_wer": round(sum(r["norm_edits"] for r in rows) / ref_n, 4) if ref_n else None,
        "exact_tokens": round(sum(r["tokens_found"] for r in rows) / tok_t, 4) if tok_t else None,
        "tokens_found": sum(r["tokens_found"] for r in rows), "tokens_total": tok_t,
        "exact_tokens_any_form": round(sum(r.get("tokens_found_any_form", 0) for r in rows) / tok_t, 4) if tok_t else None,
        "stt_ms_p50": percentile([r.get("stt_ms") for r in rows], 50), "stt_ms_p95": percentile([r.get("stt_ms") for r in rows], 95),
    }


def score_row(text: str, heard: str, must_keep=(), accept=()) -> dict:
    sr, sh = strict_words(text), strict_words(heard)
    nr, nh = normalised_words(text, accept), normalised_words(heard, accept)
    found, total, missing = exact_tokens(must_keep, heard)
    any_found = exact_tokens(must_keep, heard, any_form=True, accept=accept)[0]
    return {
        "strict_wer": round(wer(sr, sh), 4), "strict_edits": edit_distance(sr, sh), "strict_ref_words": len(sr),
        "normalised_wer": round(wer(nr, nh), 4), "norm_edits": edit_distance(nr, nh), "norm_ref_words": len(nr),
        "tokens_found": found, "tokens_total": total, "missing": missing, "tokens_found_any_form": any_found,
    }


def summary_line(agg: dict, silence_ok: bool, tts_p50) -> str:
    """The one line gate_summary.py and the logs read."""
    def f(v, nd):
        return "n/a" if v is None else f"{v:.{nd}f}"
    stt = "n/a" if agg.get("stt_ms_p50") is None else f"{agg['stt_ms_p50']:.0f}"
    tts = "n/a" if tts_p50 is None else f"{tts_p50:.0f}"
    return (f"AUDIO: strict WER {f(agg.get('strict_wer'), 3)}, normalised {f(agg.get('normalised_wer'), 3)}, "
            f"exact tokens {f(agg.get('exact_tokens'), 2)}, silence {'ok' if silence_ok else 'FAILED'}, {agg.get('n', 0)} sentences, "
            f"p50 stt {stt} ms, p50 tts {tts} ms")


def checks(agg: dict, silence_ok: bool, too_long_ok: bool) -> dict:
    """Pass or fail of each threshold (a check on a synthetic set, not an accuracy claim)."""
    sw, et = agg.get("strict_wer"), agg.get("exact_tokens")
    return {
        "strict_wer": sw is not None and sw <= THRESHOLDS["strict_wer_max"],
        "exact_tokens": et is not None and et >= THRESHOLDS["exact_tokens_min"],
        "silence_and_noise": bool(silence_ok),
        "over_60_s_refused": bool(too_long_ok),
    }


# -------------------------------------------------------------------------------------------------------------- HTTP

class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str = ""):
        super().__init__(f"{status} {code}")
        self.status, self.code, self.message = status, code, message


def read_token() -> str:
    """The audio service's shared token ({"token": "..."}), read from config.AUDIO_TOKEN_FILE; never printed."""
    try:
        with open(config.AUDIO_TOKEN_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("token") or "").strip() if isinstance(data, dict) else ""
    except (OSError, ValueError):
        return ""


class Client:
    def __init__(self, url: str, token: str, wait_s: float = 120.0):
        self.url, self.token, self.wait_s = url.rstrip("/"), token, wait_s

    def _once(self, method: str, path: str, body: bytes | None, ctype: str | None, timeout: float):
        req = urllib.request.Request(self.url + path, data=body, method=method)
        if ctype:
            req.add_header("Content-Type", ctype)
        if self.token:
            req.add_header("X-Audio-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers or {}), e.read()

    def call(self, method: str, path: str, body: bytes | None = None, ctype: str | None = None, timeout: float = 180.0):
        """One request; a 429 busy or a 503 loading is waited out (the orchestrator runs nothing else on the GPU meanwhile)."""
        t_end = time.monotonic() + self.wait_s
        while True:
            t0 = time.perf_counter()
            status, headers, data = self._once(method, path, body, ctype, timeout)
            wall = (time.perf_counter() - t0) * 1000
            if status < 400:
                return status, headers, data, wall
            try:
                err = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                err = {}
            code = str(err.get("code") or "")
            if (status == 429 or (status == 503 and code == "loading")) and time.monotonic() < t_end:
                time.sleep(2.0)
                continue
            raise ServiceError(status, code or "http_error", str(err.get("message") or ""))

    def health(self) -> dict:
        _, _, data, _ = self.call("GET", "/health", timeout=10)
        return json.loads(data.decode("utf-8"))

    def tts(self, text: str, voice: str) -> tuple[bytes, float | None, float]:
        body = json.dumps({"text": text, "voice": voice}).encode("utf-8")
        _, headers, data, wall = self.call("POST", "/tts", body, "application/json")
        took = headers.get("X-Took-Ms") or headers.get("x-took-ms")
        return data, (float(took) if took else None), wall

    def stt(self, audio: bytes, engine: str, ctype: str = "audio/wav") -> tuple[dict, float]:
        _, _, data, wall = self.call("POST", f"/stt?engine={engine}", audio, ctype)
        return json.loads(data.decode("utf-8")), wall


# --------------------------------------------------------------------------------------------------------- the runs

def run_synthetic(client: Client, sentences: list[dict], voices: list[str], engines: list[str], verbose=True):
    rows, tts_ms, unavailable = [], {v: [] for v in voices}, {}
    for voice in voices:
        for s in sentences:
            try:
                wav, took, wall = client.tts(s["text"], voice)
            except ServiceError as e:
                rows.append({"id": s["id"], "category": s["category"], "voice": voice, "engine": None, "error": f"tts {e.status} {e.code}"})
                continue
            tts_ms[voice].append(took if took is not None else wall)
            for engine in engines:
                if engine in unavailable:
                    continue
                row = {"id": s["id"], "category": s["category"], "voice": voice, "engine": engine, "text": s["text"],
                       "tts_ms": took, "tts_wall_ms": round(wall), "audio_seconds": round(wav_seconds(wav), 2)}
                try:
                    res, swall = client.stt(wav, engine)
                except ServiceError as e:
                    if e.code == "engine_unavailable":
                        unavailable[engine] = "not available"
                        if verbose:
                            print(f"engine {engine}: not available (the service says engine_unavailable); skipped")
                        continue
                    row.update(heard=None, error=f"stt {e.status} {e.code}")
                    rows.append(row)
                    continue
                heard = res.get("text") or ""
                row.update(heard=heard, stt_ms=res.get("took_ms"), stt_wall_ms=round(swall), stt_engine=res.get("engine"),
                           device=res.get("device"), code=res.get("code"))
                row.update(score_row(s["text"], heard, s.get("must_keep"), s.get("accept")))
                rows.append(row)
                if verbose:
                    mark = "ok  " if not row["missing"] and row["strict_wer"] <= THRESHOLDS["strict_wer_max"] else "LOOK"
                    print(f"{mark} {voice:8s} {engine:8s} {s['id']}  strict {row['strict_wer']:.3f} norm {row['normalised_wer']:.3f} "
                          f"tokens {row['tokens_found']}/{row['tokens_total']}" + (f" missing {row['missing']}" if row["missing"] else ""))
                    print(f"       said:  {s['text']}\n       heard: {heard}")
    return rows, tts_ms, unavailable


def run_guards(client: Client, engines: list[str], unavailable: dict) -> dict:
    """Silence and white noise give no text with no_speech; a 62 s tone is refused with 413 too_long."""
    out = {"silence": {}, "noise": {}, "too_long": None}
    clips = {"silence": silence_wav(10.0), "noise": noise_wav(10.0)}
    for name, clip in clips.items():
        for engine in engines:
            if engine in unavailable:
                continue
            try:
                res, _ = client.stt(clip, engine)
                out[name][engine] = {"text": res.get("text") or "", "code": res.get("code"),
                                     "ok": not (res.get("text") or "").strip() and res.get("code") == "no_speech"}
            except ServiceError as e:
                out[name][engine] = {"text": None, "code": e.code, "ok": False, "status": e.status}
    try:
        client.stt(tone_wav(62.0), engines[0] if engines else "whisper")
        out["too_long"] = {"status": 200, "code": None, "ok": False}
    except ServiceError as e:
        out["too_long"] = {"status": e.status, "code": e.code, "ok": e.status == 413 and e.code == "too_long"}
    out["ok"] = all(v["ok"] for k in ("silence", "noise") for v in out[k].values()) and bool(out["silence"])
    return out


# The reader of the cached parquet files, run in isolated mode (-I) by an interpreter that has pyarrow. It reads data only and
# prints one JSON line per clip: the audio bytes (base64), the transcript and the clip's name. Nothing is written to disk.
READER = r"""
import base64, glob, json, sys
import pyarrow.parquet as pq
pattern, acol, tcol, fcol, ftext, n = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], int(sys.argv[6])
files = sorted(glob.glob(pattern))
if not files:
    sys.exit(3)
cols = [acol, tcol] + ([fcol] if fcol else [])
t = pq.ParquetFile(files[0]).read(columns=cols)
texts = t.column(tcol).to_pylist()
keep = [i for i, x in enumerate(texts) if x and x.strip()]
if fcol:
    flt = t.column(fcol).to_pylist()
    keep = [i for i in keep if flt[i] and ftext in flt[i]]
step = max(1, len(keep) // n) if keep else 1
pick = keep[::step][:n]
audio = t.column(acol)
for i in pick:
    a = audio[i].as_py() or {}
    data = a.get("bytes") or b""
    if not data:
        continue
    print(json.dumps({"name": str(a.get("path") or i), "text": texts[i], "audio": base64.b64encode(data).decode("ascii")}))
"""


def _reader_python() -> str | None:
    try:
        import pyarrow.parquet  # noqa: F401
        return sys.executable
    except ImportError:
        return AUDIO_PY if os.access(AUDIO_PY, os.X_OK) else None


def read_real_clips(name: str) -> tuple[list[dict], str | None]:
    pattern, acol, tcol, fcol, ftext, n = REAL_SETS[name]
    full = str(HF_HUB / pattern)
    if not glob.glob(full):
        return [], f"{name}: no cached parquet under {HF_HUB} (nothing is downloaded)"
    py = _reader_python()
    if py is None:
        return [], f"{name}: no pyarrow in this interpreter or in {AUDIO_PY}; skipped"
    p = subprocess.run([py, "-I", "-c", READER, full, acol, tcol, fcol or "", ftext or "", str(n)], capture_output=True, text=True,
                       timeout=600, cwd="/")
    if p.returncode != 0:
        return [], f"{name}: the parquet reader failed (exit {p.returncode}); skipped"
    clips = []
    for line in p.stdout.splitlines():
        try:
            d = json.loads(line)
            clips.append({"name": d["name"], "text": d["text"], "audio": base64.b64decode(d["audio"])})
        except (ValueError, KeyError):
            continue
    return clips, None


def _ctype(data: bytes) -> str:
    if data[:4] == b"RIFF":
        return "audio/wav"
    if data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if data[:4] == b"fLaC":
        return "audio/flac"
    if data[:4] == b"OggS":
        return "audio/ogg"
    return "application/octet-stream"


def run_real(client: Client, engines: list[str], unavailable: dict, verbose=True) -> dict:
    out = {}
    for name in REAL_SETS:
        clips, note = read_real_clips(name)
        if note:
            out[name] = {"skipped": note}
            if verbose:
                print("real:", note)
            continue
        per = {}
        for engine in engines:
            if engine in unavailable:
                per[engine] = {"skipped": "not available"}
                continue
            rows = []
            for c in clips:
                try:
                    res, _ = client.stt(c["audio"], engine, _ctype(c["audio"]))
                except ServiceError as e:
                    if e.code == "engine_unavailable":
                        unavailable[engine] = "not available"
                        break
                    rows.append({"name": c["name"], "error": f"{e.status} {e.code}"})
                    continue
                heard = res.get("text") or ""
                r = {"name": c["name"], "text": c["text"], "heard": heard, "stt_ms": res.get("took_ms")}
                r.update(score_row(c["text"], heard))
                rows.append(r)
            if engine in unavailable:
                per[engine] = {"skipped": "not available"}
                continue
            agg = aggregate(rows)
            per[engine] = {"clips": len(clips), "errors": sum(1 for r in rows if "error" in r), "strict_wer": agg["strict_wer"],
                           "normalised_wer": agg["normalised_wer"], "stt_ms_p50": agg["stt_ms_p50"], "stt_ms_p95": agg["stt_ms_p95"],
                           "rows": rows}
            if verbose:
                print(f"real {name} {engine}: {len(clips)} clips, strict WER {agg['strict_wer']}, normalised {agg['normalised_wer']}, "
                      f"p50 {agg['stt_ms_p50']} ms")
        out[name] = per
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="current")
    ap.add_argument("--voices", choices=sorted(VOICES), default="default", help="default: af_heart; all: af_heart and bf_emma")
    ap.add_argument("--engines", choices=sorted(ENGINES), default="default", help="default: whisper; all: whisper, parakeet, cohere")
    ap.add_argument("--real", action="store_true", help="also the cached Svarah and Common Voice Indian-accent clips")
    ap.add_argument("--strict", action="store_true", help="exit 1 when a threshold is not met")
    ap.add_argument("--limit", type=int, default=0, help="only the first n sentences (a quick look)")
    ap.add_argument("--url", default=os.environ.get("TB_AUDIO_URL") or DEFAULT_URL)
    ap.add_argument("--sentences", default=str(SENTENCES))
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    verbose = not a.quiet

    sentences = json.loads(Path(a.sentences).read_text(encoding="utf-8"))["sentences"]
    if a.limit:
        sentences = sentences[: a.limit]
    token = read_token()
    if not token:
        print("audio_eval: the audio token file is missing or unreadable (tumour_board.config.AUDIO_TOKEN_FILE)", file=sys.stderr)
        return 2
    client = Client(a.url, token)
    try:
        before = client.health()
    except (ServiceError, OSError) as e:
        print(f"audio_eval: the audio service does not answer on {a.url} ({type(e).__name__})", file=sys.stderr)
        return 2
    voices, engines = VOICES[a.voices], ENGINES[a.engines]
    if before.get("engines", {}).get("cohere") == "unavailable" and "cohere" in engines:
        engines = [e for e in engines if e != "cohere"]
        unavailable = {"cohere": "not available"}
        if verbose:
            print("engine cohere: not available (the service reports it unavailable); skipped")
    else:
        unavailable = {}
    t0 = time.time()
    rows, tts_ms, more = run_synthetic(client, sentences, voices, engines, verbose)
    unavailable.update(more)
    run_engines = [e for e in engines if e not in unavailable]
    guards = run_guards(client, run_engines, unavailable)
    real = run_real(client, run_engines, unavailable, verbose) if a.real else None
    after = client.health()

    per = {}
    for voice in voices:
        for engine in run_engines:
            sel = [r for r in rows if r.get("voice") == voice and r.get("engine") == engine]
            agg = aggregate(sel)
            cats = {}
            for cat in sorted({r["category"] for r in sel}):
                c = aggregate([r for r in sel if r["category"] == cat])
                cats[cat] = {k: c[k] for k in ("n", "strict_wer", "normalised_wer", "exact_tokens", "exact_tokens_any_form")}
            agg["categories"] = cats
            agg["errors"] = sum(1 for r in sel if r.get("error"))
            per[f"{voice}/{engine}"] = agg
    latency = {"stt": {}, "tts": {}}
    for engine in run_engines:
        ms = [r.get("stt_ms") for r in rows if r.get("engine") == engine and r.get("heard") is not None]
        latency["stt"][engine] = {"p50": percentile(ms, 50), "p95": percentile(ms, 95), "n": len(ms)}
    for voice in voices:
        latency["tts"][voice] = {"p50": percentile(tts_ms[voice], 50), "p95": percentile(tts_ms[voice], 95), "n": len(tts_ms[voice])}

    main_key = f"{voices[0]}/{run_engines[0]}" if run_engines else None
    head = per.get(main_key) or aggregate([])
    tts_p50 = latency["tts"][voices[0]]["p50"]
    line = summary_line(head, guards["ok"], tts_p50)
    result_checks = checks(head, guards["ok"], bool(guards.get("too_long") and guards["too_long"]["ok"]))
    out = {
        "label": a.label, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "seconds": round(time.time() - t0, 1), "url": a.url,
        "note": "Checks on a synthetic set spoken by a synthetic voice; not an accuracy claim.",
        "voices": voices, "engines": engines, "unavailable": unavailable, "main": main_key,
        "summary": line, "thresholds": THRESHOLDS, "checks": result_checks,
        "results": per, "latency_ms": latency, "guards": guards, "real": real,
        "gpu_free_mib": {"before": before.get("gpu_free_mib"), "after": after.get("gpu_free_mib")},
        "health_before": {k: before.get(k) for k in ("stt", "tts", "engines")},
        "health_after": {k: after.get(k) for k in ("stt", "tts", "engines")},
        "rows": rows,
    }
    path = config.DATA_ROOT / "eval" / f"audio_eval_{a.label}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    if verbose:
        print()
        for key, agg in per.items():
            print(f"{key}: {agg['n']} sentences, strict WER {agg['strict_wer']}, normalised {agg['normalised_wer']}, "
                  f"exact tokens {agg['exact_tokens']} ({agg['tokens_found']}/{agg['tokens_total']}; in any written form "
                  f"{agg['exact_tokens_any_form']}), errors {agg['errors']}")
        for engine, l in latency["stt"].items():
            print(f"stt {engine}: p50 {l['p50']} ms, p95 {l['p95']} ms ({l['n']})")
        for voice, l in latency["tts"].items():
            print(f"tts {voice}: p50 {l['p50']} ms, p95 {l['p95']} ms ({l['n']})")
        print(f"silence {guards['silence']}\nnoise {guards['noise']}\nover 60 s {guards['too_long']}")
        print(f"GPU free MiB before {out['gpu_free_mib']['before']}, after {out['gpu_free_mib']['after']}")
        print("checks (synthetic set, not an accuracy claim): " + "; ".join(f"{k} {'pass' if v else 'FAIL'}" for k, v in result_checks.items()))
        print(f"written {path}")
    print(line)
    return 1 if a.strict and not all(result_checks.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
