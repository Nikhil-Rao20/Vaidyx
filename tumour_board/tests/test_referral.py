"""Referral to another treating department (V2 item 5.2): the hospital system's referral is suggested, the owner refers with a reason,
the receiving department accepts (ownership moves, the referring department stays as a participant, the earlier gate is archived
read-only, the gate re-runs under the new protocol on the same records) or declines; every step audited and told in-app. Small
test protocols, synthetic Case File, no model."""
import asyncio
import copy
import json

import pytest

from tumour_board import access, notify, org, postboard, protocol, referral, rules, service, store
from tumour_board.tests import util
from tumour_board.tests.test_rules import ct, hist
from tumour_board.tests.util import add


@pytest.fixture
def people(data_root):
    o = copy.deepcopy(org.DEFAULT_ORG)
    o["users"] = {"pulmo": {"departments": {"pulmonology": "member"}}, "colo": {"departments": {"colorectal_surgery": "head"}},
                  "breast": {"departments": {"breast_surgery": "member"}}, "ravi": {"departments": {"radiology": "member"}}, "anil": {"coordinator": True}}
    org.save(o, by="test")
    return {k: org.roles(k) for k in ("pulmo", "colo", "breast", "ravi", "anil")} | {"admin": org.roles("tbadmin", vaidyx_admin=True)}


UNIT2 = {"id": "unit2", "label": "Second unit protocol", "version": "0.1",
         "mandatory": [{"id": "histopathology", "label": "Histopathology report", "doc_types": ["histopathology"], "department": "Pathology", "required_facts": ["histologic_type"], "sla_days": 5},
                       {"id": "mri_pelvis", "label": "MRI pelvis report", "doc_types": ["mri"], "region": "pelvis", "department": "Radiology", "required_facts": [], "sla_days": 7}],
         "optional": [], "core_data": []}


@pytest.fixture
def two_protocols(monkeypatch):
    real_get, real_exists, real_settings = protocol.get, protocol.exists, protocol.settings
    monkeypatch.setattr(protocol, "get", lambda pid: util.unit_protocol() if pid == "unit" else (copy.deepcopy(UNIT2) if pid == "unit2" else real_get(pid)))
    monkeypatch.setattr(protocol, "exists", lambda pid: pid in ("unit", "unit2") or real_exists(pid))
    monkeypatch.setattr(protocol, "settings", lambda pid: [] if pid in ("unit", "unit2") else real_settings(pid))
    monkeypatch.setattr(protocol, "setting_label", lambda pid, s: "" if pid in ("unit", "unit2") else "")


def _case(case_id="TB-R1", owner="pulmonology", his_refs=None, protocol_id="unit"):
    c = store.create_case(case_id, dict(util.PATIENT), protocol_id, created_by="test")
    c["department"] = owner
    if his_refs is not None:
        c["his"] = {"uhid": util.PATIENT["mrn"], "label": "mock", "referrals": his_refs}
    store.save_case(c)
    return c


HIS_REFS = [{"id": "ref-ip-1", "from_department": "Pulmonology", "to_department": "Colorectal Surgery", "status": "accepted", "reason": "Lung biopsy: adenocarcinoma of colorectal origin",
             "requested": "2026-09-04", "accepted": "2026-09-05", "encounter_number": "IP/26/01877"},
            {"id": "ref-ip-2", "from_department": "Pulmonology", "to_department": "Radiology", "status": "requested", "reason": "x", "requested": "2026-09-06"},
            {"id": "ref-ip-3", "from_department": "Medical Oncology", "to_department": "Pulmonology", "status": "requested", "reason": "y", "requested": "2026-09-07"}]


