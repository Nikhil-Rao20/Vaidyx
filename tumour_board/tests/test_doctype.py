"""doctype: the keyword second opinion on the document type (V1 item 3.2). Synthetic Indian-style headers only."""
import json
from pathlib import Path

import pytest

from tumour_board import config, doctype
from tumour_board.eval import doctype_eval
from tumour_board.tests.conftest import FIXTURES

TRUTH = Path("/data/vaidyx/tb_demo_corpus/truth")


def hdr(department, title, *rest, hospital="Sahyadri Cancer Institute (SYNTHETIC), Pune"):
    """A page-1 header as Indian reports print it: hospital, department, title, patient lines."""
    return "\n".join([hospital, department, title, "Patient name Mr. Ravi Shankar", "UHID SYN-700112", "Age / Sex 55 Y / M",
                      *rest])


def kt(text, filename=""):
    return doctype.keyword_type([text], filename)["type"]


# ---- the table -----------------------------------------------------------------------------------------------------
def test_table_types_are_facts_doc_types():
    raw = json.loads((config.PROTOCOL_DIR / "doc_type_keywords.json").read_text())
    known = set(json.loads((config.PROTOCOL_DIR / "facts.json").read_text())["doc_types"])
    assert set(raw["types"]) <= known and "other" not in raw["types"]
    assert raw["_note"] and all(isinstance(v.get("patterns"), list) for v in raw["types"].values())
    for v in raw["types"].values():
        assert set(v.get("beats") or []) <= known


# ---- each keyword family with an Indian-style header -------------------------------------------------------------------
@pytest.mark.parametrize("department,title,expected", [
    ("Department of Radio-diagnosis", "CECT THORAX", "ct"),
    ("Department of Radiology", "NCCT BRAIN", "ct"),
    ("Department of Radiology", "HRCT CHEST", "ct"),
    ("Department of Radiology", "CT SCAN ABDOMEN AND PELVIS (PLAIN)", "ct"),
    ("Department of Radio-diagnosis", "MRI PELVIS (RECTAL PROTOCOL)", "mri"),
    ("Department of Radiology", "Magnetic resonance imaging of the brain", "mri"),
    ("Department of Radiology", "X-RAY CHEST PA VIEW", "xray"),
    ("Department of Radiology", "USG WHOLE ABDOMEN", "ultrasound"),
    ("Department of Radiology", "COLOUR DOPPLER STUDY", "ultrasound"),
    ("Department of Radiology", "BILATERAL SONOMAMMOGRAPHY", "mammogram"),
    ("Department of Nuclear Medicine", "68Ga-PSMA PET/CT", "pet_ct"),
    ("Department of Nuclear Medicine", "WHOLE BODY BONE SCAN (99mTc-MDP)", "bone_scan"),
    ("Department of Pathology", "HISTOPATHOLOGY REPORT", "histopathology"),
    ("Department of Pathology", "HPE REPORT: TRUCUT BIOPSY", "histopathology"),
    ("Department of Pathology", "CYTOLOGY REPORT (FNAC)", "cytology"),
    ("Department of Pathology", "IMMUNOHISTOCHEMISTRY REPORT", "ihc"),
    ("Department of Molecular Pathology", "EGFR MUTATION ANALYSIS (RT-PCR)", "molecular"),
    ("Department of Laboratory Medicine", "HAEMATOLOGY REPORT (CBC)", "lab"),
    ("Department of Biochemistry", "LFT / KFT", "lab"),
    ("Department of Gastroenterology", "UGI SCOPY REPORT", "endoscopy"),
    ("Department of Pulmonary Medicine", "BRONCHOSCOPY REPORT", "endoscopy"),
    ("Department of Surgical Oncology", "OPERATIVE NOTE", "operative_note"),
    ("Department of Medicine", "DISCHARGE SUMMARY", "discharge_summary"),
    ("Department of Radiation Oncology", "RT COMPLETION SUMMARY", "treatment_summary"),
    ("Multidisciplinary Tumour Board", "TUMOUR BOARD MINUTES", "tumour_board_record"),
    ("Department of Medical Oncology", "MEDICAL ONCOLOGY OPD NOTE", "clinical_note"),
    ("Department of Medical Oncology", "REFERRAL LETTER", "referral"),
    ("Department of Pulmonary Medicine", "PULMONARY FUNCTION TEST (SPIROMETRY)", "pulmonary_function"),
])
def test_keyword_families(department, title, expected):
    r = doctype.keyword_type([hdr(department, title)], "")
    assert r["type"] == expected
    title_ev = [e for e in r["evidence"] if e["type"] == expected and e["where"] == "line 3"]
    assert title_ev and title_ev[0]["quote"] == title


