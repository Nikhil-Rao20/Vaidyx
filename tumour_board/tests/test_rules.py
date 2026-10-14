"""rules: Pre-Authorization verdicts, readiness / passed, overrides, resolve_facts and sync_actions (small test protocol)."""
from datetime import date, timedelta

from tumour_board import rules, store
from tumour_board.tests.util import add, fact, make_doc, req


def hist(doc_id="Dhist0001", facts=None, **kw):
    f = {"histologic_type": fact("Adenocarcinoma, lung, acinar predominant."), "pdl1": fact("TPS 60%")} if facts is None else facts
    return make_doc(doc_id, "histopathology", facts=f, **kw)


def ct(doc_id="Dct000001", facts=None, **kw):
    kw.setdefault("region", "chest")
    return make_doc(doc_id, "ct", facts={"lesion_size": fact("3.2 cm")} if facts is None else facts, **kw)


# ---- verdicts ----------------------------------------------------------------------------------------------
def test_all_satisfied_passes(unit_case):
    add(unit_case, hist(), ct())
    g = rules.evaluate(unit_case)
    assert [(r["id"], r["status"]) for r in g["requirements"]] == [
        ("histopathology", "satisfied"), ("ct_thorax", "satisfied"), ("pdl1", "satisfied"), ("restaging_mri", "not_applicable")]
    assert g["passed"] and g["readiness"] == 100 and (g["satisfied"], g["total"]) == (3, 3)
    assert g["protocol"] == "unit" and g["protocol_version"] == "0.0"
    assert req(g, "pdl1")["evidence"] == [{"doc_id": "Dhist0001", "fact": "pdl1", "value": "TPS 60%", "quote": "TPS 60%"}]


def test_missing_record(unit_case):
    add(unit_case, hist())
    g = rules.evaluate(unit_case)
    r = req(g, "ct_thorax")
    assert r["status"] == "missing_record" and r["department"] == "Radiology"
    assert r["problems"] == ["No diagnostic ct thorax report in the Case File"]
    assert r["notes"] == ["That record must document: Primary lesion size"]
    assert not g["passed"] and g["readiness"] == 67 and (g["satisfied"], g["total"]) == (2, 3)


def test_region_must_match_region_title_or_filename(unit_case):
    add(unit_case, hist(), ct(region="abdomen", title="CECT ABDOMEN", filename="cect_abdomen.pdf"))
    assert req(rules.evaluate(unit_case), "ct_thorax")["status"] == "missing_record"
    add(unit_case, ct(region="", title="CECT THORAX", filename="scan.pdf"))
    assert req(rules.evaluate(unit_case), "ct_thorax")["status"] == "satisfied"


def test_not_final_draft_unsigned(unit_case):
    add(unit_case, hist(status="DRAFT", signed="no", title="HISTOPATHOLOGY REPORT"), ct())
    g = rules.evaluate(unit_case)
    r = req(g, "histopathology")
    assert r["status"] == "not_final"
    assert r["problems"] == ["HISTOPATHOLOGY REPORT is DRAFT and unsigned: a final, signed version is required",
                             "Pending: Histologic type: only in a non-final document (HISTOPATHOLOGY REPORT)"]
    assert r["evidence"] == [{"doc_id": "Dhist0001", "quote": "Report status: DRAFT"}]
    p = req(g, "pdl1")
    assert p["status"] == "missing_field" and p["problems"] == ["Pending: PD-L1: only in a non-final document (HISTOPATHOLOGY REPORT)"]
    assert g["documents"]["non_final"] == ["Dhist0001"]


def test_not_final_preliminary_signed(unit_case):
    add(unit_case, hist(status="PRELIMINARY", signed="yes", title="IHC"), ct())
    r = req(rules.evaluate(unit_case), "histopathology")
    assert r["status"] == "not_final" and r["problems"][0] == "IHC is PRELIMINARY: a final, signed version is required"


def test_final_but_unsigned_is_not_final(unit_case):
    add(unit_case, hist(status="FINAL", signed="no"), ct())
    assert req(rules.evaluate(unit_case), "histopathology")["status"] == "not_final"


