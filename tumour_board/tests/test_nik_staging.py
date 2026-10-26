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
    from tumour_board.api import common as api_common, staging as staging_api
    monkeypatch.setattr(staging_api, "_RUNS", api_common.RateLimit(6, 60))  # a fresh limit per test: the tests run the draft often
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


# ---- lung (AJCC 8, chapter 36) -------------------------------------------------------------------------------------------------------

def _lung_docs():
    ct = util.make_doc("LC1", "ct", title="CECT THORAX", text="CECT thorax (SYNTHETIC)\nA 3.6 x 2.9 cm spiculated mass in the right upper lobe.\n"
                       "The mass abuts and invades the visceral pleura.\nEnlarged right hilar lymph node, 1.4 cm.\nNo pleural effusion. No distant metastasis.")
    ct2 = util.make_doc("LC2", "ct", title="CT CHEST", text="CT chest (SYNTHETIC)\nA 4.6 cm mass in the left lower lobe invading the chest wall with rib erosion.\n"
                        "Subcarinal lymph node, 1.8 cm.\nMultiple liver and bone metastases.")
    return {d["doc_id"]: d for d in (ct, ct2)}


def test_lung_size_against_features_and_the_table():
    r = staging.rules_for("lung_nsclc")
    by_id = _lung_docs()
    # 3.6 cm with visceral pleural invasion: the T2 feature by size is T2a; N1 hilar; M0: stage IIB
    ans = {"T": {"cat": "T2-features", "quotes": [{"doc_id": "LC1", "quote": "The mass abuts and invades the visceral pleura."}],
                 "size_quote": {"doc_id": "LC1", "quote": "A 3.6 x 2.9 cm spiculated mass in the right upper lobe."}},
           "N": {"cat": "N1", "quotes": [{"doc_id": "LC1", "quote": "Enlarged right hilar lymph node, 1.4 cm."}]},
           "M": {"cat": "M0", "quotes": [{"doc_id": "LC1", "quote": "No distant metastasis."}]}}
    d = staging.decide(r, ans, by_id)
    assert d["components"]["T"]["cat"] == "T2a" and d["components"]["T"]["size_mm"] == 36.0 and d["stage"] == "IIB"
    # 4.6 cm alone is T2b; with chest wall invasion the feature (T3) is higher; N2 subcarinal; several extrathoracic metastases M1c: IVB
    ans = {"T": {"cat": "T3-invades", "quotes": [{"doc_id": "LC2", "quote": "invading the chest wall with rib erosion"}],
                 "size_quote": {"doc_id": "LC2", "quote": "A 4.6 cm mass in the left lower lobe"}},
           "N": {"cat": "N2", "quotes": [{"doc_id": "LC2", "quote": "Subcarinal lymph node, 1.8 cm."}]},
           "M": {"cat": "M1c", "quotes": [{"doc_id": "LC2", "quote": "Multiple liver and bone metastases."}]}}
    d = staging.decide(r, ans, by_id)
    assert d["components"]["T"]["cat"] == "T3" and "T2b" in d["components"]["T"]["note"] and d["stage"] == "IVB"
    # the table rows by category and by group
    assert [staging.stage_group(r, *x)["stage"] for x in (("T1a", "N0", "M0"), ("T1c", "N0", "M0"), ("T2b", "N0", "M0"), ("T1b", "N1", "M0"),
                                                         ("T3", "N1", "M0"), ("T4", "N1", "M0"), ("T2a", "N3", "M0"), ("T4", "N3", "M0"), ("T1a", "N0", "M1b"))] == \
        ["IA1", "IA3", "IIA", "IIB", "IIIA", "IIIA", "IIIB", "IIIC", "IVA"]


