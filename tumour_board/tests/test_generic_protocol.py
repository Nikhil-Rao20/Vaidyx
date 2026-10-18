"""A cancer with no checklist yet (owner decision R05-Q04, 17 Oct 2026): protocol "generic" requires four core records, histopathology,
staging imaging, a clinical note with performance status and the question for the board, labelled "No disease-specific Indian
protocol". The cancer's name is kept on the Case File (case.json "cancer_name", 2 to 80 characters, required under the generic rule),
accepted by POST /cases/from-his and POST /cases, audited, and shown by GET /case-list as "<name> (no checklist yet)". The gate, the
routes table, the request sync, the fill-in summary and the summary all run on it. Synthetic Case Files in the conftest temporary data
root; the hospital system is an in-memory fake and no model is ever called."""
import asyncio
import json

import pytest

from tumour_board import config, his_case, his_client, llm, org, protocol, rules, slots, store, summary
from tumour_board.tests import util
from tumour_board.tests.test_his_case import ROLES_DOC, UHID, FakeHIS, _two_reports, fakes  # noqa: F401 (fixture)
from tumour_board.tests.test_nik_slots import OWNER, nik_app, people  # noqa: F401 (fixtures)

CORE = ["histopathology", "staging_imaging", "clinical_history", "board_question"]
DECISION = "Owner decision R05-Q04, 17 Oct 2026"


def _case(case_id="TB-GEN-1", name="Urinary bladder", owner=OWNER, **extra):
    c = store.create_case(case_id, dict(util.PATIENT), protocol.GENERIC, created_by="dr.rao", setting="as_recorded")
    if owner:
        c["department"] = owner
    if name:
        c["cancer_name"] = name
    c.update(extra)
    store.save_case(c)
    return case_id


def _four_records(case_id, imaging="ct", question_in_note=False):
    note_facts = {"ecog": util.fact("1", quote="ECOG PS 1")}
    if question_in_note:
        note_facts["clinical_question"] = util.fact("Bladder preservation or cystectomy?", quote="Question for MDT: Bladder preservation or cystectomy?")
    util.add(case_id, util.make_doc("Dhpe", "histopathology", facts={"histologic_type": util.fact("Urothelial carcinoma, high grade")}),
             util.make_doc("Dimg", imaging, region="abdomen and pelvis"),
             util.make_doc("Dnote", "clinical_note", facts=note_facts))


# ---- the protocol file ----------------------------------------------------------------------------------------------------------------

def test_generic_protocol_loads_with_the_four_core_records():
    assert protocol.exists("generic")
    listed = next(p for p in protocol.list_protocols() if p["id"] == "generic")
    assert listed["label"] == "Other cancer (no disease-specific Indian protocol)" and listed["version"] == "0.1"
    assert listed["settings"] == [{"id": "as_recorded", "label": "As recorded by the doctor"}] == protocol.settings("generic")
    p = protocol.get("generic")
    recs = {r["id"]: r for r in protocol.records(p)}
    assert list(recs) == CORE and all(r["tier"] == "a" and not r.get("tiers") for r in recs.values())
    assert recs["histopathology"]["doc_types"] == ["histopathology", "cytology"]
    assert set(recs["staging_imaging"]["doc_types"]) == {"ct", "mri", "pet_ct"} and not recs["staging_imaging"].get("region")  # any one
    assert recs["clinical_history"]["doc_types"] == ["clinical_note", "referral"] and recs["clinical_history"]["required_facts"] == ["ecog"]
    assert recs["board_question"]["required_facts"] == ["clinical_question"] and recs["board_question"]["typable"] is True
    assert "clinical_question" in slots.typable_facts(p) and "ecog" in slots.typable_facts(p)
    cat, types = protocol.facts(), set(protocol.doc_types())
    for r in recs.values():
        assert all(f in cat for f in r["required_facts"]) and set(r.get("doc_types") or r.get("fact_doc_types")) <= types, r["id"]
        assert org.department_id(r["department"]), r["id"]
        assert r["sources"] and r["source"] == r["sources"][0]
        for s in r["sources"]:  # the owner's decision, quoted word for word, instead of a guideline
            assert s["guideline"] == DECISION and s["page"] == "n/a" and s["where"]
            assert s["quote"] == ("Histopathology, staging imaging, a clinical note with performance status, and a typed question for the board; "
                                  "labelled 'No disease-specific Indian protocol'.")
    assert "Not a clinical guideline" in p["note"] and "reviewed by the hospital" in p["note"] and "No disease-specific Indian protocol" in p["note"]
    raw = (config.PROTOCOL_DIR / "generic.json").read_text()
    assert "NCG" not in raw and "NCCN" not in raw and "\u2014" not in raw and "\u2013" not in raw  # no guideline claim, no dashes
    json.loads(raw)
    assert [o["id"] for o in p["optional"]] == ["prior_treatment", "previous_board"]
    assert all(f in cat for f in p["extract_facts"]) and all(f in cat for c in p["core_data"] for f in c["facts"])


