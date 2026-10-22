"""Report documents of the mock hospital (plan item V2-1.2): every report version as a PDF in an Indian layout, digitally
signed by the fictitious "Vaidyx Demo CA". SYNTHETIC data only; never imports tumour_board.

    from his_mock import documents
    html = documents.html_for(store, report, version)      # one report version as HTML (store data only)
    documents.render_all(store, files)                     # every version + the outside reports, one pdf-venv subprocess
    documents.render_versions(store, files, [(r, v)])      # only these versions (the reporting desk, 1.5)
    problems = documents.check(store, files)               # [] when every PDF holds what its record holds

Layouts (one generic dict -> HTML renderer, the idea of tumour_board/demo_data/make_corpus.py, copied not imported): NABL-style
lab reports (Investigation / Result / Units / Biological reference interval), radiology (Technique, Findings, Impression),
HPE, IHC, molecular and cytology (Specimen, Block No.), endoscopy (Procedure, Findings, Impression), clinical notes (OP / IP
No., department, unit, consultant), referral notes and discharge summaries (ward / bed with transfers, referrals).
Every page carries the rotated watermark "SYNTHETIC - DEMO ONLY" and a SYNTHETIC footer. The footer of each report starts with
a `Report status:` line, then the signature block of signatures[sid]["block"] verbatim (signed), "Reported by: ... (preliminary,
verification awaited)" (preliminary) or "Signature pending" (final, never signed).

PDFs are written with WeasyPrint in the pdf venv (render_cli.py), so this module needs no PDF library at render time;
text_of() and check() use pypdf (app venv). Rendering is deterministic: the HTML holds store times only, never "now".

`python -m his_mock.documents --check [--data DIR]` checks the built documents; `--render` re-renders them into the store.
"""
import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

from .ids import display_date, display_time, parse_time
from .model import CA_NAME, IMAGING_MODALITY, MARKER, Store

# The cursive face of the sign-off (Great Vibes, SIL Open Font Licence 1.1, his_mock/fonts/OFL-GreatVibes.txt).
SIGNATURE_FONT = Path(__file__).resolve().parent / "fonts" / "GreatVibes-Regular.ttf"
from .paths import layout
from .scenarios import AADHAAR_LIKE, MASKED_AADHAAR

HOSPITAL = "Vaidyx Demo Hospital (SYNTHETIC)"
HOSPITAL_SUB = "A fictitious hospital for software demonstration; every record is SYNTHETIC"
WATERMARK = "SYNTHETIC - DEMO ONLY"
PAGE_FOOTER = "SYNTHETIC record of the Vaidyx Demo Hospital; not a real patient"
OUTSIDE_FOOTER = "SYNTHETIC outside report for the Vaidyx demo; not a real patient"
NABL_LINE = "NABL-style report layout (SYNTHETIC); Vaidyx Demo Hospital Laboratory"
PDF_PYTHON = os.environ.get("TB_PDF_PYTHON") or "/data/vaidyx/venv/pdf/bin/python"
RENDER_CLI = Path(__file__).with_name("render_cli.py")
OUTSIDE_DIR = "outside"

STATUS_WORDS = {"preliminary": "PRELIMINARY", "final": "FINAL", "amended": "AMENDED", "cancelled": "CANCELLED"}
# words a signed report never prints (Vaidyx-TB's text rules read them as "not signed" or "not final")
NOT_ON_SIGNED = ("unsigned", "signature pending", "awaiting verification", "draft")
FORBIDDEN = ("Sahyadri", "SYN-", "\u2014")   # the V1 corpus hospital and ids must not leak; no em dashes

# ------------------------------------------------------------------------ layouts and wording
RADIOLOGY = set(IMAGING_MODALITY)
LAYOUT = {"lab": "lab", "histopathology": "hpe", "ihc": "ihc", "molecular": "molecular", "cytology": "cytology",
          "endoscopy": "endoscopy", "clinical_note": "clinical", "referral": "referral",
          "discharge_summary": "discharge", **{t: "radiology" for t in RADIOLOGY}}

