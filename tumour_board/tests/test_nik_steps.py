"""The guided Case File (21 Oct 2026, docs/ui/casefile-steps/DESIGN.md): GET /cases/{id}/steps (six sections with their status, the next
action, To do and Waiting, warnings, the patient at a glance, every document's check), the reason for discussion, the key-value checks,
setting aside the cancer warning, and the one count of what is left before the board. Synthetic Case Files only (the TB-001 fixture and
hand-made documents); no model is ever called."""
from tumour_board import service, steps, store
from tumour_board.tests import util
from tumour_board.tests.test_nik_slots import CASE, FakeAuth, nik_app, people, tb001  # noqa: F401


def section(v, sid):
    return next(s for s in v["sections"] if s["id"] == sid)


def get(tc, case=CASE):
    r = tc.get(f"/api/tb/cases/{case}/steps")
    assert r.status_code == 200, r.text
    return r.json()


# ---- the view ----------------------------------------------------------------------------------------------------------------------

def test_the_consultant_prepares_in_six_sections(nik_app, tb001):
    tc, who = nik_app
    v = get(tc)
    assert v["mode"] == "prepare" and v["role"] == "consultant"
    assert [s["id"] for s in v["sections"]] == ["overview", "question", "reports", "check", "pre_authorization", "summary"]
    # the OPD note carries a question, but it counts only when the doctor writes it (owner, B3)
    assert section(v, "question")["status"] == "not_started" and v["question"]["text"] == "" and v["question"]["note_text"]
    assert v["next"]["section"] == "question" and v["todo"][0]["id"] == "question"
    assert v["left"] == steps.open_count(CASE) >= 1
    # the draft histopathology report: what the board still needs, grouped by the department that receives the request
    groups = {g["department"]["label"]: [i["label"] for i in g["items"]] for g in v["pre_authorization"]["groups"]}
    assert "Pathology department" in groups and section(v, "pre_authorization")["status"] == "todo"
    req = next(t for t in v["todo"] if t["section"] == "pre_authorization")
    assert req["action"]["kind"] == "ask_department" and req["action"]["label"] == "Send request to Pathology department"
    # typing the question settles it, and the next thing is sending the requests (they take days)
    r = tc.post(f"/api/tb/cases/{CASE}/slots/fact:clinical_question/value", json={"value": "Fitness for surgery?"})
    assert r.status_code == 200, r.text
    v2 = get(tc)
    assert section(v2, "question")["status"] == "done" and v2["question"]["text"] == "Fitness for surgery?"
    assert v2["left"] == v["left"] - 1 == steps.open_count(CASE)
    assert v2["next"]["section"] == "pre_authorization" and v2["next"]["label"].startswith("Send ")


def test_others_read_three_sections(nik_app, tb001):
    tc, who = nik_app
    who["user"] = "anil"  # the MDT Coordinator reads; a doctor of a department not on the Case File cannot open it at all
    v = get(tc)
    assert v["mode"] == "read" and [s["id"] for s in v["sections"]] == ["overview", "reports", "summary"]
    assert v["todo"] == [] and v["next"] is None
    who["user"] = "dr.nair"
    assert tc.get(f"/api/tb/cases/{CASE}/steps").status_code == 403


def test_the_reason_for_discussion(nik_app, tb001):
    tc, who = nik_app
    assert tc.put(f"/api/tb/cases/{CASE}/reason", json={"value": "whatever"}).status_code == 400
    r = tc.put(f"/api/tb/cases/{CASE}/reason", json={"value": "after_surgery"})
    assert r.status_code == 200 and r.json()["label"] == "After surgery: plan next"
    assert get(tc)["question"]["reason"]["value"] == "after_surgery"
    assert "board_reason" in [e.get("kind") for e in store.read_audit(CASE)]
    who["user"] = "dr.nair"
    assert tc.put(f"/api/tb/cases/{CASE}/reason", json={"value": "other"}).status_code == 403