def test_unstated_unknown_needs_confirmation(unit_case):
    add(unit_case, hist(status="UNSTATED", signed="unknown", title="HPE", status_notes=["the word 'draft' appears in the text; confirm this is the final version"]), ct())
    g = rules.evaluate(unit_case)
    r = req(g, "histopathology")
    assert r["status"] == "needs_confirmation"
    assert r["problems"][0] == ("HPE has no explicit status or signature line: confirm it is the final, signed version; "
                                "the word 'draft' appears in the text; confirm this is the final version")
    assert "Pending: Histologic type: only in a non-final document (HPE)" in r["problems"]  # listed, confirmation first
    assert g["documents"]["unconfirmed"] == ["Dhist0001"] and not g["passed"]


def test_unstated_signed_counts_as_final(unit_case):
    add(unit_case, hist(status="UNSTATED", signed="yes", title="HPE"), ct())
    r = req(rules.evaluate(unit_case), "histopathology")
    assert r["status"] == "satisfied" and r["notes"] == ["status not explicit in HPE; signature line present"]


def test_unstated_unsigned_is_not_final(unit_case):
    add(unit_case, hist(status="UNSTATED", signed="no"), ct())
    assert req(rules.evaluate(unit_case), "histopathology")["status"] == "not_final"


def test_missing_field(unit_case):
    add(unit_case, hist(facts={"pdl1": fact("TPS 60%")}), ct())
    r = req(rules.evaluate(unit_case), "histopathology")
    assert r["status"] == "missing_field" and r["problems"] == ["Required field not documented: Histologic type"]


def test_unverified_value_counts_as_missing(unit_case):
    add(unit_case, hist(facts={"histologic_type": fact("Adenocarcinoma", verification="unverified"), "pdl1": fact("TPS 60%")}), ct())
    r = req(rules.evaluate(unit_case), "histopathology")
    assert r["status"] == "missing_field" and r["problems"] == ["Required field not documented: Histologic type"]


def test_pending_value_is_missing_field(unit_case):
    add(unit_case, hist(title="HPE", facts={"histologic_type": fact("Adenocarcinoma"), "pdl1": fact("Pending", state="pending")}), ct())
    r = req(rules.evaluate(unit_case), "pdl1")
    assert r["status"] == "missing_field" and r["problems"] == ['Pending: PD-L1: "Pending" in HPE']


def test_approximate_match_needs_review(unit_case):
    add(unit_case, hist(facts={"histologic_type": fact("Adenocarcinoma", verification="needs_review"), "pdl1": fact("TPS 60%")}), ct())
    r = req(rules.evaluate(unit_case), "histopathology")
    assert r["status"] == "needs_review" and r["problems"] == ["Needs expert review (approximate source match): Histologic type"]


def test_identity_mismatch_needs_review(unit_case):
    add(unit_case, hist(identity="mismatch_or_missing", title="HPE"), ct())
    g = rules.evaluate(unit_case)
    r = req(g, "histopathology")
    assert r["status"] == "needs_review"
    assert r["problems"] == ["Patient identifier not found in HPE: check the document belongs to this patient"]
    assert g["documents"]["identity_flags"] == ["Dhist0001"]


def test_facts_only_value_must_come_from_allowed_doc_types(unit_case):
    add(unit_case, hist(facts={"histologic_type": fact("Adenocarcinoma")}), ct(facts={"lesion_size": fact("3.2 cm"), "pdl1": fact("TPS 60%")}))
    r = req(rules.evaluate(unit_case), "pdl1")
    assert r["status"] == "missing_field" and r["problems"] == ["Required field not documented: PD-L1"]


def test_newest_final_is_the_evidence(unit_case):
    add(unit_case, hist("Dhist_old", date="2026-08-01"), hist("Dhist_new", date="2026-09-01"), ct())
    assert req(rules.evaluate(unit_case), "histopathology")["evidence"][0]["doc_id"] == "Dhist_new"


def test_older_final_satisfies_despite_newer_draft(unit_case):
    add(unit_case, hist("Dhist_old", date="2026-08-01"), hist("Dhist_new", date="2026-09-01", status="DRAFT", signed="no"), ct())
    r = req(rules.evaluate(unit_case), "histopathology")
    assert r["status"] == "satisfied" and r["evidence"][0]["doc_id"] == "Dhist_old"


def test_documents_not_ready_do_not_count(unit_case):
    add(unit_case, hist(state="extracting"), ct())
    g = rules.evaluate(unit_case)
    assert req(g, "histopathology")["status"] == "missing_record"
    assert g["documents"]["processing"] == 1 and g["documents"]["ready"] == 1


