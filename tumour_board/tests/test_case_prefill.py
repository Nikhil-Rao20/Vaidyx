"""AI pre-fill of the New Case File (docs/new-case/DESIGN.md N6, tumour_board/case_prefill.py): the quote check (a made-up quote is
dropped, a real one kept and pointed at the report that holds it, and a quote that is found but does not SAY the value is dropped
too: the cancer's site and name, the setting's words, an urgency that rests on a finding and not a heading), the setting must belong
to the suggested checklist, urgency 1 to 5 only, the owning department from the visits without the model, the job (same gate as the lookup, a guest reviewer refused, only the
starter reads it, per hospital, never for the Vaidyx admin, 30 starts per 10 minutes per login, model down = a quiet failure) and the PDF text reading. The hospital system is the captured mock
hospital served through httpx.MockTransport (test_his_client.Mock); llm.chat is replaced by a fake. SYNTHETIC data only; no model."""
import asyncio
import base64
import json
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tumour_board import case_prefill, config, his_client, llm, org
from tumour_board.tests.test_his_client import BASE, FIX, TOKEN, Mock
from tumour_board.tests.test_nik_me import MEHTA, RAO, RAVI, VX, Api, FakeAuth, people  # noqa: F401 (fixture)

UHID = "VXH/26/004201"
GR = "guest.reviewer@example.org"
HPE = ("Vaidyx Demo Hospital (SYNTHETIC)\nHISTOPATHOLOGY REPORT\nDiagnosis: Invasive breast carcinoma of no special type, left breast,\n"
       "grade 2.\nReport status: FINAL\n")
CT = ("Vaidyx Demo Hospital (SYNTHETIC)\nCECT THORAX ABDOMEN PELVIS\nImpression: No evidence of distant metastasis.\n"
      "Left breast mass 3.4 x 2.8 cm with ipsilateral axillary nodes, in keeping with early breast cancer, operable.\n")
OPD = ("OPD consultation note (SYNTHETIC)\nPlan: biopsy confirmed carcinoma; discuss upfront surgery versus neoadjuvant chemotherapy\n"
       "at the tumour board. Patient anxious to start treatment early.\n")
TEXTS = {"doc-p01-r04-v1": HPE, "doc-p01-r03-v1": CT, "doc-p01-r01-v1": OPD}

READ = [{"id": "R1", "title": "Histopathology report (biopsy)", "date": "2026-09-05", "department": "Pathology", "text": HPE},
        {"id": "R2", "title": "CECT", "date": "2026-09-03", "department": "Radiology", "text": CT}]
CHECKLISTS = case_prefill._checklists()


def his_mock():
    """The captured mock hospital, with every DocumentReference of patient vxh-26-004201 answered inline: the three above as text,
    the others as an empty file (nothing to read)."""
    b = json.loads((FIX / "patient_vxh_26_004201_everything.json").read_text())
    over = {}
    for e in b["entry"]:
        r = e["resource"]
        if r["resourceType"] != "DocumentReference":
            continue
        text = TEXTS.get(r["id"], "")
        doc = {**r, "content": [{"attachment": {"contentType": "text/plain", "data": base64.b64encode(text.encode()).decode(), "title": r["content"][0]["attachment"].get("title")}}]}
        doc["extension"] = [x for x in r.get("extension") or [] if "sha256" not in str(x.get("url"))]
        over[f"/fhir/DocumentReference/{r['id']}"] = (lambda d: lambda req: d)(doc)
    return Mock(over)


@pytest.fixture
def his(monkeypatch):
    m = his_mock()
    monkeypatch.setattr(his_client, "client", lambda *a, **k: his_client.FHIRClient(BASE, TOKEN, label="Mock hospital (SYNTHETIC)", transport=httpx.MockTransport(m)))
    return m