# printed titles: chosen so the title line names one document type only (tumour_board/protocols/doc_type_keywords.json
# reads the first lines of page 1; "EBUS procedure note" would tie endoscopy with operative note)
TITLES = {
    "opd_note": "OPD CONSULTATION NOTE",
    "referral_note": "INTER-DEPARTMENT REFERRAL NOTE",
    "discharge_summary": "DISCHARGE SUMMARY",
    "mammogram": "BILATERAL MAMMOGRAPHY REPORT",
    "usg_breast_axilla": "USG BOTH BREASTS AND AXILLAE",
    "usg_abdomen_pelvis": "USG ABDOMEN AND PELVIS",
    "cect_chest_abdomen_pelvis": "CECT CHEST, ABDOMEN AND PELVIS",
    "cect_tap": "CECT THORAX, ABDOMEN AND PELVIS",
    "cect_abdomen_pelvis": "CECT ABDOMEN AND PELVIS",
    "cect_face_neck": "CECT FACE AND NECK",
    "mri_oral_cavity_neck": "MRI ORAL CAVITY AND NECK",
    "mri_pelvis": "MRI PELVIS",
    "mri_pelvis_rectum": "MRI PELVIS (RECTAL PROTOCOL)",
    "mri_brain": "MRI BRAIN WITH CONTRAST",
    "chest_xray": "X-RAY CHEST PA VIEW",
    "pet_ct": "WHOLE BODY FDG PET-CT",
    "bone_scan": "WHOLE BODY BONE SCAN (Tc-99m MDP)",
    "hpe_biopsy": "HISTOPATHOLOGY REPORT",
    "hpe_slide_review": "HISTOPATHOLOGY REPORT (REVIEW OF OUTSIDE SLIDES AND BLOCKS)",
    "ihc_breast": "IMMUNOHISTOCHEMISTRY REPORT (ER, PR, HER2, Ki-67)",
    "ihc_panel": "IMMUNOHISTOCHEMISTRY REPORT",
    "pdl1_ihc": "IMMUNOHISTOCHEMISTRY REPORT: PD-L1 (22C3)",
    "molecular_lung": "MOLECULAR PATHOLOGY REPORT: EGFR, ALK, ROS1, MET",
    "cytology_ebus": "CYTOLOGY REPORT: MEDIASTINAL LYMPH NODE ASPIRATES",
    "cbc": "HAEMATOLOGY REPORT: COMPLETE BLOOD COUNT",
    "lft": "BIOCHEMISTRY REPORT: LIVER FUNCTION TESTS",
    "rft": "BIOCHEMISTRY REPORT: RENAL FUNCTION TESTS",
    "cea": "TUMOUR MARKER REPORT: SERUM CEA",
    "viral_markers": "SEROLOGY REPORT: VIRAL MARKERS",
    "dental_evaluation": "DENTAL EVALUATION (PRE-RADIOTHERAPY)",
    "pre_anaesthetic_check": "PRE-ANAESTHETIC CHECK-UP: CONSULTATION NOTE",
    "medication_review": "MEDICATION REVIEW: CONSULTATION NOTE",
    "bronchoscopy": "FIBREOPTIC BRONCHOSCOPY REPORT",
    "ebus": "EBUS BRONCHOSCOPY REPORT",
    "pft": "PULMONARY FUNCTION TEST (SPIROMETRY)",
    "colonoscopy": "COLONOSCOPY REPORT",
    "cystoscopy_proctoscopy": "CYSTOSCOPY AND PROCTOSCOPY REPORT",
    "eua": "EXAMINATION UNDER ANAESTHESIA (EUA): OPERATIVE NOTE",
}

LABELS = {
    "presenting_complaint": "Presenting complaint", "ecog": "ECOG performance status", "clinical_question": "Clinical question",
    "menopausal_status": "Menopausal status", "comorbidities": "Comorbidities", "smoking_history": "Smoking history",
    "tobacco_use": "Tobacco use", "figo_stage": "FIGO stage", "dental_evaluation": "Dental evaluation",
    "lesion_size": "Lesion size", "birads": "BI-RADS category", "nodal_findings": "Lymph nodes",
    "distant_findings": "Distant sites", "hydronephrosis": "Kidneys and ureters", "parametrial_involvement": "Parametria",
    "rectal_findings": "Rectum", "depth_of_invasion": "Depth of invasion", "emvi": "Extramural venous invasion (EMVI)",
    "mrf_status": "Mesorectal fascia (MRF)", "recorded_stage": "Staging", "suv_max": "SUV (maximum)",
    "histologic_type": "Histological type", "grade": "Grade", "lvi": "Lymphovascular invasion", "pni": "Perineural invasion",
    "er": "Oestrogen receptor (ER)", "pr": "Progesterone receptor (PR)", "her2": "HER2/neu (IHC score)",
    "ki67": "Ki-67 labelling index", "pdl1": "PD-L1 (22C3), tumour proportion score", "egfr": "EGFR mutation analysis",
    "alk": "ALK rearrangement", "ros1": "ROS1 rearrangement", "met": "MET exon 14 skipping", "kras": "KRAS mutation analysis",
    "bladder_mucosa": "Bladder", "rectal_mucosa": "Rectum", "distance_from_anal_verge": "Distance from the anal verge",
    "endobronchial_findings": "Tracheobronchial tree",
    "haemoglobin": "Haemoglobin (Hb)", "wbc": "Total leucocyte count (TLC)", "platelets": "Platelet count",
    "creatinine": "Serum creatinine", "bilirubin": "Serum bilirubin (total)", "urea": "Blood urea", "sgot": "SGOT (AST)",
    "sgpt": "SGPT (ALT)", "cea": "Carcinoembryonic antigen (CEA)", "hiv_status": "HIV 1 and 2 antibodies",
    "hbsag": "HBsAg", "anti_hcv": "Anti-HCV antibodies",
    "technique": "Technique", "comparison": "Comparison", "findings": "Findings", "impression": "Impression",
    "specimen": "Specimen", "gross": "Gross", "microscopy": "Microscopy", "diagnosis": "Diagnosis",
    "examination": "Examination", "plan": "Plan", "course": "Course", "advice": "Advice", "remarks": "Remarks",
}
# values the HIMS entry forms type as free text: printed as paragraphs inside their own section, without a label
PLAIN_KEYS = {"technique", "comparison", "findings", "impression", "specimen", "gross", "microscopy", "diagnosis",
              "examination", "plan", "course", "advice"}

# Biological reference intervals (plausible Indian adult ranges, SYNTHETIC; printed without the unit, which has its column)
REFERENCE = {
    "haemoglobin": {"M": "13.0-17.0", "F": "12.0-15.0"}, "wbc": "4,000-11,000", "platelets": "1.5-4.5",
    "creatinine": "0.6-1.2", "bilirubin": "0.3-1.2", "urea": "15-40", "sgot": "5-40", "sgpt": "5-40", "cea": "0-5",
    "hiv_status": "Non-reactive", "hbsag": "Non-reactive", "anti_hcv": "Non-reactive",
}
MOLECULAR_METHOD = {"egfr": "Real-time PCR", "alk": "IHC (D5F3 clone)", "ros1": "FISH", "met": "RT-PCR",
                    "kras": "Real-time PCR", "her2": "FISH"}