def test_restaging_not_applicable_without_treatment_summary(unit_case):
    add(unit_case, hist(), ct())
    assert req(rules.evaluate(unit_case), "restaging_mri")["status"] == "not_applicable"


def test_restaging_must_postdate_treatment_summary(unit_case):
    add(unit_case, hist(), ct(), make_doc("Dtx000001", "treatment_summary", date="2026-08-10"),
        make_doc("Dmri_base", "mri", region="pelvis", date="2026-06-05"))
    r = req(rules.evaluate(unit_case), "restaging_mri")
    assert r["status"] == "missing_record" and r["postdate_reference"] == "2026-08-10"
    assert r["problems"] == ["No restaging mri pelvis in the Case File dated after 2026-08-10"]
    add(unit_case, make_doc("Dmri_brain", "mri", region="brain", date="2026-09-01"))
    assert req(rules.evaluate(unit_case), "restaging_mri")["status"] == "missing_record"
    add(unit_case, make_doc("Dmri_rest", "mri", region="rectum", date="2026-09-20"))
    g = rules.evaluate(unit_case)
    assert req(g, "restaging_mri")["status"] == "satisfied" and g["passed"] and g["total"] == 4


# ---- passed / readiness ------------------------------------------------------------------------------------
def test_processing_document_blocks_passed(unit_case):
    add(unit_case, hist(), ct(), make_doc("Dnew00001", "lab", state="reading"))
    g = rules.evaluate(unit_case)
    assert g["readiness"] == 100 and not g["passed"] and g["documents"]["processing"] == 1


def test_failed_document_blocks_the_gate_until_dismissed(unit_case):
    """V1 item 4.3: a document that failed to read blocks the gate until it is re-processed or dismissed (audited, with a reason)."""
    add(unit_case, hist(), ct(), {**make_doc("Dbad00001", "other", state="error"), "error": "PdfStreamError: Stream has ended unexpectedly", "rel_path": "radiology/mri_brain.pdf"})
    g = rules.evaluate(unit_case)
    assert g["readiness"] == 100 and not g["passed"] and g["documents"]["errors"] == 1 and g["documents"]["processing"] == 0
    assert g["blockers"] == [{"doc_id": "Dbad00001", "filename": "radiology/mri_brain.pdf", "error": "PdfStreamError: Stream has ended unexpectedly", "department": None}]
    assert g["documents"]["failed"] == ["Dbad00001"] and g["documents"]["dismissed"] == []
    from tumour_board import confirm
    confirm.record(unit_case, "dismiss_failed", "Dbad00001", {}, "duplicate of the CECT already filed; original requested from Radiology", by="Dr. Rao")
    g = rules.evaluate(unit_case)
    assert g["passed"] and g["blockers"] == [] and g["documents"]["failed"] == [] and g["documents"]["errors"] == 1
    assert g["documents"]["dismissed"][0]["doc_id"] == "Dbad00001" and g["documents"]["dismissed"][0]["by"] == "Dr. Rao" and "duplicate" in g["documents"]["dismissed"][0]["reason"]
    rec = confirm.active(unit_case, "dismiss_failed", "Dbad00001")[0]
    confirm.undo(unit_case, rec["id"], by="Dr. Rao")
    assert not rules.evaluate(unit_case)["passed"]


def test_dismissal_of_a_document_that_now_reads_is_harmless(unit_case):
    from tumour_board import confirm
    add(unit_case, hist(), ct(), make_doc("Dbad00001", "other", state="error"))
    confirm.record(unit_case, "dismiss_failed", "Dbad00001", {}, "unreadable copy", by="Dr. Rao")
    add(unit_case, make_doc("Dbad00001", "lab", state="ready"))  # re-processed and read
    g = rules.evaluate(unit_case)
    assert g["passed"] and g["documents"]["dismissed"] == [] and g["documents"]["errors"] == 0


def test_optional_and_core_data(unit_case):
    add(unit_case, hist(), ct(), make_doc("Dxray0001", "xray"))
    g = rules.evaluate(unit_case)
    assert g["optional"] == [{"id": "prior_imaging", "label": "Prior imaging", "available": True, "doc_ids": ["Dxray0001"]}]
    assert g["core_data"][0]["present"] and g["core_data"][0]["evidence"][0]["fact"] == "histologic_type"


