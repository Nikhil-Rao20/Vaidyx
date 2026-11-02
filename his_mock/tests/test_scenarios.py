"""V2-0.3: the scenario fixtures are complete and self-consistent (his_mock/scenarios.json)."""
import copy
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from his_mock import scenarios as sc

PROTOCOL_DIR = Path(__file__).resolve().parents[2] / "tumour_board" / "protocols"  # read as files only, never imported


@pytest.fixture(scope="module")
def data():
    return sc.load()


def test_validate_reports_no_problems(data):
    assert sc.validate(data) == []


def test_top_level_keys_and_synthetic_note(data):
    for k in sc.TOP_KEYS:
        assert k in data
    assert data["note"].startswith("SYNTHETIC only")


def test_eleven_plan_scenarios_present(data):
    ids = sc.by_id(data)
    assert len(sc.PLAN_SCENARIOS) == 11
    for sid in sc.PLAN_SCENARIOS:
        assert sid in ids, sid
        assert ids[sid]["plan_1_1"] is True
    assert sum(1 for s in data["scenarios"] if s["plan_1_1"]) == 11


def test_checklist_extras_present(data):
    ids = sc.by_id(data)
    for sid in sc.CHECKLIST_SCENARIOS:
        assert sid in ids, sid


def test_every_checklist_tag_covered(data):
    cov = sc.coverage(data)
    assert cov, "checklist is empty"
    assert [t for t, ids in cov.items() if not ids] == []
    groups = set(data["checklist"])
    assert groups == {"identity", "encounters", "report_lifecycle", "values", "departments", "board", "outside_reports"}


def test_every_supporting_department_receives_a_request(data):
    supporting = {d["name"] for d in data["departments"] if d["group"] == "supporting"}
    got = sc.requests_by_department(data)
    assert supporting - set(got) == set()
    assert len(supporting) == 8


def test_treating_department_receives_a_procedure_request(data):
    reqs = sc.by_id(data)["treating_department_procedure_request"]["expected"]["requests"]
    assert any(r["department"] == "Pulmonology" and r["requirement"] == "bronchoscopy" and r["accession"] is None for r in reqs)


def test_each_board_head_absent_somewhere(data):
    absent = sc.absent_heads(data)
    assert set(absent) == set(sc.BOARD_HEADS)
    assert [h for h, ids in absent.items() if not ids] == []


def test_pmjay_on_and_off_and_surgeon_outside_list(data):
    ids = sc.by_id(data)
    hosp = [ids[s]["setup"]["hospital"]["pmjay_empanelled"] for s in ids if s.startswith("board_")]
    assert True in hosp and False in hosp
    s = ids["board_surgeon_outside_surgical_oncology_list"]
    assert s["setup"]["surgeon_present"]["department"] not in data["hospital"]["surgical_oncology_list"]
    assert s["expected"]["board"]["check_pmjay_requirement"] is True


def test_patient_count_and_protocol_spread(data):
    pts = data["patients"]
    assert sc.MIN_PATIENTS <= len(pts) <= sc.MAX_PATIENTS and len(pts) == 23
    per = Counter(cf["protocol"] for p in pts for cf in p["case_files"])
    for proto in sc.PROTOCOLS:
        assert per[proto] >= 2, (proto, per[proto])
    for proto in sc.NEW_PROTOCOLS:  # night-v3 item 2.11: one patient each
        assert per[proto] == 1, (proto, per[proto])
    assert set(per) <= set(sc.ALL_PROTOCOLS)


def test_protocol_ids_exist_in_vaidyx_tb():
    if not PROTOCOL_DIR.is_dir():
        pytest.skip("tumour_board protocols not present")
    for proto in sc.ALL_PROTOCOLS:
        assert json.loads((PROTOCOL_DIR / f"{proto}.json").read_text())["id"] == proto


def test_ids_unique(data):
    for items in ([p["slot"] for p in data["patients"]], [s["id"] for s in data["scenarios"]],
                  [r["id"] for p in data["patients"] for r in p["records"]],
                  [e["number"] for p in data["patients"] for e in p["encounters"]],
                  [row["tag"] for rows in data["checklist"].values() for row in rows],
                  [d["name"] for d in data["departments"]], [d["code"] for d in data["departments"]]):
        assert len(items) == len(set(items))


