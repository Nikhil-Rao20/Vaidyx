"""The draft stage (owner decision, 22 Oct 2026, docs/staging/DECISION.md): the measured size and the stage table in code, every quote checked
against its report, "cannot stage" when something is missing, the written stage compared, confirm and reject, the switch (off by default,
preview, on only when signed off) and the staging book's pages with the line highlighted. A synthetic breast Case File; the reasoner is a
fake; no model is ever called."""
import pytest

from tumour_board import service, staging, store
from tumour_board.staging import book
from tumour_board.tests import util
from tumour_board.tests.test_nik_slots import OWNER, FakeAuth, nik_app, people  # noqa: F401

CASE = "TB-STG-1"
MAMMO = "Bilateral mammography (SYNTHETIC)\nRight breast: irregular spiculated mass measuring 2.8 x 2.2 cm in the upper outer quadrant.\nBI-RADS 5."
USG = "USG both breasts and axillae (SYNTHETIC)\nOne enlarged right axillary lymph node, 1.6 cm, mobile, with loss of the fatty hilum."
CECT = "CECT chest, abdomen and pelvis (SYNTHETIC)\nImpression: No evidence of distant metastasis in the chest, abdomen or pelvis."
OPD = "OPD consultation note (SYNTHETIC)\nClinical stage: cT2 N0 M0.\nECOG 1."
GOOD = {"T": {"cat": "T2", "quotes": [{"doc_id": "DM1", "quote": "irregular spiculated mass measuring 2.8 x 2.2 cm"}]},
        "N": {"cat": "cN1", "quotes": [{"doc_id": "DU1", "quote": "One enlarged right axillary lymph node, 1.6 cm, mobile"}]},
        "M": {"cat": "cM0", "quotes": [{"doc_id": "DC1", "quote": "No evidence of distant metastasis in the chest, abdomen or pelvis"}]}}


@pytest.fixture
def breast(nik_app, people, monkeypatch):
    c = store.create_case(CASE, dict(util.PATIENT), "breast", created_by="dr.rao"); c["department"] = OWNER; store.save_case(c)
    util.add(CASE, util.make_doc("DM1", "mammogram", text=MAMMO, title="BILATERAL MAMMOGRAPHY REPORT", date="2026-10-01",
                           facts={"lesion_size": util.fact("2.8 x 2.2 cm", quote="irregular spiculated mass measuring 2.8 x 2.2 cm")}),
             util.make_doc("DU1", "ultrasound", text=USG, title="USG BOTH BREASTS AND AXILLAE", date="2026-10-01"),
             util.make_doc("DC1", "ct", text=CECT, title="CECT CHEST, ABDOMEN AND PELVIS", date="2026-10-02"),
             util.make_doc("DO1", "clinical_note", text=OPD, title="OPD CONSULTATION NOTE", date="2026-09-25",
                           facts={"recorded_stage": util.fact("cT2 N0 M0", quote="Clinical stage: cT2 N0 M0.")}))
    service.recheck(CASE, "test")
    calls = []

    async def fake_chat(role, messages, **kw):
        calls.append(kw.get("purpose"))
        return fake_chat.answer
    fake_chat.answer = GOOD
    monkeypatch.setattr(staging.llm, "chat", fake_chat)
    monkeypatch.setenv("TB_STAGING", "preview")
    return nik_app[0], nik_app[1], fake_chat, calls


# ---- plain code: sizes, groups, the table -------------------------------------------------------------------------------------------

def test_sizes_and_the_stage_table():
    r = staging.rules_for("breast")
    assert [staging.size_mm(s) for s in ("2.8 x 2.2 cm", "18 × 12 mm", "1.6 cm", "a 5.5 x 4 x 3 cm mass", "no number")] == [28.0, 18.0, 16.0, 55.0, None]
    assert [staging.t_by_size(r, mm)["cat"] for mm in (0.8, 1.5, 7, 15, 20, 28, 50, 51)] == ["T1mi", "T1a", "T1b", "T1c", "T1c", "T2", "T2", "T3"]
    assert [staging.stage_group(r, *x)["stage"] for x in (("T2", "N1", "M0"), ("T3", "N0", "M0"), ("T4", "N2", "M0"), ("T1", "N3", "M0"), ("T2", "N0", "M1"), ("T1", "N1mi", "M0"))] == \
        ["IIB", "IIB", "IIIB", "IIIC", "IV", "IB"]
    assert staging.group_of("cN2a", "N") == "N2" and staging.group_of("T1c", "T") == "T1" and staging.group_of("cM0", "M") == "M0"
    assert staging.parse_written("cT2 N1 M0, stage IIB") == {"T": "T2", "N": "N1", "M": "M0", "stage": "IIB"}


