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
    if b not in _version_cache:  # per binary; a failed version read is cached too (None), not retried on every page
        try:
            out = subprocess.run([b, "--version"], capture_output=True, timeout=20, env=_env())
            m = re.search(r"tesseract\s+v?(\d+(?:\.\d+)*)", (out.stdout + out.stderr).decode(errors="replace"), re.I)
            _version_cache[b] = m.group(1) if m else ""
        except Exception:
            _version_cache[b] = None
    if _version_cache[b] is None:
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


# ---- Aadhaar masking of the engine's reading ------------------------------------------------------------------------
# The reader's text is masked by identity.mask_aadhaar (V1 item 2.4). The engine reads the same digits independently and can
# read them in a form that rule misses ("22O0" for "2200", a number split over two lines), so its reading is masked with
# looser rules, and with the numbers the reader saw (ocr_page passes them): over-masking is acceptable, under-masking never.
# Masking is character for character ("6043-1187-2200" -> "XXXX-XXXX-2200"): offsets and word boxes stay aligned.
#  1. identity.mask_aadhaar's own rules (12 digits in 4-4-4 groups; any 12 digits on or under an Aadhaar / UID label)
#  2. 12 digit-like characters ([0-9OoIlSB], OCR look-alikes) in 4-4-4 groups with a space, hyphen, point, line break or no
#     separator, on, under or above a line labelled Aadhaar / UID (label read loosely: "Aadhar", "Adhaar", "UID", ...)
#  3. engine only: such groups with a space or hyphen anywhere, when at least 6 of the 12 are real digits
#  4. the reader's Aadhaar numbers (cross-mask): the 12-digit run with any separators, and engine only, each 4-digit group
#     except the last one wherever it stands, digit look-alikes included
# Rules 1 to 3 and the run of rule 4 keep the last 4 digits, as the reader's text does; a lone group of rule 4 is masked whole.
_LOOKALIKE = {"0": "0OoDQ", "1": "1Il!i", "2": "2Zz", "3": "3", "4": "4A", "5": "5Ss", "6": "6Gb", "7": "7T", "8": "8B", "9": "9gq"}
_AS_DIGIT = {c: d for d, cs in _LOOKALIKE.items() for c in cs}
_DIGIT_LIKE = re.compile(r"[0-9" + re.escape("".join(sorted(set("".join(_LOOKALIKE.values())) - set("0123456789")))) + "]")
_C = "[0-9OoIlSB]"
_LOOSE_LABEL = re.compile(r"(?<![A-Za-z])(?:aa?dh[a-z]{0,4}|uid)(?![A-Za-z])", re.I)
_LOOSE_LABELLED = re.compile(rf"(?<![0-9]){_C}{{4}}[ \-.\n]?{_C}{{4}}[ \-.\n]?{_C}{{4}}(?![0-9])")
_LOOSE_GROUPED = re.compile(rf"(?<![0-9]){_C}{{4}}[ \-]{_C}{{4}}[ \-]{_C}{{4}}(?![0-9])")
_RUN_SEP = r"[\s\-.:,/]{0,3}"
_GROUP_SEP = r"[ \-.]?"


def _like(ch: str) -> bool:
    return ch.isdigit() or ch in _AS_DIGIT


def _keep_last4(text: str, s: int, e: int) -> set:
    """Offsets of the digit-like characters of text[s:e] except the last 4."""
    pos = [i for i in range(s, e) if _like(text[i])]
    return set(pos[:-4])


def _identity_spans(text: str) -> list:
    """(start, end) of the numbers identity.mask_aadhaar masks, as offsets into text (its rules, line by line)."""
    out, pos, prev = [], 0, ""
    for line in text.split("\n"):
        labelled = identity._AADHAAR_LABEL.search(line) or identity._AADHAAR_LABEL.search(prev)
        rx = identity._AADHAAR_ANY if labelled else identity._AADHAAR_GROUPED
        out += [(pos + m.start(), pos + m.end()) for m in rx.finditer(line)]
        prev = line
        pos += len(line) + 1
    return out