def test_typed_facts_reports_rarely_carry(nik_app, tb001):
    tc, who = nik_app
    for fid, value, want in (("patient_awareness", "partly", "Partly"), ("patient_preference", "Wants breast conservation", "Wants breast conservation"),
                             ("comorbidities", "Type 2 diabetes on metformin", "Type 2 diabetes on metformin")):
        r = tc.post(f"/api/tb/cases/{CASE}/slots/fact:{fid}/value", json={"value": value})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "entered" and r.json()["value"] == want
    assert tc.post(f"/api/tb/cases/{CASE}/slots/fact:patient_awareness/value", json={"value": "maybe"}).status_code == 400
    extras = {x["fact_id"]: x for x in get(tc)["question"]["extras"]}
    assert extras["patient_awareness"]["value"] == "Partly" and extras["patient_awareness"]["entered_by"] == "Dr Rao"


# ---- documents ---------------------------------------------------------------------------------------------------------------------

def test_a_signature_flag_alone_never_makes_a_draft_final():
    d = util.make_doc("D9", "ct", status="UNSTATED", signed="unclear"); d["his"] = {"signed": True}
    assert steps.final_status(d)["final"] is False and steps.final_status(d)["label"] == "Status not stated" and steps.final_status(d)["warn"]
    assert steps.final_status(util.make_doc("D9", "ct"))["label"] == "Final, signed" and not steps.final_status(util.make_doc("D9", "ct"))["warn"]
    assert steps.final_status(util.make_doc("D9", "mammogram", status="PRELIMINARY", signed="no"))["label"] == "Preliminary, not signed yet"
    d = util.make_doc("D9", "ct"); d["his"] = {"status": "preliminary", "signed": False}
    assert steps.final_status(d)["preliminary"] is True  # the stricter of the text and the hospital system


def test_a_value_only_in_a_report_not_signed_is_shown_marked():
    """Owner, 2 Nov 2026: the value of a report that is final but not signed is shown with its line and the mark "not signed" (never
    counted: the row stays not found); every chip citing such a report gets the same mark, on a copy."""
    q = {"doc_id": "D1", "doc_title": "HISTOPATHOLOGY REPORT", "page": 0, "text": "Grade: Moderately differentiated"}
    s = {"id": "fact:grade", "fact_id": "grade", "label": "Grade", "status": "not_found", "note": "Only in a non-final document (HISTOPATHOLOGY REPORT)",
         "draft": {"doc_id": "D1", "doc_title": "HISTOPATHOLOGY REPORT", "status": "FINAL", "value": "Moderately differentiated", "quote": q}}
    row = steps._row(s)
    assert row["status"] == "not_found" and row["value"] == "" and row["unsigned"] == {"value": "Moderately differentiated", "word": "not signed", "quote": q}
    assert "unsigned" not in steps._row({**s, "status": "found", "value": "Moderately differentiated"})
    assert "unsigned" not in steps._row({**s, "draft": {**s["draft"], "value": ""}})
    assert [steps.unsigned_word(x) for x in ("FINAL", "PRELIMINARY", "")] == ["not signed", "preliminary", "not final"]
    docs = [util.make_doc("D1", "histopathology", status="FINAL", signed="no"), util.make_doc("D2", "ct"),
            util.make_doc("D3", "mammogram", status="PRELIMINARY", signed="no")]
    words = steps.unsigned_words("TB-X", docs)
    assert words == {"D1": "not signed", "D3": "preliminary"}
    node = {"sections": [{"sentences": [{"text": "a", "citations": [{"doc_id": "D1"}, {"doc_id": "D2"}]}]}], "points": [{"citations": [{"doc_id": "D3"}]}]}
    marked = steps.mark_citations(node, words)
    assert marked["sections"][0]["sentences"][0]["citations"] == [{"doc_id": "D1", "final_word": "not signed"}, {"doc_id": "D2"}]
    assert marked["points"][0]["citations"] == [{"doc_id": "D3", "final_word": "preliminary"}]
    assert "final_word" not in node["sections"][0]["sentences"][0]["citations"][0]  # the saved summary is not touched