@pytest.mark.skipif(not book.books().get("ajcc8_lung"), reason="the licensed AJCC chapter is not on this machine")
def test_every_lung_rule_line_is_found_on_its_book_page():
    r = staging.rules_for("lung_nsclc")
    for c in r["T"] + r["N"] + r["M"] + [r["groups"]] + [x for x in r["groups"]["rows"] if x.get("find")]:
        img, hl = book.page_png("ajcc8_lung", c.get("page", r["groups"]["page"]), c["find"])
        assert hl, f"{c.get('cat') or c.get('stage')}: {c['find']!r} not found on p. {c.get('page')}"


# ---- cervix (FIGO 2018) --------------------------------------------------------------------------------------------------------------

def _cervix_docs():
    mri = util.make_doc("CM1", "mri", title="MRI PELVIS", text="MRI pelvis (SYNTHETIC)\nA 3.5 x 3.0 cm mass in the cervix.\n"
                        "Right parametrial involvement is seen, not reaching the pelvic wall.\nEnlarged right external iliac lymph node, 1.6 cm.\nNo hydronephrosis.")
    hpe = util.make_doc("CH1", "histopathology", title="HISTOPATHOLOGY REPORT", text="Cone biopsy (SYNTHETIC)\nSquamous cell carcinoma.\n"
                        "Depth of stromal invasion: 2 mm.\nMargins free.")
    return {d["doc_id"]: d for d in (mri, hpe)}


def test_cervix_figo_2018():
    r = staging.rules_for("cervix")
    assert r["system"] == "FIGO 2018" and r["signed_off"] is None
    by_id = _cervix_docs()
    size = {"doc_id": "CM1", "quote": "A 3.5 x 3.0 cm mass in the cervix."}
    no_m = {"cat": "M0", "quotes": [{"doc_id": "CM1", "quote": "No hydronephrosis."}]}
    # parametrial involvement (IIB) with a pelvic node on imaging: Stage IIIC1r (nodes allot IIIC whatever the local extent)
    ans = {"T": {"cat": "IIB", "quotes": [{"doc_id": "CM1", "quote": "Right parametrial involvement is seen, not reaching the pelvic wall."}], "size_quote": size},
           "N": {"cat": "IIIC1", "quotes": [{"doc_id": "CM1", "quote": "Enlarged right external iliac lymph node, 1.6 cm."}]}, "M": no_m}
    d = staging.decide(r, ans, by_id)
    assert d["components"]["T"]["cat"] == "IIB" and d["stage"] == "IIIC1r"
    # no nodes stated as involved: the local extent stands
    d = staging.decide(r, {**ans, "N": {"cat": "N0", "quotes": [{"doc_id": "CM1", "quote": "No hydronephrosis."}]}}, by_id)
    assert d["stage"] == "IIB"
    # size alone: 3.5 cm confined to the cervix is IB2; a 2 mm depth on pathology (IA1) is lower than the measured size
    d = staging.decide(r, {"T": {"cat": "IA1", "quotes": [{"doc_id": "CH1", "quote": "Depth of stromal invasion: 2 mm."}], "size_quote": size},
                           "N": {"cat": "N0", "quotes": [{"doc_id": "CM1", "quote": "No hydronephrosis."}]}, "M": no_m}, by_id)
    assert d["components"]["T"]["cat"] == "IB2" and d["stage"] == "IB2"
    assert staging.parse_written("FIGO stage IIIC1r")["stage"] == "IIIC1" and staging.parse_written("Stage IB3")["stage"] == "IB3"
    assert staging.parse_written("IIB")["stage"] == "IIB" and staging.parse_written("FIGO 2018 IIIC2p")["stage"] == "IIIC2"
    assert staging.parse_written("Invasive carcinoma")["stage"] is None
    assert staging.stage_group(r, "IIA2", "N0", "M0")["stage"] == "IIA2" and staging.stage_group(r, "IVA", "IIIC1", "M0")["stage"] == "IVA"


# ---- breast prognostic stage group (AJCC 8, pp. 621 to 624; night-v3 item 1.12) -----------------------------------------------------

HPE = ("Core biopsy, right breast (SYNTHETIC)\nInvasive breast carcinoma of no special type.\nModified Bloom Richardson grade I (score 5/9).\n"
       "AJCC prognostic stage group: IIB")