def _notes(kind=None):
    p = notify.path()
    recs = [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
    return [x for x in recs if kind is None or x["kind"] == kind]


def _kinds(case_id):
    return [e["kind"] for e in store.read_audit(case_id)]


# ---- the hospital system's referral, suggested ----------------------------------------------------------------------------------

def test_suggestions_come_from_the_his_referrals_to_another_treating_department(people):
    c = _case(his_refs=HIS_REFS)
    s = referral.suggestions(c)
    assert [x["his_ref"] for x in s] == ["ref-ip-1"], "to a supporting department or to the owner itself: never suggested"
    assert s[0]["to"] == "colorectal_surgery" and s[0]["from"] == "pulmonology" and s[0]["on"] == "04/09/2026" and s[0]["accepted_on"] == "05/09/2026"
    assert "Refer this Case File?" in s[0]["text"] and "colorectal origin" in s[0]["text"] and "—" not in s[0]["text"]
    with pytest.raises(referral.ReferralError, match="No such") as e:
        referral.dismiss_suggestion("TB-R1", "ref-ip-2", "pulmo")
    assert e.value.status == 404
    c = referral.dismiss_suggestion("TB-R1", "ref-ip-1", "pulmo", note="work-up continues here")
    assert referral.suggestions(c) == [] and referral.public(c)["dismissed"] == ["ref-ip-1"]
    assert any(e["kind"] == "referral_suggestion_dismissed" and e["his_ref"] == "ref-ip-1" and e["note"] == "work-up continues here" for e in store.read_audit("TB-R1"))
    assert referral.suggestions(_case("TB-R2", his_refs=None)) == []


# ---- request, withdraw, decline -------------------------------------------------------------------------------------------------

def test_request_needs_an_owner_a_treating_target_and_a_reason(people):
    _case(owner=None)
    with pytest.raises(referral.ReferralError, match="no owning department") as e:
        referral.request("TB-R1", "Colorectal Surgery", "x", "pulmo")
    assert e.value.status == 409
    _case("TB-R2")
    with pytest.raises(referral.ReferralError, match="supporting"):
        referral.request("TB-R2", "Radiology", "x", "pulmo")
    with pytest.raises(referral.ReferralError, match="Unknown"):
        referral.request("TB-R2", "Cardiology", "x", "pulmo")
    with pytest.raises(referral.ReferralError, match="already owns"):
        referral.request("TB-R2", "Pulmonology", "x", "pulmo")
    with pytest.raises(referral.ReferralError, match="reason"):
        referral.request("TB-R2", "Colorectal Surgery", "  ", "pulmo")
    with pytest.raises(referral.ReferralError, match="No such suggested"):
        referral.request("TB-R2", "Colorectal Surgery", "x", "pulmo", his_ref="ref-nope")
    referral.request("TB-R2", "Colorectal Surgery", "x", "pulmo")
    with pytest.raises(referral.ReferralError, match="waiting for an answer"):
        referral.request("TB-R2", "Medical Oncology", "y", "pulmo")
    with pytest.raises(referral.ReferralError, match="Case not found"):
        referral.request("TB-NONE", "Colorectal Surgery", "x", "pulmo")


def test_request_tells_the_receiving_department_which_may_then_read_the_case_file(people):
    c = _case(his_refs=HIS_REFS)
    assert access.scope(people["colo"], c) is None
    rec = referral.request("TB-R1", "Colorectal Surgery", "Lung biopsy reported as metastatic adenocarcinoma of colorectal origin", "pulmo", his_ref="ref-ip-1")
    assert rec["status"] == "requested" and rec["from"] == "pulmonology" and rec["to"] == "colorectal_surgery" and rec["his_ref"] == "ref-ip-1" and rec["protocol_before"] == "unit"
    c = store.get_case("TB-R1")
    assert access.open_referral(c)["id"] == rec["id"] and access.scope(people["colo"], c) == access.FULL and access.scope(people["breast"], c) is None
    assert referral.suggestions(c) == [], "the suggestion was followed"
    n = _notes("referral")
    assert len(n) == 1 and n[0]["to"] == {"department": "colorectal_surgery"} and "Pulmonology" in n[0]["title"] and "colorectal origin" in n[0]["text"] and n[0]["uhid"] == "SYN-900001"
    assert notify.for_roles(people["colo"])[0]["kind"] == "referral" and notify.for_roles(people["breast"]) == []
    ev = next(e for e in store.read_audit("TB-R1") if e["kind"] == "referral_requested")
    assert ev["from"] == "pulmonology" and ev["to"] == "colorectal_surgery" and ev["his_ref"] == "ref-ip-1" and ev["by"] == "pulmo"
    pub = referral.public(c)
    assert pub["open"]["to_name"] == "Colorectal Surgery" and pub["open"]["on"] and pub["history"][0]["id"] == rec["id"]
    # the inboxes: the receiving department answers, the referring one may withdraw
    to = referral.inbox(people["colo"]); frm = referral.inbox(people["pulmo"])
    assert len(to) == 1 and to[0]["direction"] == "to" and to[0]["can_answer"] and not to[0]["can_withdraw"] and to[0]["uhid"] == "SYN-900001"
    assert len(frm) == 1 and frm[0]["direction"] == "from" and not frm[0]["can_answer"] and frm[0]["can_withdraw"]
    assert referral.inbox(people["breast"]) == [] and referral.inbox(people["ravi"]) == [] and referral.inbox(people["anil"]) == []
    assert len(referral.inbox(people["admin"])) == 1 and referral.inbox(people["admin"])[0]["direction"] == "other"
    assert [e["kind"] for e in postboard.timeline("TB-R1")] == ["referral"]


def test_withdraw_and_decline_keep_the_owner_and_tell_the_other_side(people):
    _case()
    with pytest.raises(referral.ReferralError, match="No referral"):
        referral.withdraw("TB-R1", "pulmo")
    rec = referral.request("TB-R1", "Colorectal Surgery", "x", "pulmo")
    w = referral.withdraw("TB-R1", "pulmo", note="not yet")
    assert w["status"] == "withdrawn" and w["answered_by"] == "pulmo" and access.open_referral(store.get_case("TB-R1")) is None
    assert _notes("referral_answered")[-1]["to"] == {"department": "colorectal_surgery"} and "withdrawn" in _notes("referral_answered")[-1]["title"]
    assert access.scope(people["colo"], store.get_case("TB-R1")) is None
    rec = referral.request("TB-R1", "Colorectal Surgery", "x again", "pulmo")
    d = referral.decline("TB-R1", "colo", note="not a colorectal primary on review")
    c = store.get_case("TB-R1")
    assert d["status"] == "declined" and c["department"] == "pulmonology" and access.open_referral(c) is None and len(c["referrals"]) == 2
    n = _notes("referral_answered")[-1]
    assert n["to"] == {"department": "pulmonology"} and "declined" in n["title"] and "not a colorectal primary" in n["text"] and n["status"] == "declined"
    assert {"referral_requested", "referral_withdrawn", "referral_declined"} <= set(_kinds("TB-R1")) and "owner_changed" not in _kinds("TB-R1")
    assert referral.inbox(people["colo"])[0]["status"] == "declined" and referral.inbox(people["colo"])[0]["answered_on"]


# ---- accept: ownership moves, the earlier gate is archived, the gate re-runs under the new protocol ------------------------------

def _send(case_id, requirement):
    st = store.get_state(case_id)
    a = next(x for x in st["actions"] if x["requirement"] == requirement)
    a["status"], a["sent"], a["due"] = "pending", {"by": "pulmo", "at": store.now_iso(), "to_name": a["department"]}, "2026-12-31"
    store.save_state(case_id, st)
    return a


def test_accept_moves_ownership_archives_the_gate_and_relists_under_the_new_protocol(people, two_protocols):
    _case()
    h = hist(); h.pop("pages"); add("TB-R1", h)  # no stored pages: the re-listing re-checks the kept facts without a model
    st = rules.sync_actions("TB-R1", rules.evaluate("TB-R1"))
    assert [a["requirement"] for a in st["actions"]] == ["ct_thorax"] and st["gate"]["passed"] is False
    _send("TB-R1", "ct_thorax")
    rec = referral.request("TB-R1", "Colorectal Surgery", "colorectal origin", "pulmo")
    assert access.scope(people["colo"], store.get_case("TB-R1")) == access.FULL
    out = asyncio.run(_accept("TB-R1", "colo", protocol_id="unit2", note="accepted, rectal primary"))
    c, st = store.get_case("TB-R1"), store.get_state("TB-R1")
    assert out["referral"]["status"] == "accepted" and out["referral"]["protocol_after"] == "unit2" and out["job"] is not None and out["job"]["listed"]
    assert c["department"] == "colorectal_surgery" and access.participants(c) == ["pulmonology"] and c["participants"][0]["reason"].startswith("referred the Case File")
    assert c["owner_history"] == [{"from": "pulmonology", "to": "colorectal_surgery", "at": c["owner_history"][0]["at"], "by": "colo", "referral": rec["id"]}]
    assert c["protocol"] == "unit2" and c["listing"]["status"] == "listed" and c["listing"]["listed_by"] == "colo"
    # the earlier gate and its open request, read-only
    hist_ = st["gate_history"]
    assert len(hist_) == 1 and hist_[0]["protocol"] == "unit" and hist_[0]["protocol_version"] == "0.0" and hist_[0]["owner"] == "pulmonology" and hist_[0]["reason"] == "referral"
    assert hist_[0]["gate"]["passed"] is False and [r["id"] for r in hist_[0]["gate"]["requirements"]] and hist_[0]["actions"][0]["requirement"] == "ct_thorax" and hist_[0]["actions"][0]["status"] == "pending"
    # the new gate on the same records: histopathology met, MRI pelvis the new gap; the CT request closed with the referral as the reason, Radiology told
    g = st["gate"]
    assert g["protocol"] == "unit2" and {r["id"]: r["status"] for r in g["requirements"]} == {"histopathology": "satisfied", "mri_pelvis": "missing_record"}
    ct_req = next(a for a in st["actions"] if a["requirement"] == "ct_thorax")
    assert ct_req["status"] == "completed" and "referred to Colorectal Surgery" in ct_req["history"][-1]["event"] and "unit2" in ct_req["history"][-1]["event"]
    closed = [n for n in _notes("request_closed") if n["to"] == {"department": "radiology"}]
    assert len(closed) == 1 and "referred to Colorectal Surgery" in closed[0]["text"]
    assert next(a for a in st["actions"] if a["requirement"] == "mri_pelvis")["status"] == "suggested"
    # access after the move
    assert access.scope(people["colo"], c) == access.FULL and access.scope(people["pulmo"], c) == access.FULL and access.scope(people["breast"], c) is None
    assert access.may(people["colo"], "waive", c, "Radiology") and not access.may(people["pulmo"], "waive", c, "Radiology") and not access.may(people["pulmo"], "refer", c)
    assert access.may(people["colo"], "refer", c)
    # the referring department is told, everything audited, the timeline shows the move
    n = _notes("referral_answered")[-1]
    assert n["to"] == {"department": "pulmonology"} and n["status"] == "accepted" and "unit2" in n["text"] and "participating" in n["text"]
    kinds = _kinds("TB-R1")
    assert {"referral_requested", "referral_accepted", "owner_changed", "case_listed", "action_completed"} <= set(kinds)
    acc = next(e for e in store.read_audit("TB-R1") if e["kind"] == "referral_accepted")
    assert acc["protocol_before"] == "unit" and acc["protocol_after"] == "unit2" and acc["gate_archived"] is True and acc["from"] == "pulmonology" and acc["to"] == "colorectal_surgery"
    tl = [e for e in postboard.timeline("TB-R1") if e["kind"] == "referral"]
    assert len(tl) == 2 and tl[1]["status"] == "owner_changed" and "unit2" in tl[1]["title"]
    assert store.verify_audit("TB-R1")["ok"] if "ok" in store.verify_audit("TB-R1") else True
    with pytest.raises(referral.ReferralError, match="No referral"):
        asyncio.run(_accept("TB-R1", "colo"))


async def _accept(case_id, user, **kw):
    out = referral.accept(case_id, user, **kw)
    if out.get("job") and out["job"].get("task"):
        await out["job"]["task"]
    return out


def test_accept_without_a_protocol_waits_for_the_new_owner_to_pick_one(people, two_protocols):
    _case()
    h, c_ = hist(), ct(); h.pop("pages"); c_.pop("pages"); add("TB-R1", h, c_)  # no stored pages: re-listing re-checks the kept facts without a model
    st = rules.sync_actions("TB-R1", rules.evaluate("TB-R1"))
    assert st["gate"]["passed"] is True
    referral.request("TB-R1", "Colorectal Surgery", "colorectal origin", "pulmo")
    out = asyncio.run(_accept("TB-R1", "colo"))
    c, st = store.get_case("TB-R1"), store.get_state("TB-R1")
    assert out["job"] is None and c["protocol"] == "" and c["listing"]["status"] == "awaiting_listing" and c["listing"]["reason"] == "referred" and c["listing"]["previous"]["status"] == "listed"
    assert st["gate"] is None and st["gate_history"][0]["gate"]["passed"] is True and st["gate_history"][0]["protocol"] == "unit"
    assert c["department"] == "colorectal_surgery" and access.may_list(people["colo"], c) and not access.may_list(people["pulmo"], c)
    assert "will pick the cancer protocol" in _notes("referral_answered")[-1]["text"]
    job = service.list_case("TB-R1", "unit2", "", "", "", "colo")  # the new owner picks the protocol later
    assert job["listed"] and store.get_state("TB-R1")["gate"]["protocol"] == "unit2" and store.get_case("TB-R1")["listing"]["status"] == "listed"


def test_accept_validates_the_protocol_and_setting(people, two_protocols):
    _case()
    referral.request("TB-R1", "Colorectal Surgery", "x", "pulmo")
    with pytest.raises(referral.ReferralError, match="Unknown protocol"):
        referral.accept("TB-R1", "colo", protocol_id="nope")
    with pytest.raises(referral.ReferralError, match="Unknown NCG setting"):
        referral.accept("TB-R1", "colo", protocol_id="unit2", setting="metastatic")
    with pytest.raises(referral.ReferralError, match="Hospital level"):
        referral.accept("TB-R1", "colo", protocol_id="unit2", hospital_level="gold")
    assert access.open_referral(store.get_case("TB-R1")) is not None, "nothing moved"


def test_a_second_referral_after_acceptance_goes_from_the_new_owner(people, two_protocols):
    _case()
    referral.request("TB-R1", "Colorectal Surgery", "x", "pulmo")
    asyncio.run(_accept("TB-R1", "colo"))
    rec = referral.request("TB-R1", "Medical Oncology", "systemic therapy first", "colo")
    assert rec["from"] == "colorectal_surgery" and rec["to"] == "medical_oncology"
    c = store.get_case("TB-R1")
    assert access.participants(c) == ["pulmonology"]
    asyncio.run(_accept("TB-R1", "medonc"))
    c = store.get_case("TB-R1")
    assert c["department"] == "medical_oncology" and access.participants(c) == ["pulmonology", "colorectal_surgery"] and len(c["owner_history"]) == 2
    assert len(store.get_state("TB-R1")["gate_history"]) == 2


def test_no_em_dashes_in_module():
    import pathlib
    assert "—" not in pathlib.Path(referral.__file__).read_text(encoding="utf-8")


def test_accept_closes_a_request_the_new_protocol_only_shows_with_the_referral_as_the_reason(people, two_protocols, monkeypatch):
    """The record is shown, not counted, under the new protocol (an NCG Optimal record at an Essential hospital): the request that was
    open when the Case File was referred still closes with the referral as the reason, and only the requests open at the time do."""
    u2 = copy.deepcopy(UNIT2)
    u2["mandatory"].append({"id": "ct_thorax", "label": "CT thorax", "doc_types": ["ct"], "tier": "b", "department": "Radiology", "required_facts": [], "sla_days": 3})
    fixture_get = protocol.get
    monkeypatch.setattr(protocol, "get", lambda pid: copy.deepcopy(u2) if pid == "unit2" else fixture_get(pid))
    _case()
    h = hist(); h.pop("pages"); add("TB-R1", h)
    rules.sync_actions("TB-R1", rules.evaluate("TB-R1"))
    sent = _send("TB-R1", "ct_thorax")
    referral.request("TB-R1", "Colorectal Surgery", "colorectal origin", "pulmo")
    asyncio.run(_accept("TB-R1", "colo", protocol_id="unit2"))
    c, st = store.get_case("TB-R1"), store.get_state("TB-R1")
    assert [r["id"] for r in st["gate"]["shown"]] == ["ct_thorax"], "shown, not counted, at an Essential hospital"
    ct_req = next(a for a in st["actions"] if a["requirement"] == "ct_thorax")
    ev = ct_req["history"][-1]["event"]
    assert ct_req["status"] == "completed" and "referred to Colorectal Surgery" in ev and "shown, not counted" in ev and "unit2" in ev
    assert "no longer required for this Case File (NCG tier" not in ev
    assert [n for n in _notes("request_closed") if n["to"] == {"department": "radiology"}][-1]["text"].startswith("The request closed: the Case File was referred")
    referred = rules._referred_from(c, st, protocol.get("unit2"))
    mri = next(a for a in st["actions"] if a["requirement"] == "mri_pelvis")
    assert referred["actions"] == {sent["id"]} and mri["id"] not in referred["actions"], "only the requests open at the referral close with it as the reason"