def test_the_check_of_one_document():
    case = {"protocol": "lung_nsclc"}
    good = util.make_doc("D2", "ct", facts={"lesion_size": util.fact("3.2 cm", quote="Size: 3.2 cm")}); good["extracted_under"] = "lung_nsclc"
    c = steps.doc_check(good, case)
    assert c["status"] == "checked" and c["reasons"] == [] and [x["value"] for x in c["values"]] == ["3.2 cm"]
    bad = util.make_doc("D1", "histopathology", identity="id_differs",
                        facts={"grade": util.fact("2", verification="needs_review"), "egfr": util.fact("Exon 19", verification="unverified")})
    bad["extracted_under"] = "breast"
    c = steps.doc_check(bad, case)
    assert c["status"] == "please_check" and c["values"] == []
    assert c["reasons"] == ["The patient's name or number does not match this Case File", "1 line unclear", "1 value could not be matched to a line",
                            "Read before the cancer was changed: read it again for this cancer"]
    assert steps.doc_check(util.make_doc("D3", "ct", state="reading"), case)["status"] == "reading"
    assert steps.doc_check({**util.make_doc("D4", "ct", state="error"), "error": "bad pdf"}, case)["status"] == "failed"


def test_reports_are_grouped_by_type(nik_app, tb001):
    tc, who = nik_app
    docs = get(tc)["documents"]
    assert docs and all(d["group"] in {g for g, _, _ in steps.DOC_GROUPS} for d in docs)
    hp = next(d for d in docs if d["doc_type"] == "histopathology")
    assert hp["group"] == "pathology" and hp["final"]["final"] is False  # the fixture's histopathology report is a draft


# ---- warnings ----------------------------------------------------------------------------------------------------------------------

def _doc(doc_id, title):
    return {"doc_id": doc_id, "title": title, "date": "2026-10-20", "check": {"status": "checked", "reasons": []}, "final": {"preliminary": False}}


def _view(**facts):
    return {"sections": [{"slots": [{"kind": "fact", "fact_id": k, "status": "found", "value": v, "label": k.replace("_", " ").title()} for k, v in facts.items()]}]}


def test_the_cancer_chosen_against_the_reports():
    case = {"protocol": "cervix"}
    docs = [_doc("D1", "BILATERAL MAMMOGRAPHY REPORT"), _doc("D2", "HISTOPATHOLOGY REPORT"), _doc("D3", "CECT CHEST, ABDOMEN AND PELVIS")]
    w = steps.warnings(case, docs, _view(histologic_type="Invasive breast carcinoma of no special type"))
    assert [x["kind"] for x in w] == ["cancer_mismatch"]
    assert w[0]["text"].startswith("The reports mention the breast (Bilateral mammography report; histologic type:")
    assert w[0]["text"].endswith("none mention the cervix. This Case File is set to Cervix cancer.")
    assert [f["kind"] for f in w[0]["fixes"]] == ["change_cancer", "dismiss"]
    # one mention is not enough; a report that names the cervix settles it (a second primary is real)
    assert steps.warnings(case, docs, _view()) == []
    assert steps.warnings(case, docs + [_doc("D4", "MRI PELVIS (CERVIX PROTOCOL)")], _view(histologic_type="Invasive breast carcinoma")) == []
    # set aside once, it stays set aside
    assert steps.warnings({**case, "warnings_dismissed": {w[0]["id"]: {"by": "dr.rao"}}}, docs, _view(histologic_type="Invasive breast carcinoma")) == []


def test_only_the_cancer_warning_can_be_set_aside(nik_app, tb001):
    tc, who = nik_app
    assert tc.post(f"/api/tb/cases/{CASE}/warnings/identity:D1/dismiss").status_code == 409
    r = tc.post(f"/api/tb/cases/{CASE}/warnings/cancer:lung_nsclc:breast/dismiss")
    assert r.status_code == 200 and store.get_case(CASE)["warnings_dismissed"]["cancer:lung_nsclc:breast"]["by"] == "dr.rao"


# ---- key values ----------------------------------------------------------------------------------------------------------------------