IHC = "IHC panel (SYNTHETIC)\nER: Positive (90%, strong)\nPR: Positive (60%)\nHER2/neu: Score 1+ (Negative)\nKi-67: 15%"


def _prog_docs(her2_line="HER2/neu: Score 1+ (Negative)", pr=True):
    text = IHC.replace("HER2/neu: Score 1+ (Negative)", her2_line)
    facts = {"er": util.fact("Positive (90%, strong)", quote="ER: Positive (90%, strong)"), "her2": util.fact(her2_line, quote=her2_line)}
    if pr:
        facts["pr"] = util.fact("Positive (60%)", quote="PR: Positive (60%)")
    util.add(CASE, util.make_doc("DH1", "histopathology", text=HPE, title="HISTOPATHOLOGY REPORT", date="2026-10-03",
                                 facts={"grade": util.fact("grade I", quote="Modified Bloom Richardson grade I (score 5/9).")}),
             util.make_doc("DI1", "ihc", text=text, title="IHC REPORT", date="2026-10-04", facts=facts))
    service.recheck(CASE, "test")


def test_the_prognostic_table_is_data_with_its_pages():
    r = staging.rules_for("breast")
    gp = r["groups_prognostic"]
    assert gp["title"] == "AJCC Prognostic Stage Groups" and gp["page"] == 621 and len(gp["rows"]) == 152
    assert all(row["page"] in (621, 622, 623, 624) and row["printed"] for row in gp["rows"])
    assert not [row for row in gp["rows"] if row.get("unsure")]
    onco = [row for row in gp["rows"] if row.get("requires")]
    assert len(onco) == 1 and onco[0]["requires"] == "oncotype_dx_score" and onco[0]["page"] == 621
    assert [f["mark"] for f in gp["footnotes"]] == ["*", "**", "***"] and all(f["page"] == 624 for f in gp["footnotes"])
    assert {row["stage"] for row in gp["rows"]} == {"0", "IA", "IB", "IIA", "IIB", "IIIA", "IIIB", "IIIC", "IV"}
    assert "152 rows" in r["_note"] and "0 unmatched" in r["_note"]
    import json, re
    assert not re.search(r"treat|therap|chemo|endocrine|surgery|radiation|mastectomy", json.dumps(gp), re.I)  # guard 6


@pytest.mark.skipif(not book.books().get("ajcc8_breast"), reason="the licensed AJCC chapter is not on this machine")
def test_the_prognostic_table_heading_and_lines_are_found_on_their_pages():
    gp = staging.rules_for("breast")["groups_prognostic"]
    for c in [gp] + gp["footnotes"] + [c for k in gp["criteria"] for c in gp["criteria"][k]]:
        img, hl = book.page_png("ajcc8_breast", c["page"], c["find"])
        assert hl, f"{c['find']!r} not found on p. {c['page']}"


