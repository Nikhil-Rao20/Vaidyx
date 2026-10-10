"""Document type cross-check in the gate (V1 item 3.2): a document whose title keywords disagree with the reader model's type counts
under both types, and a requirement it matches under only one of them asks the clinician to confirm the type; `other` documents are
asked only for the protocol's required fields; the region check reads the header text."""
import asyncio

from tumour_board import confirm, protocol, rules, service, store
from tumour_board.tests.util import add, fact, make_doc, req


def disagree(doc, keyword_type, note=None):
    c = doc["classification"]
    c["doc_type_keyword"] = keyword_type
    c["doc_type_disagreement"] = {"keyword_type": keyword_type, "model_type": c["doc_type"], "note": note or f"the title line says {keyword_type.upper()} ({keyword_type}); the reader model said {c['doc_type']}"}
    return doc


def hist(facts=None, **kw):
    return make_doc("Dhist0001", "histopathology", facts={"histologic_type": fact("Adenocarcinoma"), "pdl1": fact("TPS 60%")} if facts is None else facts, **kw)


def ct(**kw):
    kw.setdefault("region", "chest")
    return make_doc("Dct000001", "ct", facts={"lesion_size": fact("3.2 cm")}, **kw)


def test_model_mri_but_title_says_ct_asks_for_confirmation(unit_case):
    """The reader called the CT thorax an MRI: without the keyword check the CT requirement would be missing; now it asks."""
    add(unit_case, hist(), disagree(make_doc("Dct000001", "mri", region="chest", title="CECT THORAX", facts={"lesion_size": fact("3.2 cm")}), "ct"))
    g = rules.evaluate(unit_case)
    r = req(g, "ct_thorax")
    assert r["status"] == "needs_confirmation"
    assert r["problems"][0] == "Confirm the document type of CECT THORAX: the title line says CT (ct); the reader model said mri"
    assert r["needs"] == [{"type": "confirm_doc_type", "doc_id": "Dct000001"}]
    assert g["documents"]["type_disagreements"] == ["Dct000001"] and not g["passed"]


def test_model_ct_but_title_says_mri_asks_instead_of_satisfying(unit_case):
    """The reader called an MRI a CT: it must not satisfy the CT requirement silently."""
    add(unit_case, hist(), disagree(ct(title="MRI BRAIN"), "mri"))
    r = req(rules.evaluate(unit_case), "ct_thorax")
    assert r["status"] == "needs_confirmation" and r["needs"] == [{"type": "confirm_doc_type", "doc_id": "Dct000001"}]


def test_agreeing_types_or_no_keyword_evidence_leave_the_gate_alone(unit_case):
    add(unit_case, hist(), ct())
    g = rules.evaluate(unit_case)
    assert req(g, "ct_thorax")["status"] == "satisfied" and g["passed"] and g["documents"]["type_disagreements"] == []


def test_confirmed_type_ends_the_question(unit_case):
    add(unit_case, hist(), disagree(make_doc("Dct000001", "mri", region="chest", title="CECT THORAX", facts={"lesion_size": fact("3.2 cm")}), "ct"))
    confirm.record(unit_case, "confirm_doc_type", "Dct000001", {"doc_type": "ct"}, by="Dr. Rao")
    g = rules.evaluate(unit_case)
    assert req(g, "ct_thorax")["status"] == "satisfied" and g["documents"]["type_disagreements"] == []
    confirm.record(unit_case, "confirm_doc_type", "Dct000001", {"doc_type": "mri"}, by="Dr. Rao")
    assert req(rules.evaluate(unit_case), "ct_thorax")["status"] == "missing_record"


def test_facts_only_requirement_asks_when_the_value_comes_from_a_disputed_document(unit_case):
    """PD-L1 may come from histopathology or IHC; a document the model called lab but titled IHC matches under one type only."""
    add(unit_case, hist(facts={"histologic_type": fact("Adenocarcinoma")}), ct(),
        disagree(make_doc("Dihc00001", "lab", title="IMMUNOHISTOCHEMISTRY REPORT", facts={"pdl1": fact("TPS 60%")}), "ihc"))
    r = req(rules.evaluate(unit_case), "pdl1")
    assert r["status"] == "needs_confirmation" and r["needs"] == [{"type": "confirm_doc_type", "doc_id": "Dihc00001"}]
    assert r["problems"][0].startswith("Confirm the document type of IMMUNOHISTOCHEMISTRY REPORT")


def test_disputed_document_matching_under_both_types_is_fine(unit_case):
    add(unit_case, disagree(hist(title="HPE / IHC"), "ihc"), ct())  # pdl1 accepts histopathology and ihc alike
    g = rules.evaluate(unit_case)
    assert req(g, "pdl1")["status"] == "satisfied"
    assert req(g, "histopathology")["status"] == "needs_confirmation"  # the histopathology requirement takes histopathology only


