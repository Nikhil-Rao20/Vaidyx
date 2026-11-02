"""Result entry templates (his_mock/templates.py) and the report layouts they print through (documents.py): the lab
templates derived from the fixtures, numeric and choice parsing, the field lists of the other modules, and the new
free-text sections (technique, comparison, specimen, gross, plan, diagnosis, advice). SYNTHETIC data only."""
import pytest

from his_mock import documents, generator, templates


@pytest.fixture(scope="module")
def store():
    return generator.build_store(generator.scenarios.load())[0]


def test_lab_templates_follow_the_fixture_keys_units_and_reference_intervals():
    t = templates.lab_templates()
    assert set(t) == {"cbc", "lft", "rft", "cea", "viral_markers", "ca125_cea", "psa", "ldh"}
    cbc = {f["key"]: f for f in t["cbc"]["fields"]}
    assert list(cbc) == ["haemoglobin", "wbc", "platelets"]
    assert cbc["haemoglobin"]["unit"] == "gm%" and cbc["haemoglobin"]["reference"] == {"M": "13.0-17.0", "F": "12.0-15.0"}
    assert cbc["wbc"]["unit"] == "/cumm" and cbc["wbc"]["reference"] == "4,000-11,000"
    assert cbc["platelets"]["unit"] == "lakhs/cumm" and cbc["platelets"]["reference"] == "1.5-4.5"
    assert [f["key"] for f in t["lft"]["fields"]] == ["bilirubin", "sgot", "sgpt"]
    assert [f["key"] for f in t["rft"]["fields"]] == ["creatinine", "urea"]
    assert t["cea"]["fields"][0]["unit"] == "ng/mL" and t["cea"]["fields"][0]["reference"] == "0-5"
    vm = t["viral_markers"]["fields"]
    assert [f["key"] for f in vm] == ["hiv_status", "hbsag", "anti_hcv"] and all(f["kind"] == "choice" for f in vm)
    assert vm[0]["options"][0] == "Non-reactive" and "Reactive" in vm[0]["options"]
    assert t["cbc"]["title"] == "HAEMATOLOGY REPORT: COMPLETE BLOOD COUNT" and t["lft"]["department"] == "Biochemistry"
    assert templates.lab_template("mammogram") is None
    assert templates.reference_text(cbc["haemoglobin"], "F") == "12.0-15.0"
    assert templates.reference_text(cbc["wbc"], "M") == "4,000-11,000"


def test_parse_lab_form_stores_the_fixture_format():
    t = templates.lab_template("cbc")
    values, errors = templates.parse_lab_form(t, {"v_haemoglobin": " 11.2 ", "v_wbc": "7,600", "v_platelets": ""}, "F")
    assert errors == {} and values == {"haemoglobin": "11.2 gm%", "wbc": "7,600 /cumm"}
    values, errors = templates.parse_lab_form(t, {"v_haemoglobin": "eleven"}, "F")
    assert "v_haemoglobin" in errors and "Enter a number" in errors["v_haemoglobin"] and values == {}
    values, errors = templates.parse_lab_form(t, {}, "F")
    assert errors == {"v_haemoglobin": "Enter at least one result."}
    vm = templates.lab_template("viral_markers")
    values, errors = templates.parse_lab_form(vm, {"v_hiv_status": "Non-reactive", "v_hbsag": "Maybe"}, "M")
    assert values == {"hiv_status": "Non-reactive"} and "Choose one of" in errors["v_hbsag"]
    assert documents._split_result("11.2 gm%") == ("11.2", "gm%")


def test_field_lists_and_parse_fields():
    assert [f["key"] for f in templates.RADIOLOGY] == ["technique", "comparison", "findings", "impression"]
    assert [f["key"] for f in templates.HPE] == ["specimen", "gross", "microscopy", "histologic_type", "grade", "diagnosis"]
    assert [f["key"] for f in templates.pathology_fields("ihc_breast", "ihc")] == ["er", "pr", "her2", "ki67"]
    assert templates.pathology_fields("ihc_panel", "ihc") is None          # free marker: result lines
    assert [f["key"] for f in templates.pathology_fields("molecular_lung", "molecular")] == ["egfr", "alk", "ros1", "met"]
    assert templates.pathology_fields("cytology_ebus", "cytology") is templates.CYTOLOGY
    assert templates.clinical_fields("discharge_summary") is templates.DISCHARGE_SUMMARY
    assert templates.clinical_fields("endoscopy") is templates.PROCEDURE
    values, errors = templates.parse_fields(templates.RADIOLOGY, {"v_findings": "a\r\n\r\n b ", "v_impression": ""})
    assert values == {"findings": "a\nb"} and errors == {"v_impression": "Impression is required."}
    values, errors = templates.parse_fields(templates.OPD_NOTE, {"v_presenting_complaint": "Lump", "v_plan": "Biopsy"})
    assert errors == {} and values == {"presenting_complaint": "Lump", "plan": "Biopsy"}


