"""Ask PubMed on the platform (docs/pubmed-ask/DESIGN.md section 8): the job (start, poll by its starter only, the steps filled, at most
two running per login, 15 minutes), the threads (Case File shared with the team, Home private in a file of mode 600), pin, Save to
Published (the owning department's consultants, the quotes carried), the audit, the rate limit and the input checks, who may ask on each
route (the meeting window's members on the Case File on the floor), suggest_pubmed on a records answer, the voice reference "pubmed",
and no provenance URL or email in any answer. Hermetic: the fixtures of test_nik_meetings (fake logins, synthetic Case Files TB-001..003);
pubmed_ask.ask is replaced by a fake (no network, no model)."""
import asyncio
import json
import os
import stat
import threading
import time

import pytest

from tumour_board import access, audio_proxy as ap, chats, config, org, published, pubmed_ask, qa, store
from tumour_board import pubmed_threads as pt
from tumour_board.api import chats as chats_api
from tumour_board.api import pubmed as api_pubmed
from tumour_board.tests import test_nik_meetings as M
from tumour_board.tests.test_audio_routes import stub  # noqa: F401 (fixture)
from tumour_board.tests.test_nik_meetings import As, app, owned, started, tc  # noqa: F401 (fixtures)

CASE = "TB-002"  # breast, owned by Breast Surgery (priya, consultant; asha, resident) in these tests
Q = "What pathological complete response did trials report with neoadjuvant drug A in triple-negative breast cancer?"
SHA_SEARCH, SHA_FETCH, SHA_PAPER = "a" * 64, "b" * 64, "c" * 64
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
LEAK = "&email=contact%40hospital.example"  # what a careless provenance would carry: never shown


def paper(pmid, rank, **kw):
    p = {"pmid": pmid, "title": f"Synthetic paper {pmid} on drug A.", "journal": "Journal of synthetic oncology : official journal of the Test Society",
         "journal_abbr": "J Synth Oncol", "year": "2024", "authors_line": "Rao A, Iyer L, Nair K, et al.", "study_type": "Randomised trial", "tier": 2,
         "types": ["Journal Article", "Randomized Controlled Trial"], "preprint": False, "retracted": False, "retraction_notice": False, "concern": False,
         "erratum": False, "india": False, "doi": f"10.1000/synth.{pmid}", "pmcid": "", "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
         "has_abstract": True, "rank": rank, "read": True, "why_not_read": "", "cited": False,
         "provenance": {"url": EUTILS + f"efetch.fcgi?db=pubmed&id={pmid}&retmode=xml&tool=vaidyx-tb" + LEAK, "at": "2026-11-03T10:00:00+00:00",
                        "status": 200, "bytes": 5000, "sha256": SHA_PAPER, "tries": 1, "seconds": 0.4, "cached": False}}
    p.update(kw)
    return p


def answered(question, in_case_file, years):
    return {
        "question": question, "label": pubmed_ask.LABEL if in_case_file else pubmed_ask.LABEL_HOME, "status": "answered", "message": "",
        "search": {"query": "drug A AND triple-negative breast cancer", "broader_query": "drug A", "by": "model",
                   "attempts": [{"term": "drug A AND triple-negative breast cancer", "years": years, "count": 42, "warnings": []}],
                   "used": "drug A AND triple-negative breast cancer", "years": years, "translation": "\"drug a\"[All Fields]"},
        "statements": [
            {"text": "A phase 3 trial reported a pathological complete response of 64.8% with drug A.",
             "citations": [{"pmid": "39000001", "quote": "pathological complete response was 64.8% with drug A", "where": "RESULTS"},
                           {"pmid": "39000001", "quote": "Drug A improved the response.", "where": "CONCLUSIONS", "whole_sentence": True}]},
            {"text": "An Indian cohort reported a response in 52% of patients.",
             "citations": [{"pmid": "39000003", "quote": "52% of patients responded", "where": "Abstract"}]}],
        "removed": [{"text": "An unverified line.", "reason": "the quote is not word for word in the paper", "model_quotes": ["x"]}],
        "invented_pmids": 1,
        "papers": [paper("39000001", 1, cited=True), paper("39000002", 2, study_type="Preprint", tier=8, preprint=True, doi=""),
                   paper("39000003", 3, cited=True, india=True, study_type="Observational study", tier=5, journal="Indian journal of synthetic cancer")],
        "counts": {"found": 42, "fetched": 3, "read": 3},
        "calls": [{"what": "search", "url": EUTILS + "esearch.fcgi?db=pubmed&term=drug+A&tool=vaidyx-tb" + LEAK, "at": "2026-11-03T10:00:00+00:00",
                   "status": 200, "bytes": 900, "sha256": SHA_SEARCH, "tries": 1, "seconds": 0.5},
                  {"what": "fetch", "url": EUTILS + "efetch.fcgi?db=pubmed&id=39000001&tool=vaidyx-tb" + LEAK, "at": "2026-11-03T10:00:01+00:00",
                   "status": 200, "bytes": 15000, "sha256": SHA_FETCH, "tries": 1, "seconds": 0.9}],
        "model": "Gemma-4-31B-it (non-medical)", "searched_at": "2026-11-03T10:00:00+00:00", "steps": [], "seconds": 9.3}


