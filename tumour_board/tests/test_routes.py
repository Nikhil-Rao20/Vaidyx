"""Routing map (V2 item 2.4): every protocol record is requested from the department that produces it; the root admin overrides a route
in org.json; clinical records go to the owning treating department, previous board records to the MDT Coordinator."""
import copy

import pytest

from tumour_board import org, protocol, rules

PROTOCOLS = ("breast", "cervix", "colorectal_rectum", "lung_nsclc", "oral_cavity")


def _all_records():
    for pid in PROTOCOLS:
        p = protocol.get(pid)
        for kind, recs in (("required", protocol.records(p)), ("optional", p.get("optional") or [])):
            for r in recs:
                yield pid, kind, r


def test_every_record_of_the_five_protocols_has_a_route(data_root):
    for pid, kind, r in _all_records():
        name, did, rkind = rules.routed(protocol.get(pid), r)
        assert rkind in org.ROUTE_KINDS, (pid, r["id"])
        if rkind == org.COORDINATOR_ID:
            assert did is None and name == org.COORDINATOR_NAME, (pid, r["id"])
        else:
            assert did and org.department(did), (pid, r["id"], r.get("department"))  # the department exists in the organisation
        if r.get("route"):
            assert r["route"] in (org.OWNER_ID, org.COORDINATOR_ID), (pid, r["id"])


@pytest.mark.parametrize("pid,rec,dept", [
    ("breast", "cbc", "pathology"), ("lung_nsclc", "cbc", "pathology"), ("cervix", "cbc", "pathology"),
    ("breast", "liver_renal_function", "biochemistry"), ("lung_nsclc", "liver_renal_function", "biochemistry"), ("cervix", "liver_renal_function", "biochemistry"),
    ("colorectal_rectum", "cea", "biochemistry"),
    ("cervix", "viral_markers", "microbiology"),
    ("lung_nsclc", "driver_mutations", "pathology"), ("lung_nsclc", "met", "pathology"), ("colorectal_rectum", "ras_braf", "pathology"), ("colorectal_rectum", "mmr", "pathology"),
    ("oral_cavity", "dental_evaluation", "dental_surgery"),
    ("lung_nsclc", "bronchoscopy", "pulmonology"), ("lung_nsclc", "mediastinal_staging", "pulmonology"), ("lung_nsclc", "pft", "pulmonology"),
    ("colorectal_rectum", "endoscopy", "medical_gastroenterology"),
    ("cervix", "eua", "gynaecologic_oncology"), ("cervix", "cystoscopy_proctoscopy", "gynaecologic_oncology"),
    ("breast", "breast_imaging", "radiology"), ("breast", "bone_scan", "nuclear_medicine"), ("breast", "histopathology", "pathology"),
])
def test_plan_routes(data_root, pid, rec, dept):
    """The plan's 2.4 table: supporting tests by test, procedures by the treating department that does them."""
    p = protocol.get(pid)
    r = next(x for x in protocol.records(p) + (p.get("optional") or []) if x["id"] == rec)
    assert rules.routed(p, r)[1] == dept


def test_clinical_records_route_to_the_owner_and_previous_board_to_the_coordinator(data_root):
    for pid in PROTOCOLS:
        p = protocol.get(pid)
        ch = next(x for x in protocol.records(p) if x["id"] == "clinical_history")
        assert ch["route"] == "owner"
        name, did, kind = rules.routed(p, ch)  # no owner yet (before 5.1): the protocol's default treating department
        assert kind == "owner" and did == org.department_id(ch["department"]) and org.department_group(did) == "treating", pid
        name, did, kind = rules.routed(p, ch, {"department": "breast_surgery"})  # a Case File with an owner (5.1)
        assert (name, did, kind) == ("Breast Surgery", "breast_surgery", "owner")
        pb = next(x for x in p.get("optional") or [] if x["id"] == "previous_board")
        assert rules.routed(p, pb) == (org.COORDINATOR_NAME, None, "coordinator")
    disch = next(x for x in protocol.get("lung_nsclc")["optional"] if x["id"] == "discharge")
    assert disch["route"] == "owner" and rules.routed(protocol.get("lung_nsclc"), disch)[1] == "medical_oncology"