# ---- overrides (attest final, waiver) ----------------------------------------------------------------------
def test_attest_final_satisfies_unstated(unit_case):
    add(unit_case, hist(status="UNSTATED", signed="unknown", title="HPE"), ct())
    rules.set_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    g = rules.evaluate(unit_case)
    r = req(g, "histopathology")
    assert r["status"] == "satisfied" and r["notes"] == ["status not explicit in HPE; attested final by Dr. Rao"]
    assert req(g, "pdl1")["status"] == "satisfied" and g["passed"] and g["documents"]["unconfirmed"] == []
    ev = [a for a in store.read_audit(unit_case) if a["kind"] == "override"]
    assert ev[-1]["target"] == "documents" and ev[-1]["key"] == "Dhist0001" and ev[-1]["by"] == "Dr. Rao"


def test_removing_attestation_restores_confirmation(unit_case):
    add(unit_case, hist(status="UNSTATED", signed="unknown"), ct())
    rules.set_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    rules.set_override(unit_case, "documents", "Dhist0001", None, by="Dr. Rao")
    assert req(rules.evaluate(unit_case), "histopathology")["status"] == "needs_confirmation"


def test_attestation_does_not_override_explicit_draft(unit_case):
    add(unit_case, hist(status="DRAFT", signed="no"), ct())
    rules.set_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    assert req(rules.evaluate(unit_case), "histopathology")["status"] == "not_final"


def test_waiver_beats_missing_record(unit_case):
    add(unit_case, hist())
    rules.set_override(unit_case, "requirements", "ct_thorax", {"waived": True, "reason": "CT done at referring hospital"}, by="Dr. Rao")
    g = rules.evaluate(unit_case)
    r = req(g, "ct_thorax")
    assert r["status"] == "waived" and r["waiver"]["by"] == "Dr. Rao"
    assert r["problems"] == ["Waived for this Case File by Dr. Rao: CT done at referring hospital"]
    assert g["passed"] and (g["satisfied"], g["total"]) == (2, 2)


def test_waiver_not_set_is_ignored(unit_case):
    add(unit_case, hist())
    rules.set_override(unit_case, "requirements", "ct_thorax", {"waived": False, "reason": ""}, by="Dr. Rao")
    assert req(rules.evaluate(unit_case), "ct_thorax")["status"] == "missing_record"


def test_overrides_survive_reprocess_of_doc(unit_case):
    """Overrides live in state.json, not doc.json: rewriting the document keeps the attestation."""
    add(unit_case, hist(status="UNSTATED", signed="unknown"), ct())
    rules.set_override(unit_case, "documents", "Dhist0001", {"attested_final": True}, by="Dr. Rao")
    add(unit_case, hist(status="UNSTATED", signed="unknown", facts={"histologic_type": fact("Adenocarcinoma"), "pdl1": fact("TPS 70%")}))
    g = rules.evaluate(unit_case)
    assert req(g, "histopathology")["status"] == "satisfied" and req(g, "pdl1")["evidence"][0]["value"] == "TPS 70%"


# ---- resolve_facts -----------------------------------------------------------------------------------------
def _hb(doc_id, value, date, **kw):
    return make_doc(doc_id, "lab", date=date, facts={"haemoglobin": fact(value, **{k: kw.pop(k) for k in ("verification", "state") if k in kw})}, **kw)


def test_resolve_current_is_newest_final_verified():
    docs = [_hb("D2", "11.2 g/dL", "2026-09-04"), _hb("D1", "12.5 g/dL", "2026-08-01"), _hb("D3", "10.1 g/dL", "2026-07-01")]
    f = rules.resolve_facts(docs)["haemoglobin"]
    assert f["current"]["value"] == "11.2 g/dL" and f["current"]["doc_id"] == "D2"
    assert [h["date"] for h in f["history"]] == ["2026-07-01", "2026-08-01", "2026-09-04"]
    h = f["history"][-1]
    assert (h["doc_type"], h["doc_status"], h["doc_final"], h["doc_title"]) == ("lab", "FINAL", True, "LAB REPORT D2")


def test_resolve_newer_draft_does_not_replace_final():
    docs = [_hb("D1", "12.5 g/dL", "2026-08-01"), _hb("D2", "9.0 g/dL", "2026-09-04", status="DRAFT", signed="no")]
    f = rules.resolve_facts(docs)["haemoglobin"]
    assert f["current"]["doc_id"] == "D1" and len(f["history"]) == 2