class FakeAsk:
    """pubmed_ask.ask without PubMed or the model: reports the steps, writes one model-call line through `audit`, waits on `gate` when set,
    raises `crash` when set, else returns `answered`."""

    def __init__(self):
        self.calls, self.gate, self.crash = [], None, None

    async def __call__(self, question, *, context=None, identifiers=(), in_case_file=False, fresh=False, years=None, words=None, on_step=None,
                       audit=None, client=None):
        self.calls.append({"question": question, "context": context, "identifiers": list(identifiers), "in_case_file": in_case_file, "years": years,
                           **({"words": words} if words is not None else {})})
        on_step("words", "writing the PubMed search words")
        if audit:
            audit({"kind": "llm_call", "role": "reasoner", "model": "fake", "purpose": "pubmed search words", "seconds": 0.1, "attempts": 1})
        on_step("search", "searching PubMed: drug A (all years)")
        while self.gate is not None and not self.gate.is_set():
            await asyncio.sleep(0.01)
        if self.crash:
            raise self.crash
        on_step("fetch", "42 papers found, fetching the top 3 records")
        on_step("read", "the model is reading 3 abstracts")
        on_step("check", "checking every quote against PubMed's text")
        if audit:
            audit({"kind": "pubmed_ask", "status": "answered", "question": question[:300]})
        return answered(question, in_case_file, years)


@pytest.fixture
def fake(monkeypatch):
    f = FakeAsk()
    monkeypatch.setattr(pubmed_ask, "ask", f)
    pt.reset()
    api_pubmed.ASK_LIMIT._hits.clear()
    chats_api.ASK_LIMIT._hits.clear()
    yield f
    if f.gate is not None:
        f.gate.set()
    pt.reset()


@pytest.fixture
def hosp(tc, monkeypatch):  # noqa: F811
    """TB-002 owned by Breast Surgery; three more logins: an auditor, a department admin and a disabled doctor."""
    for u in ("audra", "deptad", "gone"):
        monkeypatch.setitem(M.TOKENS, f"tok-{u}", u)
    o = org.load()
    o["users"].update({"audra": {"auditor": True, "display_name": "Audra"}, "deptad": {"admin_of": ["radiology"], "display_name": "Dept Admin"},
                       "gone": {"departments": {"breast_surgery": "member"}, "disabled": True}})
    org.save(o, by="test")
    owned(CASE)
    return tc


def wait(tc, user, job_id, timeout=5.0):  # noqa: F811
    end = time.time() + timeout
    while time.time() < end:
        r = As(tc, user).get(f"/pubmed/jobs/{job_id}")
        assert r.status_code == 200, r.text
        if r.json()["status"] != "running":
            return r.json()
        time.sleep(0.02)
    raise AssertionError("the job is still running")


def ask_home(tc, user, question=Q, **kw):  # noqa: F811
    return As(tc, user).post("/pubmed/ask", json={"question": question, **kw})


def ask_case(tc, user, case_id=CASE, question=Q, **kw):  # noqa: F811
    return As(tc, user).post(f"/cases/{case_id}/pubmed/ask", json={"question": question, **kw})


def asked(tc, user, case_id=None, question=Q):  # noqa: F811
    """Ask, wait, return the job's answer (with its thread)."""
    r = ask_case(tc, user, case_id, question) if case_id else ask_home(tc, user, question)
    assert r.status_code == 202, r.text
    return wait(tc, user, r.json()["job_id"])


def clean(r):
    """No provenance URL, no email, no hash in what the screen gets."""
    assert "eutils" not in r.text and "@" not in r.text and "%40" not in r.text and "sha256" not in r.text and SHA_PAPER not in r.text, r.text
    return r


def code(r):
    d = r.json().get("detail")
    return d.get("code") if isinstance(d, dict) else None


# ---- Home ---------------------------------------------------------------------------------------------------------------------------

