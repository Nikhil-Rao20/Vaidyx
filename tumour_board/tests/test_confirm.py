"""confirm: clinician confirmations (validate, record, supersede, undo, legacy /overrides mirror, read-time overlay)."""
import copy

import pytest

from tumour_board import confirm, rules, store
from tumour_board.tests.util import add, fact, make_doc, req


def hist(doc_id="Dhist0001", facts=None, **kw):
    f = {"histologic_type": fact("Adenocarcinoma, lung, acinar predominant."), "pdl1": fact("TPS 60%")} if facts is None else facts
    return make_doc(doc_id, "histopathology", facts=f, **kw)


def ct(doc_id="Dct000001", **kw):
    kw.setdefault("region", "chest")
    return make_doc(doc_id, "ct", facts={"lesion_size": fact("3.2 cm")}, **kw)


def events(case_id, kind):
    return [e for e in store.read_audit(case_id) if e["kind"] == kind]


# ---- validate ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("ctype,key,fields,reason,msg", [
    ("guess_stage", "D1", {}, "", "Unknown confirmation type"),
    ("waive", "ct_thorax", {}, "", "reason is required"),
    ("waive", "ct_thorax", {}, "   ", "reason is required"),
    ("dismiss_failed", "Dbad00001", {}, "", "reason is required"),
    ("attest_final", "", {}, "", "Choose what"),
    ("attest_final", "../etc", {}, "", "Not a valid document id"),
    ("confirm_dates", "Dhist0001", {}, "", "report date"),
    ("confirm_dates", "Dhist0001", {"report_date": "31/02/2026"}, "", "Not a valid date"),
    ("confirm_dates", "Dhist0001", {"event_date": "last Tuesday"}, "", "Not a valid date"),
    ("confirm_doc_type", "Dhist0001", {"doc_type": "biopsy_guess"}, "", "Unknown document type"),
    ("confirm_doc_type", "Dhist0001", {}, "", "Unknown document type"),
    ("confirm_match", "Dintake01", {}, "", "Choose the Case File"),
    ("confirm_match", "Dintake01", {"case_id": "TB 001/x"}, "", "Not a valid Case File id"),
    ("confirm_value", "Dhist0001:pdl1", {"value": "  "}, "", "Type the value"),
    ("confirm_value", "Dhist0001", {"value": "TPS 60%"}, "", "document and the field"),
    ("resolve_flag", "F1", {"resolution": "ignore"}, "", "Choose how the flag"),
    ("resolve_flag", "F1", {"resolution": "intentional_deviation"}, "", "intentional deviation"),
    ("resolve_flag", "F1", {"resolution": "corrected"}, "", "corrected value"),
    ("attest_final", "Dhist0001", ["not", "a", "dict"], "", "name: value"),
])
def test_validate_rejects(ctype, key, fields, reason, msg):
    with pytest.raises(ValueError, match=msg):
        confirm.validate(ctype, key, fields, reason)


def test_validate_cleans():
    assert confirm.validate("confirm_dates", "Dhist0001", {"report_date": "04/09/2026", "event_date": "", "junk": 1}) == {
        "type": "confirm_dates", "key": "Dhist0001", "fields": {"report_date": "2026-09-04", "event_date": ""}, "reason": ""}
    assert confirm.validate("confirm_doc_type", " Dhist0001 ", {"doc_type": "ihc"})["fields"] == {"doc_type": "ihc"}
    assert confirm.validate("confirm_match", "Dintake01", {"case_id": ""})["fields"] == {"case_id": ""}
    assert confirm.validate("confirm_value", "Dhist0001:pdl1", {"value": " TPS 60% "})["fields"] == {"value": "TPS 60%"}
    assert confirm.validate("resolve_flag", "F1", {"resolution": "false_alarm"})["fields"] == {"resolution": "false_alarm", "value": ""}
    assert confirm.validate("resolve_flag", "F1", {"resolution": "intentional_deviation"}, "patient preference")["reason"] == "patient preference"
    assert confirm.validate("resolve_flag", "F1", {"resolution": "corrected", "value": "60%"})["fields"]["value"] == "60%"
    assert confirm.validate("waive", "ct_thorax", None, " done at referring hospital ")["reason"] == "done at referring hospital"
    assert confirm.validate("dismiss_failed", "Dbad00001", {}, "blank scan")["fields"] == {}