# ---- conflict rules -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("title", ["WHOLE BODY 18F-FDG PET-CT", "PET/CT WHOLE BODY", "FDG PET CT REPORT"])
def test_pet_ct_is_not_ct(title):
    r = doctype.keyword_type([hdr("Department of Nuclear Medicine", title)], "")
    assert r["type"] == "pet_ct" and "ct" not in r["scores"]


def test_fnac_is_cytology_not_histopathology():
    t = hdr("Department of Pathology", "FNAC REPORT", "Specimen: USG guided FNAC, left axillary node (biopsy of node)")
    r = doctype.keyword_type([t], "")
    assert r["type"] == "cytology" and "ultrasound" not in r["scores"]


def test_usg_guided_biopsy_titled_histopathology_is_histopathology():
    t = hdr("Department of Pathology", "HISTOPATHOLOGY REPORT", "Specimen: USG-guided core biopsy, left breast mass")
    r = doctype.keyword_type([t], "")
    assert r["type"] == "histopathology" and "ultrasound" not in r["scores"]


def test_ct_guided_biopsy_is_not_ct():
    t = hdr("Department of Pathology", "HISTOPATHOLOGY REPORT", "Specimen: CT guided biopsy, right lower lobe")
    assert doctype.keyword_type([t], "")["scores"] == {"histopathology": 3}


def test_ct_does_not_match_inside_words():
    t = hdr("Department of Laboratory Medicine", "DIRECT BILIRUBIN AND ELECTROLYTES", "Collected on 05/09/2026 08:10",
            "Sample: SERUM")
    r = doctype.keyword_type([t], "")
    assert "ct" not in r["scores"] and r["type"] == "lab"


def test_mrd_number_and_salutation_are_not_mri():
    t = hdr("Department of Biochemistry", "BIOCHEMISTRY REPORT", "MRD No. 2026/44871", "Ref. by: Dr. MR Patil")
    t += "\nNAME: MR. RAVI SHANKAR"
    r = doctype.keyword_type([t], "")
    assert r["type"] == "lab" and "mri" not in r["scores"]


def test_ihc_addendum_in_histopathology_title_is_ihc():
    assert kt(hdr("Department of Pathology", "HISTOPATHOLOGY REPORT - IHC ADDENDUM")) == "ihc"


def test_addendum_follows_its_parent_report():
    t = hdr("Department of Pathology", "ADDENDUM: HER2 FISH", "Relates to IHC report of 19/08/2026")
    r = doctype.keyword_type([t], "")
    assert r["type"] == "ihc"
    assert any(e["type"] == "ihc" and e["weight"] == 5 and e["quote"] == "Relates to IHC report of 19/08/2026" for e in r["evidence"])


def test_pathology_department_with_haematology_is_lab():
    t = "Sahyadri Cancer Institute (SYNTHETIC)\nDEPARTMENT OF PATHOLOGY - HAEMATOLOGY\nCOMPLETE BLOOD COUNT\nName: Mr. Arjun"
    assert kt(t) == "lab"
    t2 = "Sahyadri Cancer Institute (SYNTHETIC)\nDEPARTMENT OF PATHOLOGY (HAEMATOLOGY SECTION)\nName: Mr. Arjun\nUHID 12"
    assert kt(t2) == "lab"


def test_department_line_weighs_less_than_the_study_line():
    t = "SAHYADRI CANCER INSTITUTE\nDEPARTMENT OF HISTOPATHOLOGY\nIMMUNOHISTOCHEMISTRY REPORT"
    r = doctype.keyword_type([t], "")
    assert r["type"] == "ihc"
    assert {e["where"]: e["weight"] for e in r["evidence"] if e["type"] == "histopathology"} == {"line 2": 1}


