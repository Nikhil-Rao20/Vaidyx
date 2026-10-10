"""Turn any file in a Case File folder into per-page text.

Order of preference (most faithful first):
  1. text layer of a PDF / plain-text / office document (exact, no model involved)
  2. page image -> vision "reader" model, verbatim transcription (only for scans / photos / image-only PDFs)
"""
import asyncio, io, re, shutil, subprocess, tempfile
from pathlib import Path

from . import config, identity, llm, store

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".xml", ".hl7"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
OFFICE_EXT = {".docx", ".doc", ".rtf", ".odt", ".xls", ".xlsx", ".pptx"}
SUPPORTED = TEXT_EXT | IMG_EXT | OFFICE_EXT | {".pdf"}
# Accepted only when LibreOffice (soffice) is on PATH to convert them to PDF; otherwise refused at upload.
REJECTED_EXT = {".doc", ".rtf", ".odt", ".xls"}
REJECT_MESSAGE = "Save as PDF or DOCX and upload again"
REJECT_MESSAGES = {".xls": "Save as XLSX or PDF and upload again"}  # anything else in REJECTED_EXT: REJECT_MESSAGE
SOFFICE_TIMEOUT = 120


def reject_reason(name_or_path) -> str | None:
    """Why a file must be refused at upload, or None if it can be read. Only .doc / .rtf / .odt / .xls without
    LibreOffice."""
    ext = Path(str(name_or_path)).suffix.lower()
    if ext in REJECTED_EXT and shutil.which("soffice") is None:
        return REJECT_MESSAGES.get(ext, REJECT_MESSAGE)
    return None

OCR_PROMPT = (
    "Transcribe all text on this page exactly as written, from top to bottom. Keep every value, unit, date, name, "
    "status line and signature line exactly. For tables write one row per line with cells separated by ' | '. "
    "Do not correct, interpret, summarise, translate or add anything. If a word is unreadable write [illegible]. "
    "Output only the transcription.")


async def ocr_image(png_bytes: bytes, audit=None, max_side=None) -> str:
    msg = [{"role": "user", "content": [llm.image_part(png_bytes, "image/png", max_side=max_side), {"type": "text", "text": OCR_PROMPT}]}]
    return (await llm.chat("reader", msg, max_tokens=3000, purpose="transcribe page", audit=audit)).strip()


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


# Two-read OCR check, line by line (V1 item 3.3). Not compared: list markers at the start of a line ("1.", "1)", "(1)",
# "a)", "- 1 -"), page markers ("Page 1 of 2") and the pipes of table rows.
_LIST_MARKER = re.compile(r"^\s*(?:\(\s*(?:\d{1,3}|[A-Za-z]|[ivxIVX]{1,4})\s*\)|(?:\d{1,3}|[A-Za-z])[.)]|-\s*\d{1,3}\s*-)(?=\s|$)")
_PAGE_MARK = re.compile(r"\bpage\s*(?:no\.?\s*)?\d+(?:\s*(?:of|/)\s*\d+)?\b", re.I)
OCR_NUMBER_DISAGREES = "the two OCR reads disagree on a number"
OCR_ONE_READ_ONLY = "this line with numbers appears in one read only"
_OCR_PAIR_MIN = 0.5  # lines less alike than this are not partners (each then counts as in one read only)


def _ocr_lines(text: str) -> list:
    """(start, end, line, key) of each line with content; start/end are offsets of the stripped line in text, key is the
    line normalised for alignment (no pipes or list marker, lowercase, spaces collapsed, thousands commas dropped,
    digits kept)."""
    out, pos = [], 0
    for raw in (text or "").split("\n"):
        line = raw.strip()
        key = " ".join(re.sub(r"(?<=\d),(?=\d)", "", _LIST_MARKER.sub(" ", line.replace("|", " "), count=1)).lower().split())
        if key:
            start = pos + len(raw) - len(raw.lstrip())
            out.append((start, start + len(line), line, key))
        pos += len(raw) + 1
    return out


def _ocr_line_numbers(line: str) -> list:
    """The numbers of a line in order (thousands commas removed), without list markers and page markers."""
    s = _PAGE_MARK.sub(" ", _LIST_MARKER.sub(" ", line.replace("|", " "), count=1))
    return [x.replace(",", "") for x in _NUM.findall(s)]