def test_the_prognostic_lookup_from_the_book():
    r = staging.rules_for("breast")
    look = lambda *a: (staging.prognostic_group(r, *a) or {}).get("stage")
    assert look("T1c", "cN0", "cM0", "G1", "positive", "positive", "positive") == "IA"       # p. 621: T1 N0 M0 1 Positive Any Any IA
    assert look("T1b", "cN0", "cM0", 2, "negative", "positive", "positive") == "IA"           # p. 621: 1-2 Negative Positive Positive IA
    assert look("T2", "cN0", "cM0", 2, "negative", "positive", "positive") == "IB"            # p. 621: the row printed "1,2"
    assert look("T2", "cN1", "cM0", 1, "negative", "positive", "positive") == "IB"            # p. 621: IB***
    assert look("T2", "cN1", "cM0", 2, "negative", "negative", "negative") == "IIIB"          # p. 623: 1-2 Negative Negative Negative IIIB***
    assert look("T2", "cN1", "cM0", 3, "negative", "negative", "positive") == "IIIC"          # p. 624: 3 Negative Negative Any IIIC***
    assert look("T4b", "cN2a", "cM0", 3, "negative", "positive", "positive") == "IIIC"        # p. 624: T4 N0-2 3 Negative Any Any
    assert look("T1c", "cN3c", "cM0", 1, "negative", "positive", "positive") == "IIIA"        # p. 623: Any N3 M0 1 Negative Positive Positive
    assert look("T1c", "cN1mi", "cM0", 3, "negative", "negative", "negative") == "IIA"        # p. 622
    assert look("T2", "cN0", "cM1", 3, "negative", "negative", "negative") == "IV"
    # the Oncotype Dx row (T1-2 N0 M0 HER2 negative ER positive: IA) is never applied: no recurrence score on record
    assert look("T1c", "cN0", "cM0", 3, "negative", "positive", "negative") == "IIA"          # p. 622: IIA***
    # the table as printed has no row: nothing is guessed
    assert look("T3", "cN0", "cM0", 1, "positive", "positive", "positive") is None
    assert look("T2", "cN0", "cM0", None, "negative", "positive", "positive") is None


def test_the_category_comes_from_the_line_in_code():
    assert staging.grade_cat("Modified Bloom Richardson grade II (score 6/9)")[0] == "G2" and staging.grade_cat("G3")[0] == "G3"
    assert staging.grade_cat("GX")[0] is None and staging.grade_cat("Grade II-III")[0] is None and staging.grade_cat("Moderately differentiated")[0] is None
    assert staging.grade_cat("Histologic grade 2; nuclear grade 3")[0] == "G2"
    assert staging.her2_cat("HER2/neu: Score 3+ (Positive)")[0] == "positive" and staging.her2_cat("HER2: 1+")[0] == "negative"
    # equivocal by ISH counts as negative (footnote *); IHC 2+ without ISH is unclear
    assert staging.her2_cat("HER2 IHC 2+; FISH: equivocal (ratio 1.9)")[0] == "negative_ish_equivocal"
    assert staging.her2_cat("HER2 IHC 2+ (equivocal)") == (None, "IHC 2+ (equivocal) with no ISH result in the line")
    assert staging.her2_cat("HER2 IHC 2+ (equivocal); FISH: amplified")[0] == "positive"
    assert staging.her2_cat("HER2 2+, sent for FISH")[0] is None
    assert staging.receptor_cat("ER: Positive (90%), PR: Negative (0%)", "PR")[0] == "negative"
    assert staging.receptor_cat("ER +ve, PR -ve", "ER")[0] == "positive" and staging.receptor_cat("ER-ve", "ER")[0] == "negative"
    assert staging.receptor_cat("ER 90%", "ER")[0] is None  # a percentage alone is unclear
    assert staging.parse_prognostic("AJCC prognostic stage group: IIB") == "IIB" and staging.parse_prognostic("prognostic factors") is None


def test_an_unsure_row_is_never_used():
    import copy
    r = copy.deepcopy(staging.rules_for("breast"))
    row = staging.prognostic_group(r, "T2", "cN1", "cM0", 1, "negative", "positive", "positive")
    row["unsure"] = True
    q = {"quotes": [], "how": "test"}
    ana = {"status": "staged", "components": {"T": {"cat": "T2"}, "N": {"cat": "cN1"}, "M": {"cat": "cM0"}}}
    d = staging.decide_prognostic(r, ana, {"G": {**q, "cat": "G1"}, "HER2": {**q, "cat": "negative"}, "ER": {**q, "cat": "positive"}, "PR": {**q, "cat": "positive"}})
    assert d["status"] == "cannot_stage" and d["stage"] is None and d["missing"] == ["The table row needs a clinician's check"]
    # and without an anatomic draft there is nothing to look up
    d = staging.decide_prognostic(r, {"status": "cannot_stage", "components": {}}, {"G": {**q, "cat": "G1"}, "HER2": {**q, "cat": "negative"}, "ER": {**q, "cat": "positive"}, "PR": {**q, "cat": "positive"}})
    assert d["status"] == "cannot_stage" and d["missing"][0].startswith("T, N and M:")