def test_egfr_kidney_test_is_not_molecular():
    t = hdr("Department of Biochemistry", "RENAL FUNCTION TEST", "eGFR 88 mL/min/1.73m2")
    r = doctype.keyword_type([t], "")
    assert r["type"] == "lab" and "molecular" not in r["scores"]


# ---- where the evidence may come from -------------------------------------------------------------------------------------
def test_body_mentions_are_ignored():
    body = "\n".join(f"line {i}" for i in range(10))
    t = hdr("Department of Pathology", "HISTOPATHOLOGY REPORT") + "\n" + body + "\nComparison with CECT thorax, MRI brain and PET-CT."
    assert doctype.keyword_type([t], "")["scores"] == {"histopathology": 3}


def test_only_page_one_is_read():
    r = doctype.keyword_type(["Sahyadri Cancer Institute\nPage 1 of 2", "CECT THORAX REPORT"], "")
    assert r["type"] == "" and r["evidence"] == []


def test_filename_only_evidence():
    r = doctype.keyword_type([], "cect_thorax_2026-09-02.pdf")
    assert r["type"] == "ct"
    assert r["evidence"] == [{"type": "ct", "keyword": "cect", "quote": "cect_thorax_2026-09-02.pdf", "where": "filename",
                              "weight": 0.5}]


def test_filename_weighs_least():
    r = doctype.keyword_type([hdr("Department of Radiology", "MRI BRAIN WITH CONTRAST")], "ct_scan_2026.pdf")
    assert r["type"] == "mri" and r["scores"] == {"mri": 3, "ct": 0.5}


def test_ambiguous_evidence_gives_no_type():
    r = doctype.keyword_type([hdr("Department of Radiology", "MRI BRAIN AND CT THORAX")], "")
    assert r["type"] == "" and r["scores"] == {"mri": 3, "ct": 3}


def test_no_evidence_gives_no_type():
    r = doctype.keyword_type(["Deccan General Hospital (SYNTHETIC)\nCASE RECORD, SCANNED COPY\nPage 1 of 100"], "scan_001.pdf")
    assert r == {"type": "", "evidence": [], "scores": {}}


def test_transcribed_boxed_header():
    t = "| DEPARTMENT OF RADIO-DIAGNOSIS | CECT THORAX |\n| Name | Mr. Ravi Shankar | UHID | SYN-700112 |"
    r = doctype.keyword_type([t], "")
    assert r["type"] == "ct" and r["scores"] == {"ct": 3}
    assert r["evidence"][0]["quote"] == "| DEPARTMENT OF RADIO-DIAGNOSIS | CECT THORAX |" and r["evidence"][0]["where"] == "line 1"


def test_page_dicts_and_markdown_are_accepted():
    pages = [{"text": "## Report\n\n**Sahyadri Cancer Institute**\n**COLONOSCOPY REPORT**", "method": "vision-transcription"}]
    r = doctype.keyword_type(pages, "")
    assert r["type"] == "endoscopy" and r["evidence"][0]["where"] == "line 4"


def test_all_capitals_report_does_not_make_every_line_a_title():
    t = ("SAHYADRI CANCER INSTITUTE\nDEPARTMENT OF MEDICAL ONCOLOGY\nOPD CONSULTATION\nNAME: RAVI SHANKAR\nUHID: SYN-700112\n"
         "PET CT DONE ON 02/09/2026\nPLAN: DISCUSS IN TUMOUR BOARD")
    r = doctype.keyword_type([t], "")
    assert r["type"] == "clinical_note"
    assert r["scores"]["pet_ct"] == 1 and r["scores"]["tumour_board_record"] == 1


# ---- cross_check -------------------------------------------------------------------------------------------------------------
CECT = hdr("Department of Radio-diagnosis", "CECT THORAX")


def test_cross_check_agree():
    r = doctype.cross_check("ct", [CECT], "")
    assert (r["keyword_type"], r["model_type"], r["agree"]) == ("ct", "ct", True)
    assert r["note"] == "the title line says CECT THORAX (ct); the reader model (Qwen3.5-4B, Chinese, non-medical) also said ct"