def _ocr_pair_block(a: list, b: list) -> list:
    """Partners between two runs of differing lines (keys), in order: the pairing with the greatest total likeness,
    lines less alike than _OCR_PAIR_MIN never paired. Returns [(i, j)]."""
    from difflib import SequenceMatcher
    n, m = len(a), len(b)
    sim = [[0.0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            sm = SequenceMatcher(None, a[i], b[j], autojunk=False)
            if sm.real_quick_ratio() >= _OCR_PAIR_MIN and sm.quick_ratio() >= _OCR_PAIR_MIN:
                r = sm.ratio()
                sim[i][j] = r if r >= _OCR_PAIR_MIN else 0.0
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best[i][j] = max(best[i + 1][j], best[i][j + 1], best[i + 1][j + 1] + sim[i][j] if sim[i][j] else 0.0)
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if sim[i][j] and best[i][j] == best[i + 1][j + 1] + sim[i][j]:
            pairs.append((i, j)); i += 1; j += 1
        elif best[i][j] == best[i + 1][j]:
            i += 1
        else:
            j += 1
    return pairs


def _ocr_differing(a: list, b: list) -> list:
    """Numbers that differ between two lines' number lists (digits, count or order); [] when they agree."""
    if a == b:
        return []
    from collections import Counter
    ca, cb = Counter(a), Counter(b)
    diff = set((ca - cb) + (cb - ca))
    if not diff:  # same numbers in a different order
        diff = {x for pair in zip(a, b) if pair[0] != pair[1] for x in pair}
    return sorted(diff)


def ocr_line_check(full: str, second: str) -> list:
    """Uncertain spans of the full-resolution read: lines whose numbers differ from their partner line in the second read
    (aligned with SequenceMatcher, so a dropped or merged row affects only that row), and lines with numbers that have
    no partner. Offsets are into `full`. A line found only in the second read gets a zero-width span where it would
    sit in `full` (marked "read": "second"); its "line" is the second read's line."""
    from difflib import SequenceMatcher
    la, lb = _ocr_lines(full), _ocr_lines(second)
    pairs, only_a, only_b = [], [], []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, [x[3] for x in la], [x[3] for x in lb], autojunk=False).get_opcodes():
        if tag == "equal":
            pairs += zip(range(i1, i2), range(j1, j2))
            continue
        block = [(i1 + i, j1 + j) for i, j in _ocr_pair_block([x[3] for x in la[i1:i2]], [x[3] for x in lb[j1:j2]])]
        pairs += block
        only_a += sorted(set(range(i1, i2)) - {i for i, _ in block})
        at = la[i2][0] if i2 < len(la) else len(full or "")
        only_b += [(j, at) for j in sorted(set(range(j1, j2)) - {j for _, j in block})]
    spans = []
    for i, j in pairs:
        diff = _ocr_differing(_ocr_line_numbers(la[i][2]), _ocr_line_numbers(lb[j][2]))
        if diff:
            spans.append({"start": la[i][0], "end": la[i][1], "line": la[i][2], "numbers": diff, "reason": OCR_NUMBER_DISAGREES})
    for i in only_a:
        nums = _ocr_line_numbers(la[i][2])
        if nums:
            spans.append({"start": la[i][0], "end": la[i][1], "line": la[i][2], "numbers": sorted(set(nums)), "reason": OCR_ONE_READ_ONLY})
    for j, at in only_b:
        nums = _ocr_line_numbers(lb[j][2])
        if nums:
            spans.append({"start": at, "end": at, "line": lb[j][2], "numbers": sorted(set(nums)), "reason": OCR_ONE_READ_ONLY, "read": "second"})
    return sorted(spans, key=lambda s: (s["start"], s["end"]))


async def ocr_page(png_bytes: bytes, audit=None) -> dict:
    """Two independent reads of the page (full resolution and a 70% downscale), compared line by line: a line whose
    numbers differ from its partner line in the other read, or a line with numbers found in one read only, is an
    uncertain span (generative OCR can silently 'correct' a digit, and lab values are where that matters most). Single
    digits count (ECOG 1 vs 2, TPS 6% vs 8%); list markers, page markers and table pipes do not. The full-resolution
    read is the transcription used downstream; the second read is kept as "second_read"."""
    full, second = await asyncio.gather(ocr_image(png_bytes, audit), ocr_image(png_bytes, audit, max_side=int(0.7 * config.OCR_MAX_SIDE)))
    full, n_masked = identity.mask_aadhaar(full)  # Aadhaar masked at the source: never in the text, the uncertain numbers or the audit (V1 item 2.4)
    second, _ = identity.mask_aadhaar(second)
    spans = ocr_line_check(full, second)
    uncertain = sorted({n for s in spans for n in s["numbers"]})
    page = {"text": full, "second_read": second, "method": "vision-transcription", "ocr_reads": 2}
    if n_masked:
        page["aadhaar_masked"] = n_masked
    page.update(page_flags(full))
    if spans:
        page["ocr_uncertain_spans"] = spans
        page["ocr_uncertain_numbers"] = uncertain
        if audit:
            audit({"kind": "ocr_disagreement", "numbers": uncertain, "lines": len(spans)})
    return page


def uncertain_overlap(page: dict, start: int, end: int) -> dict | None:
    """The first uncertain OCR span of this page overlapping [start, end) of page["text"], else None. A zero-width span
    (a line found only in the second read) overlaps only a range that strictly contains its position."""
    for span in page.get("ocr_uncertain_spans") or []:
        if span["start"] < end and start < span["end"]:
            return span
    return None


# Hindi / regional text and handwriting (V1 item 3.6): flagged, never translated or removed; values from flagged lines
# need review.
INDIC_SCRIPTS = (("Devanagari", 0x0900, 0x097F), ("Bengali", 0x0980, 0x09FF), ("Gurmukhi", 0x0A00, 0x0A7F),
                 ("Gujarati", 0x0A80, 0x0AFF), ("Odia", 0x0B00, 0x0B7F), ("Tamil", 0x0B80, 0x0BFF), ("Telugu", 0x0C00, 0x0C7F),
                 ("Kannada", 0x0C80, 0x0CFF), ("Malayalam", 0x0D00, 0x0D7F))
REGIONAL_FLAG = "contains Hindi / regional text"
ILLEGIBLE_FLAG = "handwriting / illegible parts: verify"
_ILLEGIBLE = re.compile(r"\[\s*(?:illegible|unreadable|unclear)\b[^\]\n]*\]|\(\s*(?:illegible|unreadable|unclear)\b[^)\n]*\)"
                        r"|\[\s*handwritten\b[^\]\n]*\]|\?{3,}", re.I)


def _indic_scripts(line: str) -> list:
    """Indic scripts with at least one letter or sign in this line, in INDIC_SCRIPTS order (punctuation alone, such as
    a danda, does not count; the rupee sign and Latin text are outside these blocks)."""
    import unicodedata
    found = set()
    for ch in line:
        o = ord(ch)
        if 0x0900 <= o <= 0x0D7F and unicodedata.category(ch)[0] in "LM":
            found.update(name for name, lo, hi in INDIC_SCRIPTS if lo <= o <= hi)
    return [name for name, _, _ in INDIC_SCRIPTS if name in found]


def page_flags(text: str) -> dict:
    """{} for a page in plain English. Otherwise {"flags": [...], "flagged_lines": [{"start", "end", "line", "flag"}]}:
    lines in an Indic script ("contains Hindi / regional text (Devanagari)") and lines with an illegible / handwriting
    marker ("handwriting / illegible parts: verify"). Offsets are of the stripped line in text, as for the OCR spans; a
    line with both gets one entry per flag. The text itself is never changed."""
    lines, scripts, pos = [], [], 0
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if line:
            start = pos + len(raw) - len(raw.lstrip())
            here = _indic_scripts(line)
            if here:
                scripts += [x for x in here if x not in scripts]
                lines.append({"start": start, "end": start + len(line), "line": line, "flag": f"{REGIONAL_FLAG} ({', '.join(here)})"})
            if _ILLEGIBLE.search(line):
                lines.append({"start": start, "end": start + len(line), "line": line, "flag": ILLEGIBLE_FLAG})
        pos += len(raw) + 1
    if not lines:
        return {}
    flags = ([f"{REGIONAL_FLAG} ({', '.join(n for n, _, _ in INDIC_SCRIPTS if n in scripts)})"] if scripts else []) + \
            ([ILLEGIBLE_FLAG] if any(x["flag"] == ILLEGIBLE_FLAG for x in lines) else [])
    return {"flags": flags, "flagged_lines": lines}


def flagged_overlap(page: dict, start: int, end: int) -> dict | None:
    """The first flagged line of this page overlapping [start, end) of page["text"], else None."""
    for line in page.get("flagged_lines") or []:
        if line["start"] < end and start < line["end"]:
            return line
    return None


def text_layer_usable(t: str) -> bool:
    """A PDF text layer is trusted only if it reads like text (bad OCR layers from old scanners fail this)."""
    words = [w for w in t.split() if len(w) >= 3]
    if len(words) < 8:
        return False
    wordy = sum(1 for w in words if any(c in "aeiouAEIOU" for c in w) and sum(ch.isalpha() for ch in w) >= len(w) * 0.6)
    return wordy / len(words) >= 0.55


def _docx_text(path: Path) -> str:
    import re, zipfile
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml); xml = re.sub(r"</w:tc>", " | ", xml); xml = re.sub(r"<w:tab/>", "\t", xml)
    return re.sub(r"<[^>]+>", "", xml)