def test_baseline_blood_tests_are_split_by_test(data_root):
    for pid in ("breast", "cervix", "lung_nsclc"):
        ids = [r["id"] for r in protocol.records(pid)]
        assert "baseline_labs" not in ids and "cbc" in ids and "liver_renal_function" in ids, pid
        cbc = next(r for r in protocol.records(pid) if r["id"] == "cbc"); lrf = next(r for r in protocol.records(pid) if r["id"] == "liver_renal_function")
        assert cbc["required_facts"] == ["haemoglobin", "wbc", "platelets"] and lrf["required_facts"] == ["creatinine", "bilirubin"]
        assert cbc["doc_types"] == ["lab"] and lrf["doc_types"] == ["lab"] and cbc["region"] and lrf["region"]
        assert cbc.get("sources") and cbc["sources"] == lrf["sources"]  # the NCG line travels with both halves
    assert [r["id"] for r in protocol.records("cervix") if r["id"] == "viral_markers"] and next(r for r in protocol.records("cervix") if r["id"] == "viral_markers")["required_facts"] == ["hiv_status"]
    assert "viral_markers" not in [r["id"] for r in protocol.records("breast")]
    assert [r["id"] for r in protocol.get("oral_cavity")["optional"] if r["id"] in ("cbc", "liver_renal_function")] == ["cbc", "liver_renal_function"]


def test_region_words_match_lab_titles_and_file_names():
    cbc = next(r for r in protocol.records("lung_nsclc") if r["id"] == "cbc"); lrf = next(r for r in protocol.records("lung_nsclc") if r["id"] == "liver_renal_function")
    doc = lambda title, fn: {"classification": {"title": title, "doc_type": "lab"}, "filename": fn}
    assert rules._region_ok(doc("HAEMATOLOGY REPORT (CBC)", "cbc_2026-09-04.png"), cbc["region"]) and not rules._region_ok(doc("HAEMATOLOGY REPORT (CBC)", "cbc_2026-09-04.png"), lrf["region"])
    assert rules._region_ok(doc("BIOCHEMISTRY REPORT", "renal_liver_function_2026-09-04.pdf"), lrf["region"]) and not rules._region_ok(doc("BIOCHEMISTRY REPORT", "renal_liver_function_2026-09-04.pdf"), cbc["region"])
    assert rules._region_ok(doc("HAEMATOLOGY AND BIOCHEMISTRY", "blood_tests_2026-08-20.pdf"), cbc["region"]) and rules._region_ok(doc("HAEMATOLOGY AND BIOCHEMISTRY", "blood_tests_2026-08-20.pdf"), lrf["region"])
    assert rules._region_ok(doc("LAB", "cbc_rft_lft_serology_2026-09-15.pdf"), lrf["region"])  # file names are read word by word (underscores)
    viral = next(r for r in protocol.records("cervix") if r["id"] == "viral_markers")
    assert rules._region_ok(doc("SEROLOGY", "x.pdf"), viral["region"]) and rules._region_ok(doc("LAB", "cbc_lft_rft_hiv_2026-09-15.pdf"), viral["region"]) and not rules._region_ok(doc("HAEMATOLOGY", "cbc.pdf"), viral["region"])
    dental = next(r for r in protocol.records("oral_cavity") if r["id"] == "dental_evaluation")
    assert dental["doc_types"] == ["clinical_note", "referral"] and rules._region_ok(doc("PRE-TREATMENT DENTAL EVALUATION", "dental_evaluation_2026-09-17.docx"), dental["region"])
    assert not rules._region_ok(doc("OPD NOTE", "surgical_oncology_opd.pdf"), dental["region"])


def test_root_admin_override_wins(data_root):
    p = protocol.get("breast")
    cbc = next(r for r in protocol.records(p) if r["id"] == "cbc")
    assert rules.routed(p, cbc)[1] == "pathology" and org.route_for("breast", "cbc") is None
    o = copy.deepcopy(org.load()); o["routes"] = {"breast.cbc": "Biochemistry", "breast.clinical_history": "coordinator", "breast.bone_scan": "owner"}
    org.save(o, by="root")
    assert org.route_for("breast", "cbc") == "biochemistry"
    assert rules.routed(p, cbc) == ("Biochemistry", "biochemistry", "department")
    ch = next(r for r in protocol.records(p) if r["id"] == "clinical_history")
    assert rules.routed(p, ch) == (org.COORDINATOR_NAME, None, "coordinator")
    bone = next(r for r in protocol.records(p) if r["id"] == "bone_scan")
    assert rules.routed(p, bone, {"department": "breast_surgery"})[1] == "breast_surgery" and rules.routed(p, bone)[1] == "nuclear_medicine"
    assert [e["kind"] for e in org.read_audit()][:2] == ["routes_changed", "org_saved"]


