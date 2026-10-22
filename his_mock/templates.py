"""Result entry templates of the demo HIMS (LIS, RIS, pathology, clinical notes). SYNTHETIC data only.

Laboratory templates are derived from the fixtures: for every test of scenarios.json whose document type is `lab`, the
value keys are the keys its fixture records print, in order (cbc: haemoglobin, wbc, platelets; lft: bilirubin, sgot, sgpt;
rft: creatinine, urea; cea: cea; viral_markers: hiv_status, hbsag, anti_hcv), each with the unit the fixtures print
(Indian units: gm%, /cumm, lakhs/cumm, mg/dL, U/L, ng/mL) and the biological reference interval of documents.REFERENCE
(sex-specific for haemoglobin). A numeric result is stored as "<result> <unit>" exactly as the fixtures print it, so the
NABL-style PDF layout of documents.py keeps rendering it (Investigation / Result / Units / Reference interval).

The other templates (radiology report, HPE, IHC panels, molecular, cytology, OPD note, discharge summary, generic
procedure report) are plain field lists; their values print through the layouts of documents.py.
"""
import re

from . import documents, scenarios

NUMBER = re.compile(r"^[<>]?\s*\d[\d,]*(\.\d+)?$")
_FIXTURES = None


def fixtures():
    global _FIXTURES
    if _FIXTURES is None:
        _FIXTURES = scenarios.load()
    return _FIXTURES


# ------------------------------------------------------------------------ laboratory
def _fixture_values(test_key):
    """The printed values of every fixture record of a test, in record order: [(key, value)]."""
    out = []
    for p in fixtures()["patients"]:
        for r in p["records"]:
            if r["test"] != test_key:
                continue
            sets = ([r["values"]] if r.get("values") else []) + [v["values"] for v in r.get("versions") or [] if v.get("values")]
            for vs in sets:
                out.extend(vs.items())
    return out


def _reference(key):
    ref = documents.REFERENCE.get(key)
    if ref is None:
        return None
    return dict(ref) if isinstance(ref, dict) else str(ref)


def lab_template(test_key):
    """{test, label, title, fields: [{key, label, unit, reference, kind, options, example}]} of one lab test."""
    spec = fixtures()["tests"].get(test_key)
    if not spec or spec["doc_type"] != "lab":
        return None
    fields, seen = [], set()
    for key, value in _fixture_values(test_key):
        result, unit = documents._split_result(value)
        if key not in seen:
            seen.add(key)
            numeric = bool(NUMBER.match(result))
            fields.append({"key": key, "label": documents.label(key), "unit": unit if numeric else "",
                           "reference": _reference(key), "kind": "numeric" if numeric else "choice",
                           "options": [] if numeric else [value], "example": result if numeric else value})
        else:
            f = next(f for f in fields if f["key"] == key)
            if f["kind"] == "choice" and value not in f["options"]:
                f["options"].append(value)
    for f in fields:
        if f["kind"] == "choice":
            for extra in ("Reactive", "Indeterminate"):
                if extra not in f["options"]:
                    f["options"].append(extra)
    return {"test": test_key, "label": spec["label"], "title": documents.TITLES.get(test_key, spec["label"]),
            "department": spec["department"], "fields": fields}


def lab_templates():
    """Every lab template keyed by test."""
    return {k: lab_template(k) for k, spec in fixtures()["tests"].items() if spec["doc_type"] == "lab"}


def reference_text(field, sex):
    ref = field.get("reference")
    if isinstance(ref, dict):
        return ref.get(sex) or next(iter(ref.values()))
    return ref or "Not applicable"


def parse_lab_form(template, form, sex, prefix="v_"):
    """(values, errors) of a posted result entry: numeric results are checked and stored as "<result> <unit>"; a choice
    must be one of its options. At least one result is required."""
    values, errors = {}, {}
    for f in template["fields"]:
        raw = " ".join(str(form.get(prefix + f["key"]) or "").split())
        if not raw:
            continue
        if f["kind"] == "numeric":
            if not NUMBER.match(raw):
                errors[prefix + f["key"]] = f"Enter a number, for example {f['example']}."
                continue
            values[f["key"]] = f"{raw} {f['unit']}".strip()
        else:
            if f["options"] and raw not in f["options"]:
                errors[prefix + f["key"]] = "Choose one of " + ", ".join(f["options"]) + "."
                continue
            values[f["key"]] = raw
    if not values and not errors:
        first = template["fields"][0]["key"] if template["fields"] else "values"
        errors[prefix + first] = "Enter at least one result."
    return values, errors