TECHNIQUE = {
    "ct": "Contrast-enhanced multidetector CT; axial sections with multiplanar reformats reviewed.",
    "mri": "Multiplanar multisequence MRI (T1, T2, diffusion-weighted and post-contrast sequences).",
    "xray": "Frontal (PA) radiograph of the chest.",
    "ultrasound": "High-resolution real-time ultrasonography.",
    "mammogram": "Digital mammography, craniocaudal and mediolateral oblique views of both breasts.",
    "pet_ct": "18F-FDG PET with low-dose CT for attenuation correction, skull base to mid-thigh.",
    "bone_scan": "Whole-body planar images after intravenous Tc-99m MDP.",
}
IMPRESSION_KEY = re.compile(r"impression|conclusion|stage|rads|diagnosis")
HPE_DIAGNOSIS_KEYS = ("histologic_type", "grade", "nodal_findings", "diagnosis")
LAB_GROUPS = {"Pathology": "Whole blood (EDTA)"}       # other laboratories report on serum
_NUMERIC = re.compile(r"^[<>]?\s*[\d][\d.,]*\s+(\S.*)$")

CSS = """
@page { size: A4; margin: 14mm 14mm 18mm;
  @bottom-center { content: "%(footer)s  |  Page " counter(page) " of " counter(pages); font-family: 'DejaVu Sans', sans-serif;
                   font-size: 7.5pt; color: #555; } }
body { font-family: 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif; font-size: 10pt; color: #111;
       font-variant-ligatures: none; font-kerning: none; }
.hdr { border-bottom: 2px solid #1f3b63; padding-bottom: 6px; margin-bottom: 8px; }
.hdr .h { font-size: 15pt; font-weight: bold; color: #1f3b63; }
.hdr .d { font-size: 9pt; color: #444; }
.wm { position: fixed; top: 45%%; left: 8%%; font-size: 54pt; color: rgba(150,150,150,0.16); transform: rotate(-28deg);
      font-weight: bold; }
h1 { font-size: 12.5pt; margin: 6px 0 6px; }
h2 { font-size: 10.5pt; margin: 10px 0 3px; color: #1f3b63; }
table.grid { border-collapse: collapse; width: 100%%; margin: 4px 0 8px; border: 1px solid #999; }
table.grid td { font-size: 9pt; padding: 2px 5px; vertical-align: top; }
table.grid td.l { color: #333; width: 17%%; }
table.grid td.v { font-weight: bold; width: 33%%; }
table.res { border-collapse: collapse; width: 100%%; margin-top: 4px; }
table.res th, table.res td { border-bottom: 1px solid #ccc; text-align: left; padding: 3px 6px; font-size: 9.5pt; }
table.res th { background: #f3f3f3; }
.foot { margin-top: 20px; border-top: 1px solid #999; padding-top: 6px; font-size: 9.5pt; }
.foot .status { font-weight: bold; }
.sig { border: 1px solid #1f3b63; padding: 4px 8px; margin-top: 6px; }
@font-face { font-family: 'Great Vibes'; src: url('%(sigfont)s'); }
.signoff { margin: 14px 0 0 auto; width: 82mm; page-break-inside: avoid; text-align: left; }
.signoff .ink { font-family: 'Great Vibes', cursive; font-size: 26pt; color: #12305e; line-height: 1.05; margin: 0 0 0 4mm;
                transform: rotate(-3deg); }
.signoff .rule { border-top: 1px solid #555; margin: 1px 0 3px; }
.signoff .who { font-size: 8.8pt; line-height: 1.3; color: #222; }
.signoff .who b { font-size: 9.5pt; }
.signoff .dsc { margin-top: 5px; border: 1px solid #2f6f3a; background: #f3faf3; padding: 3px 6px; font-size: 7.6pt; color: #1d3d22;
                line-height: 1.3; }
.signoff .dsc .tick { color: #2f6f3a; font-weight: bold; }
.signoff .dsc p.sig { border: 0; padding: 0; margin: 2px 0 0; }
table.res td:nth-child(5) { font-weight: bold; color: #b23a2f; }
.nabl { font-size: 8pt; color: #444; margin-top: 10px; border-top: 1px dotted #999; padding-top: 4px; }
p { margin: 3px 0 5px; line-height: 1.35; }
"""


# ------------------------------------------------------------------------ small helpers
def _e(x):
    return html.escape(str(x), quote=False)


def label(key):
    """Readable label of a value key (LABELS, else the key in words)."""
    return LABELS.get(key) or str(key).replace("_", " ").capitalize()


def _when(value):
    """DD/MM/YYYY, with HH:MM when the value carries a time."""
    if not value:
        return None
    return display_date(value) if len(str(value).strip()) == 10 else display_time(value)


def _split_result(value):
    """(result, unit) of a printed lab value: "12.4 gm%" -> ("12.4", "gm%"); "Non-reactive" -> ("Non-reactive", "").
    The two cells sit side by side, so the text layer still reads the fixture string ("12.4 gm%")."""
    v = str(value).strip()
    m = _NUMERIC.match(v)
    return (v[:m.start(1)].rstrip(), m.group(1)) if m else (v, "")


def _lab_rows(vals, sex, flags=False):
    """One row per value: investigation, result, unit, reference interval, and (flags=True, the hospital's own reports) a last
    "Flag" column, Low or High when a numeric result lies outside its interval, as a laboratory system prints it."""
    out = []
    for k, v in vals.items():
        result, unit = _split_result(v)
        ref = _reference(k, sex)
        row = (label(k), result, unit, ref)
        out.append(row + (_flag(result, ref),) if flags else row)
    return out


_RANGE = re.compile(r"^\s*([\d.,]+)\s*-\s*([\d.,]+)\s*$")