def test_home_ask_runs_a_job_with_steps_and_keeps_a_private_history(hosp, fake):
    tc = hosp
    r = clean(ask_home(tc, "priya", "  " + Q + "  "))
    assert r.status_code == 202 and set(r.json()) == {"job_id"}
    j = wait(tc, "priya", r.json()["job_id"])
    assert j["status"] == "done" and "error" not in j
    assert [s["step"] for s in j["steps"]] == ["words", "search", "fetch", "read", "check"]
    assert all(isinstance(s["seconds"], (int, float)) and s["detail"] for s in j["steps"])
    t = j["thread"]
    assert set(t) == set(pt.THREAD_KEYS)
    assert t["id"].startswith("PM") and t["kind"] == "pubmed" and t["by"] == "priya" and t["by_name"] == "Dr Priya Nair" and t["question"] == Q
    assert t["status"] == "answered" and t["label"] == pubmed_ask.LABEL_HOME and t["model"] == "Gemma-4-31B-it (non-medical)"
    assert t["search"] == {"used": "drug A AND triple-negative breast cancer", "years": None, "by": "model", "count": 42,
                           "attempts": [{"term": "drug A AND triple-negative breast cancer", "years": None, "count": 42}]}
    assert t["counts"] == {"found": 42, "fetched": 3, "read": 3} and t["dropped"] == 1 and t["invented_pmids"] == 1
    assert t["pinned"] is False and t["saved_pmids"] == [] and t["seconds"] == 9.3
    assert t["statements"][0]["citations"][1] == {"pmid": "39000001", "quote": "Drug A improved the response.", "where": "CONCLUSIONS", "whole_sentence": True}
    assert all(set(p) == set(pt.PAPER_KEYS) for p in t["papers"]) and [p["cited"] for p in t["papers"]] == [True, False, True]
    assert t["papers"][0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/39000001/"  # the paper's own PubMed page stays: it is not a call
    assert fake.calls == [{"question": Q, "context": None, "identifiers": [], "in_case_file": False, "years": None}]  # Home: nothing of a patient
    # the history: the login's own, newest first; another login sees none of it
    h = clean(As(tc, "priya").get("/pubmed/history")).json()
    assert [x["id"] for x in h["threads"]] == [t["id"]] and h["threads"][0] == t
    assert As(tc, "anil").get("/pubmed/history").json() == {"threads": []}
    t2 = asked(tc, "priya", question="What overall survival did trials of drug A report in breast cancer?")["thread"]
    assert [x["id"] for x in As(tc, "priya").get("/pubmed/history").json()["threads"]] == [t2["id"], t["id"]]
    # the file: mode 600 in a folder of mode 700; the calls' SHA-256 kept, never their URLs
    p = pt.home_path("priya")
    assert p == config.DATA_ROOT / "pubmed_home" / "priya.json"
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600 and stat.S_IMODE(os.stat(p.parent).st_mode) == 0o700
    raw = p.read_text()
    saved = json.loads(raw)["threads"][0]
    assert [c["sha256"] for c in saved["calls"]] == [SHA_SEARCH, SHA_FETCH] and saved["papers"][0]["sha256"] == SHA_PAPER
    assert "eutils" not in raw and "%40" not in raw and "@" not in raw
    # the organisation log, not a Case File's
    ev = [e for e in org.read_audit(1000) if e.get("kind") == "pubmed_asked"]
    assert len(ev) == 2 and ev[-1]["by"] == "priya" and ev[-1]["question"] == Q and ev[-1]["words"] == "drug A AND triple-negative breast cancer"
    assert ev[-1]["status"] == "answered" and ev[-1]["found"] == 42 and ev[-1]["read"] == 3 and ev[-1]["thread"] == t["id"] and ev[-1]["model_calls"] == 1
    assert not [e for e in store.read_audit(CASE) if e.get("kind") == "pubmed_asked"]


def test_home_history_keeps_the_newest_100(hosp, fake, monkeypatch):
    tc = hosp
    monkeypatch.setattr(pt, "MAX_HOME", 3)
    ids = [asked(tc, "anil", question=f"What response did trials of drug {x} report?")["thread"]["id"] for x in "ABCD"]
    assert [x["id"] for x in As(tc, "anil").get("/pubmed/history").json()["threads"]] == ids[:0:-1]
    assert pt.MAX_CASE == 300 and pt.JOB_TTL == 900 and pt.MAX_RUNNING == 2


@pytest.mark.parametrize("user,ok", [("priya", True), ("asha", True), ("anil", True), ("ravi", True), ("guest", True),
                                     ("admin", False), ("tbroot", False), ("audra", False), ("deptad", False), ("gone", False)])
def test_who_asks_on_home(hosp, fake, user, ok):
    r = ask_home(hosp, user)
    if ok:
        assert r.status_code == 202, r.text
        assert wait(hosp, user, r.json()["job_id"])["status"] == "done"
    else:
        assert r.status_code == 403 and not fake.calls
        if user != "gone":  # a disabled login is refused on every Tumour Board route first
            assert r.json()["detail"] == {"message": pt.NOT_CLINICAL, "code": "not_clinical"}


def test_only_the_starter_polls_and_a_job_is_forgotten_after_15_minutes(hosp, fake):
    tc = hosp
    jid = ask_home(tc, "priya").json()["job_id"]
    wait(tc, "priya", jid)
    for user in ("anil", "asha", "admin"):
        r = As(tc, user).get(f"/pubmed/jobs/{jid}")
        assert r.status_code == 404 and code(r) == "no_job" and "thread" not in r.text
    assert As(tc, "priya").get("/pubmed/jobs/not-a-job").status_code == 404
    assert As(tc, "priya").get("/pubmed/jobs/J" + "0" * 32).status_code == 404
    pt._jobs[jid]["started"] -= pt.JOB_TTL + 1
    assert As(tc, "priya").get(f"/pubmed/jobs/{jid}").status_code == 404 and jid not in pt._jobs


# ---- the Case File ------------------------------------------------------------------------------------------------------------------

def seed_gate(case_id=CASE):
    st = store.get_state(case_id)
    st["gate"] = {"core_data": [
        {"id": "diagnosis", "evidence": [{"fact": "histologic_type", "value": "Invasive breast carcinoma of no special type (ductal).", "quote": "x"}]},
        {"id": "stage", "evidence": [{"fact": "recorded_stage", "value": "cT2 N1 M0, Stage IIB (AJCC 8th edition)", "quote": "x"}]},
        {"id": "biomarkers", "evidence": [{"fact": "er", "value": "Positive, 90% strong (Allred 8)"}, {"fact": "er", "value": "ER positive"},
                                          {"fact": "her2", "value": "Equivocal, FISH sent on 12/09/2026"}]},  # a date: left out
        {"id": "diagnosis_date_mode", "evidence": [{"fact": "diagnosis_date_mode", "value": "08-Sep-2026"}]}],  # not a search term
        "requirements": [{"id": "pathology", "evidence": [{"fact": "pr", "value": "Positive, 70% (Allred 7)"},
                                                          {"fact": "grade", "value": "Grade 2, block SYN-200417"}]}]}  # the MRN: left out
    store.save_state(case_id, st)


def test_case_ask_sends_the_cancer_and_documented_terms_never_identifiers_and_is_shared(hosp, fake):
    tc = hosp
    seed_gate()
    j = asked(tc, "asha", CASE)
    t = j["thread"]
    assert j["status"] == "done" and t["label"] == pubmed_ask.LABEL and t["by"] == "asha"
    call = fake.calls[-1]
    assert call["in_case_file"] is True and call["context"] == {"cancer": "Breast cancer", "terms": [
        "histology: Invasive breast carcinoma of no special type (ductal).", "stage: cT2 N1 M0, Stage IIB (AJCC 8th edition)",
        "ER: Positive, 90% strong (Allred 8)", "PR: Positive, 70% (Allred 7)"]}
    assert "SYNTHETIC, Lakshmi Iyer" in call["identifiers"] and "SYN-200417" in call["identifiers"]
    # the whole team reads it: the owner consultant and the coordinator; it is not in anyone's Home history
    for user in ("priya", "anil", "asha"):
        r = clean(As(tc, user).get(f"/cases/{CASE}/pubmed"))
        assert r.status_code == 200 and [x["id"] for x in r.json()["threads"]] == [t["id"]] and r.json()["threads"][0] == t
    assert As(tc, "asha").get("/pubmed/history").json() == {"threads": []}
    # stored with the calls' SHA-256, no URL
    raw = (store.case_dir(CASE) / "pubmed_threads.json").read_text()
    saved = json.loads(raw)["threads"][0]
    assert [c["sha256"] for c in saved["calls"]] == [SHA_SEARCH, SHA_FETCH] and "eutils" not in raw and "%40" not in raw
    # the Case File's audit: the model call with who asked, then pubmed_asked; the pipeline's own line is not doubled
    ev = store.read_audit(CASE)
    asked_ev = [e for e in ev if e.get("kind") == "pubmed_asked"]
    assert len(asked_ev) == 1 and asked_ev[0]["by"] == "asha" and asked_ev[0]["question"] == Q and asked_ev[0]["thread"] == t["id"]
    assert asked_ev[0]["words"] == "drug A AND triple-negative breast cancer" and asked_ev[0]["status"] == "answered"
    assert asked_ev[0]["found"] == 42 and asked_ev[0]["read"] == 3 and asked_ev[0]["statements"] == 2 and asked_ev[0]["dropped"] == 1
    assert [e["by"] for e in ev if e.get("kind") == "llm_call"] == ["asha"] and not [e for e in ev if e.get("kind") == "pubmed_ask"]
    assert store.verify_audit(CASE)["ok"]
    assert not [e for e in org.read_audit(1000) if e.get("kind") == "pubmed_asked"]


def test_who_reads_and_asks_in_a_case_file(hosp, fake):
    tc = hosp
    for user in ("priya", "asha", "anil"):
        assert ask_case(tc, user).status_code == 202, user
    tid = asked(tc, "priya", CASE)["thread"]["id"]

    def refused(user, ok_codes=(403,)):
        for r in (ask_case(tc, user), As(tc, user).get(f"/cases/{CASE}/pubmed"), As(tc, user).post(f"/cases/{CASE}/pubmed/{tid}/pin", json={"pinned": True})):
            assert r.status_code in ok_codes, (user, r.status_code, r.text)
            assert "Synthetic paper" not in r.text and "drug A" not in r.text

    refused("ravi")    # Radiology: no scope at all
    refused("dev")     # a treating consultant of another department
    refused("admin")   # the Vaidyx admin without a break-glass window
    refused("guest")   # an outside expert outside a meeting
    # a supporting department taking part reads the whole Case File, never the team's lists
    c = store.get_case(CASE); c["participants"] = [{"department": "radiology", "since": store.now_iso(), "by": "priya"}]; store.save_case(c)
    assert access.scope(org.roles("ravi"), store.get_case(CASE)) == access.FULL
    refused("ravi")
    r = As(tc, "ravi").get(f"/cases/{CASE}/pubmed")
    assert r.json()["detail"] == {"message": pt.NOT_READER, "code": "pubmed_forbidden"}
    # a department that was only asked (REQUESTS) never reads them
    st = store.get_state(CASE)
    st["actions"].append({"id": "A9", "source": "pre_authorization", "requirement": "biopsy", "label": "Biopsy", "department": "Pathology",
                          "department_id": "pathology", "status": "pending", "created": store.now_iso(), "history": []})
    store.save_state(CASE, st)
    assert access.scope(org.roles("meena"), store.get_case(CASE)) == access.REQUESTS
    refused("meena")
    # a doctor's window opened with a reason (READ) is not the meeting window
    access.open_doctor_window("lata", CASE, "Second opinion asked in the corridor")
    assert access.scope(org.roles("lata"), store.get_case(CASE)) == access.READ
    refused("lata")
    assert len(fake.calls) == 4


def test_an_admitted_meeting_member_asks_on_the_case_on_the_floor_only(hosp, fake):
    tc = hosp
    mid = started(tc, discussion=(CASE, "TB-001"), noting=())  # TB-002 on the floor
    code_ = As(tc, "anil").post(f"/meetings/{mid}/code").json()["value"]
    As(tc, "kiran").post("/meetings/join", json={"code": code_})
    assert ask_case(tc, "kiran").status_code == 403  # waiting, not admitted yet
    As(tc, "anil").post(f"/meetings/{mid}/admit", json={"user": "kiran"})
    access.meeting_window_reset()
    assert access.scope(org.roles("kiran"), store.get_case(CASE)) == access.READ
    j = asked(tc, "kiran", CASE)
    assert j["status"] == "done" and j["thread"]["label"] == pubmed_ask.LABEL
    tid = j["thread"]["id"]
    assert [x["id"] for x in As(tc, "kiran").get(f"/cases/{CASE}/pubmed").json()["threads"]] == [tid]
    assert As(tc, "kiran").post(f"/cases/{CASE}/pubmed/{tid}/pin", json={"pinned": True}).json()["pinned"] is True
    assert As(tc, "kiran").post(f"/cases/{CASE}/pubmed/{tid}/save", json={"pmid": "39000001"}).status_code == 403  # the owner's consultants save
    assert [e["by"] for e in store.read_audit(CASE) if e.get("kind") == "pubmed_asked"] == ["kiran"]
    # not another Case File on the agenda
    assert ask_case(tc, "kiran", "TB-001").status_code == 403 and As(tc, "kiran").get("/cases/TB-001/pubmed").status_code == 403
    # Next: the window follows the floor
    assert As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": "TB-001"}).status_code == 200
    assert ask_case(tc, "kiran").status_code == 403 and As(tc, "kiran").get(f"/cases/{CASE}/pubmed").status_code == 403
    # the voice reference follows the same rule
    ref = {"kind": "pubmed", "case_id": CASE, "id": tid}
    assert ap.resolve(org.roles("kiran"), ref) is None
    As(tc, "anil").post(f"/meetings/{mid}/current", json={"case_id": CASE})
    access.meeting_window_reset()
    assert ap.resolve(org.roles("kiran"), ref).startswith("From PubMed.")


def test_a_crash_inside_ask_is_an_unavailable_thread_never_a_500(hosp, fake, monkeypatch):
    tc = hosp
    fake.crash = RuntimeError("internal detail /data/vaidyx secret")
    r = ask_case(tc, "priya")
    assert r.status_code == 202
    j = wait(tc, "priya", r.json()["job_id"])
    clean(As(tc, "priya").get(f"/pubmed/jobs/{r.json()['job_id']}"))
    assert j["status"] == "failed" and j["error"] == "Ask PubMed could not finish this question (RuntimeError). Try again in a minute."
    t = j["thread"]
    assert t["status"] == "unavailable" and t["message"] == j["error"] and t["statements"] == [] and t["papers"] == [] and t["label"] == pubmed_ask.LABEL
    assert "secret" not in json.dumps(j)
    assert [x["id"] for x in As(tc, "priya").get(f"/cases/{CASE}/pubmed").json()["threads"]] == [t["id"]]
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "pubmed_asked"]
    assert ev[-1]["status"] == "unavailable" and ev[-1]["words"] == ""
    # a job that hangs ends too
    fake.crash, fake.gate = None, threading.Event()
    monkeypatch.setattr(pt, "JOB_TIMEOUT", 0.2)
    j = wait(tc, "priya", ask_home(tc, "priya").json()["job_id"])
    assert j["status"] == "failed" and j["thread"]["status"] == "unavailable" and j["error"] == pt.TIMED_OUT
    assert As(tc, "priya").get("/pubmed/history").json()["threads"][0]["status"] == "unavailable"


