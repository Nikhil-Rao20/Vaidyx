"""The staging book as the doctor reads it: one page of the guideline PDF rendered as an image, with the line of a criterion highlighted
(found in the page's own text layer with pdfium's search). Only books named in a rule file are served, and only when the file is on this
server (the licensed AJCC chapters are on the internal instance only).

pdfium is not thread-safe, and the app reads report pages with it on its main thread: page images are therefore drawn in a separate worker
PROCESS (page_image), never in a thread of the app (22 Oct: a render in a worker thread crashed the app). Drawn pages are kept in memory."""
import asyncio
import io
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

from .. import config
from . import PROTOCOL_RULES, rules_for

SCALE = 1.7


def books() -> dict:
    """book id -> {id, title, file, first_page, licensed} for every rule file's book that is on this server."""
    out = {}
    for prot in PROTOCOL_RULES:
        r = rules_for(prot)
        b = (r or {}).get("book")
        if b and path(b).exists():
            out[b["id"]] = b
    return out


def path(book: dict) -> Path:
    p = (config.GUIDELINE_DIR / book["file"]).resolve()
    if config.GUIDELINE_DIR.resolve() not in p.parents:
        raise ValueError("book outside the guideline library")
    return p


def meta(book_id: str) -> dict | None:
    b = books().get(book_id)
    if not b:
        return None
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(path(b)))
    try:
        n = len(pdf)
    finally:
        pdf.close()
    printed = sorted(page_map(book_id))
    return {**b, "pages": n, "printed": printed, "last_page": printed[-1] if printed else b["first_page"] + n - 1, "aspect": aspect(book_id)}


@lru_cache(maxsize=16)
def aspect(book_id: str) -> float:
    """Width over height of the book's pages (the viewer keeps a page's place before its image arrives)."""
    import pypdfium2 as pdfium
    b = books().get(book_id)
    pdf = pdfium.PdfDocument(str(path(b)))
    try:
        w, h = pdf[min(1, len(pdf) - 1)].get_size()
    finally:
        pdf.close()
    return round(w / h, 4) if h else 0.77


def boxes(pdf, index: int, find: str) -> list[list[float]]:
    """Rectangles (fractions of the page: x0, y0, x1, y1, top-left origin) of every match of `find` on the page."""
    page = pdf[index]
    w, h = page.get_size()
    tp = page.get_textpage()
    out = []
    try:
        se = tp.search(find, match_case=False)
        while True:
            r = se.get_next()
            if not r:
                break
            start, count = r
            for i in range(tp.count_rects(start, count)):
                x0, y0, x1, y1 = tp.get_rect(i)  # PDF space: origin bottom left
                out.append([max(0.0, x0 / w), max(0.0, 1 - y1 / h), min(1.0, x1 / w), min(1.0, 1 - y0 / h)])
        out = _whole_lines(tp, w, h, out)
    finally:
        tp.close()
    return out


def _whole_lines(tp, w, h, found):
    """Each match widened to its whole printed line within its column (a scanned two-column page): every text rectangle whose middle sits
    inside the match's height and on the same half of the page joins it."""
    if not found:
        return found
    rects = []
    for i in range(tp.count_rects(0, -1)):
        x0, y0, x1, y1 = tp.get_rect(i)
        rects.append([x0 / w, 1 - y1 / h, x1 / w, 1 - y0 / h])
    out = []
    for fx0, fy0, fx1, fy1 in found:
        left = (fx0 + fx1) / 2 < 0.5
        line = [r for r in rects if fy0 - 0.002 <= (r[1] + r[3]) / 2 <= fy1 + 0.002 and (((r[0] + r[2]) / 2 < 0.5) == left)]
        if line:
            out.append([min(r[0] for r in line + [[fx0, fy0, fx1, fy1]]), min(fy0, min(r[1] for r in line)),
                        max(r[2] for r in line + [[fx0, fy0, fx1, fy1]]), max(fy1, max(r[3] for r in line))])
        else:
            out.append([fx0, fy0, fx1, fy1])
    return out


