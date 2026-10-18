"""V2 item 4.1 ("Done when: scenario outcomes match"): the gate and request expectations of his_mock/scenarios.json agree with the
protocols, the NCG tiers at the Optimal hospital level and the routing map, so the live check (tumour_board/eval/his_scenarios.py)
compares the gate against expectations that can be met. Deterministic: no model, no network, the default organisation in a temporary
data root. The fixture is SYNTHETIC (fake IDs, fictitious hospital); nothing here comes from a real patient."""
import json
from pathlib import Path

import pytest

from tumour_board import org, protocol, rules

REPO = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((REPO / "his_mock" / "scenarios.json").read_text())
PATIENTS = {p["slot"]: p for p in FIXTURE["patients"]}
LEVEL = "optimal"  # the mock hospital is an NCG Optimal centre (scenarios.json hospital.ncg_level)
WHEN = {"first_fetch", "after_refetch", "after_link", "after_referral", "after_outside_upload"}
OPEN = {"suggested_from_gap", "doctor_initiated"}


def _gates():
    return [(s["id"], g) for s in FIXTURE["scenarios"] for g in (s.get("expected") or {}).get("gate") or []]


def _requests():
    return [(s["id"], r) for s in FIXTURE["scenarios"] for r in (s.get("expected") or {}).get("requests") or []]


GATES = _gates()
REQUESTS = _requests()
SUGGESTED = [(sid, r) for sid, r in REQUESTS if r.get("origin") == "suggested_from_gap"]
DOCTOR = [(sid, r) for sid, r in REQUESTS if r.get("origin") == "doctor_initiated"]


def _gid(x):
    sid, g = x
    return f"{sid}:{g['patient']}:{g['protocol']}:{g['when']}"


def _rid(x):
    sid, r = x
    return f"{sid}:{r['patient']}:{r.get('requirement') or r.get('test')}"


def _setting(g):
    """The NCG setting of a gate entry: its own, else the one the same patient's first-fetch entry (or Case File) under that protocol gives."""
    if g.get("ncg_setting"):
        return g["ncg_setting"]
    for _sid, f in GATES:
        if f["patient"] == g["patient"] and f["protocol"] == g["protocol"] and f.get("ncg_setting"):
            return f["ncg_setting"]
    cf = next((c for c in PATIENTS[g["patient"]].get("case_files") or [] if c.get("protocol") == g["protocol"]), None)
    return (cf or {}).get("ncg_setting") or ""


def _record(pid, rid):
    return next((r for r in protocol.records(protocol.get(pid)) if r.get("id") == rid), None)


def _entries_for(r):
    """The gate entries of the request's patient that list its requirement as open: (entry, level)."""
    out = []
    for _sid, g in GATES:
        if g["patient"] != r["patient"]:
            continue
        for lvl in (1, 2):
            if r.get("requirement") in (g.get(f"level{lvl}") or []):
                out.append((g, lvl))
    return out


def test_the_fixture_has_gate_and_request_expectations():
    assert len(GATES) >= 20 and len(SUGGESTED) >= 20 and len(DOCTOR) >= 2
    assert FIXTURE["hospital"]["ncg_level"] == LEVEL


@pytest.mark.parametrize("item", GATES, ids=_gid)
def test_gate_entry_names_records_the_protocol_requires(data_root, item):
    """(a) Every requirement in level1 / level2 is a record of the protocol, required at an Optimal hospital in the entry's NCG setting."""
    _sid, g = item
    assert g["when"] in WHEN, g
    assert protocol.exists(g["protocol"]), g["protocol"]
    assert g["result"] in ("pass", "gaps")
    l1, l2 = g.get("level1") or [], g.get("level2") or []
    assert (g["result"] == "pass") == (not l1 and not l2), "a passing gate lists no gap and a gate with gaps lists at least one"
    assert not set(l1) & set(l2), "a record is open at one level only"
    assert len(set(l1)) == len(l1) and len(set(l2)) == len(l2)
    setting = _setting(g)
    if g.get("ncg_setting"):
        assert setting in {s["id"] for s in protocol.settings(g["protocol"])}, (g["protocol"], setting)
    for rid in l1 + l2:
        rec = _record(g["protocol"], rid)
        assert rec is not None, f"{rid} is not a record of {g['protocol']}"
        if setting:
            tier = protocol.tier_for(rec, setting)
            assert tier != "none", f"{g['protocol']}.{rid} is not applicable in the {setting} setting"
            assert protocol.required(rec, setting, LEVEL), f"{g['protocol']}.{rid} (tier {tier}) is not required at an Optimal hospital in {setting}"


@pytest.mark.parametrize("item", SUGGESTED, ids=_rid)
def test_suggested_request_matches_a_gate_gap_its_level_and_the_routing_map(data_root, item):
    """(a) the requirement is a record of the protocol, (b) the department is the routed one, (c) the level is the gate entry's list."""
    _sid, r = item
    assert r["patient"] in PATIENTS
    entries = _entries_for(r)
    assert entries, f"{r['patient']} {r['requirement']}: no gate entry of this patient lists it as open"
    for g, lvl in entries:
        assert r["level"] == lvl, f"{r['patient']} {r['requirement']}: request level {r['level']}, gate entry ({g['protocol']}, {g['when']}) puts it at level {lvl}"
        prot = protocol.get(g["protocol"])
        rec = _record(g["protocol"], r["requirement"])
        assert rec is not None, f"{r['requirement']} is not a record of {g['protocol']}"
        name, did, kind = rules.routed(prot, rec)
        assert kind != org.COORDINATOR_ID, f"{g['protocol']}.{r['requirement']} goes to the MDT Coordinator, not a department"
        if kind == org.OWNER_ID and org.is_owner_alias(r["department"]):  # a dental evaluation: the owning department's own work from 18 Oct (R02-Q02)
            assert name == org.OWNER_NAME and did is None
            continue
        assert name == r["department"], f"{g['protocol']}.{r['requirement']}: fixture names {r['department']}, the routing map {name}"
        assert org.department_id(r["department"]) == did and did, (r["department"], did)
    acc = r.get("accession")
    assert acc is None or (isinstance(acc, str) and acc.strip() == acc and "/" in acc), acc


