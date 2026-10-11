"""Values read from scans (V1 items 8.1 and 8.2).

A scanned page (a scan, a phone photo, an image-only PDF page) is transcribed by the vision reader (Qwen3.5-4B, Chinese,
non-medical); a value's quote is then checked against that transcription, not against the image, which is weaker than a
quote found in a PDF text layer. Every fact and citation therefore carries the method of the page its quote sits on
(`source_method`), and the UI shows "from scan (OCR)" wherever it is "vision-transcription".

No model here and nothing is changed in the documents' text: this only reads the page records.
"""

SCAN_METHOD = "vision-transcription"  # ingest.ocr_page: a page read by the vision reader from an image
SCAN_LABEL = "from scan (OCR)"


def page_method(pages, page_index) -> str:
    """The method of one page ("text-layer", "vision-transcription", ...), "" when the index is not a page."""
    if isinstance(page_index, int) and not isinstance(page_index, bool) and 0 <= page_index < len(pages or []):
        p = pages[page_index]
        return (p.get("method") or "") if isinstance(p, dict) else ""
    return ""


def fact_source_method(pages, fact) -> str:
    """How the text a value was checked against was obtained: the method of the page its quote sits on. A value without a
    location (not verified, or confirmed by a clinician: then the model's location) takes the document's method when all its
    pages share one, else ""."""
    fact = fact or {}
    loc = fact.get("location") or fact.get("model_location")
    if isinstance(loc, dict) and loc.get("page") is not None:
        m = page_method(pages, loc.get("page"))
        if m:
            return m
    methods = {p.get("method") or "" for p in pages or [] if isinstance(p, dict)}
    return methods.pop() if len(methods) == 1 else ""


def scan_pages(pages) -> list:
    """Indices of the pages read from an image by the vision reader."""
    return [i for i, p in enumerate(pages or []) if isinstance(p, dict) and p.get("method") == SCAN_METHOD]


def with_source_methods(doc):
    """The document with `source_method` on every fact (and on every alternative of a fact) that lacks it: documents processed
    before item 8.1 get it from their page records, with no re-processing. Returns a new dict when anything was added; the
    input is never mutated."""
    facts = (doc or {}).get("facts") or {}
    pages = (doc or {}).get("pages") or []
    if not facts or all(isinstance(f, dict) and "source_method" in f and all("source_method" in a for a in f.get("alternatives") or [])
                        for f in facts.values()):
        return doc
    out = {}
    for fid, f in facts.items():
        if not isinstance(f, dict):
            out[fid] = f
            continue
        g = dict(f)
        if "source_method" not in g:
            g["source_method"] = fact_source_method(pages, g)
        if g.get("alternatives"):
            g["alternatives"] = [a if "source_method" in a else {**a, "source_method": fact_source_method(pages, a)} for a in g["alternatives"]]
        out[fid] = g
    return {**doc, "facts": out}


def needs_scan_confirmation(entry, spec) -> bool:
    """V1 item 8.2: a critical value (facts.json "critical": true) whose quote was verified on a scanned page counts for the
    Pre-Authorization only after a clinician has confirmed it against the image (confirm_value turns it "confirmed"). A value
    found in a PDF text layer, or one already confirmed, needs nothing; a value not verified never counts anyway."""
    entry = entry or {}
    return bool((spec or {}).get("critical")) and entry.get("verification") == "verified" and entry.get("source_method") == SCAN_METHOD


def citation_source_method(pages, page_index) -> dict:
    """{"source_method": ...} for a citation located on page_index of a document's pages, {} when unknown."""
    m = page_method(pages, page_index)
    return {"source_method": m} if m else {}
