"""The board deck (.pptx), 19 Oct 2026: the slides of a Tumour Board meeting or of one Case File, drawn by python-pptx on a design of
our own (16:9, the hospital's logo and the Vaidyx mark on every cover, a quiet footer on every slide), from the same material the
room screen shows (meetings.slides: the summary, the values with their sources, the gaps, the imaging and pathology records, the
points for review) and, after the meeting, the outcome of each case and the minutes. No model call: every sentence on a slide is
one the Case File already holds, with its source; an AI draft is labelled as such.

    build_meeting(mid, r)  -> bytes    cover, agenda, one chapter per Case File, outcomes and minutes when the meeting is closed
    build_case(cid, r)     -> bytes    cover and the chapter of one Case File
    filename(...)

The design (theme.py): Arial (on every laptop and in LibreOffice), the Vaidyx teal for one accent, the logo's deep navy for the cover,
ink on white for the body, a 0.4 in margin, 14 pt body, titles 28 pt. Text that does not fit is carried to a further slide, never cut.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from .. import board, config, meetings, org, store

ASSETS = Path(__file__).resolve().parent / "assets"
W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.45)
FONT = "Arial"

INK = RGBColor(0x12, 0x1A, 0x24)
BODY = RGBColor(0x3B, 0x47, 0x54)
MUTED = RGBColor(0x5F, 0x6B, 0x78)
LINE = RGBColor(0xE2, 0xE8, 0xEF)
PAGE = RGBColor(0xF5, 0xF7, 0xFA)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TEAL = RGBColor(0x00, 0xC0, 0xB5)
TEAL_DARK = RGBColor(0x00, 0x8F, 0x87)
NAVY = RGBColor(0x00, 0x18, 0x3C)
OK = RGBColor(0x1D, 0x6A, 0x44)
WARN = RGBColor(0x8A, 0x52, 0x00)
BAD = RGBColor(0xB2, 0x36, 0x2B)
REVIEW = RGBColor(0x5B, 0x3F, 0xC4)
SOFT = {"ok": RGBColor(0xE4, 0xF4, 0xEA), "warn": RGBColor(0xFD, 0xF1, 0xD6), "bad": RGBColor(0xFB, 0xE8, 0xE5), "review": RGBColor(0xEE, 0xEB, 0xFF), "muted": RGBColor(0xF1, 0xF4, 0xF8), "teal": RGBColor(0xE4, 0xF6, 0xF4)}
TONE = {"ok": OK, "warn": WARN, "bad": BAD, "review": REVIEW, "muted": MUTED, "teal": TEAL_DARK}

SCOPE_LINE = "Vaidyx checks, routes, summarises and flags. Never a diagnosis, a stage or a treatment advice: the decision is the board's."


# ---------------------------------------------------------------------------------------------------- small helpers
def _dmy(iso) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(iso or "")


def _dmy_hm(iso) -> str:
    s = str(iso or "")
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})", s)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}, {m.group(4)}:{m.group(5)}" if m else _dmy(s)


def _clean(s) -> str:
    return " ".join(str(s or "").split())


def _title_case(t: str) -> str:
    """A record title shouted in capitals ("HISTOPATHOLOGY REPORT") in sentence case, the medical acronyms kept."""
    t = _clean(t)
    letters = re.sub(r"[^A-Za-z]", "", t)
    if not letters or len(re.sub(r"[^A-Z]", "", letters)) / len(letters) < 0.8:
        return t
    keep = {"ER", "PR", "HER2", "CBC", "LFT", "RFT", "USG", "CT", "CECT", "MRI", "PET", "IHC", "HPE", "OPD", "BI-RADS", "TNM", "FNAC", "ECG", "HIV", "CEA", "PSA", "AFP", "LDH", "TLC", "WBC", "EGFR", "ALK", "PD-L1", "MG", "US", "DX", "UHID", "OP", "IP", "II", "III", "IV"}
    special = {"KI-67": "Ki-67", "X-RAY": "X-ray", "HBSAG": "HBsAg", "HBA1C": "HbA1c"}
    out = []
    for w in t.lower().split(" "):
        core = re.sub(r"^[(\[]+|[)\],.;:]+$", "", w)
        up = core.upper()
        fixed = special.get(up) or (up if up in keep else None)
        out.append(w.replace(core, fixed) if fixed else w)
    s = " ".join(out)
    return s[:1].upper() + s[1:]


def _lines(text: str, width: Emu, pt: float) -> int:
    """How many lines `text` takes at `pt` in a box `width` wide (Arial averages about 0.5 em per character)."""
    per_line = max(10, int(width / Emu(int(Pt(pt) * 0.52))))
    n = 0
    for para in str(text or "").split("\n"):
        n += max(1, -(-len(para) // per_line))
    return n


def _fit(items: list[str], width: Emu, height: Emu, pt: float, gap_lines: float = 0.35) -> list[list[str]]:
    """Split `items` into pages, each fitting `height` at `pt` (a short gap between items). An item longer than a page stands alone."""
    line_h = Emu(int(Pt(pt) * 1.25))
    pages, cur, used = [], [], 0
    for it in items:
        need = (_lines(it, width, pt) + gap_lines) * line_h
        if cur and used + need > height:
            pages.append(cur); cur, used = [], 0
        cur.append(it); used += need
    if cur:
        pages.append(cur)
    return pages or [[]]


# ---------------------------------------------------------------------------------------------------- drawing
class Deck:
    """One presentation being drawn: the hospital, the footer words, the page counter."""

    def __init__(self, hospital: dict, footer: str, synthetic: bool = False):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = W, H
        self.blank = self.prs.slide_layouts[6]
        self.hospital = hospital
        self.footer = footer
        self.synthetic = synthetic
        self.n = 0
        self.logo = hospital_logo_path()

    # -- primitives
    def slide(self):
        self.n += 1
        return self.prs.slides.add_slide(self.blank)

    @staticmethod
    def rect(s, x, y, w, h, fill: RGBColor | None, line: RGBColor | None = None, radius: float | None = None):
        shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, x, y, w, h)
        if radius is not None:
            shp.adjustments[0] = radius
        if fill is None:
            shp.fill.background()
        else:
            shp.fill.solid(); shp.fill.fore_color.rgb = fill
        if line is None:
            shp.line.fill.background()
        else:
            shp.line.color.rgb = line; shp.line.width = Pt(0.75)
        shp.shadow.inherit = False
        return shp

    @staticmethod
    def text(s, x, y, w, h, runs, size: float = 14, color: RGBColor = BODY, bold: bool = False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font: str = FONT, line_spacing: float = 1.15):
        """`runs`: a string (paragraphs split on \\n) or a list of paragraphs, each a string or a list of (text, {size, color, bold}) runs."""
        tb = s.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.05); tf.margin_top = tf.margin_bottom = Inches(0.03)
        tf.vertical_anchor = anchor
        paras = runs.split("\n") if isinstance(runs, str) else list(runs)
        for i, para in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            p.line_spacing = line_spacing
            pieces = [(para, {})] if isinstance(para, str) else para
            for txt, st in pieces:
                r = p.add_run(); r.text = str(txt)
                f = r.font; f.name = st.get("font", font); f.size = Pt(st.get("size", size)); f.bold = st.get("bold", bold)
                f.color.rgb = st.get("color", color)
                if st.get("italic"):
                    f.italic = True
        return tb

    @staticmethod
    def image(s, path: Path | None, x, y, w=None, h=None):
        if not path or not Path(path).exists():
            return None
        try:
            return s.shapes.add_picture(str(path), x, y, width=w, height=h)
        except Exception:
            return None

    def pill(self, s, x, y, text: str, tone: str = "muted", size: float = 10) -> Emu:
        w = Emu(int(Pt(size) * 0.58 * (len(text) + 3)))
        h = Emu(int(Pt(size) * 2.0))
        self.rect(s, x, y, w, h, SOFT.get(tone, SOFT["muted"]), None, radius=0.5)
        self.text(s, x, y, w, h, text, size=size, color=TONE.get(tone, MUTED), bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        return w

    # -- page furniture
    def chrome(self, s, title: str, kicker: str = "", tone: str | None = None, tag: str | None = None):
        """The page's title row and footer; returns the top of the body area."""
        self.rect(s, 0, 0, W, H, PAGE)
        self.rect(s, MARGIN, Inches(0.4), Inches(0.08), Inches(0.62), TEAL)
        if kicker:
            self.text(s, MARGIN + Inches(0.2), Inches(0.32), W - 2 * MARGIN - Inches(3), Inches(0.3), kicker.upper(), size=10, color=TEAL_DARK, bold=True)
        self.text(s, MARGIN + Inches(0.2), Inches(0.52) if kicker else Inches(0.4), W - 2 * MARGIN - Inches(3.2), Inches(0.6), title, size=26, color=INK, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        if tag:
            self.pill(s, W - MARGIN - Inches(2.6), Inches(0.58), tag, tone or "muted", size=10)
        self.footer_on(s)
        return Inches(1.3)

    def footer_on(self, s):
        y = H - Inches(0.42)
        self.rect(s, MARGIN, y - Inches(0.08), W - 2 * MARGIN, Emu(9525), LINE)
        self.image(s, ASSETS / "vaidyx-icon.png", MARGIN, y + Inches(0.02), h=Inches(0.22))
        self.text(s, MARGIN + Inches(0.36), y - Inches(0.02), W - 2 * MARGIN - Inches(2), Inches(0.3), self.footer, size=9, color=MUTED, anchor=MSO_ANCHOR.MIDDLE)
        self.text(s, W - MARGIN - Inches(1.6), y - Inches(0.02), Inches(1.6), Inches(0.3), f"{self.n}", size=9, color=MUTED, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
        if self.synthetic:
            self.text(s, W - MARGIN - Inches(4.2), y - Inches(0.02), Inches(2.5), Inches(0.3), "SYNTHETIC DATA", size=9, color=BAD, bold=True, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)

    # -- the cover
    def cover(self, title: str, lines: list[str], small: list[str]):
        s = self.slide()
        self.rect(s, 0, 0, W, H, WHITE)
        self.rect(s, 0, 0, Inches(4.9), H, NAVY)
        self.rect(s, Inches(4.9), 0, Inches(0.12), H, TEAL)
        self.image(s, ASSETS / "vaidyx-icon-white.png", Inches(0.6), Inches(0.6), h=Inches(0.7))
        self.image(s, ASSETS / "vaidyx-wordmark-white.png", Inches(1.55), Inches(0.72), h=Inches(0.46))
        self.text(s, Inches(0.6), Inches(1.5), Inches(3.9), Inches(0.4), "TUMOUR BOARD", size=12, color=RGBColor(0x9F, 0xE3, 0xDF), bold=True)
        self.text(s, Inches(0.6), H - Inches(2.4), Inches(3.9), Inches(1.6), small, size=10, color=RGBColor(0xC9, 0xD4, 0xDE), line_spacing=1.3)
        x = Inches(5.6)
        y = Inches(0.8)
        if self.logo:
            pic = self.image(s, self.logo, x, y, h=Inches(1.0))
            y += Inches(1.3) if pic else 0
        hosp = _clean(self.hospital.get("name")) or "Hospital"
        self.text(s, x, y, W - x - MARGIN, Inches(0.5), hosp, size=16, color=MUTED, bold=True)
        tw = W - x - MARGIN
        tsize = 36 if len(title) <= 20 else 30 if len(title) <= 34 else 24
        tlines = _lines(title, tw, tsize * 1.25)  # bold display text runs wider than body text
        th = Emu(int(Pt(tsize) * 1.25 * tlines)) + Inches(0.2)
        self.text(s, x, y + Inches(0.55), tw, th, title, size=tsize, color=INK, bold=True, line_spacing=1.05)
        self.text(s, x, y + Inches(0.7) + th, tw, Inches(2.4), lines, size=16, color=BODY, line_spacing=1.35)
        self.text(s, x, H - Inches(0.9), W - x - MARGIN, Inches(0.5), SCOPE_LINE, size=10, color=MUTED)
        if self.synthetic:
            self.pill(s, x, H - Inches(1.35), "SYNTHETIC DATA: demo hospital, fake patients", "bad", 10)
        return s

    # -- content blocks
    def bullets(self, s, x, y, w, h, items: list, size: float = 14, numbered: bool = False, color: RGBColor = BODY):
        paras = []
        for i, it in enumerate(items):
            runs = it if isinstance(it, list) else [(it, {})]
            lead = f"{i + 1}.  " if numbered else "•  "
            paras.append([(lead, {"color": TEAL_DARK, "bold": True})] + runs)
        return self.text(s, x, y, w, h, paras, size=size, color=color, line_spacing=1.2)

    def section_list(self, kicker: str, title: str, items: list, size: float = 14, numbered: bool = False, tag: str | None = None, tone: str | None = None, note: str = ""):
        """One or more slides of bulleted items; a long list carries on."""
        w = W - 2 * MARGIN
        body_top = Inches(1.3)
        body_h = H - body_top - Inches(0.7) - (Inches(0.4) if note else 0)
        plain = [it if isinstance(it, str) else "".join(t for t, _ in it) for it in items] or ["Nothing documented."]
        pages = _fit(plain, w, body_h, size)
        idx = 0
        for pi, page in enumerate(pages):
            s = self.slide()
            self.chrome(s, title + (f" ({pi + 1} of {len(pages)})" if len(pages) > 1 else ""), kicker, tone, tag)
            chunk = items[idx: idx + len(page)] if items else ["Nothing documented."]
            idx += len(page)
            self.bullets(s, MARGIN, body_top, w, body_h, chunk, size=size, numbered=numbered)
            if note:
                self.text(s, MARGIN, H - Inches(1.05), w, Inches(0.4), note, size=10, color=MUTED)

    def table(self, kicker: str, title: str, rows: list[list], widths: list[float], header: list[str], size: float = 11, tag: str | None = None, tone: str | None = None, note: str = ""):
        """Rows of text cells drawn as a light table, paginated by height."""
        body_top = Inches(1.3)
        row_h = Emu(int(Pt(size) * 2.6))
        avail = H - body_top - Inches(0.85) - (Inches(0.3) if note else 0)
        per_page = max(4, int(avail / row_h) - 1)
        pages = [rows[i: i + per_page] for i in range(0, len(rows), per_page)] or [[]]
        total_w = W - 2 * MARGIN
        xs = [MARGIN]
        for f in widths[:-1]:
            xs.append(xs[-1] + Emu(int(total_w * f)))
        for pi, page in enumerate(pages):
            s = self.slide()
            self.chrome(s, title + (f" ({pi + 1} of {len(pages)})" if len(pages) > 1 else ""), kicker, tone, tag)
            y = body_top
            self.rect(s, MARGIN, y, total_w, row_h, SOFT["muted"])
            for j, hd in enumerate(header):
                self.text(s, xs[j] + Inches(0.05), y, Emu(int(total_w * widths[j])) - Inches(0.1), row_h, hd.upper(), size=size - 2, color=MUTED, bold=True, anchor=MSO_ANCHOR.MIDDLE)
            y += row_h
            for row in page:
                self.rect(s, MARGIN, y + row_h - Emu(9525), total_w, Emu(9525), LINE)
                for j, cell in enumerate(row):
                    runs = cell if isinstance(cell, list) else [(str(cell), {})]
                    self.text(s, xs[j] + Inches(0.05), y, Emu(int(total_w * widths[j])) - Inches(0.1), row_h, [runs], size=size, color=INK if j == 1 else BODY, anchor=MSO_ANCHOR.MIDDLE, line_spacing=1.0)
                y += row_h
            if not page:
                self.text(s, MARGIN, y + Inches(0.1), total_w, Inches(0.5), "Nothing documented.", size=12, color=MUTED)
            if note:
                self.text(s, MARGIN, H - Inches(0.95), total_w, Inches(0.35), note, size=10, color=MUTED)

    def save(self) -> bytes:
        buf = io.BytesIO()
        self.prs.save(buf)
        return buf.getvalue()


# ---------------------------------------------------------------------------------------------------- the material
def hospital_logo_path() -> Path | None:
    """The hospital's uploaded logo (PNG or JPEG under the data root), else the demo emblem when the hospital is the demo one."""
    h = org.hospital()
    logo = h.get("logo") if isinstance(h.get("logo"), dict) else {}
    f = str(logo.get("file") or "")
    if f and re.match(r"^hospital_logo\.(png|jpe?g)$", f):
        p = config.DATA_ROOT / f
        if p.exists():
            return p
    if "demo" in _clean(h.get("name")).lower():
        return ASSETS / "demo-hospital.png"
    return None


def _src(c: dict) -> str:
    t = _title_case(c.get("doc_title") or "record")
    return f"{t}, p. {int(c['page']) + 1}" if isinstance(c.get("page"), int) else t


def _sentence_runs(x, size_small: float = 9) -> list:
    """A summary sentence with its sources as small grey runs."""
    if isinstance(x, str):
        return [(x, {})]
    runs = [(str(x.get("text") or ""), {})]
    cites = x.get("citations") or []
    if cites:
        runs.append(("  [" + "; ".join(_src(c) for c in cites[:2]) + "]", {"size": size_small, "color": MUTED}))
    return runs


def _case_material(cid: str, r: dict | None) -> dict:
    """What a chapter needs: the case, the slides material from meetings.slides, the question, the patient line."""
    c = store.get_case(cid)
    st = store.get_state(cid) or {}
    sl = {x["id"]: x for x in meetings.slides(cid, r)}
    return {"case": c, "state": st, "slides": sl, "patient_line": meetings.patient_line(c, r), "question": meetings._board_question(c, st)}


def _summary_items(sl: dict) -> tuple[list, str | None, str]:
    """The summary sentences (with sources) or the gate lines; the tag and tone for the title row."""
    summ = (sl.get("summary") or {}).get("content") or {}
    if summ.get("from") == "summary":
        items = []
        for sec in summ.get("sections") or []:
            title = _clean(sec.get("title"))
            sents = sec.get("sentences") or []
            if not sents:
                continue
            if title:
                items.append([(title + ": ", {"bold": True, "color": INK})] + sum((_sentence_runs(x) + [(" ", {})] for x in sents), []))
            else:
                for x in sents:
                    items.append(_sentence_runs(x))
        tag = "Reviewed" if summ.get("reviewed") else "AI draft, not reviewed"
        tone = "ok" if summ.get("reviewed") else "review"
        if summ.get("stale"):
            items.append([("Records changed since this draft: " + _clean(summ["stale"]), {"color": WARN, "size": 11})])
        return items, tag, tone
    reqs = summ.get("requirements") or []
    word = {"satisfied": "found", "missing": "not in the file", "needs_confirmation": "needs confirmation", "waived": "not needed", "not_applicable": "not applicable"}
    items = [[(f"{word.get(q.get('status'), q.get('status'))}: ", {"bold": True, "color": OK if q.get("status") == "satisfied" else WARN}), (_clean(q.get("label")), {})] for q in reqs]
    if not items:
        items = ["No Case File summary compiled yet; the Pre-Authorization checklist is empty."]
    return items, "Checklist, no summary yet", "warn"


def chapter(deck: Deck, m: dict, number: int | None = None, total: int | None = None, outcome: dict | None = None, cards: dict | None = None, record: dict | None = None):
    """The slides of one Case File: title, summary, values, imaging and pathology, gaps, points for review, and the outcome when there is one."""
    c, sl = m["case"], m["slides"]
    p = c.get("patient") if isinstance(c.get("patient"), dict) else {}
    cancer = _clean(c.get("cancer_name")) or _clean(c.get("protocol")).replace("_", " ")
    setting = _clean(c.get("setting")).replace("_", " ")
    owner = org.department_name(c.get("department")) if c.get("department") else ""
    kicker = f"Case {number} of {total}" if number else "Case File"
    # -- the title slide of the case
    s = deck.slide()
    deck.rect(s, 0, 0, W, H, WHITE)
    deck.rect(s, 0, 0, W, Inches(0.14), TEAL)
    deck.text(s, MARGIN, Inches(0.6), W - 2 * MARGIN, Inches(0.35), kicker.upper(), size=11, color=TEAL_DARK, bold=True)
    deck.text(s, MARGIN, Inches(1.0), W - 2 * MARGIN, Inches(1.1), m["patient_line"], size=34, color=INK, bold=True, line_spacing=1.05)
    ids = [x.get("value") for x in (p.get("ids") or []) if isinstance(x, dict) and x.get("kind") in ("ip_no", "op_no") and x.get("value")]
    meta = [f"{cancer}{', ' + setting if setting else ''}{'  (as recorded)' if setting else ''}", f"Responsible Department: {owner}" if owner else "", "  ·  ".join(ids) if ids else "",
            f"Board date {_dmy(c.get('board_date'))}" if c.get("board_date") else ""]
    deck.text(s, MARGIN, Inches(2.2), W - 2 * MARGIN, Inches(1.2), [x for x in meta if x], size=16, color=BODY, line_spacing=1.3)
    deck.rect(s, MARGIN, Inches(3.7), W - 2 * MARGIN, Inches(2.2), SOFT["teal"], None, radius=0.08)
    deck.text(s, MARGIN + Inches(0.3), Inches(3.85), W - 2 * MARGIN - Inches(0.6), Inches(0.35), "QUESTION FOR THE TUMOUR BOARD", size=11, color=TEAL_DARK, bold=True)
    deck.text(s, MARGIN + Inches(0.3), Inches(4.2), W - 2 * MARGIN - Inches(0.6), Inches(1.6), m["question"] or "Not recorded yet.", size=20, color=INK, line_spacing=1.25)
    deck.footer_on(s)
    # -- the summary
    items, tag, tone = _summary_items(sl)
    deck.section_list("Summary", m["patient_line"], items, size=13, tag=tag, tone=tone, note="Every sentence is from the records; the sources are in brackets. " + SCOPE_LINE)
    # -- the values
    vals = ((sl.get("values") or {}).get("content") or {}).get("values") or []
    rows = [[_clean(v.get("label")), [(_clean(v.get("value")), {"bold": True})], _src({"doc_title": v.get("doc_title"), "page": v.get("page")}), _dmy(v.get("date"))] for v in vals]
    deck.table("Key values", "Values with their sources", rows, [0.3, 0.3, 0.28, 0.12], ["Item", "Value", "Source", "Date"], size=11, note="Every value is a verbatim quote from the record named.")
    # -- imaging and pathology
    docs_rows = []
    for kind in ("imaging", "pathology"):
        for d in ((sl.get(kind) or {}).get("content") or {}).get("documents") or []:
            status = [(_clean(d.get("status")).lower() or "", {})]
            if d.get("signed") == "yes":
                status = [("final, signed", {"color": OK, "bold": True})]
            elif _clean(d.get("status")).lower() in ("preliminary", "cancelled", "amended"):
                status = [(_clean(d.get("status")).lower(), {"color": WARN, "bold": True})]
            extra = "images in the viewer" if d.get("viewer_available") else ("images listed" if d.get("images") else "")
            facts = "; ".join(f"{_clean(f.get('label'))}: {_clean(f.get('value'))}" for f in (d.get("facts") or [])[:4])
            docs_rows.append([kind.capitalize(), [(_title_case(d.get("title")), {"bold": True})], status, _dmy(d.get("date")), facts or extra])
    deck.table("Records", "Imaging and pathology records", docs_rows, [0.11, 0.3, 0.12, 0.1, 0.37], ["Kind", "Record", "Status", "Date", "Findings as recorded / images"], size=10,
               note="Images are viewed by people in the hospital's viewer; no model reads them.")
    # -- the gaps
    gc = (sl.get("gaps") or {}).get("content") or {}
    word = {"missing": "not in the file", "needs_confirmation": "needs confirmation", "not_final": "not final", "waived": "not needed", "not_applicable": "not applicable"}
    gaps = [[(word.get(g.get("status"), _clean(g.get("status"))) + ": ", {"bold": True, "color": WARN if g.get("status") in ("missing", "not_final") else MUTED}), (_clean(g.get("label")), {}), ((f"  ({g['department']})" if g.get("department") else ""), {"color": MUTED, "size": 11})] for g in gc.get("gaps") or []]
    waivers = [[("not needed: ", {"bold": True, "color": MUTED}), (_clean(w.get("requirement")).replace("_", " "), {}), ((f"  {w['reason']}" if w.get("reason") else "") + (f"  ({w['by']})" if w.get("by") else ""), {"color": MUTED, "size": 11})] for w in gc.get("waivers") or []]
    if gaps or waivers:
        deck.section_list("Before the board", "Gaps and waivers", gaps + waivers, size=13, tag=(f"{gc.get('satisfied')} of {gc.get('total')} records in the file" if gc.get("total") else None), tone="warn" if gaps else "ok")
    # -- the points for review
    pts = ((sl.get("points") or {}).get("content") or {}).get("points") or []
    if pts:
        items = [_sentence_runs({"text": p.get("text"), "citations": p.get("citations")}) + ([(f"  ({_clean(p.get('label'))})", {"size": 9, "color": MUTED})] if p.get("label") else []) for p in pts]
        deck.section_list("Points for review", "Points for review", items, size=13, numbered=True, tag="AI drafts from the records", tone="review", note="Drafted from the records and guideline points; never advice. The board reads them against the records.")
    # -- the outcome
    if outcome or record:
        rec = record or {}
        oc = outcome or {}
        label = _clean(oc.get("label") or rec.get("outcome_type") or "Outcome")
        lines = []
        txt = _clean(rec.get("decision_text") or oc.get("decision_text"))
        if txt:
            lines.append([("Decision, in the board's words: ", {"bold": True, "color": INK}), (txt, {})])
        for key, lab in (("rationale", "Rationale as discussed"), ("intent_as_stated", "Treatment intent as stated"), ("responsible_doctor", "Responsible doctor"), ("next_step", "Next step"), ("awaited", "Awaited"), ("awaited_from", "From"), ("referred_to", "Referred to")):
            v = _clean(rec.get(key))
            if v:
                lines.append([(lab + ": ", {"bold": True, "color": INK}), (v + (f" by {_dmy(rec.get('next_step_date'))}" if key == "next_step" and rec.get("next_step_date") else ""), {})])
        for cc in rec.get("concerns") or []:
            if isinstance(cc, dict) and _clean(cc.get("text")):
                lines.append([("Concern: ", {"bold": True, "color": WARN}), (_clean(cc.get("text")) + (f" ({_clean(cc.get('by'))})" if cc.get("by") else ""), {})])
        present = rec.get("members_present") or []
        if present:
            lines.append([("Members present: ", {"bold": True, "color": INK}), (", ".join(_clean(x) for x in present), {})])
        for u, card in (cards or {}).items():
            if isinstance(card, dict):
                lines.append([(("Agrees: " if card.get("agree") else "Concern: "), {"bold": True, "color": OK if card.get("agree") else WARN}), (f"{_clean(card.get('name') or u)}" + (f", {_clean(card.get('note'))}" if card.get("note") else ""), {})])
        who = _clean(rec.get("recorded_by") or oc.get("by"))
        when = _dmy_hm(rec.get("recorded_at") or oc.get("at"))
        deck.section_list("Outcome", f"Outcome: {label}", lines or ["No decision text recorded."], size=14, tag=label, tone="ok" if oc.get("outcome") == "decision" else "warn",
                          note=f"Recorded{(' by ' + who) if who else ''}{(' on ' + when) if when else ''}. " + SCOPE_LINE)


def _record_for(st: dict, mid: str | None, record_id: str | None) -> dict | None:
    recs = [x for x in (st.get("board_records") or []) if isinstance(x, dict)]
    if record_id:
        for x in recs:
            if x.get("id") == record_id:
                return x
    if mid:
        for x in reversed(recs):
            if x.get("session") == mid:
                return x
    return recs[-1] if recs and not mid else None


def _is_synthetic(hospital: dict, cases: list) -> bool:
    if "demo" in _clean(hospital.get("name")).lower():
        return True
    return any("synthetic" in _clean(((c.get("patient") or {}).get("name"))).lower() for c in cases if isinstance(c, dict))


def filename(kind: str, ident: str, when: str = "") -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", ident).strip("-")
    return f"Tumour-Board-{kind}-{safe}{('-' + when) if when else ''}.pptx"


# ---------------------------------------------------------------------------------------------------- the two decks
def build_meeting(mid: str, r: dict | None = None) -> bytes:
    """The deck of a meeting: cover, agenda, a chapter per Case File (for discussion, then for noting); when the meeting is closed, each
    chapter ends with its outcome and the deck ends with the minutes."""
    s = meetings.get(mid)
    if not s:
        raise KeyError(mid)
    hospital = org.hospital()
    lists = s.get("agenda_lists") or {}
    rows = [(it.get("case_id"), "discussion") for it in lists.get("discussion") or []] + [(it.get("case_id"), "noting") for it in lists.get("noting") or []]
    mats = []
    for cid, lst in rows:
        try:
            mats.append((_case_material(cid, r), lst))
        except Exception:
            continue
    closed = s.get("status") in ("closed", "decided")
    when = f"{_dmy(s.get('date'))}{', ' + s['time'] if s.get('time') else ''}"
    deck = Deck(hospital, f"Vaidyx Tumour Board  ·  {_clean(hospital.get('name')) or 'Hospital'}  ·  {when}", synthetic=_is_synthetic(hospital, [m["case"] for m, _ in mats]))
    deck.cover("Tumour Board meeting", [when + (f", {s['room']}" if s.get("room") else ""), f"{len(mats)} Case File{'s' if len(mats) != 1 else ''} on the agenda", "Closed: outcomes and minutes inside" if closed else "Agenda deck, prepared before the meeting"],
               [f"Prepared by Vaidyx Tumour Board on {_dmy(date.today().isoformat())}", "For the members of the board. Patient records: handle as confidential.", "Every sentence carries its source in the Case File."])
    # the agenda
    outcomes = s.get("outcomes") or {}
    agenda_items = []
    for i, (m, lst) in enumerate(mats, start=1):
        oc = outcomes.get(m["case"]["case_id"]) if isinstance(outcomes, dict) else None
        runs = [(f"{m['patient_line']}", {"bold": True, "color": INK}), (f"  ·  {_clean(m['case'].get('cancer_name')) or _clean(m['case'].get('protocol')).replace('_', ' ')}", {"color": BODY}), (f"  ·  for {lst}", {"color": MUTED, "size": 11})]
        if oc:
            runs.append((f"  ·  {_clean(oc.get('label') or oc.get('outcome'))}", {"color": OK, "bold": True, "size": 11}))
        if m["question"]:
            runs.append(("\n      " + m["question"], {"color": MUTED, "size": 11}))
        agenda_items.append(runs)
    deck.section_list("Agenda", "Agenda", agenda_items or ["No Case File on the agenda yet."], size=14, numbered=True)
    # the chapters
    cards_all = s.get("cards") or {}
    for i, (m, lst) in enumerate(mats, start=1):
        cid = m["case"]["case_id"]
        oc = outcomes.get(cid) if isinstance(outcomes, dict) else None
        rec = _record_for(m["state"], mid, (oc or {}).get("record")) if oc else None
        chapter(deck, m, i, len(mats), outcome=oc, cards=cards_all.get(cid) if isinstance(cards_all, dict) else None, record=rec)
    # the minutes
    if closed:
        part = board.participants(s)
        rows_ = []
        for i, (m, lst) in enumerate(mats, start=1):
            cid = m["case"]["case_id"]
            oc = outcomes.get(cid) if isinstance(outcomes, dict) else None
            rows_.append([str(i), [(m["patient_line"], {"bold": True})], _clean((oc or {}).get("label") or "not discussed"), _clean((oc or {}).get("decision_text"))[:220]])
        deck.table("Minutes", "Outcomes of the meeting", rows_, [0.05, 0.3, 0.17, 0.48], ["#", "Case File", "Outcome", "Decision as recorded"], size=10,
                   note=f"Present: {', '.join(part.get('present') or []) or 'not marked'}.  Absent: {', '.join(part.get('absent') or []) or 'none marked'}.")
        people = s.get("people") or {}
        if isinstance(people, dict) and people:
            lines = [[(_clean(v.get("name")), {"bold": True}), (f"  ·  {org.department_name(v.get('department')) if v.get('department') else ''}", {}), (f"  ·  {'in the room' if v.get('mode') == 'room' else 'remote'}", {"color": MUTED, "size": 11})] for v in people.values() if isinstance(v, dict) and v.get("status") in ("present", "remote")]
            deck.section_list("Minutes", "Members who took part", lines or ["No member joined through Vaidyx."], size=13)
    closing(deck)
    return deck.save()


def build_case(cid: str, r: dict | None = None) -> bytes:
    """The deck of one Case File: cover, its chapter, the latest outcome if any."""
    m = _case_material(cid, r)
    hospital = org.hospital()
    c = m["case"]
    deck = Deck(hospital, f"Vaidyx Tumour Board  ·  {_clean(hospital.get('name')) or 'Hospital'}  ·  Case File {cid}", synthetic=_is_synthetic(hospital, [c]))
    cancer = _clean(c.get("cancer_name")) or _clean(c.get("protocol")).replace("_", " ")
    p = c.get("patient") if isinstance(c.get("patient"), dict) else {}
    name = _clean(p.get("name")) if not meetings.outside_view(r, c) else m["patient_line"]
    ident = ", ".join(x for x in (_clean(p.get("agesex")), f"UHID {_clean(p.get('mrn'))}" if p.get("mrn") and not meetings.outside_view(r, c) else "") if x)
    deck.cover(name or m["patient_line"], [x for x in (ident, cancer + (f", {_clean(c.get('setting')).replace('_', ' ')} (as recorded)" if c.get("setting") else ""), f"Case File {cid}", f"Board date {_dmy(c.get('board_date'))}" if c.get("board_date") else "Board date not set") if x],
               [f"Prepared by Vaidyx Tumour Board on {_dmy(date.today().isoformat())}", "For the owner's team and the board. Patient records: handle as confidential.", "Every sentence carries its source in the Case File."])
    rec = _record_for(m["state"], None, None)
    chapter(deck, m, record=rec, outcome={"label": _clean(rec.get("outcome_type") or "Decision").replace("_", " ").capitalize(), "outcome": rec.get("outcome_type"), "by": rec.get("recorded_by"), "at": rec.get("recorded_at")} if rec else None)
    closing(deck)
    return deck.save()


def closing(deck: Deck):
    s = deck.slide()
    deck.rect(s, 0, 0, W, H, NAVY)
    deck.image(s, ASSETS / "vaidyx-icon-white.png", W / 2 - Inches(0.6), Inches(2.4), h=Inches(1.0))
    deck.image(s, ASSETS / "vaidyx-wordmark-white.png", W / 2 - Inches(1.3), Inches(3.55), h=Inches(0.6))
    deck.text(s, MARGIN, Inches(4.4), W - 2 * MARGIN, Inches(0.5), "Tumour Board", size=14, color=RGBColor(0x9F, 0xE3, 0xDF), bold=True, align=PP_ALIGN.CENTER)
    deck.text(s, Inches(2), Inches(5.2), W - Inches(4), Inches(0.9), SCOPE_LINE, size=12, color=RGBColor(0xC9, 0xD4, 0xDE), align=PP_ALIGN.CENTER)
    if deck.logo:
        deck.image(s, deck.logo, W - MARGIN - Inches(1.4), H - Inches(1.5), h=Inches(0.9))
