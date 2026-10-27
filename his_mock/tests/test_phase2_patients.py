"""night-v3 item 2.11 (seed part): four new synthetic patients in the demo HIS for the Phase 2 draft checklists (ovary, prostate,
stomach, lymphoma), their new tests (tumour markers, prostate biopsy and MRI, upper GI endoscopy, HER2 IHC, lymph node biopsy and
IHC panel, CECT neck to pelvis, 2D echocardiography) end to end: seed -> templates -> documents -> FHIR. SYNTHETIC data only; the
Vaidyx-TB protocol and keyword files are read as files, never imported; nothing is written outside a temporary directory."""
import json
import re
from pathlib import Path

import pytest

from his_mock import documents, fhir, generator, scenarios as sc, templates

PROTOCOL_DIR = Path(__file__).resolve().parents[2] / "tumour_board" / "protocols"
NEW = {"P20": ("ovary", "advanced", "Gynaecologic Oncology"),
       "P21": ("prostate", "locally_extensive", "Urology"),
       "P22": ("stomach", "locally_advanced", "Gastrointestinal Surgery"),
       "P23": ("lymphoma", "adult_hodgkin", "Haematology")}
NEW_TESTS = ("ca125_cea", "psa", "ldh", "ascitic_fluid_cytology", "trus_biopsy", "her2_ihc", "lymph_node_biopsy", "ihc_lymphoma",
             "mri_prostate", "cect_neck_tap", "ugi_endoscopy", "echo")


@pytest.fixture(scope="module")
def data():
    return sc.load()


@pytest.fixture(scope="module")
def built(data):
    return generator.build_store(data)


@pytest.fixture(scope="module")
def store(built):
    return built[0]


def _protocol(pid):
    if not PROTOCOL_DIR.is_dir():
        pytest.skip("tumour_board protocols not present")
    return json.loads((PROTOCOL_DIR / f"{pid}.json").read_text())


def _required(rec, setting):  # the hospital is an NCG Optimal centre: Essential (a) and Optimal (b) count
    tiers = rec.get("tiers") or {}
    tier = tiers.get(setting, rec.get("tier", "a"))
    return tier in ("a", "b")


def _report(store, built, rid):
    slot = rid.split("-")[0]
    m = built[1]["slots"][slot]["records"][rid]
    return store.reports[m["report_id"]]


# ------------------------------------------------------------------ the seed
def test_the_seed_validates_and_holds_the_four_new_patients(data):
    assert sc.validate(data) == []
    pts = sc.patients_by_slot(data)
    for slot, (proto, setting, owner) in NEW.items():
        p = pts[slot]
        assert p["marker"] == "SYNTHETIC" and p["name"].endswith("(SYNTHETIC)")
        assert p["uhid"] == f"VXH/26/0042{slot[1:]}" and p["protocol"] == proto and p["treating_department"] == owner
        assert [(c["protocol"], c["ncg_setting"], c["owner"]) for c in p["case_files"]] == [(proto, setting, owner)]
        assert all(e["kind"] == "OP" and e["number"].startswith("OP/26/") and e["department"] == owner for e in p["encounters"])
        for r in p["records"]:  # every record ordered, reported, final and signed by the Vaidyx Demo CA
            assert (r["order_status"], r["report_status"], r["signed"]) == ("completed", "final", True), r["id"]
            assert r["signature"]["ca"] == "Vaidyx Demo CA" and r["signature"]["verification_status"] == "verified"
            assert r["scenarios"] == ["phase2_new_cancers"]
    assert (pts["P20"]["sex"], pts["P20"]["age"]) == ("F", 52) and (pts["P21"]["sex"], pts["P21"]["age"]) == ("M", 68)
    assert (pts["P22"]["sex"], pts["P22"]["age"]) == ("M", 58) and (pts["P23"]["sex"], pts["P23"]["age"]) == ("M", 34)
    assert [len(pts[s]["records"]) for s in NEW] == [8, 8, 9, 12]