@lru_cache(maxsize=16)
def page_map(book_id: str) -> dict:
    """Printed page number -> PDF page index, read from each page's running head ("48 Breast 619", "620 American Joint ..."): a scanned
    chapter can carry an unnumbered page, so the offset is not fixed. Pages without a number are left out."""
    import re
    import pypdfium2 as pdfium
    b = books().get(book_id)
    if not b:
        return {}
    pdf = pdfium.PdfDocument(str(path(b)))
    out = {}
    try:
        for i in range(len(pdf)):
            tp = pdf[i].get_textpage()
            head = tp.get_text_range()[:90]
            tp.close()
            m = re.match(r"\s*(?:\d{1,2}\s+[A-Za-z][A-Za-z .]*?\s+)?(\d{2,4})\b", head) or re.search(r"\b(\d{3,4})\s+A\s?m\s?erican", head)
            if m:
                out.setdefault(int(m.group(1)), i)
    finally:
        pdf.close()
    return out


def index_of(book_id: str, book_page: int) -> int | None:
    b = books().get(book_id)
    if not b:
        return None
    m = page_map(book_id)
    if int(book_page) in m:
        return m[int(book_page)]
    i = int(book_page) - int(b["first_page"])
    return i if i >= 0 else None


@lru_cache(maxsize=256)
def page_png(book_id: str, book_page: int, find: str = "") -> tuple[bytes, list] | None:
    """(JPEG bytes, the highlight boxes) of one page, given by its printed page number; None when the book or the page is not here.
    Rendering is slow (about a second): the route calls this in a worker thread, and pages are kept in memory once drawn."""
    b = books().get(book_id)
    if not b:
        return None
    import pypdfium2 as pdfium
    from PIL import ImageDraw
    pdf = pdfium.PdfDocument(str(path(b)))
    try:
        i = index_of(book_id, book_page)
        if i is None or i < 0 or i >= len(pdf):
            return None
        hl = boxes(pdf, i, find) if find else []
        im = pdf[i].render(scale=SCALE).to_pil().convert("RGB")
    finally:
        pdf.close()
    if hl:
        over = im.copy()
        d = ImageDraw.Draw(over)
        W, H = im.size
        for x0, y0, x1, y1 in hl:
            d.rectangle([x0 * W - 3, y0 * H - 2, x1 * W + 3, y1 * H + 2], fill=(1, 203, 211))
        im = __import__("PIL.Image", fromlist=["Image"]).blend(im, over, 0.32)
        d = ImageDraw.Draw(im)
        for x0, y0, x1, y1 in hl:
            d.rectangle([x0 * W - 3, y0 * H - 2, x1 * W + 3, y1 * H + 2], outline=(0, 143, 135), width=2)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=84, optimize=True)
    return buf.getvalue(), hl


_POOL = None
_IMAGES: OrderedDict = OrderedDict()
_KEEP = 200


def _pool():
    global _POOL
    if _POOL is None:
        import concurrent.futures
        import multiprocessing
        import atexit
        _POOL = concurrent.futures.ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn"))
        atexit.register(_POOL.shutdown, wait=True, cancel_futures=True)  # before the interpreter tears its modules down
    return _POOL


async def page_image(book_id: str, book_page: int, find: str = ""):
    """page_png drawn in the worker process (about a second the first time), then from memory."""
    key = (book_id, int(book_page), find or "")
    if key in _IMAGES:
        _IMAGES.move_to_end(key)
        return _IMAGES[key]
    out = await asyncio.get_running_loop().run_in_executor(_pool(), page_png, book_id, int(book_page), find or "")
    if out:
        _IMAGES[key] = out
        while len(_IMAGES) > _KEEP:
            _IMAGES.popitem(last=False)
    return out