def test_the_prognostic_draft_beside_the_anatomic_one(breast):
    tc, who, fake, calls = breast
    _prog_docs()
    v = tc.post(f"/api/tb/cases/{CASE}/staging/run").json()
    assert v["switch"]["label"] == staging.PREVIEW_LABEL and v["draft_label"] == staging.DRAFT_LABEL and calls == ["draft stage"]  # one model call
    assert v["draft"]["stage"] == "IIB" and "prognostic" not in v["draft"]
    p = v["prognostic"]
    assert p["status"] == "staged" and p["stage"] == "IB" and p["row"]["page"] == 621 and p["row"].get("changed_from_anatomic") is True
    assert p["label"] == "Prognostic stage group (AJCC 8, with grade, HER2, ER, PR)" and p["tnm"] == {"T": "T2", "N": "cN1", "M": "cM0"}
    c = p["components"]
    assert c["G"]["cat"] == "G1" and c["G"]["quotes"][0]["doc_id"] == "DH1" and c["G"]["criterion"]["page"] == 617
    assert c["HER2"]["cat"] == "negative" and c["HER2"]["criterion"]["cat"] == "ihc_0_1plus" and c["HER2"]["criterion"]["page"] == 616
    assert c["ER"]["cat"] == "positive" and c["PR"]["cat"] == "positive" and c["ER"]["quotes"][0]["quote"] == "ER: Positive (90%, strong)"
    assert p["multigene"] == {"applied": False, "note": "Multigene panel row not applied: no recurrence score on record"}
    assert v["prognostic_ref"]["page"] == 621 and len(v["prognostic_ref"]["footnotes"]) == 3
    # guard 4: the prognostic stage the pathology report wrote is shown beside it and the difference flagged; the anatomic comparison
    # is not mixed with it
    assert v["prognostic_written"][0]["stage"] == "IIB" and v["prognostic_written"][0]["doc_id"] == "DH1"
    assert v["prognostic_comparison"]["result"] == "differs" and v["prognostic_comparison"]["differences"] == ["Prognostic stage: the report writes IIB, the draft IB"]
    assert v["comparison"]["written"]["value"] == "cT2 N0 M0"
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "draft_stage"][-1]
    assert ev["prognostic"]["stage"] == "IB"
    # each draft is confirmed on its own, and the confirmation says which; an old caller without "which" confirms the anatomic draft
    assert tc.post(f"/api/tb/cases/{CASE}/staging/confirm", json={"which": "nonsense"}).status_code == 400
    # the prognostic group is built on the anatomic T, N and M: it is confirmed only once the anatomic draft is (review, 27 Oct)
    r = tc.post(f"/api/tb/cases/{CASE}/staging/confirm", json={"which": "prognostic"})
    assert r.status_code == 409 and "anatomic stage first" in r.json()["detail"]["message"], r.text
    v = tc.post(f"/api/tb/cases/{CASE}/staging/confirm", json={}).json()
    assert v["draft"]["confirmed"]["which"] == "anatomic" and v["prognostic"]["confirmed"] is None
    assert [e for e in store.read_audit(CASE) if e.get("kind") == "draft_stage_confirmed"][-1]["which"] == "anatomic"
    v = tc.post(f"/api/tb/cases/{CASE}/staging/confirm", json={"which": "prognostic"}).json()
    assert v["prognostic"]["confirmed"]["which"] == "prognostic" and v["prognostic"]["confirmed"]["by"] == "dr.rao" and v["draft"]["confirmed"]["which"] == "anatomic"
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "draft_stage_confirmed"][-1]
    assert ev["which"] == "prognostic" and ev["stage"] == "IB" and ev["components"] == {"G": "G1", "HER2": "negative", "ER": "positive", "PR": "positive"}
    v = tc.post(f"/api/tb/cases/{CASE}/staging/reject", json={"reason": "Grade is 2 on review", "which": "prognostic"}).json()
    assert v["prognostic"]["rejected"]["reason"] == "Grade is 2 on review" and v["prognostic"]["confirmed"] is None and v["draft"]["confirmed"]
    assert [e for e in store.read_audit(CASE) if e.get("kind") == "draft_stage_rejected"][-1]["which"] == "prognostic"
    # marking the anatomic draft wrong also drops a prognostic confirmation that was built on it
    v = tc.post(f"/api/tb/cases/{CASE}/staging/confirm", json={"which": "prognostic"}).json()
    assert v["prognostic"]["confirmed"]
    v = tc.post(f"/api/tb/cases/{CASE}/staging/reject", json={"reason": "N is wrong on review"}).json()
    assert v["draft"]["rejected"] and v["draft"]["confirmed"] is None and v["prognostic"]["confirmed"] is None