def test_case_label():
    assert protocol.case_label({"protocol": "generic", "cancer_name": "  Urinary   bladder "}) == "Urinary bladder (no checklist yet)"
    assert protocol.case_label({"protocol": "generic"}) == "Other cancer (no disease-specific Indian protocol)"
    assert protocol.case_label({"protocol": "breast", "cancer_name": "Breast"}) == "Breast cancer"
    assert protocol.case_label({"protocol": "breast"}, "Given label") == "Given label" and protocol.case_label({}) == ""


# ---- the gate, the requests, the fill-in summary, the summary ------------------------------------------------------------------------

def test_gate_with_nothing_filed_has_four_missing_records(people):
    cid = _case()
    g = rules.evaluate(cid)
    assert g["protocol"] == "generic" and g["setting"] == "as_recorded" and g["setting_label"] == "As recorded by the doctor"
    assert g["passed"] is False and g["total"] == 4 and g["satisfied"] == 0 and g["shown"] == []
    rows = {r["id"]: r for r in g["requirements"]}
    assert list(rows) == CORE and all(r["level"] == 1 and r["status"] != "satisfied" and r["tier_label"] == "Essential" for r in rows.values())
    assert {k: rows[k]["status"] for k in ("histopathology", "staging_imaging", "clinical_history")} == dict.fromkeys(("histopathology", "staging_imaging", "clinical_history"), "missing_record")
    assert rows["board_question"]["level1"]["status"] == "missing_record"
    assert {k: r["department"] for k, r in rows.items()} == {"histopathology": "Pathology", "staging_imaging": "Radiology",
                                                             "clinical_history": "Medical Oncology", "board_question": "Medical Oncology"}  # the owner
    assert all(r["sources"][0]["guideline"] == DECISION and "NCG" not in json.dumps(r) for r in rows.values())
    st = rules.sync_actions(cid, g, by="test")
    acts = {a["requirement"]: a for a in st["actions"]}
    assert set(acts) == set(CORE) and all(a["status"] == rules.SUGGESTED for a in acts.values())  # suggested, never sent by itself
    assert acts["histopathology"]["department_id"] == "pathology" and acts["staging_imaging"]["department_id"] == "radiology"
    assert acts["clinical_history"]["department_id"] == OWNER
    v = slots.build(cid, {"user": "dr.rao", "treating": {OWNER: "member"}})
    assert v["listed"] is True and v["protocol"] == "generic" and v["gate"]["total"] == 4
    lines = {s["id"]: s for s in slots._all_slots(v)}
    assert {f"record:{r}" for r in CORE} <= set(lines) and all(lines[f"record:{r}"]["status"] == "not_found" and lines[f"record:{r}"]["required"] for r in CORE)
    assert lines["fact:clinical_question"]["typable"] is True and lines["fact:ecog"]["typable"] is True
    assert any(b["slot_id"] == "fact:clinical_question" for b in v["blockers"]) and v["ready_allowed"] is False


@pytest.mark.parametrize("imaging", ["ct", "mri", "pet_ct"])
def test_gate_with_the_four_records_passes(people, imaging):
    cid = _case()
    _four_records(cid, imaging)
    g = rules.evaluate(cid)
    assert g["passed"] is False and g["satisfied"] == 3 and util.req(g, "board_question")["level"] == 2  # the question is not recorded yet
    slots.set_value(cid, "fact:clinical_question", "Bladder preservation or cystectomy?", "", "dr.rao")  # typed by the treating doctor, re-checked
    g = store.get_state(cid)["gate"]
    assert g["passed"] is True and g["total"] == g["satisfied"] == 4 and g["readiness"] == 100
    ev = next(e for e in util.req(g, "board_question")["evidence"] if e.get("fact") == "clinical_question")
    assert ev["verification"] == rules.ENTERED and ev["quote"] == ""  # a typed value: never a quote
    st = store.get_state(cid)
    assert all(a["status"] == "completed" for a in st["actions"] if a.get("source") == "pre_authorization")
    v = slots.build(cid, {"user": "dr.rao", "treating": {OWNER: "member"}})
    assert v["left_before_board"] == 0 and v["blockers"] == [] and v["ready_allowed"] is True
    q = next(s for s in slots._all_slots(v) if s["id"] == "fact:clinical_question")
    assert q["status"] == "entered" and q["note"].startswith("entered by Dr Rao")
    kinds = [e["kind"] for e in store.read_audit(cid)]
    assert "typed_value" in kinds and "case_ready" in kinds