def test_key_values_stay_confirmed_while_the_same_value_stands(nik_app, tb001):
    tc, who = nik_app
    util.add(CASE, util.make_doc("DK1", "ihc", title="PD-L1 IHC REPORT", facts={"pdl1": util.fact("TPS 60 %", quote="PD-L1 (22C3): TPS 60 %")}))
    service.recheck(CASE, "test")
    keys = [k for k in get(tc)["check"]["keys"] if k["fact_id"] == "pdl1"]
    assert keys, "a verified PD-L1 from a final report is a key value to confirm"
    k = keys[0]
    assert k["confirmed"] is False
    left = get(tc)["left"]
    r = tc.post(f"/api/tb/cases/{CASE}/key-checks", json={"fact_id": k["fact_id"], "value": k["value"], "doc_id": k["quote"]["doc_id"]})
    assert r.status_code == 200, r.text
    v = get(tc)
    k2 = next(x for x in v["check"]["keys"] if x["fact_id"] == k["fact_id"])
    assert k2["confirmed"] is True and k2["confirmed_by"] == "Dr Rao" and v["left"] == left - 1
    # a different value (a new report) makes it a to-do again; the confirmation never changes the value
    st = store.get_state(CASE); st["key_checks"][k["fact_id"]]["value"] = "something else"; store.save_state(CASE, st)
    assert next(x for x in get(tc)["check"]["keys"] if x["fact_id"] == k["fact_id"])["confirmed"] is False
    assert tc.delete(f"/api/tb/cases/{CASE}/key-checks/{k['fact_id']}").status_code == 200
    assert tc.delete(f"/api/tb/cases/{CASE}/key-checks/{k['fact_id']}").status_code == 404
    assert "key_value_confirmed" in [e.get("kind") for e in store.read_audit(CASE)]
    who["user"] = "dr.nair"
    assert tc.post(f"/api/tb/cases/{CASE}/key-checks", json={"fact_id": k["fact_id"], "value": k["value"]}).status_code == 403


def test_the_count_is_one_everywhere(nik_app, tb001):
    tc, who = nik_app
    n = steps.open_count(CASE)
    assert n == get(tc)["left"]
    rows = {x["case_id"]: x for x in tc.get("/api/tb/case-list").json()["cases"]}
    assert rows[CASE]["left_before_board"] == n


# ---- a resident's sign-offs (night-v3 item 1.8): the reason and a key value become proposals the consultant approves ------------------

def _outsider(people):
    """A resident of a department not on the Case File (not on its team)."""
    import copy
    from tumour_board import org
    o = copy.deepcopy(people)
    o["users"]["res.kiran"] = {"departments": {"breast_surgery": "resident"}, "display_name": "Dr Kiran"}
    org.save(o, by="test")


def _approve(tc, who, pid, user="dr.rao"):
    who["user"] = user
    return tc.post(f"/api/tb/cases/{CASE}/proposals/{pid}/approve")


def _pending(pid):
    from tumour_board import proposals
    return proposals.find(store.get_case(CASE), pid)["status"]


def test_a_residents_reason_for_discussion_is_signed_off_by_the_consultant(nik_app, tb001, people):
    tc, who = nik_app
    _outsider(people)
    who["user"] = "res.asha"
    assert tc.put(f"/api/tb/cases/{CASE}/reason", json={"value": "whatever"}).status_code == 400  # checked before it is stored
    r = tc.put(f"/api/tb/cases/{CASE}/reason", json={"value": "recurrence"})
    assert r.status_code == 200, r.text
    p = r.json()["proposal"]
    assert p["action"] == "reason" and p["payload"] == {"value": "recurrence"} and p["status"] == "pending" and p["by"] == "res.asha"
    assert store.get_case(CASE).get("board_reason") is None  # nothing changed yet
    assert "board_reason" not in [e.get("kind") for e in store.read_audit(CASE)]
    # the consultant sees it under "Sign-offs from your team" and approves: written in the consultant's name
    who["user"] = "dr.rao"
    assert get(tc)["signoffs"] == 1
    r = _approve(tc, who, p["id"])
    assert r.status_code == 200, r.text
    rec = store.get_case(CASE)["board_reason"]
    assert rec["value"] == "recurrence" and rec["by"] == "dr.rao"
    ev = next(e for e in store.read_audit(CASE) if e.get("kind") == "board_reason")
    assert ev["by"] == "dr.rao"
    ap = next(e for e in store.read_audit(CASE) if e.get("kind") == "proposal_approved")
    assert ap["by"] == "dr.rao" and ap["proposed_by"] == "res.asha" and ap["action"] == "reason"
    # a resident not on the team, and a doctor of another department, are refused; the consultant's own call works as before
    who["user"] = "res.kiran"
    assert tc.put(f"/api/tb/cases/{CASE}/reason", json={"value": "other"}).status_code == 403
    who["user"] = "dr.nair"
    assert tc.put(f"/api/tb/cases/{CASE}/reason", json={"value": "other"}).status_code == 403
    who["user"] = "dr.rao"
    r = tc.put(f"/api/tb/cases/{CASE}/reason", json={"value": "other"})
    assert r.status_code == 200 and "proposal" not in r.json() and store.get_case(CASE)["board_reason"]["value"] == "other"


