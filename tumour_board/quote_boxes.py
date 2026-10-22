"""Where a quote sits on a page, for the viewer's highlight (18 Oct, the fill-in summary's source chips).

Given a document and either a fact id or a quote text, find the page the quote is on and, when the page was read from an image by the
independent OCR engine (word boxes kept on the page, V1 items 8.3 / 8.4), the rectangles of the quote's words as fractions of the page.
A text-layer PDF page gives the page only (no word boxes exist for it: the viewer scrolls to the page). Never raises for an unknown
quote: found is False. No model, nothing is written."""
from . import confirm, extract, grounding, ocr_boxes, scanned, store

MAX_TEXT = 2000


def _pages(doc) -> list:
    return [p if isinstance(p, dict) else {"text": str(p or "")} for p in (doc or {}).get("pages") or []]


def _boxes(pages, loc) -> list:
    """Rectangles for a located span: the page's stored box map, else a map computed from the engine words it still carries; [] when
    the page has no word boxes or too few of the span's words were matched (no box rather than a misleading one)."""
    if not isinstance(loc, dict) or not isinstance(loc.get("page"), int) or not 0 <= loc["page"] < len(pages):
        return []
    p = pages[loc["page"]]
    if not p.get("box_map"):
        eng = p.get("ocr_engine")
        if isinstance(eng, dict) and eng.get("words"):
            try:
                p = {**p, "box_map": ocr_boxes.token_map(p.get("text") or "", eng["words"])}
            except Exception:
                return []
        else:
            return []
    try:
        return extract.quote_boxes([p if i == loc["page"] else x for i, x in enumerate(pages)], loc)
    except Exception:
        return []


def _found(pages, loc, quote, how) -> dict:
    page = loc.get("page") if isinstance(loc, dict) else None
    boxes = _boxes(pages, loc)
    return {"found": True, "page": page, "boxes": boxes, "start": loc.get("start"), "end": loc.get("end"), "quote": quote or loc.get("matched") or "",
            "matched": loc.get("matched") or "", "score": loc.get("score"), "method": scanned.page_method(pages, page), "how": how,
            "page_boxes": bool(boxes) or bool((pages[page] or {}).get("box_map") if isinstance(page, int) and 0 <= page < len(pages) else False)}


def _not_found(reason, **extra) -> dict:
    return {"found": False, "page": None, "boxes": [], "reason": reason, **extra}


def locate_text(doc, text) -> dict:
    """The page (and boxes) of a quote given as text, exact first, else the aligner's best match of at least 92 (reported with its score)."""
    text = str(text or "").strip()[:MAX_TEXT]
    pages = _pages(doc)
    texts = [p.get("text") or "" for p in pages]
    if not text:
        return _not_found("no quote given")
    if not any(texts):
        return _not_found("the document has no readable text")
    loc = grounding.locate(text, texts)
    if not loc:
        for seg in [s for s in text.splitlines() if len(grounding.norm(s)) >= 3]:  # a multi-line quote: the first line that is found
            loc = grounding.locate(seg, texts)
            if loc and loc["score"] == 100:
                return _found(pages, loc, seg, "line")
        return _not_found("quote not found in the document")
    return _found(pages, loc, text, "exact" if loc.get("score") == 100 else "approximate")


def locate_fact(doc, fact_id) -> dict:
    """The page (and boxes) of a fact's quote: its verified location, else the model's location kept when a clinician confirmed the value
    (the clinician's reading has no quote of its own), else the quote text found again in the pages."""
    facts = (doc or {}).get("facts") or {}
    f = facts.get(fact_id)
    if not isinstance(f, dict):
        return _not_found("no such field in this document")
    pages = _pages(doc)
    quote = f.get("quote") or f.get("model_quote") or ""
    loc = f.get("location") or f.get("model_location")
    if isinstance(loc, dict) and isinstance(loc.get("page"), int) and 0 <= loc["page"] < len(pages):
        out = _found(pages, loc, quote, "location")
        if f.get("boxes") and not out["boxes"]:
            out["boxes"] = list(f["boxes"])  # the boxes kept on the fact when it was extracted (V1 item 8.4)
        out["confirmed_by"] = f.get("confirmed_by") or ""
        out["verification"] = f.get("verification") or ""
        return out
    if quote:
        out = locate_text(doc, quote)
        out["verification"] = f.get("verification") or ""
        return out
    return _not_found("this value has no quote", verification=f.get("verification") or "")


def find(case_id, doc_id, fact_id="", text="") -> dict:
    """{found, page, boxes[[x0, y0, x1, y1] fractions of the page], start, end, quote, method, ...} for a document of the Case File; the
    document as the clinicians confirmed it. None when the document does not exist."""
    try:
        d = store.get_doc(case_id, doc_id)
    except ValueError:
        return None
    if not d:
        return None
    d = confirm.apply_to_doc(d, store.get_state(case_id), case_id)
    out = locate_fact(d, str(fact_id)) if fact_id else locate_text(d, text)
    out["doc_id"] = d.get("doc_id")
    out["doc_title"] = (d.get("classification") or {}).get("title") or d.get("filename") or d.get("doc_id")
    out["pages"] = len(d.get("pages") or [])
    if fact_id:
        out["fact_id"] = str(fact_id)
    return out