def test_the_scenario_names_the_gate_and_the_left_out_optimal_record(data):
    s = sc.by_id(data)["phase2_new_cancers"]
    assert s["patients"] == list(NEW) and s["plan_1_1"] is False
    gate = {g["patient"]: g for g in s["expected"]["gate"]}
    for slot, (proto, setting, _owner) in NEW.items():
        g = gate[slot]
        assert (g["protocol"], g["ncg_setting"], g["when"]) == (proto, setting, "first_fetch")
    assert [gate[x]["result"] for x in NEW] == ["pass", "pass", "gaps", "pass"]
    assert gate["P22"]["level1"] == ["eus"] and gate["P22"]["level2"] == []
    assert s["expected"]["requests"] == [{"patient": "P22", "requirement": "eus", "department": "Gastrointestinal Surgery",
                                          "accession": None, "origin": "suggested_from_gap", "level": 1}]
    gap = sc.patients_by_slot(data)["P22"]["case_files"][0]["first_fetch"]["gaps"]
    assert [(x["requirement"], x["level"], x["department"], x["accession"]) for x in gap] == [("eus", 1, "Gastrointestinal Surgery", None)]


@pytest.mark.parametrize("slot", list(NEW))
def test_every_required_record_and_value_is_in_a_final_signed_report(data, slot):
    """At the Optimal level, in the Case File's setting, each required record is served by a final signed report that prints every
    required value (facts-only records: by a report of their fact document types); only the stomach's EUS is left out."""
    p = sc.patients_by_slot(data)[slot]
    proto, setting, _owner = NEW[slot]
    prot = _protocol(proto)
    missing = []
    for rec in prot["records"]:
        if not _required(rec, setting):
            continue
        serving = [r for r in p["records"] if rec["id"] in (r.get("serves") or {}).get(proto, [])]
        if rec.get("facts_only"):
            assert any(r["type"] in rec["fact_doc_types"] for r in serving), rec["id"]
        if not serving:
            missing.append(rec["id"])
            continue
        types = set(rec.get("doc_types") or rec.get("fact_doc_types") or [])
        assert any(r["type"] in types for r in serving), (rec["id"], [r["type"] for r in serving])
        have = set().union(*(set(r["values"]) for r in serving))
        assert set(rec.get("required_facts") or []) <= have, (rec["id"], set(rec["required_facts"]) - have)
    assert missing == (["eus"] if slot == "P22" else [])


def test_new_tests_are_wired_to_departments_that_produce_them(data):
    depts = {d["name"]: d for d in data["departments"]}
    for key in NEW_TESTS:
        spec = data["tests"][key]
        assert key in depts[spec["department"]]["produces"], key
    card = depts["Cardiology"]
    assert card["group"] == "treating" and card["code"] == "CARD" and card["produces"] == ["echo"]
    assert data["tests"]["echo"]["doc_type"] == "echocardiogram" and data["tests"]["ugi_endoscopy"]["department"] == "Medical Gastroenterology"
    assert [c["reg_no"] for c in depts["Urology"]["consultants"]] == ["VXREG-20112"]
    assert [c["reg_no"] for c in depts["Haematology"]["consultants"]] == ["VXREG-20113"]


# ------------------------------------------------------------------ titles name one document type (doc_type_keywords.json, read as a file)
def _keyword_types(title):
    """The document types whose keywords match a title line (whole words; a space, hyphen, slash, dot or underscore matches any of
    them or nothing), after the ignore phrases are blanked and the 'beats' rules applied: a light reading of the Vaidyx-TB rule."""
    kw = json.loads((PROTOCOL_DIR / "doc_type_keywords.json").read_text())

    def rx(phrase, flags):
        body = "".join(r"[\s\-/._]?" if ch in " -/._" else re.escape(ch) for ch in phrase)
        return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", flags)

    line = title
    for phrase in kw["ignore"]:
        line = rx(phrase, re.I).sub(" ", line)
    hits = set()
    for t, spec in kw["types"].items():
        pats = [(x, re.I) for x in spec.get("patterns", []) + spec.get("title_only", [])] + [(x, 0) for x in spec.get("case_sensitive", [])]
        if any(rx(x, f).search(line) for x, f in pats):
            hits.add(t)
    beaten = {b for t in hits for b in kw["types"][t].get("beats", [])}
    return hits - beaten