def _flag(result, ref):
    """Low / High against a numeric "a-b" interval; empty for text results or text intervals."""
    m = _RANGE.match(str(ref or ""))
    try:
        x = float(str(result).replace(",", "").lstrip("<>").strip())
    except ValueError:
        return ""
    if not m:
        return ""
    lo, hi = (float(g.replace(",", "")) for g in m.groups())
    return "Low" if x < lo else "High" if x > hi else ""


def _reference(key, sex):
    ref = REFERENCE.get(key)
    if isinstance(ref, dict):
        ref = ref.get(sex) or next(iter(ref.values()))
    return ref or "Not applicable"


def _rows(values, keys=None):
    """Labelled rows ("<b>Label:</b> value"); a free-text value (PLAIN_KEYS) prints as plain paragraphs."""
    keys = list(values) if keys is None else keys
    out = []
    for k in keys:
        if k in PLAIN_KEYS:
            out.append(_paragraphs(values[k]))
        else:
            out.append(f"<p><b>{_e(label(k))}:</b> {_e(values[k])}</p>")
    return "".join(out)


def _paragraphs(text):
    lines = [x for x in str(text).replace("\r", "").split("\n") if x.strip()]
    return "".join(f"<p>{_e(x)}</p>" for x in lines) or f"<p>{_e(text)}</p>"


def _section(heading, body):
    return f"<h2>{_e(heading)}</h2>{body}"


def _table(head, rows, cls="res"):
    out = f"<table class='{cls}'><tr>" + "".join(f"<th>{_e(h)}</th>" for h in head) + "</tr>"
    out += "".join("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in r) + "</tr>" for r in rows)
    return out + "</table>"


def _grid(pairs):
    """Identity grid: label / value pairs, two per row (the boxed header of Indian hospital reports)."""
    pairs = [(k, v) for k, v in pairs if v not in (None, "")]
    rows = []
    for i in range(0, len(pairs), 2):
        cells = "".join(f"<td class='l'>{_e(k)}</td><td class='v'>: {_e(v)}</td>" for k, v in pairs[i:i + 2])
        if len(pairs[i:i + 2]) == 1:
            cells += "<td class='l'></td><td class='v'></td>"
        rows.append(f"<tr>{cells}</tr>")
    return "<table class='grid'>" + "".join(rows) + "</table>"


def _page(title, header, body, footer, page_footer=PAGE_FOOTER):
    css = CSS % {"footer": page_footer.replace('"', "'"), "sigfont": SIGNATURE_FONT.as_uri()}
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{_e(title)}</title><style>{css}</style></head><body>"
            f"<div class='wm'>{WATERMARK}</div>{header}{body}<div class='foot'>{footer}</div></body></html>")


def _hdr(name, sub, dept, title, extra=""):
    d = f"<div class='d'>{_e(dept)}</div>" if dept else ""
    return (f"<div class='hdr'><div class='h'>{_e(name)}</div><div class='d'>{_e(sub)}</div>{d}</div>"
            f"<h1>{_e(title)}</h1>{extra}")


def _ward_at(enc, t):
    """(ward, bed) of an admission at time t (the ward history entry in force then)."""
    hist = enc.get("ward_history") or []
    if not hist:
        return enc.get("ward"), enc.get("bed")
    cur = hist[0]
    if t:
        tt = parse_time(t)
        for h in hist:
            if parse_time(h["from"]) <= tt:
                cur = h
    return cur["ward"], cur["bed"]


def printed_values(report, version):
    """The values the PDF prints: the version's values minus the report's omitted ones."""
    omitted = set(report.get("omitted_values") or [])
    return {k: v for k, v in (version.get("values") or {}).items() if k not in omitted}


def _status_word(report, version):
    if report.get("status") == "cancelled" and version["version"] == report.get("current_version"):
        return "CANCELLED"
    return STATUS_WORDS.get(version["status"], str(version["status"]).upper())


# ------------------------------------------------------------------------ one report version
def html_for(store, report, version):
    """The HTML of one report version, from the store only (patient, encounter, order, specimen, practitioners, signature)."""
    patient = store.patients[report["patient_id"]]
    enc = store.encounters.get(report["encounter_id"]) or {}
    order = store.orders.get(report["order_id"]) or {}
    spec = store.specimens.get(order.get("specimen_id")) if order.get("specimen_id") else None
    doc_type = report["doc_type"]
    kind = LAYOUT.get(doc_type, "generic")
    dept = order.get("performing_department") or enc.get("department")
    group = (store.department(dept) or {}).get("group")
    consultant = store.practitioner(enc.get("consultant_id")) if enc.get("consultant_id") else None
    clinical = kind in ("clinical", "referral", "discharge")
    vals = printed_values(report, version)
    title = TITLES.get(report["test"]) or str(report.get("title") or report["test"]).upper()

    # identity grid
    is_ip = enc.get("kind") == "IP"
    pairs = [("Patient name", patient["name"]), ("UHID", patient["uhid"]),
             ("Age / Sex", f"{patient['age']} Y / {patient['sex']}"),
             ("IP No." if is_ip else "OP No.", enc.get("number")),
             ("ABHA No.", (patient.get("abha") or {}).get("number"))]
    if order.get("accession"):
        lab_like = kind in ("lab", "hpe", "ihc", "molecular", "cytology")
        pairs.append(("Lab No." if lab_like else "Accession No.", order["accession"]))
    if spec:
        pairs.append(("Sample ID", spec["barcode"]))
        if spec.get("block_no"):
            pairs.append(("Block No.", spec["block_no"]))
    if is_ip:
        ward, bed = _ward_at(enc, order.get("ordered_on") if not clinical else None)
        if kind != "discharge":
            pairs.append(("Ward / Bed", f"{ward} / {bed}"))
    if clinical:
        if is_ip:
            pairs += [("Admitted on", _when(enc.get("admitted"))), ("Discharged on", _when(enc.get("discharged")))]
        else:
            pairs.append(("Visit date", _when(enc.get("date"))))
        pairs.append(("Consultant", consultant["name"] if consultant else None))
    else:
        pairs.append(("Ordered on", _when(order.get("ordered_on"))))
        if spec:
            pairs += [("Collected on", _when(spec.get("collected_on"))), ("Received on", _when(spec.get("received_on")))]
        elif order.get("scheduled_for"):
            pairs.append(("Study date", _when(order["scheduled_for"])))
        if consultant:
            pairs.append(("Ref. by", f"{consultant['name']} ({enc.get('department')})"))
    pairs.append(("Reported on", _when(version.get("reported_on"))))
    pairs.append(("Unit", f"{enc.get('department')}, {enc.get('unit')}" if enc.get("unit") else enc.get("department")))
    if version["version"] > 1:
        pairs.append(("Report version", str(version["version"])))
    header = _hdr(store.hospital.get("name") or HOSPITAL, HOSPITAL_SUB, f"Department of {dept}" if dept else None, title,
                  _grid(pairs))

    body = _BODY.get(kind, _body_generic)(store, report, version, vals, patient=patient, enc=enc, order=order, spec=spec,
                                         group=group)
    for heading, text in (version.get("sections") or {}).items():
        text = "\n".join(text) if isinstance(text, (list, tuple)) else str(text)
        body += _section(heading, "".join(f"<p>{_e(line)}</p>" for line in text.split("\n") if line.strip()))
    return _page(f"{title} {report['id']}-v{version['version']}", header, body, _footer(store, report, version, order))


