"""Turn any file in a Case File folder into per-page text.

Order of preference (most faithful first):
  1. text layer of a PDF / plain-text / office document (exact, no model involved)
  2. page image -> vision "reader" model, verbatim transcription (only for scans / photos / image-only PDFs)
"""
import asyncio, io
from pathlib import Path

from . import llm, store

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".xml", ".hl7"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
OFFICE_EXT = {".docx", ".doc", ".rtf", ".odt", ".xlsx", ".pptx"}
SUPPORTED = TEXT_EXT | IMG_EXT | OFFICE_EXT | {".pdf"}

OCR_PROMPT = (
    "Transcribe all text on this page exactly as written, from top to bottom. Keep every value, unit, date, name, "
    "status line and signature line exactly. For tables write one row per line with cells separated by ' | '. "
    "Do not correct, interpret, summarise, translate or add anything. If a word is unreadable write [illegible]. "
    "Output only the transcription.")


async def ocr_image(png_bytes: bytes, audit=None) -> str:
    msg = [{"role": "user", "content": [llm.image_part(png_bytes, "image/png"), {"type": "text", "text": OCR_PROMPT}]}]
    return (await llm.chat("reader", msg, max_tokens=3000, purpose="transcribe page", audit=audit)).strip()


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
            if len(t.strip()) >= 40:
                pages.append({"text": t, "method": "text-layer"})
            else:
                pages.append(None); todo.append(i)
        if todo:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(str(path))
            imgs = [_img_bytes(pdf[i].render(scale=2.0).to_pil()) for i in todo]
            texts = await asyncio.gather(*[ocr_image(b, audit) for b in imgs])
            for i, t in zip(todo, texts):
                pages[i] = {"text": t, "method": "vision-transcription"}
        return pages
    if ext in IMG_EXT:
        from PIL import Image, ImageSequence
        im = Image.open(path)
        frames = [_img_bytes(f.copy()) for f in ImageSequence.Iterator(im)] if getattr(im, "n_frames", 1) > 1 else [path.read_bytes()]
        texts = await asyncio.gather(*[ocr_image(b, audit) for b in frames])
        return [{"text": t, "method": "vision-transcription"} for t in texts]
    if ext in OFFICE_EXT:
        try:
            from markitdown import MarkItDown
            return [{"text": MarkItDown().convert(str(path)).text_content, "method": "office-text"}]
        except Exception as e:
            return [{"text": "", "method": f"unsupported ({e.__class__.__name__})"}]
    return [{"text": "", "method": "unsupported format"}]