def test_every_rule_has_its_text_page_and_category():
    r = staging.rules_for("breast")
    assert r["signed_off"] is None  # guard 5: not switched on until a clinician checks it
    for k in ("T", "N", "M"):
        for c in r[k]:
            assert c["cat"] and c["text"] and c["page"] in (619, 620) and c.get("find")
    assert {row["stage"] for row in r["groups"]["rows"]} == {"0", "IA", "IB", "IIA", "IIB", "IIIA", "IIIB", "IIIC", "IV"}


@pytest.mark.skipif(not book.books().get("ajcc8_breast"), reason="the licensed AJCC chapter is not on this machine")
def test_every_rule_line_is_found_on_its_book_page():
    r = staging.rules_for("breast")
    for c in r["T"] + r["N"] + r["M"] + [r["groups"]] + [x for x in r["groups"]["rows"] if x.get("find")]:
        img, hl = book.page_png("ajcc8_breast", c.get("page", r["groups"]["page"]), c["find"])
        assert img[:3] == b"\xff\xd8\xff" and hl, f"{c.get('cat') or c.get('stage')}: {c['find']!r} not found on p. {c.get('page')}"


# ---- the switch ---------------------------------------------------------------------------------------------------------------------

def test_off_by_default_and_on_only_when_signed_off(monkeypatch):
    monkeypatch.delenv("TB_STAGING", raising=False)
    assert staging.switch("breast")["on"] is False
    monkeypatch.setenv("TB_STAGING", "preview")
    assert staging.switch("breast") == {"on": True, "preview": True, "label": staging.PREVIEW_LABEL, "why": ""}
    monkeypatch.setenv("TB_STAGING", "on")
    assert staging.switch("breast")["on"] is False and "clinician" in staging.switch("breast")["why"]  # not signed off yet
    assert staging.switch("lung_nsclc")["on"] is False  # no rule file yet


# ---- the run -------------------------------------------------------------------------------------------------------------------------

def test_the_draft_stage_with_its_proof(breast):
    tc, who, fake, calls = breast
    v = tc.get(f"/api/tb/cases/{CASE}/staging").json()
    assert v["switch"]["preview"] is True and v["draft"] is None and v["written"][0]["value"] == "cT2 N0 M0"
    r = tc.post(f"/api/tb/cases/{CASE}/staging/run")
    assert r.status_code == 200, r.text
    d = r.json()["draft"]
    assert d["status"] == "staged" and d["stage"] == "IIB" and calls == ["draft stage"]
    comps = d["components"]
    assert comps["T"]["cat"] == "T2" and comps["T"]["size_mm"] == 28.0 and comps["T"]["criterion"]["page"] == 619
    assert comps["N"]["cat"] == "cN1" and comps["N"]["quotes"][0]["doc_id"] == "DU1" and comps["M"]["cat"] == "cM0"
    # guard 4: the stage the OPD note wrote is shown beside it, and the difference flagged
    cmp = r.json()["comparison"]
    assert cmp["result"] == "differs" and cmp["differences"] == ["N: the report writes N0, the draft N1"]
    assert "draft_stage" in [e.get("kind") for e in store.read_audit(CASE)]
    # guard 1: a doctor confirms it; a change in the reports makes it stale and it cannot be confirmed until worked out again
    r = tc.post(f"/api/tb/cases/{CASE}/staging/confirm", json={})
    assert r.status_code == 200 and r.json()["draft"]["confirmed"]["by"] == "dr.rao"
    util.add(CASE, util.make_doc("DX9", "ct", text="CT thorax (SYNTHETIC)\nNo lung nodule.", title="CT THORAX", date="2026-10-05"))
    v = tc.get(f"/api/tb/cases/{CASE}/staging").json()
    assert v["stale"] is True
    assert tc.post(f"/api/tb/cases/{CASE}/staging/confirm", json={}).status_code == 409
    # "This is wrong" needs a reason
    assert tc.post(f"/api/tb/cases/{CASE}/staging/reject", json={"reason": ""}).status_code == 400
    r = tc.post(f"/api/tb/cases/{CASE}/staging/reject", json={"reason": "The node is fixed on examination"})
    assert r.status_code == 200 and r.json()["draft"]["rejected"]["reason"] == "The node is fixed on examination"