def answer(**over):
    a = {"cancer": {"name": "Invasive breast carcinoma, left breast", "protocol": "breast", "quote": "Invasive breast carcinoma of no special type, left breast", "report": "R1"},
         "setting": {"id": "early", "quote": "early breast cancer, operable", "report": "R2"},
         "board_question": {"text": "Upfront surgery or neoadjuvant chemotherapy for left breast carcinoma?", "basis": ["R1", "R3", "R99"]},
         "urgency": {"level": 3, "reason": "Biopsy-proven cancer, no metastasis seen.", "quote": "Patient anxious to start treatment early", "report": "R3"}}
    a.update(over)
    return a


@pytest.fixture
def model(monkeypatch):
    """A fake reasoner: answers `model.answer` (or raises `model.error`) and keeps the calls."""
    class M:
        answer = answer()
        error = None
        calls = []
    async def chat(role, messages, **kw):
        M.calls.append({"role": role, "messages": messages, **kw})
        if kw.get("audit"):
            kw["audit"]({"kind": "llm_call", "role": role, "model": "reasoner", "purpose": kw.get("purpose"), "seconds": 0.1})
        if M.error:
            raise M.error
        return json.loads(json.dumps(M.answer))
    M.calls = []
    monkeypatch.setattr(llm, "chat", chat)
    return M


# ---- the checks ------------------------------------------------------------------------------------------------------------------

def test_a_real_quote_is_kept_and_a_made_up_one_dropped():
    out, dropped = case_prefill.check(answer(), READ, CHECKLISTS)
    assert out["cancer"]["protocol"] == "breast" and out["cancer"]["report"]["title"] == "Histopathology report (biopsy)"
    assert out["setting"] == {"id": "early", "label": "Early (operable), as recorded", "quote": "early breast cancer, operable", "report": out["setting"]["report"]}
    assert out["cancer"]["name"] == "Invasive breast carcinoma of no special type, left breast"  # the model's paraphrase: the report's words kept
    assert "urgency" not in out and dropped == [{"field": "urgency", "reason": "the quote was not found in the reports"}]  # R3 was not read
    made_up = answer(cancer={"name": "Breast cancer", "protocol": "breast", "quote": "Carcinoma breast stage IIA", "report": "R1"})
    out, dropped = case_prefill.check(made_up, READ, CHECKLISTS)
    assert "cancer" not in out and "setting" not in out
    assert {"field": "cancer", "reason": "the quote was not found in the reports"} in dropped
    assert {"field": "setting", "reason": "no cancer was kept to hang the setting on"} in dropped


def test_the_quote_check_ignores_case_and_spacing_and_follows_the_quote_to_its_report():
    q = answer(cancer={"name": "Breast", "protocol": "breast", "quote": "INVASIVE  breast carcinoma of no special type,\nleft breast", "report": "R2"})
    out, _ = case_prefill.check(q, READ, CHECKLISTS)
    assert out["cancer"]["report"]["id"] == "R1"  # named R2, found in R1: kept, with the proof where the words are
    for few in ("breast", "left breast", "breast carcinoma", "grade 2. report"):  # under 15 characters or under 3 words
        out, dropped = case_prefill.check(answer(cancer={"name": "Breast", "protocol": "breast", "quote": few, "report": "R1"}), READ, CHECKLISTS)
        assert "cancer" not in out, few  # too short to prove anything


def test_the_setting_must_belong_to_the_checklist_and_the_checklist_must_exist():
    out, dropped = case_prefill.check(answer(setting={"id": "metastatic_crpc", "quote": "No evidence of distant metastasis.", "report": "R2"}), READ, CHECKLISTS)
    assert "setting" not in out and dropped[0]["field"] == "setting" and "not a setting of the Breast cancer checklist" in dropped[0]["reason"]
    out, dropped = case_prefill.check(answer(setting={"id": "not_recorded", "quote": "", "report": ""}), READ, CHECKLISTS)
    assert "setting" not in out and not [d for d in dropped if d["field"] == "setting"]  # not recorded: nothing to fill, nothing dropped
    out, dropped = case_prefill.check(answer(cancer={"name": "Breast", "protocol": "breast_v9", "quote": "left breast", "report": "R1"}), READ, CHECKLISTS)
    assert "cancer" not in out and "not one of the checklists" in dropped[0]["reason"]


