"""NCG Virtual Tumour Board / Regional Cancer Centre export (V1 item 4.6).

Fills the National Cancer Grid Virtual Tumour Board case template (6 slides, `ncg-vtb-case-template.pptx` in the guideline
library) from the verified Case File summary, for referral to a Regional Cancer Centre or the NCG VTB. Every sentence is copied
from the summary artefact (each one already carries its verified quote) and cited "[<document title>, <event date>]"; stage
appears only as recorded in the report that records it. No model call: nothing but the artefact and the records is written.

The template is loaded fresh on every build; its titles and pictures (the NCG logo) stay. Text goes into the template's own
content placeholders; the additions are a box for the treatment history (slide 2), a small footer on every slide and, on slide 1,
a Case File identity box above the logo: slide 1's content placeholder (idx 1) holds the large NCG logo picture, not text.
"""
import copy
import io
import math
import os
import re
from datetime import date, datetime
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.text.text import _Paragraph
from pptx.util import Pt

from . import config, dates, org, rules, store


def template_path() -> Path:
    """The NCG VTB template, read on every call so tests can point config or TB_VTB_TEMPLATE elsewhere."""
    return Path(os.getenv("TB_VTB_TEMPLATE") or str(config.GUIDELINE_DIR / "ncg_india" / "ncg-vtb-case-template.pptx"))


TEMPLATE = template_path()  # as configured at import; build() always calls template_path()


class ExportNotReady(Exception):
    """The Case File cannot be exported yet; the message is plain words for the route's 409."""


NOT_DOCUMENTED = "Not documented in the verified records of this Case File"
CONTINUED = "(continued in the Vaidyx Case File summary)"
POINTS_HEADING = "Points for review (from the verified records, not treatment recommendations):"
INCOMPLETE = "INCOMPLETE: Pre-Authorization not met"
MAX_LINES = 18          # per text box, the continuation line included
SMALL_AFTER = 10        # more lines than this: 12 pt instead of 14 pt
PT, PT_SMALL, PT_FOOTER = 14, 12, 9

# slide geometry (EMU; the template is 4:3, 9144000 x 6858000)
IDENTITY = {"left": 457200, "top": 152400, "width": 8229600, "height": 914400}  # slide 1, above the NCG logo (which starts at 1066800)
FOOTER = {"left": 457200, "top": 6400800, "width": 8229600, "height": 411480}
TREATMENT_TITLE_TOP = 3429000      # the template's "Treatment history" text box on slide 2
TREATMENT_BOX_TOP = 4572000        # the new box starts where that title box ends, so the two never overlap
BULLET_INDENT = 342900             # the master's level-1 bullet indent
INSETS = 182880                    # left + right (or top + bottom) default text insets

# slide n -> (summary section id, the template's own title). Slide 1 has no title in the template.
SLIDES = [(1, None, "Tumour Board Case File"),
          (2, "presentation", "Presenting complaints and examination (brief, and only relevant)"),
          (3, "investigations", "Relevant investigations (Biopsy / Histopathology / tumor markers)"),
          (4, "imaging", "Imaging (CT/MRI/PET CT)"),
          (5, "fitness", "Fitness for Treatment (only if relevant)"),
          (6, "questions", "Questions for the tumor board")]


def filename(case_id: str) -> str:
    return f"{case_id}_ncg_vtb_case.pptx"


# ---- text helpers ----------------------------------------------------------------------------------------------------

def _clean(s) -> str:
    """One line of plain text: no em or en dashes (house style), no line breaks."""
    s = re.sub(r"\s*\u2014\s*", ", ", str(s or ""))
    s = s.replace("\u2013", "-")
    return re.sub(r"\s+", " ", s).strip()


def _ddmmyyyy(iso) -> str:
    if not iso:
        return ""
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return _clean(iso)


def _when(iso) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return _clean(iso) or "date not recorded"


def _doc_title(doc) -> str:
    return (doc.get("classification") or {}).get("title") or doc.get("filename") or doc.get("doc_id") or ""