_SLIDE = re.compile(r"^<!-- Slide number: (\d+) -->[ \t]*$", re.M)


def _cell_text(v) -> str:
    """A cell exactly as stored: str(value), no number formatting (31 -> '31', '007' -> '007', 2.45 -> '2.45');
    dates as ISO (a midnight datetime as its date); empty -> ''. Line breaks inside a cell become spaces so that
    each row stays on one line."""
    import datetime as dt
    if v is None:
        return ""
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time() and v.tzinfo is None else v.isoformat(sep=" ")
    if isinstance(v, (dt.date, dt.time)):
        return v.isoformat()
    return str(v).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


FORMULA_NO_VALUE = "[formula, no saved value]"
FORMULA_REVIEW = "a formula cell has no saved value; open the file to check"


def _percent_text(v, fmt: str) -> str | None:
    """A number shown as a percentage in Excel (number format with '%') as the clinician sees it: 0.45 with '0%' ->
    '45%', with '0.0%' -> '45.0%' (Excel rounds half away from zero). None if the cell is not a percent number."""
    from decimal import Decimal, ROUND_HALF_UP
    if not fmt or "%" not in fmt or isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    m = re.search(r"\.([0#?]+)", fmt.split(";")[0])
    places = len(m.group(1)) if m else 0
    shown = (Decimal(repr(v)) * 100).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return f"{shown}%"