def test_question_written_in_the_clinical_note_also_counts(people):
    cid = _case()
    _four_records(cid, question_in_note=True)
    g = rules.evaluate(cid)
    assert g["passed"] is True and g["satisfied"] == 4


def test_a_waived_core_record_and_a_missing_performance_status(people):
    cid = _case()
    util.add(cid, util.make_doc("Dhpe", "cytology"), util.make_doc("Dnote", "referral"))
    rules.set_override(cid, "requirements", "staging_imaging", {"waived": True, "reason": "imaging done elsewhere, report awaited (synthetic)"}, by="dr.rao")
    g = rules.evaluate(cid)
    rows = {r["id"]: r for r in g["requirements"]}
    assert rows["histopathology"]["status"] == "satisfied" and rows["staging_imaging"]["status"] == "waived"
    assert rows["clinical_history"]["status"] == "missing_field" and rows["clinical_history"]["level"] == 2 and "ECOG" in rows["clinical_history"]["problems"][0]
    assert g["total"] == 3 and g["passed"] is False


def test_routes_table_and_summary_work_with_the_generic_protocol(people, monkeypatch):
    rows = [r for r in rules.routes_table() if r["protocol"] == "generic"]
    assert [r["record"] for r in rows] == CORE + ["prior_treatment", "previous_board"]
    assert {r["record"]: r["route_kind"] for r in rows} == {"histopathology": "department", "staging_imaging": "department", "clinical_history": "owner",
                                                            "board_question": "owner", "prior_treatment": "owner", "previous_board": "coordinator"}
    cid = _case()
    _four_records(cid, question_in_note=True)
    rules.sync_actions(cid, rules.evaluate(cid), by="test")
    calls = []

    async def fake_chat(role, msgs, **kw):
        calls.append(role)
        return {"sentences": [], "points_for_review": []}
    monkeypatch.setattr(llm, "chat", fake_chat)
    out = asyncio.run(summary.build(cid))
    assert calls == ["reasoner"] and out["status"] == "ready" and out["gate_passed"] is True
    text = json.dumps(out["sections"])
    assert "Urothelial carcinoma, high grade" in text and "ECOG" in text  # verified values from the records, with their source


# ---- the cancer's name: POST /cases/from-his and POST /cases --------------------------------------------------------------------------