def test_resolve_route_fallbacks(data_root):
    assert org.resolve_route(None, "Radiology") == ("Radiology", "radiology", "department")
    assert org.resolve_route(None, "Laboratory Medicine") == ("Biochemistry", "biochemistry", "department")  # V1 name
    assert org.resolve_route(None, "Cardiology") == ("Cardiology", None, "department")  # unresolved: the coordinator handles it (V1 rule)
    assert org.resolve_route(None, "Tumour Board coordinator") == (org.COORDINATOR_NAME, None, "coordinator")
    assert org.resolve_route("cardiology", "Radiology") == ("Radiology", "radiology", "department")  # a stale override falls back
    assert org.resolve_route("owner", "Medical Oncology", None) == ("Medical Oncology", "medical_oncology", "owner")
    assert org.resolve_route("owner", "Medical Oncology", "Pulmonology") == ("Pulmonology", "pulmonology", "owner")


def test_routes_table_lists_every_record(data_root):
    rows = rules.routes_table()
    assert len(rows) == sum(1 for _ in _all_records())
    row = next(r for r in rows if r["protocol"] == "cervix" and r["record"] == "viral_markers")
    assert row["department_id"] == "microbiology" and row["default"] == "Microbiology" and row["override"] is None and row["kind"] == "required" and row["tier"] == "a"
    row = next(r for r in rows if r["protocol"] == "breast" and r["record"] == "previous_board")
    assert row["default"] == "coordinator" and row["route_kind"] == "coordinator" and row["kind"] == "optional" and row["department"] == org.COORDINATOR_NAME
    o = copy.deepcopy(org.load()); o["routes"] = {"cervix.viral_markers": "pathology"}; org.save(o, by="root")
    row = next(r for r in rules.routes_table() if r["protocol"] == "cervix" and r["record"] == "viral_markers")
    assert row["override"] == "pathology" and row["department_id"] == "pathology"


def test_gate_rows_show_the_routed_department(demo_cases):
    g = rules.evaluate("TB-001")
    by = {r["id"]: r["department"] for r in g["requirements"] + g["shown"]}
    assert by["cbc"] == "Pathology" and by["liver_renal_function"] == "Biochemistry" and by["driver_mutations"] == "Pathology" and by["clinical_history"] == "Medical Oncology"
    o = copy.deepcopy(org.load()); o["routes"] = {"lung_nsclc.cbc": "biochemistry"}; org.save(o, by="root")
    assert {r["id"]: r["department"] for r in rules.evaluate("TB-001")["requirements"]}["cbc"] == "Biochemistry"


def test_coordinator_routed_gap_opens_an_action_for_the_coordinator_row(unit_case, monkeypatch):
    """A record routed to the MDT Coordinator (an override here) opens an action with role coordinator and a notification to the role."""
    from tumour_board import notify, store
    from tumour_board.tests import util
    o = copy.deepcopy(org.load()); o["routes"] = {"unit.ct_thorax": "coordinator"}; org.save(o, by="root")
    g = rules.evaluate(unit_case)
    assert {r["id"]: r["department"] for r in g["requirements"]}["ct_thorax"] == org.COORDINATOR_NAME
    st = rules.sync_actions(unit_case, g)
    a = next(x for x in st["actions"] if x["requirement"] == "ct_thorax")
    assert a["department"] == org.COORDINATOR_NAME and a["department_id"] is None and a["role"] == "coordinator"
    assert any(n["to"] == {"role": "coordinator"} and n["action_id"] == a["id"] for n in notify._load())
    box = notify.inbox(org.roles("", vaidyx_admin=True))
    assert a["id"] in [q["action_id"] for d in box["departments"] if d["id"] == "coordinator" for q in d["requests"]]