def _formula_cells(path: Path) -> dict:
    """{sheet title: {(row, column)}} of cells holding a formula (read-only pass with data_only=False)."""
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=False)
    try:
        out = {}
        for ws in wb.worksheets:
            ws.reset_dimensions()
            out[ws.title] = {(c.row, c.column) for row in ws.iter_rows() for c in row
                             if isinstance(c.value, str) and c.value.startswith("=") and getattr(c, "row", None)}
        return out
    finally:
        wb.close()


def _xlsx_pages(path: Path) -> list[dict]:
    """One page per worksheet: first line '## <sheet name>', then one '| a | b | c |' row per line. Read with openpyxl
    (cached values), never through pandas, which reformats values (31 -> 31.0, '007' -> 7). Each cell is str(value),
    except percent-formatted numbers (shown as Excel shows them) and formulas with no saved value (written as
    FORMULA_NO_VALUE and the page flagged needs_review). The stored <dimension> is ignored (lab systems often write a
    wrong one, which would silently cut rows and columns). Trailing empty cells and empty rows are dropped; a sheet
    with no values gives an empty page (page N stays sheet N)."""
    from openpyxl import load_workbook
    formulas = _formula_cells(path)
    wb = load_workbook(str(path), read_only=True, data_only=True)
    try:
        pages = []
        for ws in wb.worksheets:
            ws.reset_dimensions()
            rows, unsaved = [], False
            for row in ws.iter_rows():
                cells = []
                for c in row:
                    if c.value is None and (getattr(c, "row", None), getattr(c, "column", None)) in formulas.get(ws.title, ()):
                        cells.append(FORMULA_NO_VALUE); unsaved = True; continue
                    pct = _percent_text(c.value, getattr(c, "number_format", ""))
                    cells.append(pct if pct is not None else _cell_text(c.value))
                while cells and not cells[-1]:
                    cells.pop()
                if cells:
                    rows.append("| " + " | ".join(cells) + " |")
            page = {"text": "\n".join([f"## {ws.title}"] + rows) if rows else "", "method": "office-text"}
            if unsaved:
                page["needs_review"] = FORMULA_REVIEW
            pages.append(page)
    finally:
        wb.close()
    return pages or [{"text": "", "method": "office-text"}]