# ---- record, supersede, undo -------------------------------------------------------------------------------
def test_record_writes_record_mirror_and_audit(unit_case):
    rec = confirm.record(unit_case, "attest_final", "Dhist0001", reason="checked with Pathology", by="Dr. Rao")
    assert rec["id"].startswith("C") and len(rec["id"]) == 9 and rec["by"] == "Dr. Rao" and rec["undone"] is None and rec["at"]
    st = store.get_state(unit_case)
    assert st["confirmations"] == [rec]
    assert st["overrides"]["documents"]["Dhist0001"] == {"attested_final": True, "reason": "checked with Pathology", "by": "Dr. Rao",
                                                         "at": rec["at"], "confirmation": rec["id"]}
    ev = events(unit_case, "confirmation")[-1]
    assert {k: ev[k] for k in ("type", "key", "fields", "reason", "by", "id")} == {
        "type": "attest_final", "key": "Dhist0001", "fields": {}, "reason": "checked with Pathology", "by": "Dr. Rao", "id": rec["id"]}


def test_record_waive_mirror(unit_case):
    rec = confirm.record(unit_case, "waive", "ct_thorax", reason="CT done at referring hospital", by="Dr. Rao")
    assert store.get_state(unit_case)["overrides"]["requirements"]["ct_thorax"] == {
        "waived": True, "reason": "CT done at referring hospital", "by": "Dr. Rao", "at": rec["at"], "confirmation": rec["id"]}


def test_non_legacy_types_do_not_touch_overrides(unit_case):
    confirm.record(unit_case, "confirm_doc_type", "Dhist0001", {"doc_type": "ihc"}, by="Dr. Rao")
    assert "overrides" not in store.get_state(unit_case)


def test_invalid_record_writes_nothing(unit_case):
    with pytest.raises(ValueError):
        confirm.record(unit_case, "waive", "ct_thorax", reason="", by="Dr. Rao")
    assert "confirmations" not in store.get_state(unit_case) and events(unit_case, "confirmation") == []


def test_second_record_supersedes_first(unit_case):
    a = confirm.record(unit_case, "waive", "ct_thorax", reason="first", by="Dr. Rao")
    b = confirm.record(unit_case, "waive", "ct_thorax", reason="second", by="Dr. Iyer")
    st = store.get_state(unit_case)
    first = next(c for c in st["confirmations"] if c["id"] == a["id"])
    assert first["undone"]["by"] == "Dr. Iyer" and first["undone"]["superseded_by"] == b["id"]
    assert st["overrides"]["requirements"]["ct_thorax"]["confirmation"] == b["id"]
    assert st["overrides"]["requirements"]["ct_thorax"]["reason"] == "second"
    assert [c["id"] for c in confirm.active(st)] == [b["id"]]
    assert events(unit_case, "confirmation")[-1]["supersedes"] == [a["id"]]


def test_undo_removes_mirror_and_audits(unit_case):
    rec = confirm.record(unit_case, "attest_final", "Dhist0001", by="Dr. Rao")
    out = confirm.undo(unit_case, rec["id"], by="Dr. Iyer")
    assert out["undone"]["by"] == "Dr. Iyer"
    st = store.get_state(unit_case)
    assert st["overrides"]["documents"] == {} and confirm.active(st) == [] and len(st["confirmations"]) == 1
    ev = events(unit_case, "confirmation_undone")[-1]
    assert (ev["id"], ev["type"], ev["key"], ev["by"]) == (rec["id"], "attest_final", "Dhist0001", "Dr. Iyer")


def test_undo_unknown_or_twice_raises(unit_case):
    rec = confirm.record(unit_case, "attest_final", "Dhist0001", by="Dr. Rao")
    with pytest.raises(KeyError):
        confirm.undo(unit_case, "Cdeadbeef", by="Dr. Rao")
    confirm.undo(unit_case, rec["id"], by="Dr. Rao")
    with pytest.raises(KeyError):
        confirm.undo(unit_case, rec["id"], by="Dr. Rao")


def test_undo_keeps_mirror_not_its_own(unit_case):
    """Undoing an old (superseded) record never removes the entry that now belongs to a newer confirmation."""
    a = confirm.record(unit_case, "attest_final", "Dhist0001", by="Dr. Rao")
    st = store.get_state(unit_case)
    st["confirmations"][0]["undone"] = None  # an older record still marked active (e.g. written by hand)
    b = {**a, "id": "Cbbbbbbbb"}
    st["confirmations"].append(b); st["overrides"]["documents"]["Dhist0001"]["confirmation"] = b["id"]
    store.save_state(unit_case, st)
    confirm.undo(unit_case, a["id"], by="Dr. Rao")
    assert store.get_state(unit_case)["overrides"]["documents"]["Dhist0001"]["confirmation"] == "Cbbbbbbbb"