def test_a_third_running_question_is_refused_and_the_steps_show_progress(hosp, fake):
    tc = hosp
    fake.gate = threading.Event()
    a = ask_home(tc, "priya").json()["job_id"]
    b = ask_case(tc, "priya").json()["job_id"]
    deadline = time.time() + 5
    while len(As(tc, "priya").get(f"/pubmed/jobs/{a}").json()["steps"]) < 2 and time.time() < deadline:
        time.sleep(0.02)
    v = As(tc, "priya").get(f"/pubmed/jobs/{a}").json()
    assert v["status"] == "running" and [s["step"] for s in v["steps"]] == ["words", "search"] and "thread" not in v
    for r in (ask_home(tc, "priya"), ask_case(tc, "priya")):
        assert r.status_code == 429 and r.json()["detail"] == {"message": pt.BUSY, "code": "too_many_running"}
    assert ask_home(tc, "anil").status_code == 202  # another login is not held up
    fake.gate.set()
    assert wait(tc, "priya", a)["status"] == "done" and wait(tc, "priya", b)["status"] == "done"
    assert ask_home(tc, "priya").status_code == 202
    assert len(api_pubmed.ASK_LIMIT._hits["priya"]) == 3  # the refused ones did not count


def test_rate_limit_12_per_10_minutes_over_both_routes(hosp, fake):
    tc = hosp
    for i in range(12):
        r = ask_home(tc, "priya") if i % 2 else ask_case(tc, "priya")
        assert r.status_code == 202, (i, r.text)
        wait(tc, "priya", r.json()["job_id"])
    for r in (ask_home(tc, "priya"), ask_case(tc, "priya")):
        assert r.status_code == 429 and code(r) == "rate_limited" and "12 in 10 minutes" in r.json()["detail"]["message"]
    assert ask_home(tc, "anil").status_code == 202  # per login