def _report(store, test, values, doc_type=None):
    o = next(o for o in store.orders.values() if o["test"] == test)
    r = dict(store.report_for_order(o["id"]) or next(r for r in store.reports.values() if r["test"] == test))
    v = dict(store.current_version(r))
    v["values"] = values
    r["omitted_values"] = []
    return r, v


def test_radiology_layout_prints_typed_technique_and_comparison(store):
    r, v = _report(store, "mammogram", {"technique": "Digital mammography, CC and MLO views.", "comparison": "No earlier study.",
                                        "findings": "Spiculated mass, right upper outer quadrant, 2.1 cm.\nNo skin thickening.",
                                        "impression": "BI-RADS 5."})
    page = documents.html_for(store, r, v)
    tech = page.split("<h2>Technique</h2>", 1)[1].split("<h2>", 1)[0]
    assert "Digital mammography, CC and MLO views." in tech and "craniocaudal" not in tech
    assert "<h2>Comparison</h2><p>No earlier study.</p>" in page
    find = page.split("<h2>Findings</h2>", 1)[1].split("<h2>", 1)[0]
    assert "<p>Spiculated mass, right upper outer quadrant, 2.1 cm.</p><p>No skin thickening.</p>" in find
    assert "<b>Findings:</b>" not in page and "<b>Impression:</b>" not in page
    assert page.split("<h2>Impression</h2>", 1)[1].startswith("<p>BI-RADS 5.</p>")
    # the fixture style (keyed findings) still prints labelled rows and the default technique
    r, v = _report(store, "mammogram", {"lesion_size": "5.1 x 3.8 cm", "birads": "BI-RADS 5"})
    page = documents.html_for(store, r, v)
    assert "craniocaudal and mediolateral oblique" in page and "<b>Lesion size:</b> 5.1 x 3.8 cm" in page
    assert "<b>BI-RADS category:</b> BI-RADS 5" in page.split("<h2>Impression</h2>", 1)[1]


def test_hpe_layout_prints_typed_specimen_gross_microscopy_and_diagnosis(store):
    r, v = _report(store, "hpe_biopsy", {"specimen": "Core biopsy, right breast.", "gross": "Three cores, 1.2 cm each.",
                                         "microscopy": "Infiltrating nests of tumour cells.", "grade": "Grade 2",
                                         "diagnosis": "Invasive breast carcinoma, NST."})
    page = documents.html_for(store, r, v)
    assert "<h2>Specimen</h2><p>Core biopsy, right breast.</p>" in page
    assert "<h2>Gross</h2><p>Three cores, 1.2 cm each.</p>" in page
    micro = page.split("<h2>Microscopy</h2>", 1)[1].split("<h2>", 1)[0]
    assert "<p>Infiltrating nests of tumour cells.</p>" in micro and "Core biopsy" not in micro
    diag = page.split("<h2>Diagnosis</h2>", 1)[1].split("<div class='foot'>", 1)[0]
    assert "<b>Grade:</b> Grade 2" in diag and "<p>Invasive breast carcinoma, NST.</p>" in diag
    r, v = _report(store, "hpe_biopsy", {"histologic_type": "Squamous cell carcinoma"})
    assert "10% buffered formalin" in documents.html_for(store, r, v)   # the fixture default stays


def test_clinical_and_discharge_layouts(store):
    r, v = _report(store, "opd_note", {"presenting_complaint": "Lump in the right breast", "examination": "3 cm lump UOQ",
                                       "clinical_question": "Primary management plan", "plan": "Mammogram and core biopsy"})
    page = documents.html_for(store, r, v)
    plan = page.split("<h2>Clinical question / Plan</h2>", 1)[1].split("<div class='foot'>", 1)[0]
    assert "<b>Clinical question:</b> Primary management plan" in plan and "<p>Mammogram and core biopsy</p>" in plan
    exam = page.split("<h2>Examination</h2>", 1)[1].split("<h2>", 1)[0]
    assert "<p>3 cm lump UOQ</p>" in exam and "Mammogram" not in exam
    r, v = _report(store, "discharge_summary", {"diagnosis": "Carcinoma right breast, cT2N1.", "course": "Underwent core biopsy.",
                                                "advice": "Review in Breast Surgery OPD with the HPE report."})
    page = documents.html_for(store, r, v)
    assert page.split("<h2>Diagnosis</h2>", 1)[1].startswith("<p>Carcinoma right breast, cT2N1.</p>")
    assert "<p>Underwent core biopsy.</p>" in page.split("<h2>Course</h2>", 1)[1].split("<h2>Advice</h2>", 1)[0]
    assert page.split("<h2>Advice</h2>", 1)[1].startswith("<p>Review in Breast Surgery OPD with the HPE report.</p>")
    assert "\u2014" not in page