def test_variants_carry_the_cancers_ts_ids():
    read = [{"id": "R1", "title": "HPE", "date": "", "department": "", "text": "Adenocarcinoma of the rectum, 8 cm from anal verge."}]
    out, _ = case_prefill.check({"cancer": {"name": "Rectal adenocarcinoma", "protocol": "colorectal_rectum", "quote": "Adenocarcinoma of the rectum", "report": "R1"}}, read, CHECKLISTS)
    assert out["cancer"]["entry"] == "colorectal" and out["cancer"]["variant"] == "rectum"
    read.append({"id": "R2", "title": "HPE", "date": "", "department": "", "text": "Nephroblastoma (Wilms tumour) of the left kidney, favourable histology."})
    out, _ = case_prefill.check({"cancer": {"name": "Wilms", "protocol": "wilms", "quote": "Nephroblastoma (Wilms tumour) of the left kidney", "report": "R2"}}, read, CHECKLISTS)
    assert (out["cancer"]["entry"], out["cancer"]["variant"]) == ("kidney", "wilms")
    out, dropped = case_prefill.check({"cancer": {"name": "Wilms", "protocol": "wilms", "quote": "Adenocarcinoma of the rectum", "report": "R1"}}, read, CHECKLISTS)
    assert "cancer" not in out and "does not name a cancer of the Wilms" in dropped[0]["reason"]  # found, but about another cancer


@pytest.mark.parametrize("level,kept", [(0, False), (1, True), (5, True), (6, False), (-2, False), ("3", True), ("high", False)])
def test_urgency_is_one_to_five_only(level, kept):
    a = answer(urgency={"level": level, "reason": "r", "quote": "No evidence of distant metastasis.", "report": "R2"})
    out, dropped = case_prefill.check(a, READ, CHECKLISTS)
    assert ("urgency" in out) is kept
    if level not in (0,) and not kept:
        assert dropped[-1]["field"] == "urgency"


# ---- the quote must say the value (review of 17 Nov 2026) --------------------------------------------------------------------------

REVIEW = [{"id": "R1", "title": "HPE", "date": "2026-10-01", "department": "",
           "text": "HISTOPATHOLOGY REPORT. Diagnosis: Invasive ductal carcinoma of the left breast, grade 2. Report status: FINAL"}]


def test_a_quote_found_but_not_saying_the_value_is_dropped():
    raw = {"cancer": {"name": "Carcinoma of the RIGHT breast", "protocol": "breast", "quote": "carcinoma of the left breast", "report": "R1"},
           "setting": {"id": "metastatic", "quote": "Report status: FINAL", "report": "R1"},
           "urgency": {"level": 5, "reason": "spread to the liver", "quote": "HISTOPATHOLOGY REPORT", "report": "R1"}}
    kept, dropped = case_prefill.check(raw, REVIEW, CHECKLISTS)
    assert kept["cancer"]["name"] == "carcinoma of the left breast"  # the report's words, never the model's "RIGHT"
    assert "setting" not in kept and "urgency" not in kept
    assert {"field": "setting", "reason": "the quote does not state Metastatic, as recorded"} in dropped
    assert [d for d in dropped if d["field"] == "urgency"]  # two words: too short to prove anything
    raw["urgency"]["quote"] = "Report status: FINAL"
    kept, dropped = case_prefill.check(raw, REVIEW, CHECKLISTS)
    assert "urgency" not in kept and {"field": "urgency", "reason": "the quote is a heading or a status line, not a finding"} in dropped
    lung = {"cancer": {"name": "Carcinoma lung", "protocol": "lung_nsclc", "quote": "Report status: FINAL", "report": "R1"}}
    kept, dropped = case_prefill.check(lung, REVIEW, CHECKLISTS)
    assert "cancer" not in kept and "does not name a cancer of the Lung" in dropped[0]["reason"]
    lung["cancer"]["quote"] = "Invasive ductal carcinoma of the left breast"  # a breast diagnosis is not lung cancer
    assert "cancer" not in case_prefill.check(lung, REVIEW, CHECKLISTS)[0]
    other = {"cancer": {"name": "Lobular carcinoma", "protocol": "breast", "quote": "Diagnosis: Invasive ductal carcinoma of the left breast, grade 2. Report status: FINAL", "report": "R1"}}
    kept, _ = case_prefill.check(other, REVIEW, CHECKLISTS)
    assert kept["cancer"]["name"] == "Invasive ductal carcinoma of the left breast, grade 2"  # its first sentence, without the label
    long_text = [{"id": "R1", "title": "HPE", "date": "", "department": "", "text": "Invasive ductal carcinoma of the left breast with extensive "
                  "ductal carcinoma in situ, lymphovascular invasion present and perineural invasion present"}]
    other["cancer"]["quote"] = long_text[0]["text"]
    kept, dropped = case_prefill.check(other, long_text, CHECKLISTS)
    assert "cancer" not in kept and dropped[0]["reason"] == "the name is not in the words of the quote"  # too long to be a name