def test_a_residents_key_value_check_is_signed_off_unless_the_value_changed(nik_app, tb001, people):
    tc, who = nik_app
    _outsider(people)
    util.add(CASE, util.make_doc("DK1", "ihc", title="PD-L1 IHC REPORT", facts={"pdl1": util.fact("TPS 60 %", quote="PD-L1 (22C3): TPS 60 %")}))
    service.recheck(CASE, "test")
    k = next(x for x in get(tc)["check"]["keys"] if x["fact_id"] == "pdl1")
    body = {"fact_id": "pdl1", "value": k["value"], "doc_id": k["quote"]["doc_id"]}
    who["user"] = "res.asha"
    assert tc.post(f"/api/tb/cases/{CASE}/key-checks", json={**body, "fact_id": "PD-L1!"}).status_code == 400
    r = tc.post(f"/api/tb/cases/{CASE}/key-checks", json=body)
    assert r.status_code == 200, r.text
    p = r.json()["proposal"]
    assert p["action"] == "key_value" and p["payload"] == body
    assert "pdl1" not in (store.get_state(CASE).get("key_checks") or {})  # nothing changed yet
    assert "key_value_confirmed" not in [e.get("kind") for e in store.read_audit(CASE)]
    # a proposal on another report is stale at approval: 409, and it stays pending
    stale = tc.post(f"/api/tb/cases/{CASE}/key-checks", json={**body, "doc_id": "DX0"}).json()["proposal"]
    r = _approve(tc, who, stale["id"])
    assert r.status_code == 409 and "check it again" in r.text and _pending(stale["id"]) == "pending"
    # the consultant approves the right one: confirmed in the consultant's name, and the Check step shows it
    r = _approve(tc, who, p["id"])
    assert r.status_code == 200, r.text
    kc = store.get_state(CASE)["key_checks"]["pdl1"]
    assert kc["by"] == "dr.rao" and kc["value"] == k["value"] and kc["doc_id"] == k["quote"]["doc_id"]
    ev = next(e for e in store.read_audit(CASE) if e.get("kind") == "key_value_confirmed")
    assert ev["by"] == "dr.rao" and ev["fact"] == "pdl1"
    k2 = next(x for x in get(tc)["check"]["keys"] if x["fact_id"] == "pdl1")
    assert k2["confirmed"] is True and k2["confirmed_by"] == "Dr Rao"
    # the value changes after the resident checked it (a corrected report): the approval is refused and the proposal stays pending
    who["user"] = "res.asha"
    again = tc.post(f"/api/tb/cases/{CASE}/key-checks", json=body).json()["proposal"]
    util.add(CASE, util.make_doc("DK1", "ihc", title="PD-L1 IHC REPORT", facts={"pdl1": util.fact("TPS 10 %", quote="PD-L1 (22C3): TPS 10 %")}))
    service.recheck(CASE, "test")
    r = _approve(tc, who, again["id"])
    assert r.status_code == 409 and _pending(again["id"]) == "pending"
    # a resident not on the team is refused; the consultant's own call works as before
    who["user"] = "res.kiran"
    assert tc.post(f"/api/tb/cases/{CASE}/key-checks", json=body).status_code == 403
    who["user"] = "dr.rao"
    r = tc.post(f"/api/tb/cases/{CASE}/key-checks", json={**body, "value": "TPS 10 %"})
    assert r.status_code == 200 and "proposal" not in r.json() and r.json()["by"] == "dr.rao"