def test_a_missing_biomarker_means_cannot_stage(breast):
    tc, who, fake, calls = breast
    _prog_docs(pr=False)
    p = tc.post(f"/api/tb/cases/{CASE}/staging/run").json()["prognostic"]
    assert p["status"] == "cannot_stage" and p["stage"] is None and p["missing"] == ["PR: the PR status is not in a report"]
    assert tc.post(f"/api/tb/cases/{CASE}/staging/confirm", json={"which": "prognostic"}).status_code == 409


def test_her2_equivocal_by_ish_counts_as_negative_and_ihc_2plus_alone_is_unclear(breast):
    tc, who, fake, calls = breast
    _prog_docs(her2_line="HER2/neu: IHC 2+; FISH equivocal (HER2/CEP17 ratio 1.8)")
    p = tc.post(f"/api/tb/cases/{CASE}/staging/run").json()["prognostic"]
    assert p["components"]["HER2"]["cat"] == "negative" and p["components"]["HER2"]["criterion"]["page"] == 624 and p["stage"] == "IB"
    _prog_docs(her2_line="HER2/neu: IHC 2+ (equivocal)")
    p = tc.post(f"/api/tb/cases/{CASE}/staging/run").json()["prognostic"]
    assert p["status"] == "cannot_stage" and "HER2" not in p["components"]
    assert p["missing"][0].startswith("HER2: unclear: IHC 2+ (equivocal) with no ISH result in the line")


def test_the_switch_off_hides_both_drafts(breast, monkeypatch):
    tc, who, fake, calls = breast
    _prog_docs()
    assert tc.post(f"/api/tb/cases/{CASE}/staging/run").json()["prognostic"]["stage"] == "IB"
    monkeypatch.setenv("TB_STAGING", "off")
    v = tc.get(f"/api/tb/cases/{CASE}/staging").json()
    assert v["draft"] is None and v["prognostic"] is None and v["prognostic_ref"] is None and v["switch"]["on"] is False
    assert tc.post(f"/api/tb/cases/{CASE}/staging/run").status_code == 409


def test_lung_has_no_prognostic_draft():
    assert staging.prognostic_for("no-case", staging.rules_for("lung_nsclc"), {}) is None


# ---- a resident's sign-off (night-v3 item 1.8): the confirmation is a proposal pinned to the draft the resident saw -------------------

