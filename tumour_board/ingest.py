"""Turn any file in a Case File folder into per-page text.

Order of preference (most faithful first):
  1. text layer of a PDF / plain-text / office document (exact, no model involved)
  2. page image -> vision "reader" model, verbatim transcription (only for scans / photos / image-only PDFs)
"""
import asyncio, io, re
from pathlib import Path

from . import config, llm, store

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".xml", ".hl7"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
OFFICE_EXT = {".docx", ".doc", ".rtf", ".odt", ".xlsx", ".pptx"}
SUPPORTED = TEXT_EXT | IMG_EXT | OFFICE_EXT | {".pdf"}

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
        try:
            from markitdown import MarkItDown
            return [{"text": MarkItDown().convert(str(path)).text_content, "method": "office-text"}]
        except Exception as e:
            return [{"text": "", "method": f"unsupported ({e.__class__.__name__}: install markitdown for {ext})"}]
    return [{"text": "", "method": "unsupported format"}]