@pytest.mark.parametrize("body", [{}, {"question": ""}, {"question": "  ab  "}, {"question": "x" * 601}, {"question": 123},
                                  {"question": Q, "years": 3}, {"question": Q, "years": "5"}, {"question": Q, "years": True}, [Q]])
def test_input_is_checked(hosp, fake, body):
    for path in ("/pubmed/ask", f"/cases/{CASE}/pubmed/ask"):
        r = As(hosp, "priya").post(path, json=body)
        assert r.status_code == 400, (path, body, r.text)
        assert isinstance(r.json()["detail"], dict) and r.json()["detail"]["message"]
    assert not fake.calls and not api_pubmed.ASK_LIMIT._hits.get("priya")


def test_valid_years_and_lengths_pass(hosp, fake):
    tc = hosp
    for years in (None, 5, 10):
        j = wait(tc, "priya", ask_home(tc, "priya", years=years).json()["job_id"])
        assert fake.calls[-1]["years"] == years and j["thread"]["search"]["years"] == years
    q600 = "What " + "y" * 587 + " trials?"
    assert len(q600) == 600 and ask_case(tc, "priya", question="  " + q600 + "  ").status_code == 202
    r = ask_home(tc, "priya", question=" pCR ")  # three letters is a question
    assert r.status_code == 202 and wait(tc, "priya", r.json()["job_id"])["thread"]["question"] == "pCR"
    As(tc, "priya")._c()
    assert tc.post("/api/tb/pubmed/ask", content=b"not json", headers={"content-type": "application/json"}).status_code == 400