def test_resolve_falls_back_to_verified_then_any():
    docs = [_hb("D1", "12.5 g/dL", "2026-08-01", status="DRAFT", signed="no"), _hb("D2", "9.0 g/dL", "2026-09-04", verification="unverified")]
    assert rules.resolve_facts(docs)["haemoglobin"]["current"]["doc_id"] == "D1"
    docs = [_hb("D1", "12.5 g/dL", "2026-08-01", verification="unverified"), _hb("D2", "9.0 g/dL", "2026-09-04", verification="needs_review")]
    assert rules.resolve_facts(docs)["haemoglobin"]["current"]["doc_id"] == "D2"


def test_resolve_pending_newest_keeps_older_present_value():
    docs = [_hb("D1", "12.5 g/dL", "2026-08-01"), _hb("D2", "Pending", "2026-09-04", state="pending")]
    assert rules.resolve_facts(docs)["haemoglobin"]["current"]["doc_id"] == "D1"


def test_resolve_ignores_documents_not_ready():
    docs = [_hb("D1", "12.5 g/dL", "2026-08-01"), {**_hb("D2", "9.0 g/dL", "2026-09-04"), "state": "extracting"}]
    f = rules.resolve_facts(docs)["haemoglobin"]
    assert f["current"]["doc_id"] == "D1" and len(f["history"]) == 1


def test_resolve_same_date_corrected_wins_over_final():
    docs = [_hb("D2", "9.9 g/dL", "2026-09-04", status="CORRECTED"), _hb("D1", "9.0 g/dL", "2026-09-04", status="FINAL")]
    assert rules.resolve_facts(docs)["haemoglobin"]["current"]["doc_id"] == "D2"


def test_resolve_uses_attestation_override():
    docs = [_hb("D1", "12.5 g/dL", "2026-08-01"), _hb("D2", "9.0 g/dL", "2026-09-04", status="UNSTATED", signed="unknown")]
    assert rules.resolve_facts(docs)["haemoglobin"]["current"]["doc_id"] == "D1"
    ov = {"documents": {"D2": {"attested_final": True, "by": "Dr. Rao"}}}
    f = rules.resolve_facts(docs, ov)["haemoglobin"]
    assert f["current"]["doc_id"] == "D2" and f["history"][-1]["doc_final"] is True


# ---- sync_actions ------------------------------------------------------------------------------------------
def _sync(case_id):
    return rules.sync_actions(case_id, rules.evaluate(case_id))


def test_sync_opens_action_routed_to_department(unit_case):
    add(unit_case, hist())
    st = _sync(unit_case)
    assert len(st["actions"]) == 1
    a = st["actions"][0]
    assert (a["requirement"], a["department"], a["status"], a["source"]) == ("ct_thorax", "Radiology", "suggested", "pre_authorization")  # suggested, not sent (V2 item 4.2)
    assert a["what"] == "No diagnostic ct thorax report in the Case File"
    assert a["due"] is None and a["sla_days"] == 3  # the due date is set when the doctor sends it
    assert a["history"][0]["event"] == "Gap detected (Level 1: Case File), request to Radiology suggested (not sent)"
    assert (a["level"], a["level_label"], a["department_id"], a["source_doc_id"]) == (1, "Level 1: Case File", "radiology", None)
    assert store.get_state(unit_case)["gate"]["requirements"][1]["id"] == "ct_thorax"
    assert [e for e in store.read_audit(unit_case) if e["kind"] == "action_created"][0]["department"] == "Radiology"


def test_sync_uses_requirement_sla(unit_case):
    add(unit_case, hist(facts={"histologic_type": fact("Adenocarcinoma")}), ct())
    a = _sync(unit_case)["actions"][0]
    assert a["requirement"] == "pdl1" and a["department"] == "Pathology" and a["sla_days"] == 7 and a["due"] is None