def _changed_line_spans(text: str) -> list:
    """Fallback if identity's rules ever change: the whole of every line identity.mask_aadhaar changes."""
    masked, _ = identity.mask_aadhaar(text)
    out, pos = [], 0
    for old, new in zip(text.split("\n"), masked.split("\n")):
        if old != new:
            out.append((pos, pos + len(old)))
        pos += len(old) + 1
    return out


def _labelled_lines(text: str) -> set:
    """Indexes of the lines on, under or above a line with an Aadhaar / UID label (read loosely)."""
    lines = text.split("\n")
    hit = {n for n, line in enumerate(lines) if _LOOSE_LABEL.search(line) or identity._AADHAAR_LABEL.search(line)}
    return {m for n in hit for m in (n - 1, n, n + 1) if 0 <= m < len(lines)}


def _loose_spans(text: str, engine: bool) -> list:
    """(start, end) of rules 2 and 3."""
    out, labelled = [], _labelled_lines(text)
    if labelled:
        for m in _LOOSE_LABELLED.finditer(text):
            n = text.count("\n", 0, m.start())
            if n in labelled and any(ch.isdigit() for ch in m.group(0)):
                out.append((m.start(), m.end()))
    if engine:
        out += [(m.start(), m.end()) for m in _LOOSE_GROUPED.finditer(text) if sum(ch.isdigit() for ch in m.group(0)) >= 6]
    return out


def _tolerant(digits: str, sep: str) -> str:
    return sep.join("[" + re.escape(_LOOKALIKE[d]) + "]" for d in digits)


def _as_digits(s: str) -> str:
    return "".join(ch if ch.isdigit() else _AS_DIGIT.get(ch, "") for ch in s)


def aadhaar_numbers(text: str) -> list:
    """The 12-digit Aadhaar numbers found in a raw (unmasked) reading: identity.mask_aadhaar's rules and rule 2 (look-alikes
    read as the digit they stand for). Used to cross-mask the other readings of the same page; never stored."""
    text = text or ""
    spans = _identity_spans(text)
    if len(spans) != identity.mask_aadhaar(text)[1]:  # identity's rules changed: every 12-digit run of a changed line
        spans = [(s + m.start(), s + m.end()) for s, e in _changed_line_spans(text)
                 for m in re.finditer(r"\d(?:[\d \-]*\d)?", text[s:e]) if len(re.sub(r"\D", "", m.group(0))) >= 12]
    out = {re.sub(r"\D", "", text[s:e])[:12] for s, e in spans}
    out |= {_as_digits(text[s:e]) for s, e in _loose_spans(text, engine=False)}
    return sorted(n for n in out if len(n) == 12 and n.isdigit())


def _hide(text: str, numbers=(), engine: bool = True) -> tuple:
    """(offsets of text to mask, count of numbers found) under the rules above."""
    text = text or ""
    found = _identity_spans(text)
    if len(found) != identity.mask_aadhaar(text)[1]:
        found += _changed_line_spans(text)  # fallback: whole lines, every digit-like character but the last 4
    found += _loose_spans(text, engine)
    hide = set()
    for s, e in found:
        hide |= _keep_last4(text, s, e)
    for n in numbers or ():
        for m in re.finditer(_tolerant(n, _RUN_SEP), text):
            if any(ch.isdigit() for ch in m.group(0)):
                found.append((m.start(), m.end())); hide |= _keep_last4(text, m.start(), m.end())
        if engine:
            for g in (n[0:4], n[4:8]):
                for m in re.finditer(_tolerant(g, _GROUP_SEP), text):
                    if any(ch.isdigit() for ch in m.group(0)):
                        found.append((m.start(), m.end())); hide |= {i for i in range(m.start(), m.end()) if _like(text[i])}
    count, last = 0, -10
    for s, e in sorted(found):  # numbers found, overlapping or adjacent finds counted once
        if s > last + 3:
            count += 1
        last = max(last, e)
    return hide, (count if hide else 0)