def test_pin_orders_the_team_list(hosp, fake):
    tc = hosp
    t1 = asked(tc, "priya", CASE, "What response did trials of drug A report?")["thread"]
    t2 = asked(tc, "anil", CASE, "What response did trials of drug B report?")["thread"]
    assert [x["id"] for x in As(tc, "asha").get(f"/cases/{CASE}/pubmed").json()["threads"]] == [t2["id"], t1["id"]]
    r = clean(As(tc, "asha").post(f"/cases/{CASE}/pubmed/{t1['id']}/pin", json={"pinned": True}))
    assert r.status_code == 200 and r.json()["pinned"] is True and r.json()["id"] == t1["id"]
    assert [x["id"] for x in As(tc, "priya").get(f"/cases/{CASE}/pubmed").json()["threads"]] == [t1["id"], t2["id"]]
    assert As(tc, "asha").post(f"/cases/{CASE}/pubmed/{t1['id']}/pin", json={"pinned": False}).json()["pinned"] is False
    assert As(tc, "asha").post(f"/cases/{CASE}/pubmed/{t2['id']}/pin").json()["pinned"] is True  # no body: pin
    assert As(tc, "asha").post(f"/cases/{CASE}/pubmed/PM00000000/pin", json={}).status_code == 404
    home = asked(tc, "anil")["thread"]
    assert As(tc, "anil").post(f"/cases/{CASE}/pubmed/{home['id']}/pin", json={}).status_code == 404  # a Home thread is not the team's
    kinds = [e["kind"] for e in store.read_audit(CASE) if e.get("kind", "").startswith("pubmed_")]
    assert kinds == ["pubmed_asked", "pubmed_asked", "pubmed_pinned", "pubmed_unpinned", "pubmed_pinned"]