def _signoff(store, sig):
    """The signed report's sign-off at the bottom right, as Indian report PDFs carry it: the signer's name in ink (a cursive
    font: an image of a hand signature, never a real one), the printed name, qualification, designation and Reg. No., and the
    digital-signature stamp with the signature block verbatim (the text the readers check). SYNTHETIC like everything here."""
    prac = store.practitioner(sig.get("signer_id")) or {}
    name = str(prac.get("name") or "")
    ink = name[3:] if name.startswith("Dr ") else name
    role = {"consultant": "Consultant", "junior_resident": "Junior Resident"}.get(prac.get("role"), str(prac.get("role") or "").title())
    dept = prac.get("department") or ""
    designation = f"{role}, Department of {dept}" if role and dept else role or dept
    who = [f"<b>{_e(name)}</b>", _e(prac.get("qualification") or ""), _e(designation)]  # the Reg. No. is in the stamp below, once
    return ("<div class='signoff'>"
            f"<div class='ink'>{_e(ink)}</div><div class='rule'></div>"
            f"<div class='who'>{'<br>'.join(x for x in who if x)}</div>"
            f"<div class='dsc'><span class='tick'>&#10003;</span> Digitally signed, {_e(sig.get('ca') or CA_NAME)}"
            f"<p class='sig'>{_e(sig['block'])}</p></div>"
            "</div>")


def _footer(store, report, version, order):
    status = _status_word(report, version)
    lines = [f"<p class='status'>Report status: {status}</p>"]
    if version["status"] == "amended" or (version.get("amendment_note") and version["version"] > 1):
        prev = next((v for v in report["versions"] if v["version"] == version["version"] - 1), None)
        when = display_date(prev["reported_on"]) if prev else ""
        lines.append(f"<p>Amends version {version['version'] - 1} of {_e(when)}: {_e(version.get('amendment_note') or '')}</p>")
    if status == "CANCELLED":
        reason = order.get("cancel_reason")
        on = _when(order.get("cancelled_on"))
        lines.append(f"<p>Report cancelled on {_e(on)}" + (f": {_e(reason)}" if reason else "") + "</p>")
    sid = version.get("signature_id")
    by = store.practitioner(version.get("reported_by")) or {}
    if sid:
        lines.append(_signoff(store, store.signatures[sid]))
    elif version["status"] == "preliminary":
        lines.append(f"<p>Reported by: {_e(by.get('name', ''))} (preliminary, verification awaited)</p>")
    else:
        lines.append("<p>Signature pending</p>")
    return "".join(lines)


# ------------------------------------------------------------------------ bodies per layout
def _body_lab(store, report, version, vals, patient, group=None, order=None, **_):
    dept = (order or {}).get("performing_department")
    body = f"<p><b>Specimen:</b> {_e(LAB_GROUPS.get(dept, 'Serum'))}</p>"
    body += _table(("Investigation", "Result", "Units", "Biological reference interval", "Flag"), _lab_rows(vals, patient["sex"], flags=True))
    body += f"<div class='nabl'>{_e(NABL_LINE)}</div>"
    return body


def _split_impression(vals):
    imp = [k for k in vals if IMPRESSION_KEY.search(k)]
    return [k for k in vals if k not in imp], imp


def _body_radiology(store, report, version, vals, **_):
    rest = {k: v for k, v in vals.items() if k not in ("technique", "comparison")}
    find, imp = _split_impression(rest)
    technique = vals.get("technique") or TECHNIQUE.get(report["doc_type"], "As per the departmental protocol.")
    body = _section("Technique", _paragraphs(technique))
    if vals.get("comparison"):
        body += _section("Comparison", _paragraphs(vals["comparison"]))
    body += _section("Findings", _rows(vals, find) or "<p>Described in the impression below.</p>")
    body += _section("Impression", _rows(vals, imp) or "<p>As described in the findings above.</p>")
    return body