@pytest.mark.parametrize("quote,pid,ok", [
    ("Invasive ductal carcinoma of the left breast", "breast", True),
    ("Squamous cell carcinoma of the cervix, keratinising", "cervix", True),
    ("Metastatic squamous carcinoma in a cervical lymph node", "cervix", False),   # a neck node, not the cervix
    ("Non-small cell lung carcinoma, adenocarcinoma type", "lung_nsclc", True),     # "non-" does not negate the carcinoma
    ("Small cell carcinoma of the lung, extensive", "lung_nsclc", False),
    ("Adenocarcinoma of the rectum, 8 cm from the anal verge", "colorectal_colon", False),
    ("Adenocarcinoma of the sigmoid colon, moderately differentiated", "colorectal_colon", True),
    ("Hepatocellular carcinoma, moderately differentiated", "liver_hcc", True),
    ("Multiple liver metastases from a breast primary", "liver_hcc", False),
    ("No evidence of malignancy in the breast tissue", "breast", False),          # negated
    ("Lesion suspicious for carcinoma of the breast", "breast", False),           # hedged: not a diagnosis
    ("Left breast mass 3.4 x 2.8 cm", "breast", False),                           # a mass is not a cancer
    ("Carcinoma of the endometrium, endometrioid type", "corpus_uteri", True),
    ("Carcinoma of the uterine cervix, squamous", "corpus_uteri", False),
    ("Acute myeloid leukaemia with maturation", "leukaemia", True),
    ("Papillary carcinoma of the thyroid, classic type", "generic", True),
])
def test_the_cancer_quote_names_the_site_of_the_checklist(quote, pid, ok):
    assert case_prefill.site_ok(quote, pid) is ok


def test_every_checklist_has_its_site_words():
    assert {c["id"] for c in CHECKLISTS} <= set(case_prefill.SITE)
    assert case_prefill.site_ok("Papillary carcinoma of the thyroid gland", "thyroid", "Thyroid cancer")  # a new checklist: its label's main word
    assert not case_prefill.site_ok("Invasive ductal carcinoma of the breast", "thyroid", "Thyroid cancer")


ADULT, CHILD = {"age": 46}, {"age": 7}