def test_save_to_published_by_the_owner_consultant_with_the_quotes(hosp, fake):
    tc = hosp
    t = asked(tc, "asha", CASE)["thread"]
    for user in ("asha", "anil", "ravi", "dev"):
        assert As(tc, user).post(f"/cases/{CASE}/pubmed/{t['id']}/save", json={"pmid": "39000001"}).status_code == 403, user
    r = clean(As(tc, "priya").post(f"/cases/{CASE}/pubmed/{t['id']}/save", json={"pmid": "39000001"}))
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["source"] == "pubmed" and item["source_id"] == "39000001" and item["pmid"] == "39000001" and item["kind"] == "paper"
    assert item["peer_reviewed"] is True and item["label"] == published.LABEL and item["added_by"] == "priya"
    assert item["title"] == "Synthetic paper 39000001 on drug A." and item["authors"] == "Rao A, Iyer L, Nair K, et al." and item["year"] == "2024"
    assert item["doi"] == "10.1000/synth.39000001" and item["url"] == "https://pubmed.ncbi.nlm.nih.gov/39000001/"
    assert item["quotes"] == [{"text": "pathological complete response was 64.8% with drug A", "where": "Abstract, RESULTS", "label": ""},
                              {"text": "Drug A improved the response.", "where": "Abstract, CONCLUSIONS", "label": ""}]
    assert [x["id"] for x in As(tc, "priya").get(f"/cases/{CASE}/published").json()["items"]] == [item["id"]]
    assert As(tc, "asha").get(f"/cases/{CASE}/pubmed").json()["threads"][0]["saved_pmids"] == ["39000001"]
    assert As(tc, "priya").post(f"/cases/{CASE}/pubmed/{t['id']}/save", json={"pmid": "39000001"}).status_code == 409  # already there
    pre = As(tc, "priya").post(f"/cases/{CASE}/pubmed/{t['id']}/save", json={"pmid": "39000002"}).json()
    assert pre["kind"] == "preprint" and pre["peer_reviewed"] is False and pre["quotes"] == [] and pre["doi"] == ""
    assert As(tc, "priya").post(f"/cases/{CASE}/pubmed/{t['id']}/save", json={"pmid": "12345"}).status_code == 404
    assert As(tc, "priya").post(f"/cases/{CASE}/pubmed/{t['id']}/save", json={"pmid": "abc"}).status_code == 400
    assert As(tc, "priya").post(f"/cases/{CASE}/pubmed/PM00000000/save", json={"pmid": "39000001"}).status_code == 404
    ev = [e for e in store.read_audit(CASE) if e.get("kind") == "published_added"]
    assert [(e["by"], e["source"], e["quotes"]) for e in ev] == [("priya", "pubmed", 2), ("priya", "pubmed", 0)]
    assert As(tc, "asha").get(f"/cases/{CASE}/pubmed").json()["threads"][0]["saved_pmids"] == ["39000001", "39000002"]


# ---- suggest_pubmed on a records answer ---------------------------------------------------------------------------------------------

@pytest.fixture
def records(monkeypatch):
    async def ask(case_id, question, history=None):
        if "ECOG" in question:
            return {"status": "answered", "statements": [{"text": "ECOG 1 is recorded.", "citations": []}], "message": "", "seconds": 1.0}
        return {"status": "not_documented", "statements": [], "message": "Not documented in the Case File.", "seconds": 1.0}
    monkeypatch.setattr(qa, "ask", ask)


@pytest.mark.parametrize("question,want", [
    (Q, True),
    ("What did trials report for HER2-positive breast cancer with trastuzumab deruxtecan?", True),
    ("What is the evidence for her 2 positive disease and pertuzumab?", True),
    ("Is there a biopsy report in the Case File?", False),
    ("What does the scan report say about the axilla?", False),
    ("What is her ER status?", False),
    ("Is the HER2 result documented?", False),
    ("Did the discharge summary mention lymphoedema?", False),
    ("What did the latest note say about pain?", False),
    ("What response rate did trials report for this patient?", False),
    ("What did trials report for Lakshmi with drug A?", False),  # the patient's name: never a PubMed question
    ("Should we give her drug A?", False),
    ("What is the ECOG?", False),  # answered from the records
])
def test_suggest_pubmed_on_a_records_answer(hosp, fake, records, question, want):
    r = As(hosp, "priya").post(f"/cases/{CASE}/chats", json={"question": question})
    assert r.status_code == 200, r.text
    assert r.json()["suggest_pubmed"] is want
    assert not fake.calls  # only a suggestion: nothing is asked of PubMed


def test_suggest_pubmed_rule():
    assert chats.suggest_pubmed("not_documented", Q) is True
    assert chats.suggest_pubmed("answered", Q) is False and chats.suggest_pubmed("out_of_scope", Q) is False
    assert chats.suggest_pubmed("not_documented", "") is False
    assert chats.suggest_pubmed("not_documented", "What did trials of UHID 1234567 report?") is False


# ---- voice ----------------------------------------------------------------------------------------------------------------------------