def test_a_residents_confirm_is_signed_off_by_the_consultant_and_pinned_to_the_draft(breast, people):
    from tumour_board import proposals
    from tumour_board.tests.test_nik_steps import _outsider
    tc, who, fake, calls = breast
    _outsider(people)
    _prog_docs()
    d = tc.post(f"/api/tb/cases/{CASE}/staging/run").json()["draft"]
    pin = {"which": "anatomic", "stage": d["stage"], "signature": d["signature"]}
    url = f"/api/tb/cases/{CASE}/staging/confirm"

    def approve(pid):
        who["user"] = "dr.rao"
        r = tc.post(f"/api/tb/cases/{CASE}/proposals/{pid}/approve")
        who["user"] = "res.asha"
        return r

    def status(pid):
        return proposals.find(store.get_case(CASE), pid)["status"]

    who["user"] = "res.asha"
    assert tc.post(url, json={**pin, "stage": "IIIA"}).status_code == 400  # not the draft on the card: refused before it is stored
    assert tc.post(url, json={"which": "anatomic"}).status_code == 400  # the draft must be named
    r = tc.post(url, json=pin)
    assert r.status_code == 200, r.text
    p = r.json()["proposal"]
    assert p["action"] == "staging_confirm" and p["payload"] == {**pin, "note": ""}
    v = tc.get(f"/api/tb/cases/{CASE}/staging").json()
    assert v["draft"]["confirmed"] is None  # guard 1: nothing counts until a doctor confirms
    assert "draft_stage_confirmed" not in [e.get("kind") for e in store.read_audit(CASE)]
    # the consultant approves: confirmed in the consultant's name, audited
    r = approve(p["id"])
    assert r.status_code == 200, r.text
    v = tc.get(f"/api/tb/cases/{CASE}/staging").json()
    assert v["draft"]["confirmed"]["by"] == "dr.rao" and v["draft"]["confirmed"]["which"] == "anatomic" and v["prognostic"]["confirmed"] is None
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "draft_stage_confirmed"][-1]
    assert ev["by"] == "dr.rao" and ev["stage"] == d["stage"]
    ap = [e for e in store.read_audit(CASE) if e.get("kind") == "proposal_approved"][-1]
    assert ap["by"] == "dr.rao" and ap["proposed_by"] == "res.asha" and ap["action"] == "staging_confirm"
    # the prognostic stage group on its own
    pg = v["prognostic"]
    p2 = tc.post(url, json={"which": "prognostic", "stage": pg["stage"], "signature": d["signature"]}).json()["proposal"]
    assert approve(p2["id"]).status_code == 200
    v = tc.get(f"/api/tb/cases/{CASE}/staging").json()
    assert v["prognostic"]["confirmed"]["by"] == "dr.rao" and v["prognostic"]["confirmed"]["which"] == "prognostic"
    # the draft is worked out again with another stage after the resident saw it: the approval is refused and the proposal stays pending
    p3 = tc.post(url, json=pin).json()["proposal"]
    fake.answer = {**GOOD, "N": {"cat": "cN0", "quotes": [{"doc_id": "DC1", "quote": "No evidence of distant metastasis in the chest, abdomen or pelvis"}]}}
    who["user"] = "dr.rao"
    d2 = tc.post(f"/api/tb/cases/{CASE}/staging/run").json()["draft"]
    assert d2["stage"] != d["stage"] and d2["confirmed"] is None
    r = approve(p3["id"])
    assert r.status_code == 409 and "work it out again" in r.text and status(p3["id"]) == "pending"
    assert tc.get(f"/api/tb/cases/{CASE}/staging").json()["draft"]["confirmed"] is None
    # the reports changed (another signature): refused too
    p4 = tc.post(url, json={**pin, "stage": d2["stage"], "signature": d2["signature"]}).json()["proposal"]
    util.add(CASE, util.make_doc("DX9", "ct", text="CT thorax (SYNTHETIC)\nNo lung nodule.", title="CT THORAX", date="2026-10-05"))
    r = approve(p4["id"])
    assert r.status_code == 409 and status(p4["id"]) == "pending"
    # a resident not on the team is refused; reject stays the consultant's; the consultant's own confirm works as before
    who["user"] = "res.kiran"
    assert tc.post(url, json=pin).status_code == 403
    who["user"] = "res.asha"
    assert tc.post(f"/api/tb/cases/{CASE}/staging/reject", json={"reason": "N looks wrong"}).status_code == 403
    who["user"] = "dr.rao"
    tc.post(f"/api/tb/cases/{CASE}/staging/run")
    r = tc.post(url, json={})
    assert r.status_code == 200 and "proposal" not in r.json() and r.json()["draft"]["confirmed"]["by"] == "dr.rao"