def test_sync_is_idempotent_and_updates_the_gap(unit_case):
    add(unit_case, hist())
    _sync(unit_case)
    st = _sync(unit_case)
    assert len(st["actions"]) == 1 and len(st["actions"][0]["history"]) == 1
    add(unit_case, ct(facts={}))
    st = _sync(unit_case)
    a = st["actions"][0]
    assert len(st["actions"]) == 1 and a["what"] == "Required field not documented: Primary lesion size"
    assert a["history"][-1]["event"] == "Re-check: Level 2: Records routed to Radiology (suggested, not sent)" and a["level"] == 2 and a["source_doc_id"] == "Dct000001"
    st = _sync(unit_case)
    assert len(st["actions"][0]["history"]) == 2  # nothing changed: no new history entry


def test_sync_auto_completes_with_evidence(unit_case):
    add(unit_case, hist())
    _sync(unit_case)
    add(unit_case, ct())
    a = _sync(unit_case)["actions"][0]
    assert a["status"] == "completed" and a["completed"]
    assert a["history"][-1]["event"] == "Re-check: requirement met" and "Dct000001" in a["history"][-1]["evidence"]
    assert any(e["kind"] == "action_completed" and e["requirement"] == "ct_thorax" for e in store.read_audit(unit_case))
    assert len(_sync(unit_case)["actions"]) == 1  # completed actions stay completed, no new one


def test_sync_closes_a_request_when_the_record_is_no_longer_required(unit_case, monkeypatch):
    """V1 item 4.1: the CT is Essential only in the metastatic setting; once the coordinator records the non-metastatic setting at an
    Essential hospital the CT is shown, not counted, and its open request closes (audited) instead of staying open forever."""
    from tumour_board import protocol
    from tumour_board.tests.util import unit_protocol
    p = unit_protocol(); p["mandatory"][1]["tiers"] = {"metastatic": "a", "non_metastatic": "b"}
    monkeypatch.setattr(protocol, "get", lambda pid: protocol._normalise(p) if pid == "unit" else None)
    add(unit_case, hist())
    a = _sync(unit_case)["actions"][0]  # no setting recorded: the strictest tier (a) applies
    assert a["requirement"] == "ct_thorax" and a["status"] == "suggested"
    c = store.get_case(unit_case); c["setting"] = "non_metastatic"; c["hospital_level"] = "essential"; store.save_case(c)
    st = _sync(unit_case)
    assert [r["id"] for r in st["gate"]["shown"]] == ["ct_thorax"] and st["gate"]["shown"][0]["tier"] == "b"
    a = st["actions"][0]
    assert a["status"] == "completed" and a["history"][-1]["event"].startswith("Closed: no longer required for this Case File")
    assert any(e["kind"] == "action_completed" and e["reason"] == "requirement no longer required (NCG tier)" for e in store.read_audit(unit_case))


def test_sync_waiver_completes_action(unit_case):
    add(unit_case, hist())
    _sync(unit_case)
    rules.set_override(unit_case, "requirements", "ct_thorax", {"waived": True, "reason": "not needed"}, by="Dr. Rao")
    assert _sync(unit_case)["actions"][0]["status"] == "completed"


def test_sync_marks_overdue(unit_case):
    """A sent request (pending with a due date) becomes overdue; a suggestion has no due date and never does."""
    add(unit_case, hist())
    st = _sync(unit_case)
    st["actions"][0]["status"] = "pending"; st["actions"][0]["due"] = (date.today() - timedelta(days=1)).isoformat()
    store.save_state(unit_case, st)
    assert _sync(unit_case)["actions"][0]["status"] == "overdue"
    st = store.get_state(unit_case); st["actions"][0]["status"] = "suggested"; st["actions"][0]["due"] = None; store.save_state(unit_case, st)
    assert _sync(unit_case)["actions"][0]["status"] == "suggested"