@pytest.mark.parametrize("item", DOCTOR, ids=_rid)
def test_doctor_initiated_request_names_an_existing_department_and_no_requirement(data_root, item):
    """(d) A request the doctor starts is not a gate gap: no requirement, no level, a department of the organisation."""
    _sid, r = item
    assert r["patient"] in PATIENTS
    assert r.get("requirement") is None and r.get("level") is None
    did = org.department_id(r["department"])
    assert (did and org.department(did)) or org.is_owner_alias(r["department"]), r["department"]  # a pre-anaesthetic check: the owner's own work from 18 Oct
    if r.get("test"):
        assert r["test"] in FIXTURE["tests"], r["test"]


def test_every_request_has_a_known_origin():
    assert {r.get("origin") for _sid, r in REQUESTS} <= OPEN


def test_the_same_request_is_described_the_same_way_in_every_scenario():
    """every_supporting_department_request repeats the per-scenario requests: they must not disagree."""
    seen = {}
    for sid, r in SUGGESTED:
        key = (r["patient"], r["requirement"])
        val = (r["department"], r.get("accession"), r["level"])
        assert seen.setdefault(key, (sid, val))[1] == val, f"{key}: {seen[key]} vs {sid} {val}"


def test_scenario_patients_exist():
    """(e) Every patient a scenario names, gates or requests is a fixture patient."""
    for s in FIXTURE["scenarios"]:
        for slot in s.get("patients") or []:
            assert slot in PATIENTS, (s["id"], slot)
    for sid, g in GATES:
        assert g["patient"] in PATIENTS, (sid, g["patient"])
    for sid, r in REQUESTS:
        assert r["patient"] in PATIENTS, (sid, r["patient"])


@pytest.mark.parametrize("item", GATES, ids=_gid)
def test_gate_entry_protocol_matches_the_patients_case_files(data_root, item):
    """(e) The protocol (and setting) of a gate entry is one of the patient's Case Files; the referral (Phase 5) moves the patient to
    another protocol, so an after_referral entry names a protocol of its own."""
    _sid, g = item
    p = PATIENTS[g["patient"]]
    cfs = p.get("case_files") or []
    protocols = {c["protocol"] for c in cfs} | ({p["protocol"]} if p.get("protocol") else set())
    if g["when"] == "after_referral":
        assert g["protocol"] not in protocols or len(protocols) > 1
        return
    assert g["protocol"] in protocols, (g["patient"], g["protocol"], protocols)
    cf = next((c for c in cfs if c["protocol"] == g["protocol"]), None)
    if cf and g.get("ncg_setting"):
        assert cf.get("ncg_setting") == g["ncg_setting"], (g["patient"], cf.get("ncg_setting"), g["ncg_setting"])


@pytest.mark.parametrize("item", [x for x in GATES if x[1]["when"] == "first_fetch"], ids=_gid)
def test_first_fetch_entry_agrees_with_the_patients_case_file(data_root, item):
    """The live check creates one Case File per first-fetch entry, owned by the Case File's owner in the fixture: that owner is a
    treating department, and the patient's own first-fetch gaps (case_files[].first_fetch) list the same records at the same levels."""
    _sid, g = item
    cf = next((c for c in PATIENTS[g["patient"]].get("case_files") or [] if c["protocol"] == g["protocol"]), None)
    assert cf is not None, (g["patient"], g["protocol"])
    did = org.department_id(cf.get("owner") or "")
    assert did and org.department_group(did) == "treating", cf.get("owner")
    ff = cf.get("first_fetch") or {}
    assert ff.get("result") == g["result"]
    gaps = sorted((x["requirement"], x["level"]) for x in ff.get("gaps") or [])
    want = sorted([(x, 1) for x in g.get("level1") or []] + [(x, 2) for x in g.get("level2") or []])
    assert gaps == want, (g["patient"], gaps, want)


def test_case_file_gaps_name_the_routed_department_and_the_requests_accession(data_root):
    """The patients' own first-fetch gaps route like the requests: the routing map's department, and the same accession No. as the
    scenario's request for that record."""
    reqs = {(r["patient"], r["requirement"]): r for _sid, r in SUGGESTED}
    for slot, p in PATIENTS.items():
        for cf in p.get("case_files") or []:
            prot = protocol.get(cf["protocol"])
            for gap in (cf.get("first_fetch") or {}).get("gaps") or []:
                rec = _record(cf["protocol"], gap["requirement"])
                assert rec is not None, (slot, gap["requirement"])
                assert rules.routed(prot, rec)[0] == gap["department"] or (rules.routed(prot, rec)[2] == org.OWNER_ID and org.is_owner_alias(gap["department"])), \
                    (slot, gap["requirement"], gap["department"], rules.routed(prot, rec)[0])
                r = reqs.get((slot, gap["requirement"]))
                if r:
                    assert r.get("accession") == gap.get("accession") and r["department"] == gap["department"], (slot, gap, r)
