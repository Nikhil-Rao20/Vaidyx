"""Turn any file in a Case File folder into per-page text.

Order of preference (most faithful first):
  1. text layer of a PDF / plain-text / office document (exact, no model involved)
  2. page image -> vision "reader" model, verbatim transcription (only for scans / photos / image-only PDFs)
"""
import asyncio, io, re, shutil, subprocess, tempfile
from pathlib import Path

from . import config, llm, store

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".xml", ".hl7"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
OFFICE_EXT = {".docx", ".doc", ".rtf", ".odt", ".xlsx", ".pptx"}
SUPPORTED = TEXT_EXT | IMG_EXT | OFFICE_EXT | {".pdf"}
# Accepted only when LibreOffice (soffice) is on PATH to convert them to PDF; otherwise refused at upload.
REJECTED_EXT = {".doc", ".rtf", ".odt"}
REJECT_MESSAGE = "Save as PDF or DOCX and upload again"
SOFFICE_TIMEOUT = 120


def reject_reason(name_or_path) -> str | None:
    """Why a file must be refused at upload, or None if it can be read. Only .doc / .rtf / .odt without LibreOffice."""
    if Path(str(name_or_path)).suffix.lower() in REJECTED_EXT and shutil.which("soffice") is None:
        return REJECT_MESSAGE
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


async def ocr_page(png_bytes: bytes, audit=None) -> dict:
    """Two independent reads of the page (full resolution and a 70% downscale). Numbers that appear in only one read are
    reported as uncertain: generative OCR can silently 'correct' a digit, and lab values are where that matters most.
    The full-resolution read is the transcription used downstream."""
    full, second = await asyncio.gather(ocr_image(png_bytes, audit), ocr_image(png_bytes, audit, max_side=int(0.7 * config.OCR_MAX_SIDE)))
    n1 = set(x.replace(",", "") for x in _NUM.findall(full)); n2 = set(x.replace(",", "") for x in _NUM.findall(second))
    uncertain = sorted((n1 ^ n2) - {x for x in (n1 ^ n2) if len(x) <= 1})  # single digits (list numbers) are noise
    page = {"text": full, "method": "vision-transcription", "ocr_reads": 2}
    if uncertain:
        page["ocr_uncertain_numbers"] = uncertain
        if audit:
            audit({"kind": "ocr_disagreement", "numbers": uncertain})
    return page


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


def _xlsx_pages(path: Path) -> list[dict]:
    """One page per worksheet: first line '## <sheet name>', then one '| a | b | c |' row per line. Read with openpyxl
    (cached values, not formulas), never through pandas, which reformats values (31 -> 31.0, '007' -> 7). Trailing
    empty cells and empty rows are dropped; a sheet with no values gives an empty page (page N stays sheet N)."""
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    try:
        pages = []
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                cells = [_cell_text(v) for v in row]
                while cells and not cells[-1]:
                    cells.pop()
                if cells:
                    rows.append("| " + " | ".join(cells) + " |")
            pages.append({"text": "\n".join([f"## {ws.title}"] + rows) if rows else "", "method": "office-text"})
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
    """Convert .doc / .rtf / .odt with LibreOffice (headless) to PDF, then read that PDF the normal way."""
    with tempfile.TemporaryDirectory(prefix="tb-soffice-") as tmp:
        cmd = [shutil.which("soffice") or "soffice", "--headless", "--convert-to", "pdf", "--outdir", tmp, str(path)]
        try:
            await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=SOFFICE_TIMEOUT, check=False)
        except (subprocess.TimeoutExpired, OSError) as e:
            return [{"text": "", "method": f"unsupported (conversion to PDF failed: {e.__class__.__name__})"}]
        pdf = Path(tmp) / (path.stem + ".pdf")
        if not pdf.exists():
            return [{"text": "", "method": "unsupported (conversion to PDF failed)"}]
        return await extract_pages(pdf, audit)


def _img_bytes(im) -> bytes:
    buf = io.BytesIO(); im.convert("RGB").save(buf, "PNG"); return buf.getvalue()


async def extract_pages(path: Path, audit=None) -> list[dict]:
    """Returns [{"text": str, "method": "text-layer"|"vision-transcription"|"plain-text"|...}]"""
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
                return [{"text": "", "method": f"unsupported ({REJECT_MESSAGE})"}]
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