def test_voice_reads_a_pubmed_thread_with_its_access(hosp, fake, stub):  # noqa: F811
    tc = hosp
    tid = asked(tc, "priya", CASE)["thread"]["id"]
    ref = {"kind": "pubmed", "case_id": CASE, "id": tid}
    want = ("From PubMed. A phase 3 trial reported a pathological complete response of 64.8% with drug A (Rao A, Journal of synthetic oncology, 2024). "
            "An Indian cohort reported a response in 52% of patients (Rao A, Indian journal of synthetic cancer, 2024).")
    assert ap.resolve(org.roles("priya"), ref) == want
    r = As(tc, "anil").post("/audio/tts", json={"ref": ref, "screen": "ask"})
    assert r.status_code == 200 and r.headers["x-parts"] == "3" and json.loads(stub.calls[-1].content)["text"] == "From PubMed."
    r = As(tc, "anil").post("/audio/tts", json={"ref": ref, "part": 1})
    assert json.loads(stub.calls[-1].content)["text"] == "A phase 3 trial reported a pathological complete response of 64.8% with drug A (Rao A, Journal of synthetic oncology, 2024)."
    for user in ("ravi", "dev", "guest"):
        assert As(tc, user).post("/audio/tts", json={"ref": ref}).status_code in (403, 404), user
    c = store.get_case(CASE); c["participants"] = [{"department": "radiology", "since": store.now_iso(), "by": "priya"}]; store.save_case(c)
    assert As(tc, "ravi").post("/audio/tts", json={"ref": ref}).status_code == 404  # a supporting participant: not the team's lists
    spoken = [e for e in store.read_audit(CASE) if e.get("kind") == "audio_spoken"]
    assert spoken and spoken[0]["ref"] == f"pubmed:{CASE}:{tid}:" and "PubMed" not in json.dumps(spoken)
    # Home: the login's own history only
    hid = asked(tc, "priya")["thread"]["id"]
    home = {"kind": "pubmed", "id": hid}
    assert As(tc, "priya").post("/audio/tts", json={"ref": home}).status_code == 200
    for user in ("anil", "asha"):
        assert As(tc, user).post("/audio/tts", json={"ref": home}).status_code == 404
    assert ap.resolve(org.roles("priya"), {"kind": "pubmed", "case_id": CASE, "id": hid}) is None  # a Home thread is not the Case File's
    assert ap.resolve(org.roles("priya"), {"kind": "pubmed", "id": "../../etc"}) is None
    refused = [e for e in org.read_audit(1000) if e.get("kind") == "audio_refused"]
    assert refused and refused[0]["ref_kind"] == "pubmed"


def test_voice_text_for_answers_without_lines():
    base = {"statements": [], "papers": []}
    assert pt.speech({**base, "status": "not_found", "message": pubmed_ask.NOT_FOUND}) == "From PubMed. " + pubmed_ask.NOT_FOUND
    assert pt.speech({**base, "status": "refused", "message": pubmed_ask.REFUSED}) == pubmed_ask.REFUSED
    assert pt.speech({**base, "status": "unavailable", "message": "PubMed answered 503 after 4 tries. Try again in a minute."}).startswith("PubMed answered 503")
    t = {"status": "answered", "statements": [{"text": "A line.", "citations": [{"pmid": "1"}]}],
         "papers": [{"pmid": "1", "authors_line": "", "journal": "", "journal_abbr": "Lancet", "year": "2019"}]}
    assert pt.speech(t) == "From PubMed. A line (Lancet, 2019)."


def test_case_context_never_carries_an_identifier():
    case = {"case_id": "X", "protocol": "generic", "cancer_name": "Papillary thyroid carcinoma",
            "patient": {"name": "SYNTHETIC, Ramesh Kumar", "mrn": "SYN-100231"}}
    st = {"gate": {"core_data": [{"evidence": [{"fact": "histologic_type", "value": "Papillary carcinoma, Ramesh Kumar block"},
                                                {"fact": "recorded_stage", "value": "pT1b N0"}]}]}}
    assert pt.case_context(case, st) == {"cancer": "Papillary thyroid carcinoma", "terms": ["stage: pT1b N0"]}
    assert pt.case_context({"protocol": "generic"}, {}) == {"cancer": "", "terms": []}
    assert pt.case_context({"protocol": "lung_nsclc"}, {"gate": None}) == {"cancer": "Lung cancer (NSCLC)", "terms": []}
    assert pt.case_context({"protocol": "no_such"}, {}) == {"cancer": "", "terms": []}


def test_home_file_name_never_comes_from_an_odd_login():
    assert pt.home_path("dr.rao").name == "dr.rao.json"
    for odd in ("../x", "a/b", ".hidden", "", "x" * 80):
        p = pt.home_path(odd)
        assert p.parent == config.DATA_ROOT / "pubmed_home" and p.name.startswith("h-") and "/" not in p.name[:-5]



def test_search_again_with_the_doctors_words_and_can_save(hosp, fake):
    tc = hosp
    r = ask_case(tc, "asha", words="  drug A   AND  TNBC ")
    assert r.status_code == 202, r.text
    wait(tc, "asha", r.json()["job_id"])
    assert fake.calls[-1]["words"] == "drug A AND TNBC"
    wait(tc, "anil", ask_home(tc, "anil").json()["job_id"])
    assert "words" not in fake.calls[-1]  # no words given: the model writes them
    for bad in ("x", 5, "w" * 301):
        assert ask_case(tc, "asha", words=bad).status_code == 400
    assert As(tc, "priya").get(f"/cases/{CASE}/pubmed").json()["can_save"] is True  # the owning department's consultant
    assert As(tc, "asha").get(f"/cases/{CASE}/pubmed").json()["can_save"] is False