def test_an_unchecked_quote_counts_as_nothing(breast):
    tc, who, fake, calls = breast
    fake.answer = {**GOOD, "N": {"cat": "cN1", "quotes": [{"doc_id": "DU1", "quote": "three matted axillary nodes"}]}}  # not in the report
    d = tc.post(f"/api/tb/cases/{CASE}/staging/run").json()["draft"]
    assert d["status"] == "cannot_stage" and d["stage"] is None and any(m.startswith("N:") for m in d["missing"])


def test_missing_parts_mean_cannot_stage_until_the_doctor_fills_them(breast):
    tc, who, fake, calls = breast
    fake.answer = {**GOOD, "M": {"cat": "not_stated", "quotes": [], "missing": "no staging work-up report"}}
    d = tc.post(f"/api/tb/cases/{CASE}/staging/run").json()["draft"]
    assert d["status"] == "cannot_stage" and d["missing"] == ["M: no staging work-up report"]
    # the doctor fills M with a reason (AJCC: cM0 needs no imaging); no new model call; shown as entered
    assert tc.post(f"/api/tb/cases/{CASE}/staging/enter", json={"part": "M", "cat": "cM0", "reason": ""}).status_code == 400
    assert tc.post(f"/api/tb/cases/{CASE}/staging/enter", json={"part": "M", "cat": "cM9", "reason": "clinical examination"}).status_code == 400
    r = tc.post(f"/api/tb/cases/{CASE}/staging/enter", json={"part": "M", "cat": "cM0", "reason": "Clinical examination, no symptoms of spread"})
    d = r.json()["draft"]
    assert d["status"] == "staged" and d["stage"] == "IIB" and d["components"]["M"]["entered"]["by"] == "dr.rao" and calls == ["draft stage"]
    # a part a report states is never replaced by an entry
    tc.post(f"/api/tb/cases/{CASE}/staging/enter", json={"part": "N", "cat": "cN3c", "reason": "test"})
    assert tc.get(f"/api/tb/cases/{CASE}/staging").json()["draft"]["components"]["N"]["cat"] == "cN1"


def test_the_measured_size_decides_t_and_a_t4_needs_its_own_line(breast):
    tc, who, fake, calls = breast
    fake.answer = {**GOOD, "T": {"cat": "T3", "quotes": [{"doc_id": "DM1", "quote": "irregular spiculated mass measuring 2.8 x 2.2 cm"}]}}
    d = tc.post(f"/api/tb/cases/{CASE}/staging/run").json()["draft"]
    assert d["components"]["T"]["cat"] == "T2" and "the measured size decides" in d["components"]["T"]["note"]
    fake.answer = {**GOOD, "T": {"cat": "T4b", "quotes": [{"doc_id": "DM1", "quote": "skin ulceration over the mass"}]}}  # not in the report
    d = tc.post(f"/api/tb/cases/{CASE}/staging/run").json()["draft"]
    assert d["components"]["T"]["cat"] == "T2"  # the unchecked T4 line counts for nothing; the size line decides


def test_off_and_others(breast, monkeypatch):
    tc, who, fake, calls = breast
    who["user"] = "dr.nair"  # a doctor of a department not on the Case File
    assert tc.post(f"/api/tb/cases/{CASE}/staging/run").status_code == 403
    who["user"] = "dr.rao"
    monkeypatch.setenv("TB_STAGING", "off")
    assert tc.post(f"/api/tb/cases/{CASE}/staging/run").status_code == 409 and calls == []


@pytest.mark.skipif(not book.books().get("ajcc8_breast"), reason="the licensed AJCC chapter is not on this machine")
def test_the_book_pages(breast):
    tc, who, fake, calls = breast
    m = tc.get("/api/tb/staging/books/ajcc8_breast").json()
    assert 619 in m["printed"] and 620 in m["printed"]
    r = tc.get("/api/tb/staging/books/ajcc8_breast/pages/619", params={"find": "20 mm but < 50 mm"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and int(r.headers["x-highlights"]) >= 1
    assert tc.get("/api/tb/staging/books/ajcc8_breast/pages/9999").status_code == 404
    assert tc.get("/api/tb/staging/books/not_a_book").status_code == 404