def test_identifiers_match_patterns(data):
    pat = {k: re.compile(v["regex"]) for k, v in data["identifier_patterns"].items()}
    for p in data["patients"]:
        assert pat["uhid"].match(p["uhid"]) and p["uhid"].startswith("VXH/26/")
        if p.get("abha"):
            assert pat["abha_number"].match(p["abha"]["number"]) and p["abha"]["address"].endswith("@sbx")
        for e in p["encounters"]:
            assert pat["op_no" if e["kind"] == "OP" else "ip_no"].match(e["number"])
            assert pat["reg_no"].match(e["consultant"]["reg_no"])
        for r in p["records"]:
            if r.get("accession"):
                assert pat["accession"].match(r["accession"])
            if r.get("signature"):
                assert r["signature"]["ca"] == "Vaidyx Demo CA"
                assert pat["reg_no"].match(r["signature"]["signer"]["reg_no"])
    # both kinds of registration problem exist, and ABHA is present for some and absent for others
    assert any(p.get("temporary_uhid") for p in data["patients"])
    assert any(p.get("duplicate_uhid") for p in data["patients"])
    assert {bool(p.get("abha")) for p in data["patients"]} == {True, False}
    assert {bool(p.get("pmjay_id")) for p in data["patients"]} == {True, False}


def test_every_patient_marked_synthetic(data):
    for p in data["patients"]:
        assert p["marker"] == "SYNTHETIC" and "SYNTHETIC" in p["name"]


def test_two_patients_share_a_common_name(data):
    names = Counter(p["name"] for p in data["patients"])
    pair = [n for n, c in names.items() if c == 2]
    assert pair
    two = [p for p in data["patients"] if p["name"] == pair[0]]
    assert two[0]["uhid"] != two[1]["uhid"] and two[0]["age"] != two[1]["age"]


def test_no_real_looking_aadhaar(data):
    hits = [(w, s) for w, s in sc.strings(data) if sc.AADHAAR_LIKE.search(s)]
    assert hits == []
    masked = [w for w, s in sc.strings(data) if s == sc.MASKED_AADHAAR and w.startswith("$.patients")]
    assert len(masked) == 1 and masked[0].endswith(".printed_identifiers.aadhaar")


def test_dates_displayed_dd_mm_yyyy(data):
    dates = list(sc.date_values(data))
    assert len(dates) > 100
    for where, d in dates:
        assert sc.DISPLAY_DATE.match(d["display"]), where


def test_report_lifecycle_spread(data):
    recs = [r for p in data["patients"] for r in p["records"] if r["source"] == "his"]
    order = {r["order_status"] for r in recs}
    report = {r["report_status"] for r in recs}
    assert {"never_ordered", "ordered", "scheduled", "sample_collected", "completed", "cancelled"} <= order
    assert {"none", "preliminary", "final", "amended", "cancelled"} <= report
    assert any(r["report_status"] == "final" and not r["signed"] for r in recs)  # unsigned final


def test_indian_units_present(data):
    text = " ".join(s for _, s in sc.strings([p["records"] for p in data["patients"]]))
    for unit in ("gm%", "lakhs/cumm", "/cumm", "mg/dL", "ng/mL"):
        assert unit in text, unit


# ---------------------------------------------------------------- negative tests: validate() catches tampering
def _problems_after(data, change):
    d = copy.deepcopy(data)
    change(d)
    return sc.validate(d)


def test_validate_catches_aadhaar_like_number(data):
    def change(d):
        d["patients"][0]["note"] = "ID 4821 7730 1956"
    assert any("Aadhaar-like" in p for p in _problems_after(data, change))


def test_validate_catches_plain_twelve_digits(data):
    def change(d):
        d["patients"][1]["records"][0]["values"]["ref"] = "482177301956"
    assert any("Aadhaar-like" in p for p in _problems_after(data, change))


def test_validate_catches_missing_marker_bad_uhid_and_bad_date(data):
    def change(d):
        p = d["patients"][2]
        p["marker"] = "real"
        p["uhid"] = "12345"
        p["encounters"][0]["date"] = {"display": "2026-09-01", "value": "2026-09-01"}
    probs = _problems_after(data, change)
    assert any("SYNTHETIC" in p for p in probs)
    assert any("uhid" in p for p in probs)
    assert any("DD/MM/YYYY" in p for p in probs)


def test_validate_catches_unknown_department_and_patient(data):
    def change(d):
        d["patients"][0]["records"][1]["producing_department"] = "Laboratory Medicine"
        d["scenarios"][0]["patients"].append("P99")
    probs = _problems_after(data, change)
    assert any("Laboratory Medicine" in p for p in probs)
    assert any("P99" in p for p in probs)


def test_validate_catches_missing_plan_scenario_and_uncovered_tag(data):
    def change(d):
        d["scenarios"] = [s for s in d["scenarios"] if s["id"] != "two_primaries"]
    probs = _problems_after(data, change)
    assert any("scenario missing: two_primaries" in p for p in probs)
    assert any("not covered" in p and "two_primaries" in p for p in probs)


def test_validate_catches_too_few_patients(data):
    def change(d):
        d["patients"] = d["patients"][:14]
    assert any("14 patients" in p for p in _problems_after(data, change))


def test_validate_catches_signed_preliminary(data):
    def change(d):
        r = next(r for p in d["patients"] for r in p["records"] if r["report_status"] == "preliminary")
        r["signed"] = True
    assert any("preliminary report cannot be signed" in p for p in _problems_after(data, change))