def _specimen_block(spec, text):
    body = _section("Specimen", f"<p>{_e(text)}</p>")
    if spec and spec.get("block_no"):
        body += _section("Block No.", f"<p>{_e(spec['block_no'])}</p>")
    return body


def _body_hpe(store, report, version, vals, spec=None, **_):
    review = report["test"] == "hpe_slide_review"
    body = _specimen_block(spec, vals.get("specimen") or ("Outside slides and paraffin blocks received for review." if review
                           else "Biopsy received in 10% buffered formalin, labelled with the patient's name and UHID."))
    body += _section("Gross", _paragraphs(vals["gross"]) if vals.get("gross") else "<p>"
                     + ("Slides and blocks as received, labelled with the outside laboratory's numbers."
                        if review else "Specimen received as labelled and submitted for processing.") + "</p>")
    micro = [k for k in vals if k not in HPE_DIAGNOSIS_KEYS and k not in ("specimen", "gross")]
    diag = [k for k in vals if k in HPE_DIAGNOSIS_KEYS]
    body += _section("Microscopy", _rows(vals, micro) or "<p>Sections studied.</p>")
    body += _section("Diagnosis", _rows(vals, diag) or "<p>As described in the microscopy above.</p>")
    return body


def _body_ihc(store, report, version, vals, spec=None, **_):
    body = _specimen_block(spec, "Formalin-fixed paraffin-embedded (FFPE) tissue block of the biopsy.")
    body += _section("Immunohistochemistry", _table(("Marker", "Result"), [(label(k), v) for k, v in vals.items()]))
    body += "<p>External and internal controls stained appropriately.</p>"
    return body


def _body_molecular(store, report, version, vals, spec=None, **_):
    body = _specimen_block(spec, "Formalin-fixed paraffin-embedded (FFPE) tissue block received for testing.")
    rows = [(label(k), MOLECULAR_METHOD.get(k, "As per the laboratory protocol"), v) for k, v in vals.items()]
    body += _section("Results", _table(("Test", "Method", "Result"), rows))
    return body


def _body_cytology(store, report, version, vals, spec=None, **_):
    body = _specimen_block(spec, vals.get("specimen") or "Aspirates received as smears and a cell block.")
    body += _section("Microscopy", _paragraphs(vals["microscopy"]) if vals.get("microscopy") else "<p>Smears studied.</p>")
    rest = [k for k in vals if k not in ("specimen", "microscopy")]
    body += _section("Diagnosis", _rows(vals, rest) or "<p>As described in the microscopy above.</p>")
    return body


def _body_endoscopy(store, report, version, vals, **_):
    find, imp = _split_impression(vals)
    proc = str(report.get("title") or report["test"])
    body = _section("Procedure", f"<p>{_e(proc)}, performed as recorded in the procedure register.</p>")
    body += _section("Findings", _rows(vals, find) or "<p>Described in the impression below.</p>")
    body += _section("Impression", _rows(vals, imp) or "<p>As described in the findings above.</p>")
    return body


def _clinical_sections(vals):
    pc = [k for k in vals if k == "presenting_complaint"]
    plan = [k for k in vals if k in ("clinical_question", "plan")]
    exam = [k for k in vals if k not in pc + plan]
    body = _section("Presenting complaint", _rows(vals, pc) or "<p>As recorded in the case sheet.</p>")
    body += _section("Examination", _rows(vals, exam) or "<p>As recorded in the case sheet.</p>")
    # the heading names a clinical question only when one is recorded: a plan alone under "Clinical question / Plan" was read as the
    # question for the board (18 Oct, e2e)
    body += _section("Clinical question / Plan" if "clinical_question" in vals else "Plan", _rows(vals, plan) or "<p>Continue as per the treating unit.</p>")
    return body


def _body_clinical(store, report, version, vals, **_):
    return _clinical_sections(vals)


def _referral_lines(enc):
    out = []
    for r in enc.get("referrals") or []:
        line = f"Referred from {r['from']} to {r['to']} on {display_date(r['on'])}"
        if r.get("reason"):
            line += f": {r['reason']}"
        if r.get("status") == "accepted" and r.get("accepted_on"):
            line += f" (accepted on {display_date(r['accepted_on'])})"
        out.append(f"<p>{_e(line)}</p>")
    return "".join(out)


def _body_referral(store, report, version, vals, enc=None, **_):
    body = _section("Referral", _referral_lines(enc or {}) or "<p>Referral raised by the treating unit.</p>")
    return body + _clinical_sections(vals)


def _body_discharge(store, report, version, vals, patient=None, enc=None, **_):
    enc = enc or {}
    adm = [f"<p><b>IP No.:</b> {_e(enc.get('number'))}; admitted on {_e(_when(enc.get('admitted')))} under "
           f"{_e(enc.get('department'))}, {_e(enc.get('unit'))}</p>"]
    for i, h in enumerate(enc.get("ward_history") or []):
        verb = "Ward / bed" if i == 0 else "Transferred to"
        line = f"{verb}: {h['ward']}, bed {h['bed']} from {display_time(h['from'])}"
        if h.get("reason"):
            line += f" ({h['reason']})"
        adm.append(f"<p>{_e(line)}</p>")
    if enc.get("discharged"):
        adm.append(f"<p><b>Discharged on:</b> {_e(_when(enc['discharged']))}</p>")
    if patient and patient.get("pmjay_id"):
        pre = enc.get("pmjay_preauth") or {}
        line = f"PM-JAY ID {patient['pmjay_id']}"
        if pre.get("status"):
            line += f"; pre-authorisation {pre['status']}" + (f" on {display_date(pre['date'])}" if pre.get("date") else "")
        adm.append(f"<p>{_e(line)}</p>")
    body = _section("Admission", "".join(adm))
    body += _section("Referrals", _referral_lines(enc) or "<p>No inter-department referral during this admission.</p>")
    body += _section("Diagnosis", _paragraphs(vals["diagnosis"]) if vals.get("diagnosis")
                     else "<p>As per the investigation reports filed under this IP No.</p>")
    course = [k for k in vals if k not in ("diagnosis", "advice")]
    body += _section("Course", _rows(vals, course) + "<p>Course in the ward as per the movements above.</p>")
    body += _section("Advice", _paragraphs(vals["advice"]) if vals.get("advice")
                     else f"<p>Review in the {_e(enc.get('department'))} OPD, {_e(enc.get('unit'))}, with all reports.</p>")
    return body