@pytest.mark.parametrize("quote,pid,sid,patient,ok", [
    ("Multiple liver metastases, largest 3 cm", "breast", "metastatic", ADULT, True),
    ("No evidence of distant metastasis.", "breast", "metastatic", ADULT, False),
    ("Lesion in liver suspicious for metastasis", "breast", "metastatic", ADULT, False),
    ("No evidence of distant metastasis.", "lung_nsclc", "non_metastatic", ADULT, True),
    ("No evidence of distant metastasis.", "breast", "early", ADULT, False),         # not metastatic is not early: it may be locally advanced
    ("Patient anxious to start treatment early", "breast", "early", ADULT, False),
    ("Locally advanced breast cancer with skin involvement", "breast", "locally_advanced", ADULT, True),
    ("Carcinoma cervix, FIGO 2018 stage IIIB", "cervix", "locally_advanced", ADULT, True),
    ("Carcinoma cervix, FIGO 2018 stage IIIB", "cervix", "early", ADULT, False),
    ("Carcinoma cervix, FIGO 2018 stage IB2", "cervix", "early", ADULT, True),
    ("Carcinoma cervix, FIGO stage IVB with lung nodules", "cervix", "metastatic", ADULT, True),
    ("Carcinoma cervix, FIGO stage IIA", "cervix", "early", ADULT, False),          # IIA1 or IIA2: unsure, dropped
    ("Endometrioid carcinoma, FIGO stage IIIC1", "corpus_uteri", "advanced", ADULT, True),
    ("Hodgkin lymphoma, nodular sclerosis type", "lymphoma", "adult_hodgkin", ADULT, True),
    ("Hodgkin lymphoma, nodular sclerosis type", "lymphoma", "adult_hodgkin", CHILD, False),
    ("Hodgkin lymphoma, nodular sclerosis type", "lymphoma", "adult_hodgkin", {}, False),  # no age: no adult or child setting
    ("Non-Hodgkin lymphoma, diffuse large B-cell type", "lymphoma", "adult_hodgkin", ADULT, False),
    ("Non-Hodgkin lymphoma, diffuse large B-cell type", "lymphoma", "adult_nhl", ADULT, True),
    ("Report status: FINAL with all values", "leukaemia", "adult_acute", ADULT, False),  # "all" is not ALL
    ("Bone marrow: B-ALL, blasts 82 percent", "leukaemia", "adult_acute", ADULT, True),
    ("Liver lesion, Report status: FINAL", "breast", "gone_setting", ADULT, False),     # a setting with no rule is never suggested
])
def test_the_setting_quote_states_that_setting(quote, pid, sid, patient, ok):
    assert case_prefill.setting_ok(quote, pid, sid, patient) is ok


def test_an_urgency_rests_on_a_finding_and_is_never_more_than_a_suggestion():
    src = {"title": "CECT", "text": "CECT THORAX ABDOMEN PELVIS\nImpression: Multiple liver metastases, largest 3 cm.\nReport status: FINAL\n"
                                    "Vaidyx Demo Hospital (SYNTHETIC)"}
    for q, ok in [("CECT THORAX ABDOMEN PELVIS", False), ("Report status: FINAL", False), ("Vaidyx Demo Hospital (SYNTHETIC)", False),
                  ("liver metastases", False), ("Impression: Multiple liver metastases, largest 3 cm.", True), ("Multiple liver metastases, largest 3 cm", True)]:
        assert case_prefill.urgency_quote_ok(q, src) is ok, q


def test_the_prompt_asks_for_the_diagnosis_line():
    msgs = case_prefill.messages({"age": 46, "sex": "F"}, READ, CHECKLISTS)
    assert "diagnosis line" in msgs[1]["content"] and "never a heading, title or status line" in msgs[1]["content"]
    assert "copied from the quote" in msgs[1]["content"]


def test_the_board_question_is_a_draft_with_its_basis():
    out, _ = case_prefill.check(answer(), READ, CHECKLISTS)
    bq = out["board_question"]
    assert bq["draft"] is True and [b["id"] for b in bq["basis"]] == ["R1"]  # R3 and R99 were not read
    out, _ = case_prefill.check(answer(board_question={"text": "x" * 900, "basis": []}), READ, CHECKLISTS)
    assert len(out["board_question"]["text"]) == 600


def test_the_department_comes_from_the_visits_without_the_model(people):
    encs = [{"kind": "OP", "number": "OP/26/1", "department": "Breast Surgery", "start": "2026-09-01"},
            {"kind": "OP", "number": "OP/26/2", "department": "Radiology", "start": "2026-09-02"}]
    two = {"treating": {"breast_surgery": "member", "medical_oncology": "member"}}
    d = case_prefill.department_for(two, encs)
    assert d["id"] == "breast_surgery" and "OP/26/1" in d["why"] and "01/09/2026" in d["why"]
    both = encs + [{"kind": "IP", "number": "IP/26/9", "department": "Medical Oncology", "start": "2026-09-10"}]
    assert case_prefill.department_for(two, both) is None  # two of theirs in the visits: the doctor chooses
    assert case_prefill.department_for({"treating": {"medical_oncology": "member"}}, encs) is None
    assert case_prefill.department_for({}, encs) is None


