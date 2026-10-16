"""Pre-Authorization and unconfirmed document dates (V1 item 3.1 e): a date-dependent requirement, or a required value whose
current choice depends on an unconfirmed date, asks the clinician to confirm the date instead of guessing."""
from tumour_board import confirm, rules, store
from tumour_board.tests.util import add, fact, make_doc, req


def undated(doc):
    c = doc["classification"]
    c["report_date_iso"] = ""; c.pop("event_date_iso", None); c["date_unconfirmed"] = True; c["date_suggestion"] = "2026-09-01"
    return doc


def hist(**kw):
    return make_doc("Dhist0001", "histopathology", facts={"histologic_type": fact("Adenocarcinoma"), "pdl1": fact("TPS 60%")}, **kw)


def ct(**kw):
    kw.setdefault("region", "chest")
    return make_doc("Dct000001", "ct", facts={"lesion_size": fact("3.2 cm")}, **kw)


def test_undated_treatment_summary_asks_for_its_date(unit_case):
    add(unit_case, hist(), ct(), undated(make_doc("Dtx000001", "treatment_summary", title="RT COMPLETION SUMMARY")),
        make_doc("Dmri00001", "mri", region="pelvis", date="2026-09-20"))
    g = rules.evaluate(unit_case)
    r = req(g, "restaging_mri")
    assert r["status"] == "needs_confirmation"
    assert r["problems"][0] == "Confirm the date of RT COMPLETION SUMMARY: no document date was found in its text and the restaging mri pelvis must be dated after it"
    assert r["needs"] == [{"type": "confirm_dates", "doc_id": "Dtx000001"}]
    assert g["documents"]["date_unconfirmed"] == ["Dtx000001"] and not g["passed"]


def test_undated_restaging_mri_asks_instead_of_missing(unit_case):
    add(unit_case, hist(), ct(), make_doc("Dtx000001", "treatment_summary", date="2026-08-10"),
        undated(make_doc("Dmri00001", "mri", region="pelvis", title="MRI PELVIS")))
    r = req(rules.evaluate(unit_case), "restaging_mri")
    assert r["status"] == "needs_confirmation"
    assert r["problems"][0] == "Confirm the date of MRI PELVIS: no document date was found in its text and it must be dated after 2026-08-10"
    assert r["needs"] == [{"type": "confirm_dates", "doc_id": "Dmri00001"}] and r["postdate_reference"] == "2026-08-10"


def test_dated_mri_after_treatment_satisfies_despite_an_undated_one(unit_case):
    add(unit_case, hist(), ct(), make_doc("Dtx000001", "treatment_summary", date="2026-08-10"),
        undated(make_doc("Dmri00001", "mri", region="pelvis")), make_doc("Dmri00002", "mri", region="pelvis", date="2026-09-20"))
    assert req(rules.evaluate(unit_case), "restaging_mri")["status"] == "satisfied"


def test_confirmed_date_settles_the_check(unit_case):
    add(unit_case, hist(), ct(), make_doc("Dtx000001", "treatment_summary", date="2026-08-10"), undated(make_doc("Dmri00001", "mri", region="pelvis")))
    confirm.record(unit_case, "confirm_dates", "Dmri00001", {"event_date": "20/09/2026"}, by="Dr. Rao")
    g = rules.evaluate(unit_case)
    assert req(g, "restaging_mri")["status"] == "satisfied" and g["documents"]["date_unconfirmed"] == []
    confirm.record(unit_case, "confirm_dates", "Dmri00001", {"event_date": "01/08/2026"}, by="Dr. Rao")  # before treatment: a newer MRI is required
    r = req(rules.evaluate(unit_case), "restaging_mri")
    assert r["status"] == "missing_record" and r["problems"] == ["No restaging mri pelvis in the Case File dated after 2026-08-10"]


def test_confirmed_not_stated_still_counts_as_confirmed(unit_case):
    """The clinician says the document states no date: the question is settled, nothing stands in, the record cannot be placed after treatment."""
    add(unit_case, hist(), ct(), make_doc("Dtx000001", "treatment_summary", date="2026-08-10"), undated(make_doc("Dmri00001", "mri", region="pelvis")))
    confirm.record(unit_case, "confirm_dates", "Dmri00001", {"report_date": ""}, by="Dr. Rao")
    g = rules.evaluate(unit_case)
    assert req(g, "restaging_mri")["status"] == "missing_record" and g["documents"]["date_unconfirmed"] == []