# ---- notifications from the gate (V1 item 4.4) --------------------------------------------------------------
def _notes():
    import json
    from tumour_board import notify
    p = notify.path()
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_sync_notifies_the_department_and_the_coordinator(unit_case):
    """A new request is only suggested (V2 item 4.2): the department hears when the treating doctor sends it; the closing upload tells
    it the request closed; the coordinators hear once when the Case File becomes ready, not again on the next re-check."""
    from tumour_board import dept_requests
    add(unit_case, hist())
    a = _sync(unit_case)["actions"][0]
    assert [x for x in _notes() if x["kind"] == "request"] == [] and a["status"] == "suggested"
    a = dept_requests.send(unit_case, a["id"], "dr.meera", {"user": "dr.meera", "treating": {"breast_surgery": "member"}})
    n = [x for x in _notes() if x["kind"] == "request"]
    assert len(n) == 1 and n[0]["to"] == {"department": "radiology"} and n[0]["case_id"] == unit_case and n[0]["action_id"] == a["id"]
    assert n[0]["level"] == 1 and n[0]["title"].startswith("Diagnostic CT thorax report needed for SYNTHETIC, Test Patient")
    _sync(unit_case)
    assert len([x for x in _notes() if x["kind"] == "request"]) == 1  # nothing changed: no second notification
    add(unit_case, ct())
    st = _sync(unit_case)
    assert st["gate"]["passed"]
    closed = [x for x in _notes() if x["kind"] == "request_closed"]
    assert len(closed) == 1 and closed[0]["to"] == {"department": "radiology"} and closed[0]["action_id"] == a["id"]
    ready = [x for x in _notes() if x["kind"] == "case_ready"]
    assert len(ready) == 1 and ready[0]["to"] == {"role": "coordinator"} and "3 of 3" in ready[0]["text"]
    assert any(e["kind"] == "case_ready" and e["notified"] for e in store.read_audit(unit_case))
    _sync(unit_case)
    assert len([x for x in _notes() if x["kind"] == "case_ready"]) == 1