def test_pdf_text_is_read_from_the_text_layer():
    data = (FIX / "documents_documents_p02_r05_v2_pdf.pdf").read_bytes()
    text, partial = case_prefill.text_of({"content": data, "content_type": "application/pdf"})
    assert len(text) > 200 and not partial and "SYNTHETIC" in text.upper()
    assert case_prefill.text_of({"content": b"\x89PNG....", "content_type": "image/png"}) == ("", True)
    assert case_prefill.text_of({"content": b"Plain words", "content_type": "text/plain"}) == ("Plain words", False)


def test_the_prompt_stays_within_the_budget():
    big = [{"id": f"R{i}", "title": f"Report {i}", "date": "2026-09-01", "department": "", "text": "word " * 1200} for i in range(1, 13)]
    msgs = case_prefill.messages({"age": 46, "sex": "F"}, big, CHECKLISTS)
    body = msgs[1]["content"]
    assert len(body) < case_prefill.PROMPT_CHARS + 8000  # the reports within PROMPT_CHARS, plus the checklists and the task
    assert "breast: Breast cancer (settings: early = Early (operable), as recorded" in body
    assert "[R1] Report 1" in body and "never work out or guess a stage" in msgs[0]["content"]


# ---- the whole run against the mock hospital --------------------------------------------------------------------------------------

def run_prefill(roles):
    return asyncio.run(case_prefill.prefill(UHID, {"months": 24}, RAO, roles))


def test_prefill_reads_the_window_and_checks_every_value(people, his, model):
    out = run_prefill(org.roles(RAO))
    assert out["uhid"] == UHID and out["reports_in_window"] == 8 and out["reports_read"] == 3 and out["reports_skipped"] == 5
    call = model.calls[0]
    assert call["role"] == "reasoner" and call["temperature"] == 0.0 and call["purpose"] == "new case prefill" and call["json_schema"] is case_prefill.SCHEMA
    assert "HISTOPATHOLOGY REPORT" in call["messages"][1]["content"]
    # newest first: the biopsy (05/09), the CT text (02/09), the OPD note (01/09), numbered R1..R3 as the model saw them
    assert [(r["id"], r["title"][:14]) for r in out["reports"]] == [("R1", "Histopathology"), ("R2", "USG both breas"), ("R3", "OPD consultati")]
    assert out["cancer"]["report"]["id"] == "R1" and out["setting"]["id"] == "early" and out["urgency"]["level"] == 3
    assert out["urgency"]["report"]["id"] == "R3" and out["dropped"] == []
    assert [b["id"] for b in out["board_question"]["basis"]] == ["R1", "R3"]
    assert out["department"]["id"] == "breast_surgery"  # Rao's own department in the Breast Surgery visits
    assert set(out["model"]) == {"label", "origin", "medical"}
    ev = [json.loads(x) for x in (config.DATA_ROOT / "org_audit.jsonl").read_text().splitlines()]
    pf = [e for e in ev if e["kind"] == "case_prefill"][-1]
    assert pf["uhid"] == UHID and "department" in pf["fields"] and pf["dropped"] == len(out["dropped"])
    assert [e for e in ev if e["kind"] == "llm_call" and e.get("purpose") == "new case prefill" and e.get("uhid") == UHID]


def test_no_readable_report_means_no_model_call(people, his, model):
    TEXTS_SAVED = dict(TEXTS)
    TEXTS.clear()
    try:
        m = his_mock()
        his_client.client = lambda *a, **k: his_client.FHIRClient(BASE, TOKEN, transport=httpx.MockTransport(m))  # noqa: monkeypatched by `his`
        out = run_prefill(org.roles(RAO))
    finally:
        TEXTS.update(TEXTS_SAVED)
    assert out["reports_read"] == 0 and model.calls == [] and "cancer" not in out