def test_two_values_and_an_undated_document_ask_for_the_date(unit_case):
    a = hist(date="2026-09-01")
    b = undated(make_doc("Dhist0002", "histopathology", title="HPE REVIEW", facts={"histologic_type": fact("Squamous cell carcinoma"), "pdl1": fact("TPS 10%")}))
    add(unit_case, a, b, ct())
    g = rules.evaluate(unit_case)
    r = req(g, "pdl1")
    assert r["status"] == "needs_confirmation"
    assert r["problems"][0] == "Confirm the date of HPE REVIEW: no document date was found in its text and pd-l1 is documented more than once and the current value depends on the dates"
    assert {"type": "confirm_dates", "doc_id": "Dhist0002"} in r["needs"]
    assert req(g, "histopathology")["status"] == "needs_confirmation"


def test_single_undated_document_with_the_only_value_is_fine(unit_case):
    add(unit_case, undated(hist()), ct())
    g = rules.evaluate(unit_case)
    assert req(g, "pdl1")["status"] == "satisfied" and req(g, "histopathology")["status"] == "satisfied"
    assert g["documents"]["date_unconfirmed"] == ["Dhist0001"]


def test_attest_need_is_listed(unit_case):
    add(unit_case, hist(status="UNSTATED", signed="unknown"), ct())
    r = req(rules.evaluate(unit_case), "histopathology")
    assert r["status"] == "needs_confirmation" and r["needs"] == [{"type": "attest_final", "doc_id": "Dhist0001"}]


def test_date_flags_reach_the_gate(unit_case):
    d = hist(); d["classification"]["date_flags"] = ["report date is after today"]
    add(unit_case, d, ct())
    g = rules.evaluate(unit_case)
    assert g["documents"]["date_flags"] == {"Dhist0001": ["report date is after today"]} and req(g, "histopathology")["status"] == "satisfied"


def test_waived_requirement_is_not_asked_for_dates(unit_case):
    add(unit_case, hist(), ct(), undated(make_doc("Dtx000001", "treatment_summary")), undated(make_doc("Dmri00001", "mri", region="pelvis")))
    confirm.record(unit_case, "waive", "restaging_mri", {}, reason="restaging not required per board", by="Dr. Rao")
    assert req(rules.evaluate(unit_case), "restaging_mri")["status"] == "waived"


def test_confirm_dates_overlay_clears_unconfirmed(unit_case):
    confirm.record(unit_case, "confirm_dates", "Dhist0001", {"report_date": "04/09/2026"}, by="Dr. Iyer")
    c = confirm.apply_to_doc(undated(hist()), store.get_state(unit_case))["classification"]
    assert c["report_date_iso"] == "2026-09-04" and c["date_unconfirmed"] is False and c["report_date_assumed"] is False
    assert c["report_date_label"] == "confirmed by Dr. Iyer" and c["report_date_quote"] == "" and c["date_flags"] == []


def test_flagged_date_is_not_trusted_where_it_decides_the_check(unit_case):
    """Review of Phase 3: a date after today, before the DOB or on an uncertain OCR line is asked about like a missing one."""
    tx = make_doc("Dtx000001", "treatment_summary", title="RT SUMMARY", date="2026-08-10"); tx["classification"]["date_flags"] = ["event date is after today"]
    add(unit_case, hist(), ct(), tx, make_doc("Dmri00001", "mri", region="pelvis", date="2026-09-20"))
    r = req(rules.evaluate(unit_case), "restaging_mri")
    assert r["status"] == "needs_confirmation" and r["needs"] == [{"type": "confirm_dates", "doc_id": "Dtx000001"}]
    assert r["problems"][0].startswith("Confirm the date of RT SUMMARY: its date is flagged (event date is after today)")
    confirm.record(unit_case, "confirm_dates", "Dtx000001", {"event_date": "10/08/2026"}, by="Dr. Rao")
    assert req(rules.evaluate(unit_case), "restaging_mri")["status"] == "satisfied"


def test_same_value_in_two_undated_documents_is_not_asked(unit_case):
    a = hist(date="2026-09-01")
    b = undated(make_doc("Dhist0002", "histopathology", title="HPE COPY", facts={"histologic_type": fact("Adenocarcinoma"), "pdl1": fact("TPS 60%")}))
    add(unit_case, a, b, ct())
    assert req(rules.evaluate(unit_case), "pdl1")["status"] == "satisfied"


def test_confirming_one_date_clears_a_stand_in(unit_case):
    d = hist()  # report 2026-09-01, event stands in
    confirm.record(unit_case, "confirm_dates", "Dhist0001", {"report_date": "04/09/2026"}, by="Dr. Rao")
    c = confirm.apply_to_doc(d, store.get_state(unit_case))["classification"]
    assert c["report_date_iso"] == "2026-09-04" and c["event_date_iso"] == "" and c["event_date_assumed"] is False
    from tumour_board import dates
    dd = dates.doc_dates({"classification": c})
    assert dd["event"] == "2026-09-04" and dd["event_assumed"] and not dd["questionable"]