def test_a_notification_problem_never_breaks_the_gate(unit_case, monkeypatch):
    from tumour_board import notify

    def broken(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(notify, "notify", broken)
    add(unit_case, hist())
    st = _sync(unit_case)
    assert st["actions"][0]["status"] == "suggested" and st["gate"]["satisfied"] == 2


# ---- Case File signature: stale summary and briefs (V1 item 4.5) ------------------------------------------
def test_case_signature_changes_with_the_case_file(unit_case):
    from tumour_board import confirm
    add(unit_case, hist())
    s1 = rules.case_signature(unit_case)
    assert s1 == {**s1, "documents": 1, "ready": 1, "confirmations": 0, "protocol": "unit", "protocol_version": "0.0", "setting": "", "hospital_level": "essential"}  # the effective level (org.json default)
    assert rules.case_signature(unit_case)["hash"] == s1["hash"] and rules.stale_reason(s1, rules.case_signature(unit_case)) == ""
    add(unit_case, ct())
    s2 = rules.case_signature(unit_case)
    assert s2["hash"] != s1["hash"] and rules.stale_reason(s1, s2) == "The Case File changed since this was generated: 1 document added, 1 processed document added"
    confirm.record(unit_case, "attest_final", "Dct000001", {}, "", by="Dr. Rao")
    s3 = rules.case_signature(unit_case)
    assert rules.stale_reason(s2, s3) == "The Case File changed since this was generated: 1 clinician confirmation added"
    c = store.get_case(unit_case); c["setting"] = "metastatic"; store.save_case(c)
    assert rules.stale_reason(s3, rules.case_signature(unit_case)) == "The Case File changed since this was generated: the NCG setting changed"
    d = store.get_doc(unit_case, "Dct000001"); d["processed"] = "2026-10-11T07:00:00"; store.save_doc(unit_case, d)  # re-processed
    assert rules.stale_reason(s3, rules.case_signature(unit_case)).startswith("The Case File changed since this was generated")
    assert rules.stale_reason(None, s3) == ""  # nothing stored: nothing to compare (the export treats a missing signature as stale itself)


# ---- review fixes (Phase 4) ---------------------------------------------------------------------------------
def test_level2_gap_goes_to_the_department_that_uploaded_the_record(unit_case):
    """V1 item 4.2 (review M6): the CT uploaded by Nuclear Medicine lacks the lesion size: the Level 2 request moves from Radiology
    (Level 1, the record's owner) to Nuclear Medicine, both departments are told, and the history says so."""
    from tumour_board import dept_requests
    add(unit_case, hist())
    a = _sync(unit_case)["actions"][0]
    assert (a["requirement"], a["level"], a["department_id"]) == ("ct_thorax", 1, "radiology")
    dept_requests.send(unit_case, a["id"], "dr.meera", {"user": "dr.meera", "treating": {"breast_surgery": "member"}})  # the doctor sent it to Radiology (V2 item 4.2)
    add(unit_case, {**ct(facts={}), "department": "nuclear_medicine"})
    a = _sync(unit_case)["actions"][0]
    assert (a["level"], a["department"], a["department_id"], a["source_doc_id"]) == (2, "Nuclear Medicine", "nuclear_medicine", "Dct000001")
    assert a["history"][-1]["event"] == "Re-check: Level 2: Records routed to Nuclear Medicine (sent to Radiology earlier: send it again)"
    assert a["status"] == "suggested"  # the moved request is not forwarded by itself: the doctor sends it to Nuclear Medicine
    n = _notes()
    assert [x["to"] for x in n if x["kind"] == "request"] == [{"department": "radiology"}]
    moved = [x for x in n if x["kind"] == "request_closed"]
    assert len(moved) == 1 and moved[0]["to"] == {"department": "radiology"} and "moved to Nuclear Medicine" in moved[0]["title"]


def test_missing_value_of_a_facts_only_record_goes_to_its_responsible_department(unit_case):
    """Review M1: PD-L1 (facts only, Responsible Department Pathology) missing from a histopathology filed by another department:
    nobody uploaded a record "it should be in", so the Responsible Department is asked, not the uploader of the carrier."""
    add(unit_case, {**hist(facts={"histologic_type": fact("Adenocarcinoma")}), "department": "surgical_oncology"}, ct())
    g = rules.evaluate(unit_case)
    r = req(g, "pdl1")
    assert r["status"] == "missing_field" and r["level"] == 2 and r["source_doc_id"] is None
    a = rules.sync_actions(unit_case, g)["actions"][0]
    assert (a["requirement"], a["department"], a["department_id"]) == ("pdl1", "Pathology", "pathology")
    add(unit_case, {**hist(facts={"histologic_type": fact("Adenocarcinoma"), "pdl1": fact("Pending", state="pending")}), "department": "surgical_oncology"})
    a = _sync(unit_case)["actions"][0]  # a pending value sits in that report: its uploader is asked
    assert (a["department_id"], a["source_doc_id"]) == ("surgical_oncology", "Dhist0001")


def test_a_department_that_no_longer_exists_is_not_a_routing_target(unit_case):
    add(unit_case, hist(), {**ct(facts={}), "department": "closed_department"})
    a = _sync(unit_case)["actions"][0]
    assert (a["level"], a["department"], a["department_id"]) == (2, "Radiology", "radiology")


def test_waivers_on_records_the_protocol_no_longer_lists_are_shown(unit_case):
    """Review M4: a waiver recorded for a renamed or removed record never silently disappears."""
    add(unit_case, hist(), ct())
    rules.set_override(unit_case, "requirements", "old_record", {"waived": True, "reason": "done at the referring hospital"}, by="Dr. Rao")
    g = rules.evaluate(unit_case)
    assert g["orphaned_waivers"] == [{"requirement": "old_record", "by": "Dr. Rao", "reason": "done at the referring hospital", "at": g["orphaned_waivers"][0]["at"]}]
    rules.set_override(unit_case, "requirements", "ct_thorax", {"waived": True, "reason": "x"}, by="Dr. Rao")
    assert [w["requirement"] for w in rules.evaluate(unit_case)["orphaned_waivers"]] == ["old_record"]


def test_a_request_opened_before_the_two_levels_is_classified_without_a_notification(unit_case):
    add(unit_case, hist())
    st = _sync(unit_case)
    for k in ("level", "level_label", "department_id", "source_doc_id"):
        st["actions"][0].pop(k)  # as stored before V1 item 4.2
    store.save_state(unit_case, st)
    before = len(_notes())
    a = _sync(unit_case)["actions"][0]
    assert (a["level"], a["department_id"]) == (1, "radiology") and a["history"][-1]["event"] == "Re-check: Level 1: Case File"
    assert len(_notes()) == before


def test_closing_for_a_waiver_says_waived(unit_case):
    from tumour_board import dept_requests
    add(unit_case, hist())
    a = _sync(unit_case)["actions"][0]
    dept_requests.send(unit_case, a["id"], "dr.meera", {"user": "dr.meera", "treating": {"breast_surgery": "member"}})  # only a sent request closes with a notice (V2 item 4.2)
    rules.set_override(unit_case, "requirements", "ct_thorax", {"waived": True, "reason": "not needed"}, by="Dr. Rao")
    _sync(unit_case)
    closed = [x for x in _notes() if x["kind"] == "request_closed"]
    assert len(closed) == 1 and " waived for " in closed[0]["title"] and "waived" in closed[0]["text"]