def _cite(c, docs) -> str:
    """"[<title>, dd/mm/yyyy]" from the Case File's records (confirmed titles and dates overlaid); the citation's own fields otherwise."""
    d = docs.get(c.get("doc_id"))
    title = _doc_title(d) if d else (c.get("doc_title") or c.get("doc_id") or "source document")
    when = _ddmmyyyy(dates.doc_dates(d)["event"]) if d else _ddmmyyyy(c.get("date"))
    return f"[{_clean(title)}, {when or 'date not stated'}]"


def _sentence(s, docs) -> str:
    cites = []
    for c in s.get("citations") or []:
        x = _cite(c, docs)
        if x not in cites:
            cites.append(x)
    return " ".join([_clean(s.get("text"))] + cites).strip()


def _review_words(review) -> str:
    st = (review or {}).get("status")
    if st == "reviewed":
        return f"reviewed by {_clean((review or {}).get('by')) or 'an expert'}"
    if st == "flagged":
        return "flagged for correction"
    return "AI draft, awaiting expert review"


def _model_words(summary) -> str:
    """The reasoner's configured label with "(non-medical)" (project model-labelling rule); a generic name when no label was recorded."""
    label = _clean(summary.get("model"))
    if not label or label.lower() == "reasoner":
        return "the reasoner model (non-medical)"
    return label if "non-medical" in label.lower() else f"{label} (non-medical)"


def footer_text(summary) -> str:
    """At most two lines at 9 pt: the long product name gives way to "Vaidyx" when a long model label or reviewer name needs the room."""
    rest = (f"compiled by {_model_words(summary)} from verified records, every sentence cites its source; stage only as recorded; "
            f"no treatment recommendation. Human oversight: {_review_words(summary.get('review'))}. Generated {_when(summary.get('generated'))}.")
    text = "Vaidyx Tumour Board assistant: " + rest
    return text if footer_fits(text) else "Vaidyx: " + rest


def footer_lines(text) -> int:
    """Estimated wrapped lines of the footer at 9 pt in its box (no bullet indent)."""
    usable_pt = (FOOTER["width"] - INSETS) / 12700
    return max(1, math.ceil(len(text) / max(20, int(usable_pt / (PT_FOOTER * 0.5)))))


def footer_fits(text) -> bool:
    return footer_lines(text) * PT_FOOTER * 1.2 <= (FOOTER["height"] - 91440) / 12700  # top + bottom insets 0.05 in each


# ---- fitting: readable font sizes, never a silent overflow ----------------------------------------------------------

def _est_lines(text, width_emu, pt) -> int:
    usable_pt = (width_emu - BULLET_INDENT - INSETS) / 12700
    per_line = max(20, int(usable_pt / (pt * 0.5)))  # about half an em per character in the body font
    return max(1, math.ceil(len(text) / per_line))


def _fits(lines, width_emu, height_emu, pt) -> bool:
    need = sum(_est_lines(t, width_emu, pt) * pt * 1.2 + pt * 0.2 for t in lines)  # line height + the master's 20% space before
    return need <= (height_emu - INSETS) / 12700


def fit(body, tail, width_emu, height_emu):
    """(lines, pt, cut): `body` then `tail` (lines that must stay, e.g. the stage line), at 14 pt when there are at most 10 lines
    and they fit, else 12 pt; cut to at most MAX_LINES lines (or what fits) with CONTINUED as the last line."""
    lines = list(body) + list(tail)
    pt = PT if len(lines) <= SMALL_AFTER and _fits(lines, width_emu, height_emu, PT) else PT_SMALL
    if len(lines) <= MAX_LINES and _fits(lines, width_emu, height_emu, pt):
        return lines, pt, False
    keep = len(body)
    while keep > 0 and (keep + len(tail) + 1 > MAX_LINES or not _fits(list(body[:keep]) + list(tail) + [CONTINUED], width_emu, height_emu, PT_SMALL)):
        keep -= 1
    kept = list(body[:keep])
    if kept and kept[-1] == POINTS_HEADING:  # a heading with nothing under it says nothing
        kept.pop()
    return kept + list(tail) + [CONTINUED], PT_SMALL, True


# ---- what goes on each slide ----------------------------------------------------------------------------------------