@pytest.mark.parametrize("test", NEW_TESTS + ("pft",))
def test_printed_and_fixture_titles_name_the_tests_document_type(data, test):
    if not PROTOCOL_DIR.is_dir():
        pytest.skip("tumour_board protocols not present")
    want = data["tests"][test]["doc_type"]
    titles = [documents.TITLES[test], data["tests"][test]["label"]]
    titles += [r["title"] for p in data["patients"] for r in p["records"] if r["test"] == test]
    for t in titles:
        assert _keyword_types(t) == {want}, (test, t, _keyword_types(t))


# ------------------------------------------------------------------ templates
def test_lab_templates_of_the_new_markers():
    t = templates.lab_templates()
    psa, = t["psa"]["fields"]
    assert (psa["key"], psa["unit"], psa["reference"], psa["kind"]) == ("psa", "ng/mL", "0-4.0", "numeric")
    assert [(f["key"], f["unit"], f["reference"]) for f in t["ca125_cea"]["fields"]] == [("ca125", "U/mL", "0-35"), ("cea", "ng/mL", "0-5")]
    ldh, = t["ldh"]["fields"]
    assert (ldh["unit"], ldh["reference"]) == ("U/L", "140-280") and t["ldh"]["department"] == "Biochemistry"
    assert t["psa"]["title"] == "TUMOUR MARKER REPORT: SERUM PSA"
    values, errors = templates.parse_lab_form(t["ca125_cea"], {"v_ca125": "1,246", "v_cea": "2.4"}, "F")
    assert errors == {} and values == {"ca125": "1,246 U/mL", "cea": "2.4 ng/mL"}


def test_pathology_field_lists_of_the_new_tests():
    keys = [f["key"] for f in templates.pathology_fields("trus_biopsy", "histopathology")]
    assert keys == ["specimen", "gross", "microscopy", "histologic_type", "gleason_isup", "positive_cores", "diagnosis"]
    assert templates.pathology_fields("lymph_node_biopsy", "histopathology") is templates.HPE
    assert [f["key"] for f in templates.pathology_fields("her2_ihc", "ihc")] == ["her2"]
    assert [f["key"] for f in templates.pathology_fields("ihc_lymphoma", "ihc")] == ["cd45", "cd30", "cd15", "cd20", "pax5", "cd3", "ki67", "diagnosis"]
    assert templates.pathology_fields("ascitic_fluid_cytology", "cytology") is templates.CYTOLOGY
    assert templates.clinical_fields("echocardiogram") is templates.PROCEDURE


# ------------------------------------------------------------------ documents (HTML of the report versions; the PDFs are checked in test_documents)
def _page(store, built, rid):
    r = _report(store, built, rid)
    return documents.html_for(store, r, store.current_version(r))