# ---------------------------------------------------------------- cross-check against the Vaidyx-TB protocols (read-only)
def _protocol(proto):
    p = json.loads((PROTOCOL_DIR / f"{proto}.json").read_text())
    return p, {r["id"]: r for r in (p.get("records") or []) + (p.get("optional") or [])}


def _required(rec, setting, level):
    tiers = rec.get("tiers") or {}
    strict = {"a": 3, "b": 2, "c": 1, "none": 0}
    tier = tiers[setting] if setting in tiers else (max(tiers.values(), key=lambda t: strict[t]) if tiers else rec.get("tier", "a"))
    return tier == "a" or (tier == "b" and level == "optimal")


def _expected_gaps(patient, cf, level):
    """The first-fetch gaps the gate rules give, simplified: only records filed under the main UHID, outside uploads not yet
    added; a facts-only record needs a final, signed carrier document (Level 1), then its values (Level 2)."""
    proto, recs = _protocol(cf["protocol"])
    ready = [r for r in patient["records"] if r["source"] == "his" and r.get("registration", patient["uhid"]) == patient["uhid"]
             and r["report_status"] in ("preliminary", "final", "amended")]
    finals = [r for r in ready if r["report_status"] in ("final", "amended") and r["signed"]]
    out = set()
    for rec in proto["records"]:
        if not _required(rec, cf["ncg_setting"], level):
            continue
        if rec.get("applies_if_doc_type_present") and not any(r["type"] == rec["applies_if_doc_type_present"] for r in ready):
            continue
        mapped = lambda rs: [r for r in rs if rec["id"] in (r.get("serves") or {}).get(cf["protocol"], [])]
        if rec.get("facts_only"):
            if not [r for r in finals if r["type"] in (rec.get("fact_doc_types") or [])]:
                out.add((rec["id"], 1))
                continue
        elif not mapped(ready) or not mapped(finals):
            out.add((rec["id"], 1))
            continue
        have = set().union(*[set(r["values"]) for r in mapped(finals)]) if mapped(finals) else set()
        if set(rec.get("required_facts") or []) - have:
            out.add((rec["id"], 2))
    return out


def test_first_fetch_gaps_agree_with_the_protocols(data):
    if not PROTOCOL_DIR.is_dir():
        pytest.skip("tumour_board protocols not present")
    level = data["hospital"]["ncg_level"]
    for p in data["patients"]:
        for cf in p["case_files"]:
            if cf.get("created_by") == "referral":
                continue  # the colorectal Case File after the referral: same records, checked below
            declared = {(g["requirement"], g["level"]) for g in cf["first_fetch"]["gaps"]}
            assert declared == _expected_gaps(p, cf, level), (p["slot"], cf["protocol"])
    p14 = sc.patients_by_slot(data)["P14"]
    cf = sc.first_fetch(p14, "colorectal_rectum")
    assert {(g["requirement"], g["level"]) for g in cf["first_fetch"]["gaps"]} == _expected_gaps(p14, cf, level)


def test_records_serve_known_protocol_records_and_name_known_facts(data):
    if not PROTOCOL_DIR.is_dir():
        pytest.skip("tumour_board protocols not present")
    for p in data["patients"]:
        for r in p["records"]:
            for proto, ids in (r.get("serves") or {}).items():
                _, recs = _protocol(proto)
                assert set(ids) <= set(recs), (r["id"], proto, ids)
            for k in r["values"]:
                assert re.match(r"^[a-z][a-z0-9_]*$", k), (r["id"], k)


def test_document_types_match_vaidyx_tb_catalogue(data):
    f = PROTOCOL_DIR / "doc_type_keywords.json"
    if not f.is_file():
        pytest.skip("tumour_board protocols not present")
    assert set(data["document_types"]) == set(json.loads(f.read_text())["types"])


def test_loader_helpers(data):
    s = sc.by_id(data)["two_primaries"]
    assert [p["slot"] for p in sc.patients_for(s, data)] == s["patients"]
    assert [p["slot"] for p in sc.patients_for("two_primaries", data)] == s["patients"]
    assert len(sc.patients_for("two_primaries", data)[0]["case_files"]) == 2


def test_first_fetch_gap_departments_follow_the_protocol_routes(data):
    """Review (Phase 2) minor 9: the department each declared gap names is the department the protocol routes that record to (V2 item 2.4):
    the record's department, or the Case File's owner for a record routed to the owner."""
    if not PROTOCOL_DIR.is_dir():
        pytest.skip("tumour_board protocols not present")
    for p in data["patients"]:
        for cf in p["case_files"]:
            _, recs = _protocol(cf["protocol"])
            for g in (cf.get("first_fetch") or {}).get("gaps", []):
                rec = recs[g["requirement"]]
                want = cf.get("owner") if rec.get("route") == "owner" else rec["department"]
                assert g["department"] == want, (p["slot"], cf["protocol"], g["requirement"], g["department"], want)
