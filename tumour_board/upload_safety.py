"""Safe upload into a private Case File (guest reviewers with anonymized real files, 5 Nov 2026).

Before anything is stored:
  1. type     the file must be one the reader handles (PDF, images, Office, plain text) AND its content must match its name
              (a renamed file is refused);
  2. danger   password-protected PDFs, PDFs with scripts, launch actions or embedded files, Office files with macros, and images
              too large to open safely are refused;
  3. clean    hidden details are removed from the stored copy: PDF document information and XMP, image EXIF / XMP / text chunks
              (camera, GPS, author, software), Office and OpenDocument author properties, the RTF \\info group;
  4. scan     the text layer (and the file name) is searched for likely identifiers: mobile numbers, 12-digit (Aadhaar-like)
              numbers, ABHA numbers, e-mail addresses, PIN codes after an address word, dates of birth, hospital ids after a label
              (UHID, MRN, IP / OP No.), and a filled "Name:" field. Scanned pages have no text layer: they are checked after reading
              (scan_text on the read text).

Findings carry a masked sample only ("98•••••312"), never the full value, so they can be shown and audited safely.
No model is called here; everything is local and deterministic.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".docx", ".doc", ".rtf", ".odt", ".xls", ".xlsx",
           ".pptx", ".txt", ".csv"}
OOXML = {".docx", ".xlsx", ".pptx"}
OLE = {".doc", ".xls"}
IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
MAX_PIXELS = 180_000_000          # an image larger than this is refused (decompression bombs)
MAX_SCAN_PAGES = 300              # text-layer pages searched per PDF
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass
class Checked:
    name: str
    ext: str
    data: bytes                    # the cleaned bytes to store
    refused: str = ""              # a reason: the file is not stored
    notes: list = field(default_factory=list)       # what was cleaned, or could not be
    findings: list = field(default_factory=list)    # likely identifiers: {kind, where, sample}
    text_checked: bool = False     # a text layer was searched (False: a scan or image, checked after reading)


def _ext(name: str) -> str:
    n = (name or "").lower()
    return n[n.rfind("."):] if "." in n else ""


# ------------------------------------------------------------------------------------------------------------------ 1. type
def sniff(name: str, data: bytes) -> str:
    """'' when the content matches the extension, else the reason for refusing."""
    ext = _ext(name)
    if ext not in ALLOWED:
        return f"{ext or 'this kind of file'} is not accepted here (PDF, images, Word, Excel, PowerPoint, OpenDocument, RTF, TXT or CSV)"
    head = data[:2048]
    ok = {
        ".pdf": b"%PDF-" in head[:1024],
        ".png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": head.startswith(b"\xff\xd8\xff"), ".jpeg": head.startswith(b"\xff\xd8\xff"),
        ".tif": head[:4] in (b"II*\x00", b"MM\x00*"), ".tiff": head[:4] in (b"II*\x00", b"MM\x00*"),
        ".bmp": head.startswith(b"BM"),
        ".webp": head[:4] == b"RIFF" and head[8:12] == b"WEBP",
        ".doc": head.startswith(OLE_MAGIC), ".xls": head.startswith(OLE_MAGIC),
        ".rtf": head.lstrip().startswith(b"{\\rtf"),
    }.get(ext)
    if ext in OOXML or ext == ".odt":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
            ok = ("[Content_Types].xml" in names) if ext in OOXML else ("mimetype" in names and "content.xml" in names)
        except zipfile.BadZipFile:
            ok = False
    if ext in (".txt", ".csv"):
        ok = b"\x00" not in data[:65536] and _decode(data) is not None
    return "" if ok else f"the content of {name} does not match its name ({ext})"


def _decode(data: bytes):
    for enc in ("utf-8", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


# --------------------------------------------------------------------------------------------------- 2 + 3. danger, clean
_PDF_DANGER = (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/RichMedia", b"/XFA")


def _pdf(c: Checked) -> None:
    from pypdf import PdfReader, PdfWriter
    raw = c.data
    if any(t in raw for t in _PDF_DANGER):
        c.refused = "a PDF with scripts, launch actions or embedded files is not accepted; print it to a new PDF and upload that"
        return
    try:
        r = PdfReader(io.BytesIO(raw))
        if r.is_encrypted:
            c.refused = "a password-protected PDF is not accepted; remove the password and upload again"
            return
        w = PdfWriter(clone_from=r)
        w.metadata = None                      # the document information (author, creator, producer, title)
        root = w._root_object
        if "/Metadata" in root:                # XMP
            del root["/Metadata"]
        out = io.BytesIO(); w.write(out)
        c.data = out.getvalue(); c.notes.append("PDF document details (author, title, software) removed")
    except Exception as e:  # an unusual PDF: stored as it is (the reader may still read it), said plainly
        c.notes.append(f"PDF details could not be removed ({type(e).__name__}); stored as uploaded")


def _image(c: Checked) -> None:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".tif": "TIFF", ".tiff": "TIFF", ".bmp": "BMP", ".webp": "WEBP"}[c.ext]
    try:  # only the decoder of the file's own type (pillow's other decoders, where most advisories are, are never reached)
        im = Image.open(io.BytesIO(c.data), formats=[fmt])
        im.load()
    except Exception as e:  # includes Image.DecompressionBombError
        c.refused = f"the image could not be opened safely ({type(e).__name__})"
        return
    frames = []
    try:
        n = getattr(im, "n_frames", 1)
        for i in range(n):
            im.seek(i)
            f = im.copy()
            f.info = {}                        # EXIF, XMP, text chunks, comments
            frames.append(f)
    except Exception:
        frames = frames or [im.copy()]
    out = io.BytesIO()
    first = frames[0]
    if fmt == "JPEG" and first.mode not in ("RGB", "L", "CMYK"):
        first = first.convert("RGB")
    kw = {"quality": 95} if fmt in ("JPEG", "WEBP") else {}
    if len(frames) > 1 and fmt == "TIFF":
        first.save(out, format=fmt, save_all=True, append_images=frames[1:], **kw)
    else:
        first.save(out, format=fmt, **kw)
    c.data = out.getvalue(); c.notes.append("image details (camera, location, author, software) removed")


_CORE_EMPTY = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties '
               b'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
               b'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
               b'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>')
_ODT_META_EMPTY = (b'<?xml version="1.0" encoding="UTF-8"?>\n<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                   b'office:version="1.2"><office:meta/></office:document-meta>')


def _zip_office(c: Checked) -> None:
    try:
        zin = zipfile.ZipFile(io.BytesIO(c.data))
        names = zin.namelist()
    except zipfile.BadZipFile:
        c.refused = "the Office file is damaged"
        return
    if any(n.lower().endswith("vbaproject.bin") or n.lower().startswith("basic/") for n in names):
        c.refused = "an Office file with macros is not accepted; save it as a normal document and upload that"
        return
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            n = info.filename
            if n == "docProps/core.xml":
                zout.writestr(info, _CORE_EMPTY)
            elif n in ("docProps/custom.xml",):
                continue
            elif c.ext == ".odt" and n == "meta.xml":
                zout.writestr(info, _ODT_META_EMPTY)
            elif n == "mimetype":
                zout.writestr(info, zin.read(n), compress_type=zipfile.ZIP_STORED)
            else:
                zout.writestr(info, zin.read(n))
    if c.ext in OOXML and "docProps/custom.xml" in names:  # its relationship / content-type entries stay valid without the part
        pass
    c.data = out.getvalue(); c.notes.append("document author and properties removed")


def _rtf(c: Checked) -> None:
    text = c.data.decode("latin-1")
    cleaned = re.sub(r"\{\\info\b(?:[^{}]|\{[^{}]*\})*\}", "", text)
    if cleaned != text:
        c.data = cleaned.encode("latin-1"); c.notes.append("RTF document details (author) removed")


# ---------------------------------------------------------------------------------------------------------- 4. identifiers
def _mask(v: str) -> str:
    v = v.strip()
    keep = re.sub(r"\s", "", v)
    if len(keep) <= 4:
        return "•" * len(keep)
    return keep[:2] + "•" * max(3, len(keep) - 4) + keep[-2:]


_PATTERNS = [  # (kind, compiled, value group): ordered; overlapping matches of a later kind are dropped
    ("ABHA number", re.compile(r"(?<!\d)(\d{2}-\d{4}-\d{4}-\d{4})(?!\d)"), 1),
    ("12-digit number (Aadhaar-like)", re.compile(r"(?<![\d-])(\d{4}[ -]?\d{4}[ -]?\d{4})(?![\d-])"), 1),
    ("mobile number", re.compile(r"(?<![\d/-])((?:\+?91[ -]?)?[6-9]\d{4}[ -]?\d{5})(?![\d/-])"), 1),
    ("e-mail address", re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"), 1),
    ("hospital id", re.compile(r"\b(?:UHID|MRN|MR\s*No\.?|CR\s*No\.?|IP\s*No\.?|OP\s*No\.?|IPD\s*No\.?|OPD\s*No\.?|Hospital\s*No\.?|"
                               r"Reg(?:istration)?\.?\s*No\.?|Patient\s*ID)\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9/\-]{3,})", re.I), 1),
    ("date of birth", re.compile(r"\b(?:DOB|D\.O\.B\.?|Date\s+of\s+Birth)\s*[:\-]?\s*(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", re.I), 1),
    ("PIN code", re.compile(r"\b(?:PIN|Pin\s*code|Pincode|Postal\s*code)\s*[:\-]?\s*([1-9]\d{5})\b|[A-Za-z]{3,}\s*[-\u2013]\s*([1-9]\d{5})\b"), 0),
    ("patient name", re.compile(r"\b(?:Patient(?:'s)?\s+Name|Name\s+of\s+(?:the\s+)?Patient|Pt\.?\s*Name|Name)\s*[:\-]\s*"
                                r"((?:(?:Mr|Mrs|Ms|Smt|Shri|Sri|Dr|Baby|Master)\.?[ \t]+)?(?!(?:Age|Sex|Gender|UHID|MRN|Date|DOB|Case)\b)[A-Z][a-z]{2,}"
                                r"(?:[ \t](?!(?:Age|Sex|Gender|UHID|MRN|Date|DOB|IP|OP|Ward|Bed)\b)[A-Z][a-z]{1,}){0,3})"), 1),
]
_BLANKS = re.compile(r"^(?:x+|\*+|_+|-+|n/?a|nil|none|anonym\w*|redacted|withheld|not\s+given|patient|case\s+[a-z0-9]+)$", re.I)


def scan_text(text: str, where: str = "") -> list:
    """Likely identifiers in a text: [{kind, where, sample}] (masked samples, at most 12, one per value)."""
    out, seen, spans = [], set(), []
    for kind, rx, g in _PATTERNS:
        for m in rx.finditer(text or ""):
            if g == 0:
                v = next((x for x in m.groups() if x), "")
                s, e = m.span()
            else:
                v = m.group(g) or ""
                s, e = m.span(g)
            v = v.strip()
            if not v or _BLANKS.match(v) or any(a <= s < b or a < e <= b for a, b in spans):
                continue
            if kind == "12-digit number (Aadhaar-like)" and len(re.sub(r"\D", "", v)) != 12:
                continue
            key = (kind, re.sub(r"\s", "", v).lower())
            if key in seen:
                continue
            seen.add(key); spans.append((s, e))
            out.append({"kind": kind, "where": where, "sample": _mask(v)})
            if len(out) >= 12:
                return out
    return out


def _text_layer(c: Checked) -> list:
    """[(where, text)] of the text the file carries without reading (scans and images have none)."""
    if c.ext == ".pdf":
        try:
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(c.data)
            out = []
            try:
                for i in range(min(len(doc), MAX_SCAN_PAGES)):
                    tp = doc[i].get_textpage()
                    out.append((f"page {i + 1}", tp.get_text_range()))
            finally:
                doc.close()
            return out
        except Exception:
            return []
    if c.ext in (".txt", ".csv"):
        return [("text", _decode(c.data) or "")]
    if c.ext == ".rtf":
        return [("text", re.sub(r"\\[a-z]+-?\d* ?|[{}]", " ", c.data.decode("latin-1")))]
    if c.ext in OOXML or c.ext == ".odt":
        parts = []
        try:
            with zipfile.ZipFile(io.BytesIO(c.data)) as z:
                for n in z.namelist():
                    if (n.startswith(("word/", "xl/sharedStrings", "xl/worksheets/", "ppt/slides/")) and n.endswith(".xml")) or n == "content.xml":
                        parts.append(re.sub(r"<[^>]+>", " ", z.read(n).decode("utf-8", "replace")))
        except zipfile.BadZipFile:
            return []
        return [("text", re.sub(r"[ \t]+", " ", " ".join(parts)))]
    return []                                   # images and old binary Office files: checked after reading


def check(name: str, data: bytes) -> Checked:
    c = Checked(name=name, ext=_ext(name), data=data)
    c.refused = sniff(name, data)
    if c.refused:
        return c
    if c.ext == ".pdf":
        _pdf(c)
    elif c.ext in IMAGES:
        _image(c)
    elif c.ext in OOXML or c.ext == ".odt":
        _zip_office(c)
    elif c.ext == ".rtf":
        _rtf(c)
    elif c.ext in OLE:
        if b"V\x00B\x00A\x00" in c.data or b"_VBA_PROJECT" in c.data:
            c.refused = "an Office file with macros is not accepted; save it as a normal document and upload that"
            return c
        c.notes.append("older Office format: details inside the file could not be removed (save as .docx / .xlsx to remove them)")
    if c.refused:
        return c
    c.findings = scan_text(re.sub(r"[_\-]+", " ", name.rsplit(".", 1)[0]), "file name")
    layer = _text_layer(c)
    c.text_checked = any(t.strip() for _w, t in layer)
    for where, text in layer:
        c.findings += scan_text(text, where)
        if len(c.findings) >= 12:
            c.findings = c.findings[:12]
            break
    return c
