"""Independent OCR engine for numbers (V1 item 8.3): Tesseract 5, open source, CPU only, run as a subprocess.

The vision reader reads every scanned page twice (ingest.ocr_page), but both reads come from the same model, so a digit it
'corrects' the same way in both reads passes the two-read check. Tesseract reads the same page image independently; its
numbers are compared with the transcription line by line (the alignment of the two-read check, V1 item 3.3). A line
where the engine reads a different number, and a second engine read of the page at another scale doubts the same number,
is an uncertain span, so a value quoted from it needs review. The engine never replaces or edits the transcription (not a
lossy layer): it only raises doubt. Measured on the synthetic demo corpus by eval/ocr_engine_eval.py.

Settings (read on each call):
  TB_TESSERACT               the tesseract binary (default /data/vaidyx/venv/ocr/bin/tesseract, else tesseract on PATH)
  TB_OCR_ENGINE=off          turns the engine off
  TB_OCR_LANG                Tesseract language(s), default "eng" (Indic packs are installed with it: hin+eng, tam+eng, ...)
  TB_OCR_ENGINE_CONCURRENCY  pages read at the same time (default 8); one CPU thread per page (OMP_THREAD_LIMIT=1)
  TB_OCR_ENGINE_TIMEOUT      seconds per page before the read is abandoned (default 60)
No network: the binary and its language data are local files.

Word format shared with ocr_boxes (V1 item 8.4): [text, x0, y0, x1, y1, conf, line_no], coordinates normalised to 0..1
(4 decimals) of the page image that was read (the image the vision reader got), conf 0..100, line_no counting the
engine's lines from 0 in reading order (the line of "text" the word sits on).
"""
import asyncio, os, re, shutil, subprocess, weakref
from difflib import SequenceMatcher
from pathlib import Path

from . import identity

DEFAULT_BINARY = "/data/vaidyx/venv/ocr/bin/tesseract"
PSM = "4"  # page segmentation: one column of lines of varying size (rows of a table stay on one line, as the reader writes them)
ENGINE_DISAGREES = "the independent OCR engine reads a different number"
NOT_INSTALLED = "independent OCR engine not installed"
TURNED_OFF = "independent OCR engine turned off"
FAILED = "independent OCR engine could not read this page"
_version_cache = {}
_semaphores = weakref.WeakKeyDictionary()  # event loop -> (size, semaphore)


def binary() -> str | None:
    b = os.getenv("TB_TESSERACT")
    if b:
        return b if Path(b).is_file() and os.access(b, os.X_OK) else None
    if Path(DEFAULT_BINARY).is_file() and os.access(DEFAULT_BINARY, os.X_OK):
        return DEFAULT_BINARY
    return shutil.which("tesseract")


def turned_off() -> bool:
    return os.getenv("TB_OCR_ENGINE", "").strip().lower() in ("off", "0", "false", "no")


def lang() -> str:
    return os.getenv("TB_OCR_LANG", "eng").strip() or "eng"


def available() -> bool:
    return not turned_off() and binary() is not None


def unavailable_note() -> str | None:
    """Why the engine is not run (the page note), or None when it is."""
    if turned_off():
        return TURNED_OFF
    return None if binary() else NOT_INSTALLED


def _env() -> dict:
    return {**os.environ, "OMP_THREAD_LIMIT": "1"}


def engine_info() -> dict | None:
    """{"name": "tesseract", "version": "5.x.y", "lang": ...} or None when unavailable."""
    b = binary()
    if not b or turned_off():
        return None
    if b not in _version_cache:
        try:
            out = subprocess.run([b, "--version"], capture_output=True, timeout=20, env=_env())
            m = re.search(r"tesseract\s+v?(\d+(?:\.\d+)*)", (out.stdout + out.stderr).decode(errors="replace"), re.I)
            _version_cache[b] = m.group(1) if m else ""
        except Exception:
            return None
    return {"name": "tesseract", "version": _version_cache[b], "lang": lang()}


def _image_size(png_bytes: bytes):
    from PIL import Image
    import io
    with Image.open(io.BytesIO(png_bytes)) as im:
        return im.size


def parse_tsv(tsv: str, w: int, h: int) -> tuple:
    """(text, words) from Tesseract's TSV output: one text line per engine line, words normalised to 0..1."""
    words, keys, lines = [], {}, []
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or c[0] != "5":
            continue
        t = c[11].strip()
        if not t:
            continue
        key = (c[1], c[2], c[3], c[4])  # page, block, paragraph, line
        if key not in keys:
            keys[key] = len(lines); lines.append([])
        n = keys[key]
        x, y, ww, hh = (int(v) for v in c[6:10])
        try:
            conf = round(float(c[10]), 1)
        except ValueError:
            conf = -1.0
        words.append([t, round(x / w, 4), round(y / h, 4), round((x + ww) / w, 4), round((y + hh) / h, 4), conf, n])
        lines[n].append(t)
    return "\n".join(" ".join(x) for x in lines), words