def _summary(case_id):
    case = store.get_case(case_id)
    if not case:
        raise ExportNotReady(f"No Case File {case_id}")
    st = store.get_state(case_id)
    summ = (st.get("artefacts") or {}).get("summary")
    if not summ or not summ.get("sections"):
        raise ExportNotReady("Compile the Case File summary first")
    return case, st, summ


def _stale(case_id, st, summ) -> str:
    then = summ.get("signature")
    if not then or not then.get("hash"):
        return "The Case File summary was compiled before changes were tracked"
    now = rules.case_signature(case_id, st)
    if then.get("hash") == now.get("hash"):
        return ""
    return rules.stale_reason(then, now) or "The Case File changed since this was generated"


def _diagnosis(st, docs_list) -> str:
    """The histologic type as recorded: the current verified (or clinician-confirmed) value from a final report, with its source."""
    cur = (rules.resolve_facts(docs_list, st.get("overrides")).get("histologic_type") or {}).get("current")
    if not cur or cur.get("verification") not in rules.VERIFIED or cur.get("state") != "present" or not cur.get("doc_final") or not _clean(cur.get("value")):
        return "not verified in a final report yet (see the investigations slide)"
    return f"{_clean(cur['value'])} [{_clean(cur.get('doc_title'))}, {_ddmmyyyy(cur.get('date')) or 'date not stated'}]"


def _printed(summ, s) -> bool:
    """A sentence or point goes into this print view when it has text; one kept on an approximate source match only once an
    expert has reviewed the summary (V1 item 6.5)."""
    return bool(_clean(s.get("text"))) and (not s.get("approximate") or (summ.get("review") or {}).get("status") == "reviewed")


def _section_lines(summ, sid, docs):
    sec = next((s for s in summ.get("sections") or [] if s.get("id") == sid), None) or {}
    return [_sentence(s, docs) for s in sec.get("sentences") or [] if _printed(summ, s)]


def _stage_line(summ) -> str:
    sr = summ.get("stage_as_recorded")
    if not sr or not _clean(sr.get("value")):
        return ""
    line = f"Stage as recorded in {_clean(sr.get('doc_title')) or 'the source report'} ({_ddmmyyyy(sr.get('date')) or 'date not stated'}): {_clean(sr['value'])}"
    return line + (f" (confirmed by {_clean(sr['confirmed_by'])})" if sr.get("confirmed_by") else "")


def _blocked(summ) -> str:
    """Why build() refuses a summary that an expert flagged for correction; "" otherwise."""
    review = summ.get("review") or {}
    if review.get("status") != "flagged":
        return ""
    comment = _clean(review.get("comment"))
    return ("The Case File summary is flagged for correction" + (f": {comment}" if comment else "")
            + "; correct it and mark it reviewed, or regenerate it, before exporting")


def _width_height(top, height, width):
    return width, min(top + height, FOOTER["top"]) - top