def mask_text_count(text: str, numbers=(), engine: bool = True) -> tuple:
    """(text with the Aadhaar digits of the rules above masked character for character, count of numbers found).
    engine=False: a reading of the vision reader (rules 1, 2 and the run of rule 4; identity.mask_aadhaar applied first)."""
    hide, n = _hide(text, numbers, engine)
    return ("".join("X" if i in hide else ch for i, ch in enumerate(text or "")), n) if hide else (text or "", 0)


def mask_text(text: str, numbers=(), engine: bool = True) -> str:
    return mask_text_count(text, numbers, engine)[0]


def _mask_word_list(text: str, words: list, hide: set) -> tuple:
    """(words, indexes of the words that had a character masked). Each engine line is its words joined by single spaces, so a
    word's characters are the line's characters at its offset; if a line's words do not spell it, every digit-like
    character of the words on that line that hold a digit is masked."""
    words = [list(x) for x in words]
    lines, starts, pos = text.split("\n"), [], 0
    for line in lines:
        starts.append(pos); pos += len(line) + 1
    by_line, idx = {}, set()
    for k, wd in enumerate(words):
        if len(wd) >= 7 and isinstance(wd[0], str):
            by_line.setdefault(wd[6], []).append(k)
    for n, ks in by_line.items():
        ok = isinstance(n, int) and 0 <= n < len(lines)
        base = starts[n] if ok else 0
        if ok and " ".join(words[k][0] for k in ks) == lines[n]:
            p = base
            for k in ks:
                t = words[k][0]
                new = "".join("X" if (p + i) in hide else ch for i, ch in enumerate(t))
                if new != t:
                    words[k][0] = new; idx.add(k)
                p += len(t) + 1
        elif not ok or any(base <= h < base + len(lines[n]) for h in hide):
            for k in ks:
                t = words[k][0]
                if any(ch.isdigit() for ch in t):
                    words[k][0] = _DIGIT_LIKE.sub("X", t); idx.add(k)
    return words, sorted(idx)


def mask_words(text: str, words: list, numbers=()) -> tuple:
    """Aadhaar masked in the engine's text and in its words (the rules above; `numbers`: the reader's Aadhaar numbers of the
    page, for the cross-mask). Boxes are kept (the page preview is blacked out with them). Returns (masked_text,
    masked_words, count, masked_indexes): masked_indexes are the sorted indexes of the words that had a character masked
    ("XXXX", "(XXXX", "XXXX-XXXX-2200", "Aadhaar:XXXX"), the words the preview blacks out."""
    hide, count = _hide(text, numbers, engine=True)
    if not hide:
        return text, words, 0, []
    masked = "".join("X" if i in hide else ch for i, ch in enumerate(text))
    words, idx = _mask_word_list(text, words, hide)
    # safety net: identity's own rule finds nothing left in the text or in any line of words
    if identity.mask_aadhaar(masked)[1] or identity.mask_aadhaar("\n".join(w[0] for w in words if w and isinstance(w[0], str)))[1]:
        masked = identity.mask_aadhaar(masked)[0]
        for k, w in enumerate(words):
            if w and isinstance(w[0], str) and any(ch.isdigit() for ch in w[0]):
                words[k][0] = _DIGIT_LIKE.sub("X", w[0]); idx = sorted(set(idx) | {k})
    return masked, words, count, idx


def cross_mask(read: dict, numbers) -> int:
    """Mask the reader's Aadhaar numbers in an engine reading (text, words, "masked_words", the re-read's text) in place.
    Returns the count of numbers newly found."""
    if not numbers or not isinstance(read, dict):
        return 0
    text, words, n, idx = mask_words(read.get("text") or "", read.get("words") or [], numbers)
    read["text"], read["words"] = text, words
    read["masked_words"] = sorted(set(read.get("masked_words") or []) | set(idx))
    if n:
        read["aadhaar_masked"] = (read.get("aadhaar_masked") or 0) + n
    rc = read.get("recheck")
    if isinstance(rc, dict) and isinstance(rc.get("text"), str):
        rc["text"] = mask_text(rc["text"], numbers)
    return n