def _body_generic(store, report, version, vals, **_):
    return _section("Details", _rows(vals) or "<p>As recorded by the department.</p>")


_BODY = {"lab": _body_lab, "radiology": _body_radiology, "hpe": _body_hpe, "ihc": _body_ihc, "molecular": _body_molecular,
         "cytology": _body_cytology, "endoscopy": _body_endoscopy, "clinical": _body_clinical, "referral": _body_referral,
         "discharge": _body_discharge, "generic": _body_generic}


# ------------------------------------------------------------------------ outside reports (uploaded by a doctor, 3.6)
def outside_html(record):
    """An outside private laboratory's report as printed: its own name, the printed identifiers (the masked Aadhaar exactly as
    given), printed status and signature lines; no digital-signature block and no demo CA."""
    src = record.get("outside_source") or {}
    ids_ = record.get("printed_identifiers") or {}
    lab = record["type"] == "lab"
    title = ("TUMOUR MARKER REPORT: " + str(record.get("title") or "").split("(")[0].strip().upper() if lab
             else "HISTOPATHOLOGY REPORT" if record["type"] == "histopathology" else str(record.get("title") or "").upper())
    pairs = [("Name", ids_.get("name")), ("Age / Sex", ids_.get("age_sex")), ("Aadhaar No.", ids_.get("aadhaar")),
             ("Lab Ref. No.", ids_.get("lab_ref")), ("Report date", (record.get("reported_on") or {}).get("display"))]
    header = _hdr(src.get("name") or "Outside laboratory (SYNTHETIC)", "Private laboratory (SYNTHETIC, fictitious)", None,
                  title, _grid(pairs))
    vals = record.get("values") or {}
    sex = (ids_.get("age_sex") or "").strip()[-1:]
    if lab:
        body = _table(("Investigation", "Result", "Units", "Biological reference interval"), _lab_rows(vals, sex))
    else:
        body = _section("Specimen", "<p>Biopsy, as received.</p>") + _section("Diagnosis", _rows(vals))
    footer = "".join(f"<p>{_e(x)}</p>" for x in (record.get("printed_status"), record.get("printed_signature")) if x)
    return _page(f"{title} {record['id']}", header, body, footer, page_footer=OUTSIDE_FOOTER)


def _outside_records(files):
    path = Path(files["fixture_index"])
    if not path.exists():
        return []
    index = json.loads(path.read_text(encoding="utf-8"))
    return [o["record"] for o in index.get("outside_reports", [])]


def outside_paths(files, record):
    """(pdf, scan png or None) of an outside report."""
    d = Path(files["documents"]) / OUTSIDE_DIR
    rid = record["id"]
    return d / f"{rid}.pdf", (d / f"{rid}-scan.png" if record.get("file_kind") == "scanned_pdf" else None)


# ------------------------------------------------------------------------ rendering
def _sha(data):
    return hashlib.sha256(data).hexdigest()


def tampered_hash(data):
    """The hash a tampered signature carries: sha256 of the PDF bytes with the last byte flipped (a verifier recomputing the
    PDF's hash sees the mismatch; the PDF itself is untouched)."""
    b = bytearray(data)
    b[-1] ^= 0x01
    return _sha(bytes(b))


def version_path(files, report, version):
    return Path(files["documents"]) / f"{report['id']}-v{version['version']}.pdf"


def run_jobs(jobs, pdf_python=None):
    """Render [{"html", "out", ("scan", "seed")}] with WeasyPrint in the pdf venv, in one subprocess."""
    if not jobs:
        return
    py = Path(pdf_python or PDF_PYTHON)
    env = dict(os.environ)
    lib = py.parent.parent / "lib"
    env["LD_LIBRARY_PATH"] = str(lib) + (os.pathsep + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    with tempfile.TemporaryDirectory(prefix="his_mock_render_") as tmp:
        jf = Path(tmp) / "jobs.json"
        jf.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
        res = subprocess.run([str(py), "-I", str(RENDER_CLI), str(jf)], env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"render_cli failed ({res.returncode}): {res.stderr.strip()[-2000:]}")


def render_versions(store, files, pairs, pdf_python=None, extra_jobs=None):
    """Render only the given [(report, version), ...] to documents/<report id>-v<n>.pdf in one pdf-venv subprocess, then set
    version["document"] = {path (relative to the data dir), sha256} and, for a signed version, the signature's document_hash
    (the tampered hash when its verification_status is not "verified"). Returns the written paths."""
    data_dir = Path(files["data_dir"])
    Path(files["documents"]).mkdir(parents=True, exist_ok=True)
    targets, jobs = [], []
    for report, version in pairs:
        out = version_path(files, report, version)
        jobs.append({"html": html_for(store, report, version), "out": str(out)})
        targets.append((report, version, out))
    run_jobs(jobs + list(extra_jobs or []), pdf_python)
    written = []
    for report, version, out in targets:
        data = out.read_bytes()
        sha = _sha(data)
        try:
            rel = out.relative_to(data_dir).as_posix()
        except ValueError:
            rel = str(out)
        version["document"] = {"path": rel, "sha256": sha}
        sid = version.get("signature_id")
        if sid:
            sig = store.signatures[sid]
            sig["document_hash"] = sha if sig.get("verification_status", "verified") == "verified" else tampered_hash(data)
        written.append(out)
    return written


def render_all(store, files, pdf_python=None):
    """Every version of every report in the store, plus the outside reports of fixture_index.json (with a scanned-looking PNG
    for a scanned one), in one subprocess. Returns the written paths."""
    pairs = [(store.reports[rid], v) for rid in sorted(store.reports) for v in store.reports[rid]["versions"]]
    extra, extra_paths = [], []
    for rec in _outside_records(files):
        pdf, png = outside_paths(files, rec)
        job = {"html": outside_html(rec), "out": str(pdf)}
        if png:
            job["scan"], job["seed"] = str(png), int(_sha(rec["id"].encode())[:8], 16)
        extra.append(job)
        extra_paths += [pdf] + ([png] if png else [])
    return render_versions(store, files, pairs, pdf_python, extra_jobs=extra) + extra_paths


# ------------------------------------------------------------------------ reading back and checking
def text_of(pdf_path):
    """The text layer of a PDF (pypdf, app venv)."""
    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)