# ---- the routes ---------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def app(people, monkeypatch, his):
    import routes.tumour_board_routes as R
    monkeypatch.setattr(R, "_warm", lambda: None)
    monkeypatch.setenv("TB_SCHEDULER", "0")
    o = org.load()
    o["users"][GR] = {"departments": {"breast_surgery": "member"}, "display_name": "Guest reviewer (synthetic)", "real_data": True}
    org.save(o, by="test")
    case_prefill.JOBS.clear()
    case_prefill.START_LIMIT._hits.clear()
    auth = FakeAuth(list(people) + [GR, VX], admins=(VX,))
    auth.totp_enabled = lambda u: True
    a = FastAPI()
    who = {"user": RAO}

    @a.middleware("http")
    async def _signed_in(request, call_next):
        request.state.current_user = who["user"]
        return await call_next(request)
    a.include_router(R.setup_tumour_board_routes())
    a.state.auth_manager = auth
    with TestClient(a) as tc:
        yield Api(tc, who)
    case_prefill.JOBS.clear()
    case_prefill.START_LIMIT._hits.clear()


def poll(api, job, until=5.0):
    t0 = time.time()
    while time.time() - t0 < until:
        r = api.get(f"/his/prefill/{job}")
        assert r.status_code == 200, r.text
        if r.json()["state"] != "running":
            return r.json()
        time.sleep(0.05)
    raise AssertionError("the job did not finish")


def test_the_route_runs_a_job_only_the_starter_reads(app, model):
    r = app.as_(RAO).tc.post("/api/tb/his/prefill", json={"identifier": UHID, "months": 24})
    assert r.status_code == 200, r.text
    job = r.json()["job"]
    assert r.json()["state"] == "running"
    got = poll(app, job)
    assert got["state"] == "done" and got["result"]["cancer"]["protocol"] == "breast" and got["result"]["reports_read"] == 3
    assert app.as_(MEHTA).get(f"/his/prefill/{job}").status_code == 404  # another doctor: not found, never the result
    assert app.as_(RAO).get("/his/prefill/PF-000000000000").status_code == 404
    again = app.as_(RAO).tc.post("/api/tb/his/prefill", json={"identifier": UHID, "months": 24})
    assert again.json()["job"] == job and len(model.calls) == 1  # the same lookup: the same job, no second model call


def test_the_route_has_the_lookups_gate(app, model):
    assert app.as_(GR).tc.post("/api/tb/his/prefill", json={"identifier": UHID}).status_code == 403  # a guest reviewer: no hospital system
    supporting = app.as_(RAVI).tc.post("/api/tb/his/prefill", json={"identifier": UHID})
    assert supporting.status_code == (200 if org.can(org.roles(RAVI), "create_case") else 403)
    assert app.as_(RAO).tc.post("/api/tb/his/prefill", json={"identifier": ""}).status_code == 400
    assert app.as_(RAO).tc.post("/api/tb/his/prefill", json={"identifier": UHID, "months": 999}).status_code == 400
    assert model.calls == []


def test_the_vaidyx_admin_never_starts_or_reads_a_job(app, model, monkeypatch):
    """Admin consoles D5: the Vaidyx admin has no clinical access, and the job reads and quotes the patient's reports."""
    r = app.as_(VX).tc.post("/api/tb/his/prefill", json={"identifier": UHID, "months": 24})
    assert r.status_code == 403 and r.json()["detail"] == case_prefill.NO_CLINICAL_ACCESS and not case_prefill.JOBS
    job = app.as_(RAO).tc.post("/api/tb/his/prefill", json={"identifier": UHID, "months": 24}).json()["job"]
    poll(app.as_(RAO), job)
    assert app.as_(VX).get(f"/his/prefill/{job}").status_code == 403
    assert len(model.calls) == 1
    monkeypatch.setenv("AUTH_ENABLED", "false")  # single-user mode (no login at all): as before
    case_prefill.JOBS.clear()
    r = app.as_(None).tc.post("/api/tb/his/prefill", json={"identifier": UHID, "months": 24})
    assert r.status_code == 200, r.text
    assert poll(app.as_(None), r.json()["job"])["state"] == "done"