def content(case_id: str) -> dict:
    """What build() puts on each slide, as text: {"slides": [{"n", "title", "items", "extra"}], "stale", "review", "footer", ...}.
    Raises ExportNotReady when there is no summary; a stale summary is reported in "stale" and one flagged for correction in
    "blocked" (build() refuses both)."""
    case, st, summ = _summary(case_id)
    docs_list = rules.case_docs(case_id, st)
    docs = {d["doc_id"]: d for d in docs_list}
    p = case.get("patient") or {}
    slides = []

    # slide 1: the Case File and patient in a box above the logo, the template's four lines filled in place
    who_line = [x for x in (_clean(p.get("name")), f"Age / sex: {_clean(p['agesex'])}" if _clean(p.get("agesex")) else "",
                            f"UHID / MRN {_clean(p['mrn'])}" if _clean(p.get("mrn")) else "") if x]
    ident = [f"Tumour Board Case File {case_id}"] + (["; ".join(who_line)] if who_line else [])
    ident_pt = 16 if _fits(ident, IDENTITY["width"] + BULLET_INDENT, IDENTITY["height"], 18) else 14
    who = (case.get("listing") or {}).get("listed_by") or case.get("created_by") or ""
    presenter = f"Tumour Board coordinator ({_clean(who)})" if _clean(who) else "Tumour Board coordinator"
    centre = _clean((org.load().get("hospital") or {}).get("name")) or "(hospital name not set)"
    diagnosis = _diagnosis(st, docs_list)
    when = _ddmmyyyy(case.get("board_date")) or "to be fixed"
    incomplete = summ.get("status") == "incomplete_gate"
    box = [f"Name of the presenter: {presenter}", f"Name of the centre: {centre}", f"Diagnosis: {diagnosis}"]
    box += [INCOMPLETE] if incomplete else []
    box += [f"Date of presentation: {when}"]
    slides.append({"n": 1, "title": SLIDES[0][2], "items": ident,
                   "extra": {"pt": ident_pt, "presenter": presenter, "centre": centre, "diagnosis": diagnosis, "date": when, "incomplete": incomplete, "lines": box}})

    for n, sid, title in SLIDES[1:]:
        body = _section_lines(summ, sid, docs) or [NOT_DOCUMENTED]
        tail, extra = [], {}
        if n == 2:
            w, h = _width_height(2027237, TREATMENT_TITLE_TOP - 2027237, 8229600)
        elif n == 3:
            w, h = _width_height(1279440, 5410200, 8458200)
        else:
            w, h = _width_height(2027237, 4525963, 8229600)
        if n == 4:
            stage = _stage_line(summ)
            tail = [stage] if stage else []
            extra["stage"] = stage
        if n == 6:
            pts = [_sentence(x, docs) for x in summ.get("points_for_review") or [] if _printed(summ, x)]
            body = body + ([POINTS_HEADING] + pts if pts else [])
            extra["points_for_review"] = pts
        items, pt, cut = fit(body, tail, w, h)
        extra.update(pt=pt, cut=cut)
        if n == 2:
            th = _section_lines(summ, "treatment_history", docs) or [NOT_DOCUMENTED]
            th_items, th_pt, th_cut = fit(th, [], 8229600, FOOTER["top"] - TREATMENT_BOX_TOP)
            extra.update(treatment_history=th_items, treatment_pt=th_pt, treatment_cut=th_cut)
        slides.append({"n": n, "title": title, "items": items, "extra": extra})

    return {"case_id": case_id, "slides": slides, "stale": _stale(case_id, st, summ), "blocked": _blocked(summ),
            "review": summ.get("review") or {"status": "ai_draft"},
            "status": summ.get("status"), "generated": summ.get("generated"), "footer": footer_text(summ), "filename": filename(case_id)}


# ---- rendering ------------------------------------------------------------------------------------------------------

def _reset(tf):
    """Empty a text frame completely (the template's placeholders carry blank lines with bullets switched off)."""
    tb = tf._txBody
    for p in list(tb.p_lst):
        tb.remove(p)


def _bullet(p, on=True):
    pPr = p._p.get_or_add_pPr()
    for tag in ("a:buNone", "a:buFont", "a:buChar", "a:buAutoNum"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    if not on:
        pPr.set("marL", "0"); pPr.set("indent", "0")
        pPr.append(pPr.makeelement(qn("a:buNone"), {}))
        return
    pPr.set("marL", str(BULLET_INDENT)); pPr.set("indent", str(-BULLET_INDENT))
    pPr.append(pPr.makeelement(qn("a:buFont"), {"typeface": "Arial"}))
    pPr.append(pPr.makeelement(qn("a:buChar"), {"char": "•"}))


def _write(tf, lines, pt, bullets=True, bold=()):
    _reset(tf)
    for i, line in enumerate(lines):
        p = tf._txBody.add_p()
        para = _Paragraph(p, tf)
        _bullet(para, bullets and line not in (CONTINUED,))
        r = para.add_run()
        r.text = line
        r.font.size = Pt(pt)
        if line in bold or i in bold:
            r.font.bold = True
        if line == CONTINUED:
            r.font.italic = True


def _clone_after(para, tf):
    """A copy of `para` (its formatting kept) inserted right after it, holding one run."""
    new = copy.deepcopy(para._p)
    para._p.addnext(new)
    out = _Paragraph(new, tf)
    for r in out.runs[1:]:
        new.remove(r._r)
    if not out.runs:
        out.add_run()
    return out


def _fill_intro_box(shape, lines, incomplete):
    """The slide 1 text box: rewrite its lines in place (first run's formatting kept), the incomplete line after the diagnosis.
    A box with fewer paragraphs than lines gets copies of its last paragraph, so no line is ever dropped."""
    tf = shape.text_frame
    values = [l for l in lines if l != INCOMPLETE]
    paras = list(tf.paragraphs) or [tf.add_paragraph()]
    while len(paras) < len(values):
        paras.append(_clone_after(paras[-1], tf))
    pt = 16 if sum(_est_lines(l, shape.width, 16) for l in lines) <= 6 else 14
    for para, text in zip(paras, values):
        runs = para.runs
        for r in runs[1:]:
            para._p.remove(r._r)
        r = runs[0] if runs else para.add_run()
        r.text = text
        r.font.size = Pt(pt)
    if incomplete:
        diag = [i for i, v in enumerate(values) if v.startswith("Diagnosis")]
        at = diag[-1] if diag else min(2, len(values) - 1)
        r = _clone_after(paras[at], tf).runs[0]
        r.text = INCOMPLETE
        r.font.size = Pt(pt)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0xB0, 0x00, 0x20)