# ---- night-v3 item 3.4: after the first decision the Summary section follows the Case summary -----------------------------------

def test_the_summary_section_follows_the_case_summary(nik_app, tb001, monkeypatch):
    import asyncio
    from tumour_board import case_summary as cs, llm, postboard, summary
    tc, who = nik_app

    async def chat(role, msgs, **kw):  # no model: the adjudication finds no claims, the summaries get no model sentence
        return {"claims": [], "sentences": [], "points_for_review": []}
    monkeypatch.setattr(llm, "chat", chat)
    v = get(tc)
    assert v["summary"]["case_summary"] is None and set(v["summary"]) == {"prose", "sent", "case_summary", "history"}
    plain = section(v, "summary")
    assert plain["detail"] in ("Not started", "Read it", "Done", "Records changed: write it again", "Being written")  # as before item 3.4
    asyncio.run(summary.build(CASE, force=True))
    asyncio.run(summary.build(CASE, force=True))
    h = get(tc)["summary"]["history"]
    assert len(h) >= 2 and h[-1]["live"] is True and h[0]["live"] is False and h[0]["archived_at"]
    assert set(h[0]) == {"generated", "archived_at", "review", "model", "paragraphs", "points_for_review", "stage_as_recorded", "live", "sentences", "full"}
    assert h[0]["full"] is True and h[-1]["full"] is True
    assert set(h[0]["review"]) >= {"status", "by", "at"} and all(set(p) == {"id", "title", "sentences"} for p in h[0]["paragraphs"])
    decision = {"outcome": "decision", "decision_text": "Concurrent chemoradiation.", "intent": "curative", "responsible_doctor": "Dr Rao", "board_date": "2026-10-20"}
    asyncio.run(postboard.record_decision(CASE, decision, "anil"))
    asyncio.run(cs.build(CASE, {"kind": "decision"}, "anil"))
    v = get(tc)
    cv = v["summary"]["case_summary"]
    assert cv["status"] == "ready" and cv["current"] == 1 and cv["can"] == {"build": True, "review": True, "edit": True}
    assert [s["id"] for s in cv["sections"]] == ["presentation", "stage", "rounds", "since", "status"] and cv["first_board_date"] == "2026-10-20"
    assert section(v, "summary")["status"] == "todo" and section(v, "summary")["detail"] == "Read the Case summary"
    assert any(t["id"] == "case_summary" and t["label"] == "Read the Case summary" for t in v["todo"])
    assert v["summary"]["prose"]["paragraphs"]  # the live pre-board summary stays as it was for every existing reader
    asyncio.run(postboard.record_decision(CASE, {**decision, "board_date": "2026-10-27"}, "anil"))  # a later decision: out of date
    v = get(tc)
    assert v["summary"]["case_summary"]["status"] == "stale" and "board record" in v["summary"]["case_summary"]["stale_reason"]
    assert section(v, "summary")["status"] == "todo" and section(v, "summary")["detail"] == "Decision recorded: update the Case summary"
    assert any(t["id"] == "case_summary" and t["label"] == "Update the Case summary" for t in v["todo"])
    cs.RUNNING[CASE] = {"started": 0, "trigger": {}, "user": "anil"}
    try:
        v = get(tc)
        assert section(v, "summary")["status"] == "working" and section(v, "summary")["detail"] == "Being written"
        assert not any(t["id"] == "case_summary" for t in v["todo"])
    finally:
        cs.RUNNING.pop(CASE, None)
    asyncio.run(cs.build(CASE, {"kind": "decision"}, "anil"))
    cs.review(CASE, 2, "reviewed", "", "dr.rao")
    v = get(tc)
    assert section(v, "summary")["status"] == "done" and section(v, "summary")["detail"] == "Reviewed"
    assert v["summary"]["case_summary"]["label"] == "Reviewed by Dr Rao" and not any(t["id"] == "case_summary" for t in v["todo"])
    who["user"] = "anil"  # the MDT Coordinator reads: may write it again, not review or edit it
    assert get(tc)["summary"]["case_summary"]["can"] == {"build": True, "review": False, "edit": False}