def test_starts_are_limited_per_login(app, model):
    for _ in range(30):
        assert app.as_(RAO).tc.post("/api/tb/his/prefill", json={"identifier": UHID, "months": 24}).status_code == 200
    r = app.tc.post("/api/tb/his/prefill", json={"identifier": UHID, "months": 24})
    assert r.status_code == 429 and r.json()["detail"]["message"] == case_prefill.BUSY
    assert app.as_(MEHTA).tc.post("/api/tb/his/prefill", json={"identifier": UHID, "months": 24}).status_code in (200, 403)  # per login
    job = next(iter(case_prefill.JOBS))
    assert app.as_(RAO).get(f"/his/prefill/{job}").status_code == 200  # reading the job is not limited (the screen polls it)


def test_model_down_is_a_quiet_failure(app, model):
    model.error = llm.LLMError("reasoner model server unreachable at http://127.0.0.1:8100/v1 (ConnectError)")
    job = app.as_(RAO).tc.post("/api/tb/his/prefill", json={"identifier": UHID, "months": 24}).json()["job"]
    got = poll(app, job)
    assert got["state"] == "failed" and "result" not in got and "8100" not in got["error"] and "Fill the steps yourself" in got["error"]


def test_his_down_and_unknown_patient_fail_quietly(app, model, monkeypatch):
    job = app.as_(RAO).tc.post("/api/tb/his/prefill", json={"identifier": "VXH/26/999999"}).json()["job"]
    got = poll(app, job)
    assert got["state"] == "failed" and got["error"] == case_prefill.NOT_FOUND

    def down(request):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(his_client, "client", lambda *a, **k: his_client.FHIRClient(BASE, TOKEN, transport=httpx.MockTransport(down)))
    job = app.as_(RAO).tc.post("/api/tb/his/prefill", json={"identifier": "VXH/26/004209"}).json()["job"]
    got = poll(app, job)
    assert got["state"] == "failed" and got["error"] == case_prefill.FAILED_HIS and model.calls == []


def test_jobs_expire(app, model):
    job = app.as_(RAO).tc.post("/api/tb/his/prefill", json={"identifier": UHID, "months": 24}).json()["job"]
    poll(app, job)
    case_prefill.JOBS[job]["started"] -= case_prefill.JOB_TTL + 1
    assert app.as_(RAO).get(f"/his/prefill/{job}").status_code == 404
    assert job not in case_prefill.JOBS


def test_jobs_are_kept_per_hospital(people, his, model):
    async def go():
        job = case_prefill.start(UHID, {"months": 24}, RAO, org.roles(RAO))
        await job["task"]
        return job
    case_prefill.JOBS.clear()
    job = asyncio.run(go())
    assert case_prefill.view(job["id"], RAO)["state"] == "done"
    with config.use_hospital("lotus"):
        assert case_prefill.view(job["id"], RAO) is None and len(case_prefill.JOBS) == 0
    assert case_prefill.view(job["id"], RAO)["state"] == "done"
    case_prefill.JOBS.clear()


def test_a_new_lookup_stops_the_users_running_job(people, his, model):
    async def go():
        gate = asyncio.Event()
        real = llm.chat

        async def slow(*a, **k):
            await gate.wait()
            return await real(*a, **k)
        llm.chat = slow
        try:
            first = case_prefill.start(UHID, {"months": 24}, RAO, org.roles(RAO))
            await asyncio.sleep(0.2)
            second = case_prefill.start("VXH/26/004209", {"months": 24}, RAO, org.roles(RAO))
            await asyncio.sleep(0)
            gate.set()
            await asyncio.gather(first["task"], second["task"], return_exceptions=True)
            return first, second
        finally:
            llm.chat = real
    case_prefill.JOBS.clear()
    first, second = asyncio.run(go())
    assert first["state"] == "failed" and "another patient" in first["error"]
    assert second["id"] != first["id"]
    case_prefill.JOBS.clear()