# ---- legacy /overrides contract ----------------------------------------------------------------------------
def _strip(ov):
    return {k: {kk: {f: v for f, v in e.items() if f not in ("at", "confirmation")} for kk, e in d.items()} for k, d in ov.items()}


@pytest.mark.parametrize("kind,key,value", [
    ("documents", "Dhist0001", {"attested_final": True}),
    ("documents", "Dhist0001", {"attested_final": True, "reason": "verified with department"}),
    ("requirements", "ct_thorax", {"waived": True, "reason": "CT done at referring hospital"}),
])
def test_legacy_override_same_shape_as_set_override(unit_case, kind, key, value):
    rules.set_override(unit_case, kind, key, value, by="Dr. Rao")
    old = store.get_state(unit_case)["overrides"]
    store.save_state(unit_case, {**store.get_state(unit_case), "overrides": {}})
    rec = confirm.legacy_override(unit_case, kind, key, value, by="Dr. Rao")
    new = store.get_state(unit_case)["overrides"]
    assert _strip(new) == _strip(old) and new[kind][key]["confirmation"] == rec["id"]
    ev = events(unit_case, "override")[-1]
    assert (ev["target"], ev["key"], ev["value"], ev["by"]) == (kind, key, value, "Dr. Rao")


def _gate_without_time(case_id):
    g = rules.evaluate(case_id)
    g.pop("evaluated")
    return g


def test_legacy_attestation_evaluates_like_set_override(unit_case):
    add(unit_case, hist(status="UNSTATED", signed="unknown", title="HPE"), ct())
    rules.set_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    via_rules = _gate_without_time(unit_case)
    rules.set_override(unit_case, "documents", "Dhist0001", None, by="Dr. Rao")
    assert req(rules.evaluate(unit_case), "histopathology")["status"] == "needs_confirmation"
    confirm.legacy_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    via_confirm = _gate_without_time(unit_case)
    assert via_confirm == via_rules
    r = req(via_confirm, "histopathology")
    assert r["status"] == "satisfied" and r["notes"] == ["status not explicit in HPE; attested final by Dr. Rao"] and via_confirm["passed"]


def test_legacy_undo_restores_confirmation(unit_case):
    add(unit_case, hist(status="UNSTATED", signed="unknown"), ct())
    rec = confirm.legacy_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    assert confirm.legacy_override(unit_case, "documents", "Dhist0001", None, by="Dr. Rao") is None
    assert req(rules.evaluate(unit_case), "histopathology")["status"] == "needs_confirmation"
    assert next(c for c in store.get_state(unit_case)["confirmations"] if c["id"] == rec["id"])["undone"]
    confirm.legacy_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    confirm.legacy_override(unit_case, "documents", "Dhist0001", {"attested_final": False}, by="Dr. Rao")
    assert req(rules.evaluate(unit_case), "histopathology")["status"] == "needs_confirmation"


def test_legacy_undo_clears_entry_from_old_set_override(unit_case):
    add(unit_case, hist(status="UNSTATED", signed="unknown"), ct())
    rules.set_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    confirm.legacy_override(unit_case, "documents", "Dhist0001", None, by="Dr. Rao")
    assert store.get_state(unit_case)["overrides"]["documents"] == {}


def test_legacy_unknown_kind_and_waiver_without_reason(unit_case):
    with pytest.raises(ValueError, match="Unknown override kind"):
        confirm.legacy_override(unit_case, "facts", "pdl1", {"attested_final": True}, by="Dr. Rao")
    with pytest.raises(ValueError, match="reason is required"):
        confirm.legacy_override(unit_case, "requirements", "ct_thorax", {"waived": True}, by="Dr. Rao")


def test_waiver_through_confirm_excluded_from_gate(unit_case):
    add(unit_case, hist())
    confirm.record(unit_case, "waive", "ct_thorax", reason="CT done at referring hospital", by="Dr. Rao")
    g = rules.evaluate(unit_case)
    r = req(g, "ct_thorax")
    assert r["status"] == "waived" and r["waiver"]["by"] == "Dr. Rao"
    assert r["problems"] == ["Waived for this Case File by Dr. Rao: CT done at referring hospital"]
    assert g["passed"] and (g["satisfied"], g["total"]) == (2, 2)
    confirm.undo(unit_case, confirm.latest(unit_case, "waive", "ct_thorax")["id"], by="Dr. Rao")
    assert req(rules.evaluate(unit_case), "ct_thorax")["status"] == "missing_record"


