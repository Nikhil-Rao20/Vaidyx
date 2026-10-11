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
    assert (a["requirement"], a["department"], a["status"], a["source"]) == ("ct_thorax", "Radiology", "pending", "pre_authorization")
    assert a["what"] == "No diagnostic ct thorax report in the Case File"
    assert a["due"] == (date.today() + timedelta(days=3)).isoformat()
    assert a["history"][0]["event"] == "Gap detected (Level 1: Case File), routed to Radiology"
    assert (a["level"], a["level_label"], a["department_id"], a["source_doc_id"]) == (1, "Level 1: Case File", "radio_diagnosis", None)
    assert store.get_state(unit_case)["gate"]["requirements"][1]["id"] == "ct_thorax"
    assert [e for e in store.read_audit(unit_case) if e["kind"] == "action_created"][0]["department"] == "Radiology"


def test_sync_uses_requirement_sla(unit_case):
    add(unit_case, hist(facts={"histologic_type": fact("Adenocarcinoma")}), ct())
    a = _sync(unit_case)["actions"][0]
    assert a["requirement"] == "pdl1" and a["department"] == "Pathology" and a["due"] == (date.today() + timedelta(days=7)).isoformat()


def test_sync_is_idempotent_and_updates_the_gap(unit_case):
    add(unit_case, hist())
    _sync(unit_case)
    st = _sync(unit_case)
    assert len(st["actions"]) == 1 and len(st["actions"][0]["history"]) == 1
    add(unit_case, ct(facts={}))
    st = _sync(unit_case)
    a = st["actions"][0]
    assert len(st["actions"]) == 1 and a["what"] == "Required field not documented: Primary lesion size"
    assert a["history"][-1]["event"] == "Re-check: Level 2: Records routed to Radiology" and a["level"] == 2 and a["source_doc_id"] == "Dct000001"
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
    assert a["requirement"] == "ct_thorax" and a["status"] == "pending"
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
    add(unit_case, hist())
    st = _sync(unit_case)
    st["actions"][0]["due"] = (date.today() - timedelta(days=1)).isoformat()
    store.save_state(unit_case, st)
    assert _sync(unit_case)["actions"][0]["status"] == "overdue"