def _create(protocol_id="generic", cancer_name=None, setting="as_recorded", fake=None, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(his_client, "client", lambda: fake or FakeHIS(_two_reports()))

    async def go():
        out = await his_case.create(UHID, protocol_id, setting, "", "", None, "dr.breast", ROLES_DOC, cancer_name=cancer_name)
        if out["job"].get("task"):
            await out["job"]["task"]
        return out
    return asyncio.run(go())


def test_from_his_with_protocol_generic_needs_the_cancer_name(fakes, monkeypatch):
    fake = FakeHIS(_two_reports())
    monkeypatch.setattr(his_client, "client", lambda: fake)
    for bad, why in ((None, "Type the cancer's name"), ("", "Type the cancer's name"), ("   ", "Type the cancer's name"), ("X", "2 to 80 characters"),
                     ("x" * 81, "2 to 80 characters"), (42, "must be text"), ("Bladder\x00", "cannot be shown")):
        with pytest.raises(his_case.HISCaseError) as e:
            _create(cancer_name=bad)
        assert e.value.status == 400 and why in str(e.value), bad
    assert store.list_cases() == [] and fake.calls == []  # refused before the hospital system was asked
    out = _create(cancer_name="  Urinary   bladder ")
    c = store.get_case(out["case"]["case_id"])
    assert c["protocol"] == "generic" and c["setting"] == "as_recorded" and c["cancer_name"] == "Urinary bladder" and c["department"] == "breast_surgery"
    created = next(e for e in store.read_audit(c["case_id"]) if e["kind"] == "case_created")
    assert created["cancer_name"] == "Urinary bladder" and created["protocol"] == "generic"
    g = store.get_state(c["case_id"])["gate"]
    assert g["protocol"] == "generic" and g["total"] == 4 and util.req(g, "histopathology")["status"] == "satisfied"  # the HIS histopathology counts
    assert util.req(g, "staging_imaging")["status"] == "not_final"  # the preliminary CECT is a Level 1 gap


def test_from_his_built_checklist_keeps_an_optional_name_and_generic_cases_differ_by_name(fakes, monkeypatch):
    out = _create("breast", None, "early", monkeypatch=monkeypatch)
    assert "cancer_name" not in store.get_case(out["case"]["case_id"])
    out = _create("breast", "Breast", "early", monkeypatch=monkeypatch)
    assert store.get_case(out["case"]["case_id"])["cancer_name"] == "Breast"
    a = _create("generic", "Urinary bladder", monkeypatch=monkeypatch)["case"]
    b = _create("generic", "Thyroid", monkeypatch=monkeypatch)["case"]
    c = _create("generic", "urinary bladder", monkeypatch=monkeypatch)["case"]
    assert not store.get_case(b["case_id"])["his"].get("same_uhid_case")  # another typed cancer is not the same one
    assert store.get_case(c["case_id"])["his"]["same_uhid_case"] == a["case_id"]  # the same typed cancer: shown, never blocked


def test_routes_accept_store_and_audit_the_cancer_name(nik_app, people, fakes, monkeypatch):
    tc, who = nik_app
    monkeypatch.setattr(his_client, "client", lambda: FakeHIS([]))
    r = tc.post("/api/tb/cases/from-his", json={"identifier": UHID, "protocol": "generic", "setting": "as_recorded"})
    assert r.status_code == 400 and "cancer's name" in r.json()["detail"]
    r = tc.post("/api/tb/cases/from-his", json={"identifier": UHID, "protocol": "generic", "setting": "as_recorded", "cancer_name": "Gallbladder", "case_id": "TB-GEN-H"})
    assert r.status_code == 200, r.text
    assert r.json()["case"]["cancer_name"] == "Gallbladder" and r.json()["case"]["department"] == OWNER
    assert tc.get("/api/tb/cases/TB-GEN-H").json()["case"]["cancer_name"] == "Gallbladder"
    # the manual path (POST /cases)
    r = tc.post("/api/tb/cases", json={"case_id": "TB-GEN-M", "patient": dict(util.PATIENT), "protocol": "generic", "setting": "as_recorded"})
    assert r.status_code == 400 and "cancer's name" in r.json()["detail"] and store.get_case("TB-GEN-M") is None
    r = tc.post("/api/tb/cases", json={"case_id": "TB-GEN-M", "patient": dict(util.PATIENT), "protocol": "generic", "setting": "as_recorded", "cancer_name": "y" * 81})
    assert r.status_code == 400 and store.get_case("TB-GEN-M") is None
    r = tc.post("/api/tb/cases", json={"case_id": "TB-GEN-M", "patient": dict(util.PATIENT), "protocol": "generic", "setting": "as_recorded", "cancer_name": " Soft tissue sarcoma "})
    assert r.status_code == 200, r.text
    c = store.get_case("TB-GEN-M")
    assert c["cancer_name"] == "Soft tissue sarcoma" and c["department"] == OWNER
    assert next(e for e in store.read_audit("TB-GEN-M") if e["kind"] == "case_created")["cancer_name"] == "Soft tissue sarcoma"
    assert tc.get("/api/tb/cases/TB-GEN-M").json()["case"]["cancer_name"] == "Soft tissue sarcoma"
    r = tc.post("/api/tb/cases", json={"case_id": "TB-GEN-B", "patient": dict(util.PATIENT), "protocol": "breast", "setting": "early"})
    assert r.status_code == 200 and "cancer_name" not in store.get_case("TB-GEN-B")  # optional under a built checklist


# ---- GET /case-list ----------------------------------------------------------------------------------------------------------------------

def test_case_list_names_a_generic_case_by_its_cancer(nik_app, people):
    tc, who = nik_app
    _case("TB-GEN-1", "Urinary bladder")
    _case("TB-GEN-2", None)  # listed under the generic rule without a name (the old listing path): the protocol's own label
    c = store.create_case("TB-BR-1", dict(util.PATIENT), "breast", created_by="dr.rao", setting="early"); c["department"] = OWNER; store.save_case(c)
    r = tc.get("/api/tb/case-list")
    assert r.status_code == 200, r.text
    rows = {x["case_id"]: x for x in r.json()["cases"]}
    assert rows["TB-GEN-1"]["protocol_label"] == "Urinary bladder (no checklist yet)" and rows["TB-GEN-1"]["cancer_name"] == "Urinary bladder"
    assert rows["TB-GEN-2"]["protocol_label"] == "Other cancer (no disease-specific Indian protocol)" and rows["TB-GEN-2"]["cancer_name"] == ""
    assert rows["TB-BR-1"]["protocol_label"] == "Breast cancer"
    organs = r.json()["filters"]["organs"]
    assert {"id": "generic", "label": "Other cancer (no disease-specific Indian protocol)"} in organs and sum(1 for o in organs if o["id"] == "generic") == 1
    assert [x["case_id"] for x in tc.get("/api/tb/case-list?q=bladder").json()["cases"]] == ["TB-GEN-1"]
    assert {x["case_id"] for x in tc.get("/api/tb/case-list?organ=generic").json()["cases"]} == {"TB-GEN-1", "TB-GEN-2"}