def mask_words(text: str, words: list) -> tuple:
    """Aadhaar masked in the engine's text (identity.mask_aadhaar, as for the reader's text) and in its words: the digits of
    every word inside a masked number become X except the last 4-digit group ("6043" -> "XXXX", "2200" kept); boxes are
    kept (the page preview is masked with them). Returns (masked_text, masked_words, count)."""
    masked, count = identity.mask_aadhaar(text)
    if not count:
        return masked, words, 0
    words = [list(x) for x in words]
    by_line = {}
    for k, wd in enumerate(words):
        by_line.setdefault(wd[6], []).append(k)
    old_lines, new_lines = text.split("\n"), masked.split("\n")
    for n, (old, new) in enumerate(zip(old_lines, new_lines)):
        if old == new or n not in by_line:
            continue
        hide = set()  # character offsets in `old` whose digit is masked
        for tag, i1, i2, _, _ in SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag != "equal":
                hide.update(i for i in range(i1, i2) if old[i].isdigit())
        pos = 0
        for k in by_line[n]:
            t = words[k][0]
            start = old.index(t, pos) if t in old[pos:] else pos
            words[k][0] = "".join("X" if (start + i) in hide else ch for i, ch in enumerate(t))
            pos = start + len(t)
        # safety net: whatever the diff missed, no unmasked Aadhaar may remain in the words of this line
        if identity.mask_aadhaar(" ".join(words[k][0] for k in by_line[n]))[1]:
            for k in by_line[n]:
                words[k][0] = re.sub(r"\d", "X", words[k][0])
    return masked, words, count