def test_report_layouts_of_the_new_records(store, built):
    page = _page(store, built, "P21-R04")   # TRUS biopsy: Gleason and cores under Diagnosis
    diag = page.split("<h2>Diagnosis</h2>", 1)[1].split("<div class='foot'>", 1)[0]
    assert "<b>Gleason score / ISUP grade group:</b> Gleason score 4+3=7, ISUP grade group 3" in diag
    assert "<b>Positive cores:</b> 6 of 12 cores positive" in diag
    assert "HISTOPATHOLOGY REPORT: TRUS-GUIDED PROSTATE BIOPSY" in page and "PATH/26/00467-A1" in page
    page = _page(store, built, "P23-R11")   # echo: a procedure layout, signed by the cardiologist
    assert "<h1>2D ECHOCARDIOGRAPHY REPORT</h1>" in page and "Department of Cardiology" in page and "CARD/26/00318" in page
    assert "<b>LV ejection fraction (LVEF):</b> 62 %" in page.split("<h2>Impression</h2>", 1)[0]
    assert "Normal biventricular function, LVEF 62 %" in page.split("<h2>Impression</h2>", 1)[1]
    assert "Dr Sudhir Kamath" in page and "VXREG-20114" in page
    page = _page(store, built, "P23-R03")   # IHC panel as a marker table
    assert "<td>CD30</td><td>Positive in the Reed-Sternberg cells (membranous and Golgi pattern)</td>" in page
    assert "<td>Ki-67 labelling index</td><td>40 % (MIB-1, in the large atypical cells)</td>" in page
    page = _page(store, built, "P20-R02")   # tumour markers: Indian units, interval, High flag
    assert "<td>CA-125 (cancer antigen 125)</td><td>1,246</td><td>U/mL</td><td>0-35</td><td>High</td>" in page
    page = _page(store, built, "P22-R01")   # the nutrition evaluation line of the OPD note
    assert "<b>Nutrition evaluation:</b> Weight 54 kg, BMI 19.8 kg/m2" in page
    for rid in ("P20-R07", "P22-R02", "P23-R12"):
        assert "\u2014" not in _page(store, built, rid)


# ------------------------------------------------------------------ FHIR
def test_fhir_codes_give_the_vaidyx_side_a_readable_document_type(store, built):
    codes = {}
    if PROTOCOL_DIR.is_dir():
        codes = json.loads((PROTOCOL_DIR / "his_codes.json").read_text())
    for rid, loinc, profile in (("P23-R11", "34552-0", "DiagnosticReportLab"), ("P23-R12", "18759-1", "DiagnosticReportLab"),
                                ("P21-R02", "2857-1", "DiagnosticReportLab"), ("P22-R02", "18751-8", "DiagnosticReportImaging")):
        r = _report(store, built, rid)
        dr = fhir.diagnostic_report(store, r)
        coding = dr["code"]["coding"][0]
        assert coding["system"] == fhir.LOINC and coding["code"] == loinc and dr["code"]["text"] == r["title"]
        assert dr["meta"]["profile"][0].endswith(profile) and dr["status"] == "final"
        if codes and rid != "P22-R02":  # not a pathology or imaging family code: the title keywords decide on the Vaidyx side
            assert loinc not in codes["doc_type_by_loinc"] and loinc not in codes["pathology_family"]["loinc"]
            assert loinc not in codes["imaging"]["loinc"]
    echo = fhir.diagnostic_report(store, _report(store, built, "P23-R11"))
    assert echo.get("category") in (None, [])     # not filed under the pathology service
    obs = fhir.observations(store, _report(store, built, "P23-R11"))
    assert {o["category"][0]["coding"][0]["code"] for o in obs} == {"procedure"}


def test_fhir_observations_of_the_new_markers_carry_loinc_and_quantities(store, built):
    obs = {o["code"]["text"]: o for o in fhir.observations(store, _report(store, built, "P20-R02"))}
    ca125 = obs["CA-125 (cancer antigen 125)"]
    assert ca125["code"]["coding"][0]["code"] == "10334-1"
    assert ca125["valueQuantity"]["value"] == 1246 and ca125["valueQuantity"]["unit"] == "U/mL"
    psa, = fhir.observations(store, _report(store, built, "P21-R02"))
    assert psa["code"]["coding"][0]["code"] == "2857-1" and psa["valueQuantity"] == {"value": 38.6, "unit": "ng/mL", "system": fhir.UCUM, "code": "ng/mL"}
    ldh, = fhir.observations(store, _report(store, built, "P23-R07"))
    assert ldh["code"]["coding"][0]["code"] == "2532-0" and ldh["valueQuantity"]["value"] == 312
    gleason = {o["code"]["text"]: o for o in fhir.observations(store, _report(store, built, "P21-R04"))}
    assert gleason["Gleason score / ISUP grade group"]["valueString"] == "Gleason score 4+3=7, ISUP grade group 3"
    assert "Gleason score 4+3=7" in fhir.diagnostic_report(store, _report(store, built, "P21-R04"))["conclusion"]