def test_attestation_survives_reprocess(unit_case):
    add(unit_case, hist(status="UNSTATED", signed="unknown"), ct())
    confirm.record(unit_case, "attest_final", "Dhist0001", by="Dr. Rao")
    add(unit_case, hist(status="UNSTATED", signed="unknown", facts={"histologic_type": fact("Adenocarcinoma"), "pdl1": fact("TPS 70%")}))
    g = rules.evaluate(unit_case)
    assert req(g, "histopathology")["status"] == "satisfied" and req(g, "pdl1")["evidence"][0]["value"] == "TPS 70%"


# ---- read-time overlay -------------------------------------------------------------------------------------
def _confirm_all(case_id):
    confirm.record(case_id, "confirm_doc_type", "Dhist0001", {"doc_type": "ihc"}, by="Dr. Rao")
    confirm.record(case_id, "confirm_dates", "Dhist0001", {"report_date": "04/09/2026", "event_date": "2026-08-30"}, by="Dr. Iyer")
    confirm.record(case_id, "confirm_value", "Dhist0001:pdl1", {"value": "TPS 70%"}, by="Dr. Rao")
    confirm.record(case_id, "dismiss_failed", "Dhist0001", reason="blank scan, original re-requested", by="Dr. Rao")


def test_apply_to_doc_overlays_and_keeps_model_values(unit_case):
    _confirm_all(unit_case)
    doc = hist(date="2026-09-01")
    before = copy.deepcopy(doc)
    st = store.get_state(unit_case)
    d = confirm.apply_to_doc(doc, st)
    assert doc == before  # input never mutated
    c = d["classification"]
    assert (c["doc_type"], c["model_doc_type"], c["doc_type_confirmed_by"]) == ("ihc", "histopathology", "Dr. Rao")
    assert (c["report_date_iso"], c["model_report_date_iso"], c["event_date_iso"], c["dates_confirmed_by"]) == ("2026-09-04", "2026-09-01", "2026-08-30", "Dr. Iyer")
    f = d["facts"]["pdl1"]
    assert (f["value"], f["model_value"], f["verification"], f["confirmed_by"], f["state"]) == ("TPS 70%", "TPS 60%", "confirmed", "Dr. Rao", "present")
    assert d["facts"]["histologic_type"] == doc["facts"]["histologic_type"]
    assert d["dismissed"]["by"] == "Dr. Rao" and d["dismissed"]["reason"] == "blank scan, original re-requested" and d["dismissed"]["at"]
    assert len(d["confirmations"]) == 4


def test_apply_to_doc_value_the_model_missed(unit_case):
    confirm.record(unit_case, "confirm_value", "Dhist0001:pdl1", {"value": "TPS 70%"}, by="Dr. Rao")
    d = confirm.apply_to_doc(hist(facts={}), store.get_state(unit_case))
    f = d["facts"]["pdl1"]
    assert (f["value"], f["quote"], f["model_value"], f["verification"], f["state"]) == ("TPS 70%", "TPS 70%", None, "confirmed", "present")


def test_empty_confirmed_date_means_not_stated(unit_case):
    confirm.record(unit_case, "confirm_dates", "Dhist0001", {"report_date": ""}, by="Dr. Rao")
    c = confirm.apply_to_doc(hist(), store.get_state(unit_case))["classification"]
    assert c["report_date_iso"] == "" and c["model_report_date_iso"] == "2026-09-01" and "event_date_iso" not in c


def test_unconfirmed_doc_is_returned_equal(unit_case):
    _confirm_all(unit_case)
    confirm.record(unit_case, "attest_final", "Dct000001", by="Dr. Rao")  # attestation is read from overrides, not overlaid
    other = ct()
    st = store.get_state(unit_case)
    assert confirm.apply_to_doc(other, st) == other
    assert confirm.apply_to_doc(other, {}) == other
    assert confirm.apply_to_docs([other], st) == [other]


def test_undone_confirmation_not_applied(unit_case):
    rec = confirm.record(unit_case, "confirm_doc_type", "Dhist0001", {"doc_type": "ihc"}, by="Dr. Rao")
    confirm.undo(unit_case, rec["id"], by="Dr. Rao")
    doc = hist()
    assert confirm.apply_to_doc(doc, store.get_state(unit_case)) == doc


def test_confirmations_survive_reprocess(unit_case):
    """Re-processing rewrites doc.json with fresh model output; the overlay from state.json still wins."""
    add(unit_case, hist())
    _confirm_all(unit_case)
    add(unit_case, hist(date="2026-09-02", facts={"pdl1": fact("TPS 65%")}))  # simulated re-process
    d = next(x for x in confirm.apply_to_docs(store.list_docs(unit_case), store.get_state(unit_case)) if x["doc_id"] == "Dhist0001")
    assert d["classification"]["doc_type"] == "ihc" and d["classification"]["report_date_iso"] == "2026-09-04"
    assert d["facts"]["pdl1"]["value"] == "TPS 70%" and d["facts"]["pdl1"]["model_value"] == "TPS 65%" and d["dismissed"]
    assert store.get_doc(unit_case, "Dhist0001")["facts"]["pdl1"]["value"] == "TPS 65%"  # doc.json untouched