def _scaled(png_bytes: bytes, scale: float) -> bytes:
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(png_bytes))
    im = im.convert("RGB") if im.mode not in ("RGB", "L") else im
    im = im.resize((max(1, round(im.size[0] * scale)), max(1, round(im.size[1] * scale))), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return buf.getvalue()


def _read_sync(png_bytes: bytes, b: str, lng: str, timeout: float, scale: float = 1.0) -> dict:
    """One Tesseract read (blocking). "size" is the size of png_bytes; with scale != 1 the image is resized before the read
    (normalised coordinates are the same either way)."""
    w, h = _image_size(png_bytes)
    img = _scaled(png_bytes, scale) if scale != 1.0 else png_bytes
    sw, sh = (w, h) if scale == 1.0 else _image_size(img)
    out = subprocess.run([b, "stdin", "stdout", "--psm", PSM, "-l", lng, "tsv"], input=img, capture_output=True,
                         timeout=timeout, env=_env())
    if out.returncode != 0:
        raise RuntimeError(out.stderr.decode(errors="replace").strip()[-300:] or f"exit code {out.returncode}")
    text, words = parse_tsv(out.stdout.decode("utf-8", errors="replace"), sw, sh)
    text, words, n_masked = mask_words(text, words)
    info = engine_info() or {}
    res = {"engine": "tesseract", "version": info.get("version", ""), "lang": lng, "size": [w, h], "text": text, "words": words}
    if n_masked:
        res["aadhaar_masked"] = n_masked
    return res


def _semaphore():
    """The concurrency limit of this event loop (tests start a new loop per asyncio.run)."""
    loop = asyncio.get_running_loop()
    n = max(1, int(os.getenv("TB_OCR_ENGINE_CONCURRENCY", "8") or 8))
    sem = _semaphores.get(loop)
    if sem is None or sem[0] != n:
        sem = _semaphores[loop] = (n, asyncio.Semaphore(n))
    return sem[1]


async def read_page(png_bytes: bytes, audit=None, scale: float = 1.0) -> dict | None:
    """The engine's reading of one page image, or None when the engine is unavailable or fails (failure audited as
    ocr_engine_error, never raised)."""
    b = binary()
    if turned_off() or not b:
        return None
    timeout = float(os.getenv("TB_OCR_ENGINE_TIMEOUT", "60") or 60)
    try:
        async with _semaphore():
            return await asyncio.to_thread(_read_sync, png_bytes, b, lang(), timeout, scale)
    except Exception as e:
        if audit:
            audit({"kind": "ocr_engine_error", "engine": "tesseract", "error": f"{e.__class__.__name__}: {e}"[:300]})
        return None


# ---- the number check -----------------------------------------------------------------------------------------
# Rule (measured on the synthetic demo corpus, eval/ocr_engine_eval.py; numbers in data/tumour_board/eval/v1/phase8/ocr_engines):
#  - transcription lines and engine lines are aligned like the two reads of 3.3, on keys reduced to letters and digits
#    (Tesseract drops the underscores of blank form fields and reads "|" rules as letters)
#  - numbers are compared as digits only: Tesseract often loses a decimal point ("11.8" read as "118"), so a point is
#    not evidence
#  - a line is flagged when one of its numbers is not in the engine's partner line AND the engine reads there another
#    number with the same count of digits that the line does not have (a substituted digit: "60" vs "80"). A number
#    the engine misses, cuts ("17" read as "7") or merges ("10^3" read as "103") is not evidence either way
#  - transcription lines left without a partner are compared, as a group, with the engine lines left in the same
#    stretch (multi-column pages, rows split differently): numbers found anywhere in that engine stretch agree
#  - a flagged line is kept only when a second engine read of the page at 1.5x scale doubts the same number of that line
#    (confirm_spans): Tesseract's own digit slips rarely repeat at another scale, a wrong digit in the transcription does
RECHECK_SCALE = 1.5
RECHECK_MAX_SIDE = 4000  # px: the re-read of a big phone photo is not blown up further


def _digits(n: str) -> str:
    return re.sub(r"\D", "", n)


def _key(k: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", k).split())


def engine_spans(full: str, engine_text: str) -> list:
    """Uncertain spans of the transcription `full` (offsets into it, the shape of ingest.ocr_line_check) on lines where the
    engine reads a different number. Pure function of the two texts (see the rule above)."""
    from collections import Counter
    from .ingest import _ocr_differing, _ocr_line_numbers, _ocr_lines, _ocr_pair_block
    la, lb = _ocr_lines(full), _ocr_lines(engine_text)
    ka, kb = [_key(x[3]) for x in la], [_key(x[3]) for x in lb]
    groups = []  # ([transcription line], [engine lines]) compared together
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, ka, kb, autojunk=False).get_opcodes():
        if tag == "equal":
            continue  # same key: same digits
        block = [(i1 + i, j1 + j) for i, j in _ocr_pair_block(ka[i1:i2], kb[j1:j2])]
        groups += [([i], [j]) for i, j in block]
        rest_a = [i for i in range(i1, i2) if i not in {i for i, _ in block}]
        rest_b = [j for j in range(j1, j2) if j not in {j for _, j in block}]
        if rest_a and rest_b:
            groups.append((rest_a, rest_b))
    spans = []
    for ia, jb in groups:
        nums = {i: _ocr_line_numbers(la[i][2]) for i in ia}
        eng = [n for j in jb for n in _ocr_line_numbers(lb[j][2])]
        if not _ocr_differing(sorted(_digits(n) for v in nums.values() for n in v), sorted(_digits(n) for n in eng)):
            continue
        ce = Counter(_digits(n) for n in eng)
        extra = ce - Counter(_digits(n) for v in nums.values() for n in v)  # engine numbers no line of the group has
        for i in ia:
            missing = Counter(_digits(n) for n in nums[i]) - ce
            bad = {m for m in missing for x in extra if len(m) == len(x)}
            if not bad:
                continue
            widths = {len(m) for m in bad}
            shown = sorted({n for n in nums[i] if _digits(n) in bad} | {n for n in eng if _digits(n) in extra and len(_digits(n)) in widths})
            spans.append({"start": la[i][0], "end": la[i][1], "line": la[i][2], "numbers": shown, "reason": ENGINE_DISAGREES,
                          "source": "engine"})
    return sorted(spans, key=lambda s: (s["start"], s["end"]))


def confirm_spans(spans: list, full: str, recheck_text: str) -> list:
    """The spans that a second engine read flags too: same transcription line and at least one same number of that line
    in doubt (two different engine slips on one line confirm nothing)."""
    from .ingest import _ocr_line_numbers
    again = {(s["start"], s["end"]): set(s["numbers"]) for s in engine_spans(full, recheck_text)}
    return [s for s in spans if set(s["numbers"]) & again.get((s["start"], s["end"]), set()) & set(_ocr_line_numbers(s["line"]))]


def recheck_scale(size) -> float:
    """RECHECK_SCALE, smaller for big photos (long side at most RECHECK_MAX_SIDE), 0.75 for an image already that big."""
    side = max(size or [0]) or 1
    s = min(RECHECK_SCALE, RECHECK_MAX_SIDE / side)
    return round(s, 3) if s >= 1.2 else 0.75


async def check_page(png_bytes: bytes, full: str, read: dict, audit=None) -> list:
    """Engine spans of a page, each confirmed by a second engine read at another scale (run only when the first read flags
    something). Records the re-read in read["recheck"]. If the re-read fails, the first read's spans are kept unconfirmed
    (a person checks rather than a wrong digit passing)."""
    try:
        spans = engine_spans(full, read.get("text") or "")
    except Exception as e:  # the check never stops a page from being read
        if audit:
            audit({"kind": "ocr_engine_error", "engine": "tesseract", "error": f"check: {e.__class__.__name__}: {e}"[:300]})
        return []
    if not spans:
        return []
    scale = recheck_scale(read.get("size"))
    again = await read_page(png_bytes, audit, scale=scale)
    if again is None:
        read["recheck"] = {"scale": scale, "candidates": len(spans), "confirmed": None, "error": "re-read failed: spans kept unconfirmed"}
        return spans
    kept = confirm_spans(spans, full, again["text"])
    read["recheck"] = {"scale": scale, "text": again["text"], "candidates": len(spans), "confirmed": len(kept)}
    return kept