def _footer(slide, text):
    tb = slide.shapes.add_textbox(FOOTER["left"], FOOTER["top"], FOOTER["width"], FOOTER["height"])
    tb.name = "Vaidyx footer"
    tf = tb.text_frame
    tf.word_wrap = True
    r = tf.paragraphs[0].add_run()
    r.text = text
    r.font.size = Pt(PT_FOOTER)
    r.font.color.rgb = RGBColor(0x6B, 0x6B, 0x6B)


def _fit_above_footer(shape):
    if shape.top + shape.height > FOOTER["top"]:
        shape.height = FOOTER["top"] - shape.top


def build(case_id: str) -> bytes:
    """The filled NCG VTB case template (.pptx bytes). Raises ExportNotReady (no summary, stale summary, summary flagged for
    correction, template missing), in that order."""
    data = content(case_id)
    if data["stale"]:
        raise ExportNotReady(data["stale"] + "; regenerate the summary before exporting")
    if data["blocked"]:
        raise ExportNotReady(data["blocked"])
    path = template_path()
    if not path.is_file():
        raise ExportNotReady(f"The NCG Virtual Tumour Board template is missing: {path}")
    prs = Presentation(str(path))
    slides = list(prs.slides)
    if len(slides) < 6:
        raise ExportNotReady(f"The NCG Virtual Tumour Board template at {path} does not have six slides")
    for spec, slide in zip(data["slides"], slides):
        ex = spec["extra"]
        if spec["n"] == 1:  # its placeholder idx 1 is the NCG logo picture: left as it is
            box = next((s for s in slide.shapes if not s.is_placeholder and s.has_text_frame and "presenter" in s.text_frame.text.lower()), None)
            if box is not None:
                _fill_intro_box(box, ex["lines"], ex["incomplete"])
            tb = slide.shapes.add_textbox(IDENTITY["left"], IDENTITY["top"], IDENTITY["width"], IDENTITY["height"])
            tb.name = "Vaidyx case identity"
            tb.text_frame.word_wrap = True
            _write(tb.text_frame, spec["items"], ex["pt"], bullets=False, bold=(0,))
            tb.text_frame.paragraphs[0].runs[0].font.size = Pt(ex["pt"] + 4)
        else:
            ph = slide.placeholders[1]
            if spec["n"] == 2:
                ph.height = TREATMENT_TITLE_TOP - ph.top  # end above the template's "Treatment history" title
                tb = slide.shapes.add_textbox(ph.left, TREATMENT_BOX_TOP, ph.width, FOOTER["top"] - TREATMENT_BOX_TOP)
                tb.name = "Vaidyx treatment history"
                tb.text_frame.word_wrap = True
                _write(tb.text_frame, ex["treatment_history"], ex["treatment_pt"])
            _fit_above_footer(ph)
            _write(ph.text_frame, spec["items"], ex["pt"], bold=(POINTS_HEADING,))
        _footer(slide, data["footer"])
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