# ------------------------------------------------------------------------ field lists of the other modules
def _f(key, label, *, required=False, rows=0, example="", help=None):
    return {"key": key, "label": label, "required": required, "rows": rows, "example": example, "help": help}


RADIOLOGY = [
    _f("technique", "Technique", rows=2),
    _f("comparison", "Comparison (optional)", rows=2, example="No earlier study available"),
    _f("findings", "Findings", required=True, rows=6),
    _f("impression", "Impression", required=True, rows=3),
]
HPE = [
    _f("specimen", "Specimen", required=True, rows=2, example="Core biopsy, right breast, in 10% buffered formalin"),
    _f("gross", "Gross", rows=2, example="Three linear cores, 1.2 to 1.6 cm, entirely submitted"),
    _f("microscopy", "Microscopy", required=True, rows=5),
    _f("histologic_type", "Histological type", example="Invasive breast carcinoma of no special type"),
    _f("grade", "Grade", example="Grade 2 (Nottingham score 6)"),
    _f("diagnosis", "Diagnosis", required=True, rows=3),
]
IHC = {
    "ihc_breast": [_f("er", "Oestrogen receptor (ER)", required=True, example="Positive (Allred score 7/8)"),
                   _f("pr", "Progesterone receptor (PR)", required=True, example="Positive (Allred score 6/8)"),
                   _f("her2", "HER2/neu (IHC score)", required=True, example="2+ (Equivocal)"),
                   _f("ki67", "Ki-67 labelling index", required=True, example="25 %")],
    "pdl1_ihc": [_f("pdl1", "PD-L1 (22C3), tumour proportion score", required=True, example="TPS 30 %")],
}
MOLECULAR = {
    "molecular_lung": [_f("egfr", "EGFR mutation analysis", required=True, example="Not detected"),
                       _f("alk", "ALK rearrangement", required=True, example="Negative (D5F3)"),
                       _f("ros1", "ROS1 rearrangement", required=True, example="Negative"),
                       _f("met", "MET exon 14 skipping", required=True, example="Not detected")],
}
CYTOLOGY = [
    _f("specimen", "Specimen", rows=2, example="Aspirates from stations 4R and 7 as smears and a cell block"),
    _f("microscopy", "Microscopy", rows=3),
    _f("diagnosis", "Diagnosis", required=True, rows=3),
]
OPD_NOTE = [
    _f("presenting_complaint", "Presenting complaint", required=True, rows=2),
    _f("examination", "Examination", rows=4),
    _f("clinical_question", "Clinical question", rows=2),
    _f("plan", "Plan", rows=3),
]
DISCHARGE_SUMMARY = [
    _f("diagnosis", "Diagnosis", required=True, rows=2),
    _f("course", "Course in the hospital", required=True, rows=5),
    _f("advice", "Advice on discharge", required=True, rows=3),
]
PROCEDURE = [
    _f("findings", "Findings", required=True, rows=5),
    _f("impression", "Impression", required=True, rows=3),
]
CLINICAL = [
    _f("presenting_complaint", "Reason for the consultation", required=True, rows=2),
    _f("examination", "Findings", rows=4),
    _f("plan", "Opinion and plan", required=True, rows=3),
]


def pathology_fields(test_key, doc_type):
    """The entry fields of a pathology order: HPE, an IHC panel (per test, else free lines), molecular, cytology."""
    if doc_type == "histopathology":
        return HPE
    if doc_type == "ihc":
        return IHC.get(test_key)          # None: the free IHC panel (marker: result lines)
    if doc_type == "molecular":
        return MOLECULAR.get(test_key)    # None: free lines
    if doc_type == "cytology":
        return CYTOLOGY
    return None


def clinical_fields(doc_type):
    """The entry fields of a report the treating unit (or a consulting department) writes itself."""
    if doc_type == "clinical_note":
        return CLINICAL
    if doc_type == "discharge_summary":
        return DISCHARGE_SUMMARY
    return PROCEDURE


def parse_fields(fields, form, prefix="v_"):
    """(values, errors) of a posted field list: required fields must be filled; multi-line text is kept with line
    breaks (collapsed spaces)."""
    values, errors = {}, {}
    for f in fields:
        raw = str(form.get(prefix + f["key"]) or "").replace("\r", "")
        lines = [" ".join(x.split()) for x in raw.split("\n")]
        txt = "\n".join(x for x in lines if x).strip()
        if not txt:
            if f["required"]:
                errors[prefix + f["key"]] = f"{f['label']} is required."
            continue
        values[f["key"]] = txt
    return values, errors