def scrub(obj, numbers, masked: set | None = None, _path=()):
    """obj with every exact 4-digit group (all but the last) of these Aadhaar numbers replaced by XXXX in every string,
    at any depth (the last safety net before a page is stored). `masked`, if given, collects the indexes of the engine
    words (obj["words"][k][0]) that changed."""
    groups = sorted({g for n in numbers or () for g in (n[0:4], n[4:8]) if len(g) == 4})
    if not groups:
        return obj
    rx = re.compile("|".join(groups))

    def walk(x, path):
        if isinstance(x, str):
            return rx.sub("XXXX", x)
        if isinstance(x, dict):
            return {k: walk(v, path + (k,)) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            out = [walk(v, path + (i,)) for i, v in enumerate(x)]
            if masked is not None and len(path) == 2 and path[0] == "words" and out and out[0] != (x[0] if x else None):
                masked.add(path[1])
            return out
        return x
    return walk(obj, tuple(_path))


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
    text, words, n_masked, masked_idx = mask_words(text, words)
    info = engine_info() or {}
    res = {"engine": "tesseract", "version": info.get("version", ""), "lang": lng, "size": [w, h], "text": text, "words": words,
           "masked_words": masked_idx}
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
#  - a line is a candidate when one of its numbers is not in the engine's partner line AND the engine reads there another
#    number with the same count of digits that the line does not have (a substituted digit: "60" vs "80"). A number
#    the engine misses or merges ("10^3" read as "103") is not evidence either way
#  - insertion / deletion (CHECK_INDELS): the engine reads there instead a number with one digit more or less, the line's
#    number with one digit added or removed ("60%" vs "6%", "15%" vs "5%"), not the line's number run together with
#    another number of the line, nor a digit next to a letter of the line ("T2" read as "12"), and the engine's word holding
#    that number has a confidence of INDEL_MIN_CONF or more
#  - transcription lines left without a partner are compared, as a group, with the engine lines left in the same
#    stretch (multi-column pages, rows split differently): numbers found anywhere in that engine stretch agree
#  - a candidate line is kept only when a second engine read of the page at 1.5x scale doubts the same number of that line
#    (confirm_spans); for an insertion / deletion the re-read must also read the same other number. Tesseract's own digit
#    slips rarely repeat at another scale, a wrong digit in the transcription does
#  - a span's "numbers" are the transcription's numbers in doubt only, never the engine's reading (shown in the UI)
RECHECK_SCALE = 1.5
RECHECK_MAX_SIDE = 4000  # px: the re-read of a big phone photo is not blown up further
CHECK_INDELS = True
# The engine's word confidence (first read) in its other number of an insertion / deletion. Measured: without it 4 false
# alarms in (a) and (b) (Tesseract cuts the leading digit of a small number, "17" read as "7" at conf 34 to 66, and again at
# 1.5x); 0 at a floor of 70, 80 or 90. 80 keeps a margin above the highest of those.
INDEL_MIN_CONF = 80.0


def _digits(n: str) -> str:
    return re.sub(r"\D", "", n)


def _key(k: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", k).split())


def _one_indel(a: str, b: str) -> bool:
    """b is a with exactly one digit added (or a is b with one removed)."""
    if len(b) < len(a):
        a, b = b, a
    return len(b) == len(a) + 1 and any(b[:k] + b[k + 1:] == a for k in range(len(b)))


def _merged(m: str, x: str, others: list) -> bool:
    """x is m run together with another number of the line (the engine dropped what stood between them: "10^3" read as
    "103")."""
    return any(o and x in (m + o, o + m) for o in others)


def _word_conf(words, line_nos: set, x: str) -> float:
    """The engine's confidence in its number x on these engine lines (the best word holding it), -1 when not found."""
    best = -1.0
    for w in words or ():
        if len(w) >= 7 and w[6] in line_nos and isinstance(w[0], str) and x in [_digits(n) for n in re.findall(r"\d+(?:[.,]\d+)*", w[0])]:
            try:
                best = max(best, float(w[5]))
            except (TypeError, ValueError):
                pass
    return best


def _letter_digit(line: str, m: str, x: str) -> bool:
    """x is the number m with a digit added at an edge where the line has a letter next to m (the engine read the letter as a
    digit: "cT2b" read as "c12b"), or m with an edge digit dropped where the line has a letter next to it."""
    if len(x) == len(m) + 1:
        left, right = x[1:] == m, x[:-1] == m
    elif len(x) + 1 == len(m):
        left, right = m[1:] == x, m[:-1] == x
    else:
        return False
    for t in re.finditer(r"\d+(?:[.,]\d+)*", line):
        if _digits(t.group(0)) != m:
            continue
        before, after = line[t.start() - 1:t.start()], line[t.end():t.end() + 1]
        if (left and before.isalpha()) or (right and after.isalpha()):
            return True
    return False


def _candidates(full: str, engine_text: str, indels: bool = False, words=None) -> list:
    """[(span, {number digits: engine alternatives})] of the lines in doubt (see the rule above); the alternatives are
    the engine's other numbers of an insertion / deletion (empty for a substitution) and are never stored."""
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
    out = []
    for ia, jb in groups:
        line_nos = {engine_text.count("\n", 0, lb[j][0]) for j in jb}  # the engine's own line numbers (words[k][6])
        nums = {i: _ocr_line_numbers(la[i][2]) for i in ia}
        eng = [n for j in jb for n in _ocr_line_numbers(lb[j][2])]
        if not _ocr_differing(sorted(_digits(n) for v in nums.values() for n in v), sorted(_digits(n) for n in eng)):
            continue
        ce = Counter(_digits(n) for n in eng)
        extra = ce - Counter(_digits(n) for v in nums.values() for n in v)  # engine numbers no line of the group has
        for i in ia:
            missing = Counter(_digits(n) for n in nums[i]) - ce
            alts = {m: set() for m in missing for x in extra if len(m) == len(x)}
            if indels:
                line_nums = [_digits(n) for n in nums[i]]
                for m in set(missing) - set(alts):
                    others = list(line_nums); others.remove(m)
                    xs = {x for x in extra if _one_indel(m, x) and not _merged(m, x, others) and not _letter_digit(la[i][2], m, x)
                          and (words is None or _word_conf(words, line_nos, x) >= INDEL_MIN_CONF)}
                    if xs:
                        alts[m] = xs
            if not alts:
                continue
            shown = sorted({n for n in nums[i] if _digits(n) in alts})
            out.append(({"start": la[i][0], "end": la[i][1], "line": la[i][2], "numbers": shown, "reason": ENGINE_DISAGREES,
                         "source": "engine"}, alts))
    return sorted(out, key=lambda c: (c[0]["start"], c[0]["end"]))


def engine_spans(full: str, engine_text: str) -> list:
    """Uncertain spans of the transcription `full` (offsets into it, the shape of ingest.ocr_line_check) on lines where the
    engine reads a different number with the same count of digits (a substitution). Pure function of the two texts (see
    the rule above). "numbers": the transcription's numbers in doubt."""
    return [s for s, alts in _candidates(full, engine_text) if alts]


def indel_spans(full: str, engine_text: str, words=None) -> list:
    """Candidate insertion / deletion spans (one digit more or less on the engine's side); kept only when confirmed by the
    re-read (confirmed_spans). With the engine's words, only an other number read with INDEL_MIN_CONF or more counts."""
    return [s for s, alts in _candidates(full, engine_text, indels=True, words=words) if any(alts.values())]


def confirm_spans(spans: list, full: str, recheck_text: str) -> list:
    """The spans that a second engine read flags too: same transcription line and at least one same number of that line
    in doubt (two different engine slips on one line confirm nothing)."""
    from .ingest import _ocr_line_numbers
    again = {(s["start"], s["end"]): set(s["numbers"]) for s in engine_spans(full, recheck_text)}
    return [s for s in spans if set(s["numbers"]) & again.get((s["start"], s["end"]), set()) & set(_ocr_line_numbers(s["line"]))]


def candidates(full: str, engine_text: str, words=None) -> int:
    """Lines in doubt on the first engine read (the re-read is run only when there is one)."""
    return len({(s["start"], s["end"]) for s, a in _candidates(full, engine_text, indels=CHECK_INDELS, words=words)
                if any(not xs for xs in a.values()) or any(a.values())})


def confirmed_spans(full: str, engine_text: str, recheck_text: str, indels: bool | None = None, words=None) -> list:
    """The spans kept: substitutions confirmed by the re-read (confirm_spans), and with CHECK_INDELS insertions / deletions
    whose re-read reads the same other number for the same number of the line (`words`: the first read's words, for the
    confidence floor). One span per line."""
    indels = CHECK_INDELS if indels is None else indels
    kept = {(s["start"], s["end"]): dict(s) for s in confirm_spans(engine_spans(full, engine_text), full, recheck_text)}
    if indels:
        first = {(s["start"], s["end"]): (s, a) for s, a in _candidates(full, engine_text, indels=True, words=words)}
        again = {(s["start"], s["end"]): a for s, a in _candidates(full, recheck_text, indels=True)}
        for key, (s, a) in first.items():
            same = {m for m, xs in a.items() if xs and xs & again.get(key, {}).get(m, set())}
            if not same:
                continue
            nums = {n for n in s["numbers"] if _digits(n) in same}
            if key in kept:
                kept[key]["numbers"] = sorted(set(kept[key]["numbers"]) | nums)
            else:
                kept[key] = {**s, "numbers": sorted(nums)}
    return sorted(kept.values(), key=lambda s: (s["start"], s["end"]))


def recheck_scale(size) -> float:
    """RECHECK_SCALE, smaller for big photos (long side at most RECHECK_MAX_SIDE), 0.75 for an image already that big."""
    side = max(size or [0]) or 1
    s = min(RECHECK_SCALE, RECHECK_MAX_SIDE / side)
    return round(s, 3) if s >= 1.2 else 0.75


def _error(audit, where: str, e: Exception) -> None:
    if audit:
        audit({"kind": "ocr_engine_error", "engine": "tesseract", "error": f"{where}: {e.__class__.__name__}: {e}"[:300]})


async def check_page(png_bytes: bytes, full: str, read: dict, audit=None, mask=None) -> list:
    """Engine spans of a page, each confirmed by a second engine read at another scale (run only when the first read flags
    something). Records the re-read in read["recheck"]; `mask` (text -> text) is applied to the re-read's text first (the
    reader's Aadhaar numbers, ocr_page). If the re-read or its check fails, the first read's substitution spans are kept
    unconfirmed (a person checks rather than a wrong digit passing); insertion / deletion candidates need the re-read."""
    try:
        text = read.get("text") or ""
        spans = engine_spans(full, text)
        n = candidates(full, text, read.get("words"))
    except Exception as e:  # the check never stops a page from being read
        _error(audit, "check", e)
        return []
    if not n:
        return []
    scale = recheck_scale(read.get("size"))
    again = await read_page(png_bytes, audit, scale=scale)
    if again is None:
        read["recheck"] = {"scale": scale, "candidates": n, "confirmed": None, "error": "re-read failed: spans kept unconfirmed"}
        return spans
    try:
        rtext = mask(again["text"]) if mask else again["text"]
        kept = confirmed_spans(full, text, rtext, words=read.get("words"))
    except Exception as e:
        _error(audit, "re-read check", e)
        read["recheck"] = {"scale": scale, "candidates": n, "confirmed": None, "error": "check of the re-read failed: spans kept unconfirmed"}
        return spans
    read["recheck"] = {"scale": scale, "text": rtext, "candidates": n, "confirmed": len(kept)}
    return kept