def test_waived_requirement_is_not_asked(unit_case):
    add(unit_case, hist(), disagree(ct(title="MRI BRAIN"), "mri"))
    confirm.record(unit_case, "waive", "ct_thorax", {}, reason="CT at the referring hospital", by="Dr. Rao")
    assert req(rules.evaluate(unit_case), "ct_thorax")["status"] == "waived"


def test_region_check_reads_the_header_text(unit_case):
    d = ct(region="", title="CT REPORT", filename="scan.pdf")
    d["pages"] = [{"text": "Sahyadri Cancer Institute (SYNTHETIC)\nDepartment of Radio-diagnosis\nCECT THORAX WITH CONTRAST\nFindings: ...", "method": "text-layer"}]
    add(unit_case, hist(), d)
    assert req(rules.evaluate(unit_case), "ct_thorax")["status"] == "satisfied"
    d["pages"] = [{"text": "Sahyadri Cancer Institute (SYNTHETIC)\nDepartment of Radio-diagnosis\nCECT ABDOMEN\n" + "Findings line\n" * 20 + "thorax mentioned deep in the body", "method": "text-layer"}]
    add(unit_case, d)
    assert req(rules.evaluate(unit_case), "ct_thorax")["status"] == "missing_record"


def test_other_documents_get_only_the_required_fields():
    for pid in ("lung_nsclc", "breast", "colorectal_rectum"):
        p = protocol.get(pid)
        required = {f for r in p["mandatory"] for f in r.get("required_facts", [])}
        got = protocol.facts_for_doc(pid, "other")
        assert set(got) == required & set(protocol.facts()) and len(got) < len(p["extract_facts"]) + len(required)
    assert "lesion_size" in protocol.facts_for_doc("lung_nsclc", "ct") and "pdl1" not in protocol.facts_for_doc("lung_nsclc", "ct")


def test_reextract_uses_the_confirmed_type(unit_case, monkeypatch):
    """After confirm_doc_type the fields are extracted again from the stored pages, under the confirmed type, with no second read."""
    from tumour_board import extract, ingest
    asked, read = [], []

    async def fake_pages(path, audit=None):
        read.append(path); return [{"text": "SYNTHETIC\nCECT THORAX\nLesion 3.2 cm\nReported on 04/09/2026", "method": "text-layer"}]

    async def fake_classify(t, audit=None):
        return {"title": "CECT THORAX", "department": "Radiology", "doc_type": "lab", "body_region": "chest", "report_date": "", "status_quote": "", "signature_quote": "", "signer": "", "patient_name": "", "patient_id": ""}

    async def fake_facts(t, fids, audit=None, pages=None):
        asked.append(sorted(fids)); return {f: {"found": False, "value": "", "quote": ""} for f in fids}
    monkeypatch.setattr(ingest, "extract_pages", fake_pages); monkeypatch.setattr(extract, "classify", fake_classify); monkeypatch.setattr(extract, "extract_facts", fake_facts)
    c = store.get_case(unit_case); c["protocol"] = "lung_nsclc"; store.save_case(c)  # a real protocol: mri and ct ask for different fields
    doc = store.add_document_file(unit_case, "cect_thorax.txt", b"synthetic")
    asyncio.run(extract.process_document(unit_case, doc["doc_id"], "lung_nsclc", {"mrn": "SYN-900001", "name": "SYNTHETIC, Test Patient"}))
    lab, ct_ = sorted(protocol.facts_for_doc("lung_nsclc", "lab")), sorted(protocol.facts_for_doc("lung_nsclc", "ct"))
    assert lab != ct_ and asked[-1] == lab and len(read) == 1
    confirm.record(unit_case, "confirm_doc_type", doc["doc_id"], {"doc_type": "ct"}, by="Dr. Rao")

    async def go():
        job = service.reextract_document(unit_case, doc["doc_id"], "Dr. Rao"); await job["task"]; return job
    job = asyncio.run(go())
    assert job["state"] == "finished" and asked[-1] == ct_ and len(read) == 1  # no second read
    assert [e for e in store.read_audit(unit_case) if e["kind"] == "reextract"][0]["doc_id"] == doc["doc_id"]
    assert store.get_doc(unit_case, doc["doc_id"])["state"] == "ready"


def test_reextract_refuses_unlisted_or_unread(unit_case):
    doc = store.add_document_file(unit_case, "x.txt", b"synthetic")
    assert service.reextract_document(unit_case, doc["doc_id"]) is None  # never read
    c = store.get_case(unit_case); c["protocol"] = ""; store.save_case(c)
    add(unit_case, hist())
    assert service.reextract_document(unit_case, "Dhist0001") is None  # not listed