def test_cross_check_disagree():
    r = doctype.cross_check("mri", [CECT], "")
    assert r["agree"] is False and r["keyword_type"] == "ct" and r["model_type"] == "mri"
    assert r["note"] == "the title line says CECT THORAX (ct); the reader model (Qwen3.5-4B, Chinese, non-medical) said mri"


def test_cross_check_other_with_keyword_evidence_disagrees():
    r = doctype.cross_check("other", [], "usg_abdomen_2026-09-01.jpg")
    assert r["agree"] is False and r["note"] == "the filename usg_abdomen_2026-09-01.jpg (ultrasound); the reader model (Qwen3.5-4B, Chinese, non-medical) said other"


def test_cross_check_no_evidence():
    r = doctype.cross_check("mri", ["Sahyadri Cancer Institute\nPage 1"], "scan.pdf")
    assert r["agree"] is None and r["keyword_type"] == "" and r["evidence"] == []
    assert r["note"] == "no document type keywords in the header or filename; the reader model (Qwen3.5-4B, Chinese, non-medical)'s type (mri) stands"


def test_cross_check_ambiguous():
    r = doctype.cross_check("ct", [hdr("Department of Radiology", "MRI BRAIN AND CT THORAX")], "")
    assert r["agree"] is None and r["note"] == "the header points to more than one type (ct, mri); the reader model (Qwen3.5-4B, Chinese, non-medical)'s type (ct) stands"


def test_cross_check_header_line_wording():
    t = "Sahyadri Cancer Institute\nPatient name Mr. Ravi\nUHID SYN-1\nAge / Sex 55 Y / M\nStudy: contrast enhanced CT of the neck"
    r = doctype.cross_check("", [t], "")
    assert r["agree"] is False and r["keyword_type"] == "ct"
    assert r["note"] == "header line 5 says Study: contrast enhanced CT of the neck (ct); the reader model (Qwen3.5-4B, Chinese, non-medical) gave no type"


def test_module_is_import_light():
    import ast
    tree = ast.parse(Path(doctype.__file__).read_text())
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module or "." for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert mods <= {"re", "json", "functools", "."}


# ---- the eval comparison over the unit fixtures (synthetic TB-001..003) ---------------------------------------------------------
@pytest.mark.parametrize("cid", ["TB-001", "TB-002", "TB-003"])
def test_fixture_cases_agree_with_model_and_truth(cid):
    tf = TRUTH / f"{cid}.json"
    if not tf.exists():
        pytest.skip(f"answer key {tf} not available")
    rows = doctype_eval.compare_case(FIXTURES / "cases" / cid, json.loads(tf.read_text()))
    assert rows
    s = doctype_eval.summarise(rows)
    assert s["disagreements"] == [], [(r["rel_path"], r["note"]) for r in s["disagreements"]]
    assert s["keyword_ne_truth"] == []
    assert s["with_keyword"] == len(rows)  # every demo document names its type in its header or filename


def test_weak_header_hint_is_not_a_disagreement():
    """An advice line in an OPD note mentioning LFT (a header line, weight 1) must not call the note a lab report (seen on the real case)."""
    texts = ["City Hospital\nDepartment of General Medicine\nPatient Mr X, 54 Y / M\nComplaints: cough\nExamination: unremarkable\nAdvice:\nTab. Pantoprazole\nRest\nReview with CBP, LFT after 1 week.\nDr. A, MD"]
    r = doctype.cross_check("other", texts, "20260908184255.pdf")
    assert r["agree"] is None and r["keyword_type"] == "lab" and r["note"].startswith("only a weak keyword hint")
    r = doctype.cross_check("clinical_note", ["DEPARTMENT OF RADIO-DIAGNOSIS\nCECT THORAX\nPatient Mr X"], "scan.pdf")
    assert r["agree"] is False  # a title line is strong evidence
    r = doctype.cross_check("ct", ["Hospital\nPatient Mr X\nAge 54 Y / M\nComplaints: cough\nExamination: unremarkable\nAdvice: LFT after 1 week"], "x.pdf")
    assert r["agree"] is None  # a concrete model type and a lone header line: the model stands
    assert doctype.cross_check("other", ["Hospital\nPatient Mr X"], "usg_abdomen.jpg")["agree"] is False  # the model gave up: the filename counts