def _pptx_pages(text: str) -> list[dict]:
    """One page per slide, split on markitdown's '<!-- Slide number: N -->' markers (marker dropped, page N is slide
    N, a blank slide gives an empty page), so citations can point at a slide. One page if there are no markers."""
    marks = list(_SLIDE.finditer(text))
    parts = [text[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(text))].strip() for i, m in enumerate(marks)]
    if parts and text[:marks[0].start()].strip():  # anything before the first marker stays with slide 1
        parts[0] = (text[:marks[0].start()].strip() + "\n" + parts[0]).strip()
    if not parts:
        parts = [text.strip()]
    return [{"text": t, "method": "office-text"} for t in parts]


async def _soffice_to_pdf_pages(path: Path, audit=None) -> list[dict]:
    """Convert .doc / .rtf / .odt / .xls with LibreOffice (headless) to PDF, then read that PDF the normal way. Each
    run gets its own LibreOffice profile in the temporary directory, so parallel conversions do not collide."""
    with tempfile.TemporaryDirectory(prefix="tb-soffice-") as tmp:
        profile = "-env:UserInstallation=" + (Path(tmp) / "profile").as_uri()
        cmd = [shutil.which("soffice") or "soffice", profile, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(path)]
        try:
            await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=SOFFICE_TIMEOUT, check=False)
        except (subprocess.TimeoutExpired, OSError) as e:
            return [{"text": "", "method": f"unsupported (conversion to PDF failed: {e.__class__.__name__})"}]
        pdf = Path(tmp) / (path.stem + ".pdf")
        if not pdf.exists():
            return [{"text": "", "method": "unsupported (conversion to PDF failed)"}]
        return await _read_pages(pdf, audit)


def _img_bytes(im) -> bytes:
    buf = io.BytesIO(); im.convert("RGB").save(buf, "PNG"); return buf.getvalue()


async def extract_pages(path: Path, audit=None) -> list[dict]:
    """Returns [{"text": str, "method": "text-layer"|"vision-transcription"|"plain-text"|...}], each page carrying
    page_flags (Hindi / regional text, illegible parts) whatever way it was read."""
    pages = await _read_pages(path, audit)
    for page in pages:
        page.update(page_flags(page.get("text") or ""))
    return pages


async def _read_pages(path: Path, audit=None) -> list[dict]:
    ext = path.suffix.lower()
    if ext in TEXT_EXT:
        return [{"text": path.read_text(errors="replace"), "method": "plain-text"}]
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages, todo = [], []
        for i, p in enumerate(reader.pages):
            t = p.extract_text() or ""
            if len(t.strip()) >= 40 and text_layer_usable(t):
                pages.append({"text": t, "method": "text-layer"})
            else:
                pages.append(None); todo.append(i)
        if todo:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(str(path))
            imgs = [_img_bytes(pdf[i].render(scale=2.0).to_pil()) for i in todo]
            read = await asyncio.gather(*[ocr_page(b, audit) for b in imgs])
            for i, pg in zip(todo, read):
                pages[i] = pg
        return pages
    if ext in IMG_EXT:
        from PIL import Image, ImageSequence
        im = Image.open(path)
        frames = [_img_bytes(f.copy()) for f in ImageSequence.Iterator(im)] if getattr(im, "n_frames", 1) > 1 else [path.read_bytes()]
        return list(await asyncio.gather(*[ocr_page(b, audit) for b in frames]))
    if ext in OFFICE_EXT:
        if ext == ".docx":
            try:
                return [{"text": _docx_text(path), "method": "office-text"}]
            except Exception as e:
                return [{"text": "", "method": f"unsupported ({e.__class__.__name__})"}]
        if ext in REJECTED_EXT:
            if shutil.which("soffice") is None:
                return [{"text": "", "method": f"unsupported ({REJECT_MESSAGES.get(ext, REJECT_MESSAGE)})"}]
            return await _soffice_to_pdf_pages(path, audit)
        if ext == ".xlsx":
            try:
                return _xlsx_pages(path)
            except Exception as e:
                return [{"text": "", "method": f"unsupported (could not read {ext} file: {e.__class__.__name__})"}]
        try:
            from markitdown import MarkItDown
            text = MarkItDown().convert(str(path)).text_content or ""
        except ImportError:
            return [{"text": "", "method": f"unsupported (install markitdown to read {ext} files)"}]
        except Exception as e:
            return [{"text": "", "method": f"unsupported (could not read {ext} file: {e.__class__.__name__})"}]
        return _pptx_pages(text)
    return [{"text": "", "method": "unsupported format"}]