def norm(text):
    return " ".join(unicodedata.normalize("NFKC", str(text)).split())


def _common_problems(where, text):
    out = []
    for bad in FORBIDDEN:
        if bad in text:
            out.append(f"{where}: contains {bad!r}")
    for m in AADHAAR_LIKE.finditer(text):
        out.append(f"{where}: Aadhaar-like number {m.group(0)!r}")
    if MARKER not in text:
        out.append(f"{where}: no SYNTHETIC marker")
    return out


def check(store, files):
    """Problems of the rendered documents ([] when every PDF holds exactly what its record holds)."""
    problems = []
    data_dir = Path(files["data_dir"])
    for rid in sorted(store.reports):
        r = store.reports[rid]
        omitted = r.get("omitted_values") or []
        for v in r["versions"]:
            where = f"{rid} v{v['version']}"
            doc = v.get("document") or {}
            path = data_dir / doc["path"] if doc.get("path") else None
            if not path or not path.exists():
                problems.append(f"{where}: PDF missing")
                continue
            data = path.read_bytes()
            if doc.get("sha256") != _sha(data):
                problems.append(f"{where}: stored sha256 differs from the PDF")
            text = norm(text_of(path))
            for k, val in printed_values(r, v).items():
                if norm(val) not in text:
                    problems.append(f"{where}: value {k} {val!r} not in the text layer")
            for k in omitted:
                if label(k) in text or ((v.get("values") or {}).get(k) and norm(v["values"][k]) in text):
                    problems.append(f"{where}: omitted value {k} is printed")
            for k, val in (r.get("observation_values") or {}).items():
                if val != (v.get("values") or {}).get(k) and norm(val) in text:
                    problems.append(f"{where}: the HIS Observation value {k} {val!r} is printed")
            if f"Report status: {_status_word(r, v)}" not in text:
                problems.append(f"{where}: no Report status line")
            sid = v.get("signature_id")
            if sid:
                sig = store.signatures[sid]
                if "Digitally signed by" not in text or CA_NAME not in text or norm(sig["block"]) not in text:
                    problems.append(f"{where}: signature block missing")
                low = text.lower()
                for w in NOT_ON_SIGNED:
                    if w in low:
                        problems.append(f"{where}: a signed report says {w!r}")
                want = _sha(data) if sig.get("verification_status", "verified") == "verified" else tampered_hash(data)
                if sig.get("document_hash") != want:
                    problems.append(f"{where}: signature document_hash is not what its verification status needs")
            elif "Digitally signed by" in text:
                problems.append(f"{where}: an unsigned version prints a signature block")
            problems += _common_problems(where, text)
    for rec in _outside_records(files):
        pdf, png = outside_paths(files, rec)
        where = f"outside {rec['id']}"
        if not pdf.exists():
            problems.append(f"{where}: PDF missing")
            continue
        text = norm(text_of(pdf))
        for k, val in (rec.get("values") or {}).items():
            if norm(val) not in text:
                problems.append(f"{where}: value {k} {val!r} not in the text layer")
        name = (rec.get("outside_source") or {}).get("name")
        if name and name not in text:
            problems.append(f"{where}: the laboratory's name is missing")
        if CA_NAME in text or "Digitally signed" in text:
            problems.append(f"{where}: an outside report carries the demo CA")
        aad = (rec.get("printed_identifiers") or {}).get("aadhaar")
        if aad and (aad != MASKED_AADHAAR or aad not in text):
            problems.append(f"{where}: masked Aadhaar not printed as given")
        if png and not png.exists():
            problems.append(f"{where}: scanned image missing")
        problems += _common_problems(where, text)
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m his_mock.documents", description=__doc__.split("\n")[0])
    ap.add_argument("--data", help="data directory (default data/his_mock/)")
    ap.add_argument("--check", action="store_true", help="check the rendered documents against the store")
    ap.add_argument("--render", action="store_true", help="re-render every document and save the store")
    args = ap.parse_args(argv)
    files = layout(args.data)
    if "tumour_board" in Path(files["data_dir"]).resolve().parts:
        print("refusing to use a directory under data/tumour_board/", file=sys.stderr)
        return 2
    store = Store.load(files["store"])
    if args.render:
        paths = render_all(store, files)
        store.save(files["store"], files["events"])
        print(f"rendered {len(paths)} files into {files['documents']}")
    if args.check or not args.render:
        problems = check(store, files)
        for p in problems:
            print(p)
        print(f"{len(problems)} problem(s)")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