# ---- active / latest / summary -----------------------------------------------------------------------------
def test_active_latest_summary(unit_case):
    a = confirm.record(unit_case, "confirm_value", "Dhist0001:pdl1", {"value": "TPS 60%"}, by="Dr. Rao")
    b = confirm.record(unit_case, "confirm_value", "Dhist0001:histologic_type", {"value": "Adenocarcinoma"}, by="Dr. Rao")
    w = confirm.record(unit_case, "waive", "ct_thorax", reason="done elsewhere", by="Dr. Rao")
    m = confirm.record(unit_case, "confirm_match", "Dintake01", {"case_id": unit_case}, by="Dr. Rao")
    f = confirm.record(unit_case, "resolve_flag", "F1", {"resolution": "false_alarm"}, by="Dr. Rao")
    confirm.undo(unit_case, w["id"], by="Dr. Rao")
    st = store.get_state(unit_case)
    assert [c["id"] for c in confirm.active(unit_case)] == [a["id"], b["id"], m["id"], f["id"]]
    assert [c["id"] for c in confirm.active(st, "confirm_value")] == [a["id"], b["id"]]
    assert [c["id"] for c in confirm.active(st, key="Dintake01")] == [m["id"]]
    assert confirm.latest(st, "confirm_value", "Dhist0001:pdl1")["id"] == a["id"]
    assert confirm.latest(st, "waive", "ct_thorax") is None
    c = confirm.record(unit_case, "confirm_value", "Dhist0001:pdl1", {"value": "TPS 70%"}, by="Dr. Iyer")
    assert confirm.latest(unit_case, "confirm_value", "Dhist0001:pdl1")["id"] == c["id"]
    s = confirm.summary(store.get_state(unit_case))
    assert s["confirm_value"] == 2 and s["confirm_match"] == 1 and s["resolve_flag"] == 1 and s["waive"] == 0 and s["total"] == 4
    assert set(s) == set(confirm.TYPES) | {"total"}
    assert confirm.summary({}) == {**{t: 0 for t in confirm.TYPES}, "total": 0}


# --- orchestrator wiring: the gate reads confirmations through rules.case_docs and counts confirmed values as verified ---

def test_confirmed_value_satisfies_the_requirement_and_survives_reprocess(unit_case):
    from tumour_board import rules
    from tumour_board.tests.util import add, fact, make_doc, req
    add(unit_case, make_doc("Dhist0001", "histopathology", facts={"histologic_type": fact("Adenocarcinoma")}),
        make_doc("Dct000001", "ct", region="chest", facts={"lesion_size": fact("3.2 cm")}))
    g = rules.evaluate(unit_case)
    assert req(g, "pdl1")["status"] == "missing_field"  # facts-only requirement: the value is missing
    confirm.record(unit_case, "confirm_value", "Dhist0001:pdl1", {"value": "TPS 60%"}, "", by="Dr. Rao")  # read by the clinician on the scan image
    g = rules.evaluate(unit_case)
    assert req(g, "pdl1")["status"] == "satisfied"
    assert req(g, "pdl1")["evidence"] == [{"doc_id": "Dhist0001", "fact": "pdl1", "value": "TPS 60%", "quote": "TPS 60%"}]
    d = next(x for x in rules.case_docs(unit_case) if x["doc_id"] == "Dhist0001")
    assert d["facts"]["pdl1"]["verification"] == "confirmed" and d["facts"]["pdl1"]["confirmed_by"] == "Dr. Rao"
    assert "pdl1" not in store.get_doc(unit_case, "Dhist0001")["facts"]  # doc.json untouched: the overlay is read-time
    # a re-process rewrites doc.json with fresh model output; the confirmation still wins
    fresh = make_doc("Dhist0001", "histopathology", facts={"histologic_type": fact("Adenocarcinoma")}); store.save_doc(unit_case, fresh); store._docs_cache.clear()
    assert req(rules.evaluate(unit_case), "pdl1")["status"] == "satisfied"
    confirm.undo(unit_case, confirm.latest(unit_case, "confirm_value", "Dhist0001:pdl1")["id"], by="Dr. Rao")
    assert req(rules.evaluate(unit_case), "pdl1")["status"] == "missing_field"
