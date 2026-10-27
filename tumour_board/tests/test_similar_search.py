"""night-v3 item 7.2: the search and ranking of Similar Case Files (tumour_board/similar.py part 2, tumour_board/api/similar.py). The
reasoner orders the candidates over three fixed permutations merged by median rank (ties by RRF, the RRF order and "text" when no
answer is valid), cached by signature; it picks "why similar" and "how it differs" pairs by id only, and code keeps a pair only when
both quotes match their sources read again, the past line names nobody, a "differs" pair differs and both lines are the same kind of
fact; the cards carry no number, no day-level date of the past file and no identifier; the routes need full scope on this file, screen
the words, limit the rate and audit every search and opening. Synthetic Case Files only; llm.chat and search._embed are fakes (no GPU,
fastembed never loads); the real case is never opened (a synthetic protected id stands in for it)."""
import ast
import asyncio
import hashlib
import inspect
import json
import random
import re
import warnings
from pathlib import Path

import numpy as np
import pytest

from tumour_board import access, config, grounding, llm, org, published, search, similar, store
from tumour_board.tests.test_nik_me import ANIL, MEHTA, RAO, RAVI, VX, auth, people  # noqa: F401
from tumour_board.tests.test_nik_team import full  # noqa: F401
from tumour_board.tests.util import add, fact, make_doc

DIM = 16
NAMES = ("Sarojini Pillai", "Kamala Bhaskaran", "Rukmini Sethuraman", "Indira Venkatesh", "Padmavathi Reddy", "Hemalatha Gowda",
         "Sujatha Kulkarni", "Vasantha Murthy", "Annapurna Joshi", "Shanthala Hegde", "Revathi Subramanian", "Gayathri Nair")
_N = [0]


# ---- fakes ---------------------------------------------------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fake_embed(monkeypatch):
    """search._embed replaced: a float32 vector from a hash of the text (fastembed never loads)."""
    def emb(texts, prefix=""):
        out = []
        for t in texts:
            h = hashlib.sha256((prefix + t).encode()).digest()
            out.append(np.frombuffer(h[:DIM], dtype=np.uint8).astype(np.float32) + 1.0)
        return np.array(out, dtype=np.float32)
    monkeypatch.setattr(search, "_embed", emb)
    similar._loaded.update(key=None, meta=None, matrix=None)


@pytest.fixture(autouse=True)
def _fresh_limits():
    from tumour_board.api import similar as similar_api
    from tumour_board.api import team as team_api
    similar_api.SEARCH_LIMIT._hits.clear()
    similar_api.OPEN_LIMIT._hits.clear()
    team_api.OPEN_LIMIT._hits.clear()
    yield
    similar_api.SEARCH_LIMIT._hits.clear()
    similar_api.OPEN_LIMIT._hits.clear()


_LISTED = re.compile(r"^P(\d+): (.*)$", re.M)
_LINE = re.compile(r"^([AB]\d+) \[(.*?)\]: (.*)$", re.M)


def listing(msgs) -> dict:
    """{label: the candidate text} of an order prompt."""
    return {f"P{k}": t for k, t in _LISTED.findall(msgs[-1]["content"])}


def line_lists(msgs) -> tuple:
    a, b = {}, {}
    for i, label, text in _LINE.findall(msgs[-1]["content"]):
        (a if i.startswith("A") else b)[i] = (label, text)
    return a, b


def default_pairs(a, b) -> dict:
    """A sensible model: each line of A with the first line of B of the same label; agreeing texts are similar, others differ."""
    out = {"similar": [], "differs": []}
    for ai, (la, ta) in a.items():
        bi = next((k for k, (lb, _) in b.items() if lb == la), None)
        if bi:
            out["similar" if grounding.norm(ta) == grounding.norm(b[bi][1]) else "differs"].append({"a": ai, "b": bi})
    return out


class Model:
    """The reasoner: `order(listing, call_index)` and `lines(a, b)` answer; every call is kept (purpose and messages)."""

    def __init__(self):
        self.calls = []
        self.order = lambda lst, k: {"order": list(lst)}  # the listing as given
        self.lines = default_pairs
        self.lines_delay = 0

    def of(self, purpose):
        return [c for c in self.calls if c["purpose"] == purpose]

    async def chat(self, role, msgs, **kw):
        assert role == "reasoner" and kw.get("temperature", 0) == 0
        purpose = kw.get("purpose")
        self.calls.append({"purpose": purpose, "msgs": msgs})
        if purpose == "similar_order":
            ans = self.order(listing(msgs), len(self.of("similar_order")) - 1)
            if isinstance(ans, BaseException):
                raise ans
            return ans
        if purpose == "similar_lines":
            if self.lines_delay:
                await asyncio.sleep(self.lines_delay)
            return self.lines(*line_lists(msgs))
        return {"claims": []}

    def prompts(self) -> str:
        return "\n".join(m["content"] for c in self.calls for m in c["msgs"])


@pytest.fixture
def model(monkeypatch):
    m = Model()
    monkeypatch.setattr(similar.llm, "chat", m.chat)
    return m


# ---- synthetic Case Files ----------------------------------------------------------------------------------------------------------

def mk(cid, name=None, uhid=None, agesex="54 Y / F", setting="early", owner="breast_surgery", protocol="breast", **extra):
    _N[0] += 1
    patient = {"name": f"SYNTHETIC, {name or NAMES[_N[0] % len(NAMES)]}", "mrn": f"SYN-8{_N[0]:05d}", "agesex": agesex}
    if uhid:
        patient["ids"] = [{"kind": "uhid", "value": uhid}]
    c = store.create_case(cid, patient, protocol, created_by=RAO, setting=setting)
    if owner:
        c["department"] = owner
    if uhid:
        c["his"] = {"uhid": uhid}
    c.update(extra)
    store.save_case(c)
    return cid


def report(doc_id, doc_type, title, date, facts, lead=""):
    """A synthetic report whose page text holds every quote at the offsets its fact records (as grounding.locate places them)."""
    text = "\n".join(x for x in ["SYNTHETIC", title, lead] + [q for _, q in facts.values()] + ["Report status: FINAL"] if x)
    fs = {}
    for fid, (value, quote) in facts.items():
        f = fact(value, quote=quote)
        k = text.index(quote)
        f["location"] = {"page": 0, "start": k, "end": k + len(quote), "score": 100.0, "matched": quote}
        fs[fid] = f
    return make_doc(doc_id, doc_type, date=date, title=title, facts=fs, text=text)


def breast(cid, er="Positive (Allred 8/8)", her2="Negative (score 1+)", grade="Nottingham Grade 2", stage="cT2 N0 M0",
           histology="Invasive ductal carcinoma", lead="", grade_quote=None):
    add(cid,
        report(f"D{cid[-3:]}01", "histopathology", "HISTOPATHOLOGY REPORT", "2026-09-03",
               {"histologic_type": (histology, f"Diagnosis: {histology}"), "grade": (grade, grade_quote or grade)}, lead=lead),
        report(f"D{cid[-3:]}02", "ihc", "IHC REPORT", "2026-09-04", {"er": (er, f"ER: {er}"), "her2": (her2, f"HER2: {her2}")}, lead=lead),
        report(f"D{cid[-3:]}03", "ct", "CT THORAX REPORT", "2026-09-05", {"recorded_stage": (stage, f"Impression: stage as recorded {stage}")},
               lead=lead))


def record(cid, text="Breast conserving surgery, then adjuvant chemotherapy.", board_date="2026-09-10", **over):
    st = store.get_state(cid)
    rec = {"id": f"B{len(st['board_records']) + 1:06d}", "outcome": "decision", "outcome_type": "decision", "decision_text": text,
           "intent": "curative", "modalities": ["surgery", "chemotherapy"], "sequence": "Surgery first", "board_date": board_date,
           "recorded_at": f"{board_date}T12:00:00", "rationale": "Early disease on imaging", "stage_as_agreed": "cT2 N0 M0", "version": 1, **over}
    st["board_records"].append(rec)
    store.save_state(cid, st)
    return rec


def past(cid, **kw):
    """A listed, decided breast Case File (eligible)."""
    docs = {k: kw.pop(k) for k in ("er", "her2", "grade", "stage", "histology", "lead", "grade_quote") if k in kw}
    rec = {k[4:]: kw.pop(k) for k in list(kw) if k.startswith("rec_")}
    mk(cid, **kw)
    breast(cid, **docs)
    record(cid, **rec)
    return cid


def source(cid="TB-SIM-300", **kw):
    """The Case File searched from (undecided)."""
    docs = {k: kw.pop(k) for k in ("er", "her2", "grade", "stage", "histology", "lead") if k in kw}
    mk(cid, **kw)
    breast(cid, **docs)
    return cid


def run(coro):
    return asyncio.run(coro)


def summary_sentences(cid, items, status="ai_draft"):
    """A current Case summary whose "since" sentences cite (doc_id, quote) exactly at the quote's offsets in that report; a sentence
    with doc_id None has no citation."""
    sents = []
    for sid, text, doc_id, quote in items:
        cites = []
        if doc_id:
            d = store.get_doc(cid, doc_id)
            k = d["pages"][0]["text"].index(quote)
            cites.append({"doc_id": doc_id, "quote": quote, "page": 0, "start": k, "end": k + len(quote),
                          "doc_title": d["classification"]["title"], "date": d["classification"]["report_date_iso"], "status": "FINAL"})
        sents.append({"id": sid, "text": text, "citations": cites})
    st = store.get_state(cid)
    st.setdefault("artefacts", {})["case_summary"] = {"current": 1, "case_id": cid, "versions": [{"n": 1, "built_at": "2026-10-22T10:00:00",
        "review": {"status": status}, "edits": [], "label": "AI draft, not reviewed", "sections": [{"id": "since", "sentences": sents}]}]}
    store.save_state(cid, st)


def do_search(cid, words="", user=RAO):
    return run(similar.search(cid, words, user, org.roles(user)))


def walk(x, path=()):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from walk(v, path + (k,))
    elif isinstance(x, list):
        for v in x:
            yield from walk(v, path)
    else:
        yield path, x


def prof(cid, sig, marker):
    return {"case_id": cid, "signature": sig, "text": f"Cancer group: Breast cancer. Marker {marker}. Board decisions: decision recorded."}


def answer_as(order_of_markers):
    """An order answer given in markers, turned into the listing's labels."""
    def f(lst):
        by_marker = {re.search(r"Marker (\w+)", t).group(1): p for p, t in lst.items()}
        return {"order": [by_marker[m] for m in order_of_markers]}
    return f


# ---- 1. the order ----------------------------------------------------------------------------------------------------------------

def test_the_merged_order_is_the_median_over_three_permutations_with_ties_by_rrf(model):
    src = {"case_id": "TB-SIM-SRC", "signature": "s0", "text": "Cancer group: Breast cancer. Board decisions: none."}
    cands = [prof(f"TB-SIM-20{i}", f"sig{i}", f"M{i}") for i in range(1, 5)]
    answers = [answer_as(["M3", "M1", "M2", "M4"]), answer_as(["M3", "M2", "M1", "M4"]), answer_as(["M1", "M3", "M2", "M4"])]
    model.order = lambda lst, k: answers[k](lst)
    info = {}
    ids, by = run(similar.order(src, cands, "", info=info))
    assert by == "model" and ids == ["TB-SIM-203", "TB-SIM-201", "TB-SIM-202", "TB-SIM-204"] and info["valid"] == 3
    calls = model.of("similar_order")
    assert len(calls) == 3
    shown = [[re.search(r"Marker (\w+)", t).group(1) for _, t in sorted(listing(c["msgs"]).items(), key=lambda kv: int(kv[0][1:]))] for c in calls]
    assert shown[0] == ["M1", "M2", "M3", "M4"] and shown[1] == ["M4", "M3", "M2", "M1"] and sorted(shown[2]) == ["M1", "M2", "M3", "M4"]
    # the same seed gives the same shuffle
    assert similar._permutations(src, cands) == similar._permutations(src, cands)
    # ties: two valid answers (the third repeats an id), C1 and C2 share a median of 1.5: the RRF rank decides
    cands3 = [prof(f"TB-SIM-21{i}", f"t{i}", f"N{i}") for i in range(1, 4)]
    answers3 = [answer_as(["N3", "N2", "N1"]), answer_as(["N3", "N1", "N2"]), lambda lst: {"order": ["P1", "P1", "P2"]}]
    model.order = lambda lst, k: answers3[k - 3](lst)
    ids, by = run(similar.order(src, cands3, "", info=info))
    assert by == "model" and ids == ["TB-SIM-213", "TB-SIM-211", "TB-SIM-212"] and info["valid"] == 2
    prompts = model.prompts()
    assert "TB-SIM" not in prompts and "Board decisions" not in prompts


def test_invalid_answers_fall_back_to_the_rrf_order_and_one_valid_answer_is_enough(model):
    src = {"case_id": "TB-SIM-SRC", "signature": "s1", "text": "Cancer group: Breast cancer."}
    cands = [prof(f"TB-SIM-22{i}", f"u{i}", f"Q{i}") for i in range(1, 4)]
    bad = [{"order": ["P1", "P2"]}, {"order": ["P1", "P2", "P9"]}, {"order": ["P1", "P1", "P3"]}]
    model.order = lambda lst, k: bad[k % 3]
    info = {}
    assert run(similar.order(src, cands, "", info=info)) == (["TB-SIM-221", "TB-SIM-222", "TB-SIM-223"], "text")
    assert info["valid"] == 0 and info["fallback"].startswith("no valid model order")
    assert not list(similar._cache_dir().glob("*.json")) if similar._cache_dir().exists() else True  # a fallback is never cached
    model.order = lambda lst, k: llm.LLMError("reasoner model server unreachable")
    assert run(similar.order(src, cands, "", info=info)) == (["TB-SIM-221", "TB-SIM-222", "TB-SIM-223"], "text")
    assert "LLMError" in info["fallback"]
    one = answer_as(["Q2", "Q3", "Q1"])
    model.order = lambda lst, k: one(lst) if k == 6 else {"order": "P1"}
    ids, by = run(similar.order(src, cands, "", info=info))
    assert by == "model" and ids == ["TB-SIM-222", "TB-SIM-223", "TB-SIM-221"] and info["valid"] == 1


def test_a_cache_hit_makes_no_model_call_and_a_changed_signature_misses(model):
    src = {"case_id": "TB-SIM-SRC", "signature": "s2", "text": "Cancer group: Breast cancer."}
    cands = [prof(f"TB-SIM-23{i}", f"v{i}", f"R{i}") for i in range(1, 4)]
    first = run(similar.order(src, cands, "HER2 positive"))
    assert len(model.of("similar_order")) == 3
    info = {}
    assert run(similar.order(src, cands, "HER2 positive", info=info)) == first and info["cached"] is True
    assert len(model.of("similar_order")) == 3
    files = list(similar._cache_dir().glob("*.json"))
    assert len(files) == 1
    stored = json.loads(files[0].read_text())
    assert set(stored) == {"order", "ordered_by", "prompt_version", "at"} and stored["order"] == first[0]
    assert stored["ordered_by"] == "model" and stored["prompt_version"] == similar.PROMPT_VERSION
    assert "Breast" not in files[0].read_text()  # ids only, never a text
    run(similar.order(src, cands, "brain metastases"))  # other words: another key
    assert len(model.of("similar_order")) == 6
    cands[1] = {**cands[1], "signature": "v2-changed"}
    run(similar.order(src, cands, "HER2 positive"))
    assert len(model.of("similar_order")) == 9
    assert run(similar.order(src, cands[:1], "")) == (["TB-SIM-231"], "text") and len(model.of("similar_order")) == 9  # nothing to order
    assert run(similar.order(src, [], "")) == ([], "text") and len(model.of("similar_order")) == 9


def test_candidate_text_drops_the_board_decisions_and_no_prompt_carries_an_id_or_a_decision(model, people):
    source()
    past("TB-SIM-301", rec_text="Plan noted as QUOKKA protocol.")
    long_text = "Discussion recorded as XYLOPHONE pathway. " + "Neoadjuvant chemotherapy then surgery as planned. " * 40
    past("TB-SIM-302", rec_text=long_text)
    for k in range(5):
        record("TB-SIM-302", text=long_text, board_date=f"2026-09-1{k + 1}")
    similar.ensure()
    p1, p2 = similar._load_profile("TB-SIM-301"), similar._load_profile("TB-SIM-302")
    assert "Board decisions: " in p1["text"] and "QUOKKA" in p1["text"] and p2["text_decisions"] and "XYLOPHONE" in p2["text_decisions"]
    for p in (p1, p2):
        t = similar.candidate_text(p)
        assert "Board decisions" not in t and "QUOKKA" not in t and "XYLOPHONE" not in t and t.startswith("Cancer group: Breast cancer.")
    out = do_search("TB-SIM-300")
    assert {c["case_id"] for c in out["results"] + out["weaker"]} == {"TB-SIM-301", "TB-SIM-302"}
    assert model.of("similar_order") and model.of("similar_lines")
    prompts = model.prompts()
    for bad in ("TB-SIM", "QUOKKA", "XYLOPHONE", "Board decisions", "Breast conserving", "Early disease on imaging", "Surgery first"):
        assert bad not in prompts, bad
    assert "SYN-8" not in prompts and not any(n.split()[0] in prompts for n in NAMES)
    # the decision is shown on the card, whole and as written
    c = next(x for x in out["results"] + out["weaker"] if x["case_id"] == "TB-SIM-301")
    assert c["decisions"][0]["text"] == "Plan noted as QUOKKA protocol." and c["decisions"][0]["when"] == "Sep 2026"


def test_the_doctors_words_reach_the_order_prompt(model, people):
    source(); past("TB-SIM-311"); past("TB-SIM-312", her2="Positive (score 3+)")
    out = do_search("TB-SIM-300", "HER2 positive with brain metastases")
    assert out["words"] == "HER2 positive with brain metastases"
    assert all("The doctor asked to look for: HER2 positive with brain metastases" in c["msgs"][-1]["content"] for c in model.of("similar_order"))


# ---- 2. the quoted lines ---------------------------------------------------------------------------------------------------------

def _profiles(src_id, past_id):
    similar.ensure()
    return similar.query_profile(src_id), similar._load_profile(past_id)


def test_pairs_are_kept_only_while_their_quotes_match_the_sources_read_again(model, people):
    source()
    past("TB-SIM-321", her2="Positive (score 3+)")
    src, p = _profiles("TB-SIM-300", "TB-SIM-321")
    picks = run(similar.pick_lines(src, p))
    abouts = {x["about"] for x in picks["similar"]}
    assert "Estrogen receptor (ER)" in abouts and picks["no_reasons"] is False and picks["dropped"] == 0
    er = next(x for x in picks["similar"] if x["about"] == "Estrogen receptor (ER)")
    assert er == {"about": "Estrogen receptor (ER)", "this": {"text": "ER: Positive (Allred 8/8)", "where": "IHC REPORT, 04/09/2026"},
                  "past": {"text": "ER: Positive (Allred 8/8)", "where": "IHC REPORT, Sep 2026"}}
    her2 = next(x for x in picks["differs"] if x["this"]["text"].startswith("HER2"))
    assert her2["past"]["text"] == "HER2: Positive (score 3+)"
    assert len(picks["similar"]) <= similar.SIMILAR_MAX and len(picks["differs"]) <= similar.DIFFERS_MAX
    # the past report's page text changes after the profile was built: its ER line no longer matches and is dropped
    d = store.get_doc("TB-SIM-321", "D32102")
    d["pages"][0]["text"] = d["pages"][0]["text"].replace("ER: Positive (Allred 8/8)", "ER: Negative (Allred 0/8)")
    store.save_doc("TB-SIM-321", d)
    store._docs_cache.clear()
    again = run(similar.pick_lines(src, p))
    assert "Estrogen receptor (ER)" not in {x["about"] for x in again["similar"] + again["differs"]} and again["dropped"] >= 1
    # and this file's own line is checked the same way
    d = store.get_doc("TB-SIM-300", "D30001")
    d["pages"][0]["text"] = d["pages"][0]["text"].replace("Nottingham Grade 2", "Nottingham Grade 3")
    store.save_doc("TB-SIM-300", d)
    store._docs_cache.clear()
    third = run(similar.pick_lines(src, p))
    assert "Grade / differentiation" not in {x["about"] for x in third["similar"] + third["differs"]}
    assert not any(x["this"]["text"] == "Nottingham Grade 2" for x in third["similar"] + third["differs"])


def test_decision_lines_are_never_listed_or_paired_and_unknown_ids_are_dropped(model, people):
    source()
    past("TB-SIM-331")
    src, p = _profiles("TB-SIM-300", "TB-SIM-331")
    assert any(l["kind"] == "decision" for l in p["lines"])
    a, b = similar._numbered(src, "A"), similar._numbered(p, "B")
    assert b and all(l["kind"] != "decision" for l in b.values()) and len(b) == len([l for l in p["lines"] if l["kind"] != "decision"])
    n_b = len(b)
    model.lines = lambda a, b: {"similar": [{"a": "A1", "b": f"B{n_b + 1}"}, {"a": "A99", "b": "B1"}, {"a": "A1"}, "A1"], "differs": []}
    picks = run(similar.pick_lines(src, p))
    assert picks["similar"] == [] and picks["no_reasons"] is True and picks["dropped"] == 4
    lines_prompt = model.of("similar_lines")[0]["msgs"][-1]["content"]
    for bad in ("Breast conserving surgery", "Early disease on imaging", "Surgery first", "Curative"):
        assert bad not in lines_prompt


def _by_label(side, label):
    return next(i for i, (lb, _) in side.items() if lb == label)


def test_a_differs_pair_with_equal_texts_and_a_similar_pair_across_facts_are_dropped(model, people):
    source()
    past("TB-SIM-341")
    src, p = _profiles("TB-SIM-300", "TB-SIM-341")

    def lines(a, b):
        er_a, er_b = _by_label(a, "Estrogen receptor (ER)"), _by_label(b, "Estrogen receptor (ER)")
        gr_b = _by_label(b, "Grade / differentiation")
        st_a, st_b = _by_label(a, "stage"), _by_label(b, "stage")
        return {"similar": [{"a": er_a, "b": gr_b}, {"a": st_a, "b": st_b}], "differs": [{"a": er_a, "b": er_b}]}
    model.lines = lines
    picks = run(similar.pick_lines(src, p))
    assert [x["about"] for x in picks["similar"]] == ["stage"] and picks["differs"] == [] and picks["dropped"] == 2
    assert picks["no_reasons"] is True  # one line in all


def test_a_past_line_carrying_the_past_patients_name_is_dropped(model, people, monkeypatch):
    source()
    past("TB-SIM-351", name="Asha Kumari", grade_quote="Nottingham Grade 2 (Meenakshi lab)")
    src, p = _profiles("TB-SIM-300", "TB-SIM-351")
    grade = next(l for l in p["lines"] if l.get("fact") == "grade")
    assert grade["text"] == "Nottingham Grade 2 (Meenakshi lab)"  # not a name word when the profile was built
    c = store.get_case("TB-SIM-351"); c["patient"]["name"] = "SYNTHETIC, Meenakshi Sundaram"; store.save_case(c)  # the name corrected later
    picks = run(similar.pick_lines(src, p))
    assert "Meenakshi" not in json.dumps(picks) and "Grade / differentiation" not in {x["about"] for x in picks["similar"]}
    # the identifier check by itself, even for a line whose source still matches
    monkeypatch.setattr(similar, "_verified", lambda line, s: True)
    picks = run(similar.pick_lines(src, p, sources={}))
    assert "Meenakshi" not in json.dumps(picks) and picks["dropped"] >= 1
    case = {"patient": {"name": "SYNTHETIC, Meenakshi Sundaram", "mrn": "SYN-812345", "ids": [{"value": "VXH/2026/004512"}]}}
    for t in ("seen by MEENAKSHI", "UHID VXH/2026/004512", "ref 004512 noted", "lab 12345678", "on 12/09/2026", "SYN-812345", "on 12-Sep-2026",
              "on 12 September 2026", "on 12/09/26", "call 98765 43210", "mail a.b@example.com", "IP No. IP/26/01234", "RAD-26-0789"):
        assert similar._carries_id(t, case), t
    assert not similar._carries_id("ER: Positive (Allred 8/8)", case)


def test_a_model_error_or_a_bad_answer_gives_no_lines(model, people, monkeypatch):
    source(); past("TB-SIM-361")
    src, p = _profiles("TB-SIM-300", "TB-SIM-361")
    model.lines = lambda a, b: {"similar": "A1-B1"}
    assert run(similar.pick_lines(src, p)) == {"similar": [], "differs": [], "no_reasons": True, "dropped": 0}

    async def boom(role, msgs, **kw):
        raise llm.LLMError("reasoner model server unreachable")
    monkeypatch.setattr(similar.llm, "chat", boom)
    assert run(similar.pick_lines(src, p))["no_reasons"] is True


def test_the_picks_are_cached_by_ids_and_checked_again_on_a_hit(model, people, monkeypatch):
    source()
    past("TB-SIM-363", her2="Positive (score 3+)")
    src, p = _profiles("TB-SIM-300", "TB-SIM-363")
    first = run(similar.pick_lines(src, p))
    assert len(model.of("similar_lines")) == 1 and first["similar"]
    files = list(similar._cache_dir().glob("lines-*.json"))
    assert len(files) == 1
    stored = json.loads(files[0].read_text())
    assert set(stored) == {"picks", "prompt_version", "model", "at"} and set(stored["picks"]) == {"similar", "differs"}
    assert all(set(x) == {"a", "b"} and re.fullmatch(r"A\d+", x["a"]) and re.fullmatch(r"B\d+", x["b"])
               for k in ("similar", "differs") for x in stored["picks"][k])
    assert "Positive" not in files[0].read_text() and "Grade" not in files[0].read_text()  # ids only, never a text
    second = run(similar.pick_lines(src, p))
    assert second == first and len(model.of("similar_lines")) == 1  # no model call on a hit
    # on a hit the checks still run on the sources read now
    d = store.get_doc("TB-SIM-363", "D36302")
    d["pages"][0]["text"] = d["pages"][0]["text"].replace("ER: Positive (Allred 8/8)", "ER: Negative (Allred 0/8)")
    store.save_doc("TB-SIM-363", d)
    store._docs_cache.clear()
    third = run(similar.pick_lines(src, p))
    assert len(model.of("similar_lines")) == 1 and third["dropped"] >= 1
    assert "Estrogen receptor (ER)" not in {x["about"] for x in third["similar"] + third["differs"]}
    # another signature: another key (a call); a model error is never cached
    past("TB-SIM-364")
    _, p2 = _profiles("TB-SIM-300", "TB-SIM-364")

    async def boom(role, msgs, **kw):
        raise llm.LLMError("reasoner model server unreachable")
    monkeypatch.setattr(similar.llm, "chat", boom)
    assert run(similar.pick_lines(src, p2))["no_reasons"] is True
    assert len(list(similar._cache_dir().glob("lines-*.json"))) == 1


def test_case_summary_sentences_are_never_offered_as_lines(model, people):
    source()
    past("TB-SIM-365")
    summary_sentences("TB-SIM-365", [("ssince-1", "QUOKKA course recorded since the board.", "D36501", "Diagnosis: Invasive ductal carcinoma")])
    similar.ensure()
    p = similar._load_profile("TB-SIM-365")
    assert p["outcome_so_far"]["sentences"] and not any(l["kind"] == "summary" for l in p["lines"])
    out = do_search("TB-SIM-300")
    assert "QUOKKA" not in "\n".join(m["content"] for c in model.of("similar_lines") for m in c["msgs"])
    c = next(x for x in out["results"] + out["weaker"] if x["case_id"] == "TB-SIM-365")
    assert c["outcome_so_far"]["sentences"][0]["label"] == "Case summary, AI draft, not reviewed"
    assert c["outcome_so_far"]["sentences"][0]["quote"] == "Diagnosis: Invasive ductal carcinoma"
    assert not any("QUOKKA" in x["past"]["text"] for x in c["similar"] + c["differs"])


def test_one_candidate_is_ordered_by_text_without_a_call(model, people):
    source(); past("TB-SIM-366")
    out = do_search("TB-SIM-300")
    assert out["ordered_by"] == "text" and out["order_note"] == similar.ORDER_NOTE_TEXT and not model.of("similar_order")
    assert out["note"] == "Few past Case Files of this cancer group have a recorded decision."


# ---- 3. the cards and the response ------------------------------------------------------------------------------------------------

def test_no_reasons_shows_matched_by_and_a_group_only_match_goes_to_weaker(model, people):
    source()
    past("TB-SIM-371")                                                                      # same setting, age band, sex and stage
    past("TB-SIM-372", agesex="72 Y / M", setting="locally_advanced", stage="cT4 N2 M0")    # the cancer group only
    model.lines = lambda a, b: {"similar": [], "differs": []}
    out = do_search("TB-SIM-300")
    assert [c["case_id"] for c in out["results"]] == ["TB-SIM-371"] and [c["case_id"] for c in out["weaker"]] == ["TB-SIM-372"]
    r, w = out["results"][0], out["weaker"][0]
    assert r["no_reasons"] is True and r["matched_by"] == ["cancer group", "setting", "age band", "sex", "stage as recorded"]
    assert w["no_reasons"] is True and w["matched_by"] == ["cancer group"]
    model.lines = default_pairs
    similar_api_reset()
    out = do_search("TB-SIM-300")
    r = next(c for c in out["results"] if c["case_id"] == "TB-SIM-371")
    assert r["no_reasons"] is False and r["matched_by"] is None and r["similar"]


def similar_api_reset():
    for f in similar._cache_dir().glob("*.json") if similar._cache_dir().exists() else []:
        f.unlink()


def test_the_card_shape_and_no_number_or_past_day_date_anywhere(model, people):
    source()
    past("TB-SIM-381", her2="Positive (score 3+)")
    summary_sentences("TB-SIM-381", [("ssince-1", "The discharge summary of 20/10/2026 records a wide local excision.", "D38101",
                                      "Diagnosis: Invasive ductal carcinoma"),
                                     ("ssince-2", "Chemotherapy is planned.", None, None)])
    out = do_search("TB-SIM-300")
    assert set(out) == {"label", "ordered_by", "order_note", "model_line", "cancer_group", "group_label", "words", "note", "results", "weaker"}
    assert out["label"] == similar.LABEL and out["model_line"] == similar.MODEL_LINE and out["cancer_group"] == "breast"
    c = (out["results"] + out["weaker"])[0]
    assert set(c) == {"case_id", "cancer", "setting", "age_band", "sex", "stage", "values", "decisions", "outcome_so_far", "similar", "differs",
                      "matched_by", "no_reasons", "open", "label"}
    assert c["cancer"] == "Breast cancer" and c["age_band"] == "50 to 59" and c["sex"] == "F" and c["label"] == similar.LABEL
    assert c["stage"][0] == {"text": "cT2 N0 M0", "kind": "recorded", "label": "as recorded", "quote": "Impression: stage as recorded cT2 N0 M0",
                             "where": "CT THORAX REPORT, Sep 2026"}
    assert c["stage"][1]["kind"] == "agreed" and c["stage"][1]["where"] == "Board record, Sep 2026"
    assert [v["fact"] for v in c["values"][:2]] == ["histologic_type", "grade"] and all(v["shared"] for v in c["values"])
    assert set(c["values"][0]) == {"fact", "label", "value", "quote", "where", "shared"}
    assert set(c["decisions"][0]) == {"record_id", "when", "outcome", "outcome_label", "intent", "intent_label", "text", "modalities", "stage_as_agreed"}
    assert c["decisions"][0]["modalities"] == ["Surgery", "Chemotherapy"] and c["decisions"][0]["outcome_label"] == "Decision recorded"
    assert c["outcome_so_far"]["sentences"] == [{"text": "The discharge summary of [date] records a wide local excision.",
                                                 "where": "HISTOPATHOLOGY REPORT, Sep 2026", "quote": "Diagnosis: Invasive ductal carcinoma",
                                                 "quote_where": "HISTOPATHOLOGY REPORT, Sep 2026", "label": "Case summary, AI draft, not reviewed"}]
    assert set(c["open"]) == {"how", "reason", "via"} and c["open"]["how"] == "normal"
    for pair in c["similar"] + c["differs"]:
        assert set(pair) == {"about", "this", "past"} and re.fullmatch(r".+, \w{3} \d{4}", pair["past"]["where"])
    bad_keys = {"score", "rank", "rrf_rank", "percent", "count", "n", "position", "similarity"}
    for path, v in walk(out):
        assert not (isinstance(v, (int, float)) and not isinstance(v, bool)), (path, v)
        assert not set(path) & bad_keys, path
    past_only = json.dumps([{k: v for k, v in x.items() if k not in ("similar", "differs")} for x in out["results"] + out["weaker"]]
                           + [p["past"] for x in out["results"] + out["weaker"] for p in x["similar"] + x["differs"]])
    assert not re.search(r"\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}", past_only), past_only


FORMATS = ("12/03/2026", "13-03-2026", "14.03.2026", "15/03/26", "2026-03-16", "2026-03-17T10:30:00", "18-Mar-2026", "19 Mar 2026",
           "20 March 2026", "March 21, 2026", "22 sept 2026", "98765 43210", "98764-43211", "+91 98763 43212", "+91-9876243213", "9876143214",
           "asha.k@example.com", "IP/26/01234", "RAD-26-0789", "VXH/26/004202", "IP No. IP/26/05678", "OP No. OP-4521", "MRN 7781-22",
           "ABHA Number 12-3456-7890-1234")


def _residue(fmt) -> list:
    """What must not survive of a seeded format: the whole of it, and every group of three or more digits but the year."""
    return [fmt.lower()] + [g for g in re.findall(r"\d{3,}", fmt) if g != "2026"] + (["asha.k", "example.com"] if "@" in fmt else [])


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_property_no_seeded_identifier_of_the_past_patient_reaches_the_response(model, people, seed):
    rnd = random.Random(seed)
    first, last = rnd.choice(NAMES).split()
    uhid = f"VXH/2026/{rnd.randint(100000, 999999)}"
    long_no = str(rnd.randint(10 ** 10, 10 ** 11 - 1))
    fmts = list(FORMATS)
    rnd.shuffle(fmts)
    seeded = "; ".join(fmts)
    short = rnd.choice(FORMATS)  # one in a short quote, so that it also reaches the embedded text
    lead = f"Patient {first} {last.upper()} UHID {uhid} Lab no {long_no}"
    source(name="Bhavani Raghavan")  # another patient (a file of the same patient is never listed)
    grade_quote = f"{first} {last}: Nottingham Grade 2 (lab {long_no}; {seeded})"
    past("TB-SIM-391", name=f"{first} {last}", uhid=uhid, lead=lead, grade_quote=grade_quote, histology=f"Invasive ductal carcinoma (ref {short})",
         rec_text=f"Discussed for {first} {last} ({uhid}), ref {long_no}, {seeded}: breast conserving surgery.")
    summary_sentences("TB-SIM-391", [("ssince-1", f"{first} was seen on 21/10/2026, UHID {uhid}, {seeded}.", "D39101", grade_quote)])
    out = do_search("TB-SIM-300")
    assert out["results"] + out["weaker"]
    p = similar._load_profile("TB-SIM-391")
    assert p["outcome_so_far"]["sentences"], "the sentence is kept (exact citation) and scrubbed"
    texts = {"text": p["text"], "text_decisions": p["text_decisions"], "lines": " ".join(l["text"] for l in p["lines"]),
             "card": json.dumps(out), "prompts": model.prompts()}
    assert "invasive ductal carcinoma (ref [" in texts["text"].lower()  # the short quote reached the embedded text, scrubbed
    for where, blob in texts.items():
        low = blob.lower()
        for bad in (first.lower(), last.lower(), uhid.lower(), uhid.split("/")[-1], long_no, "21/10/2026"):
            assert bad not in low, (where, bad)
        for fmt in FORMATS:
            for bad in _residue(fmt):
                assert bad not in low, (where, fmt, bad)


def test_medical_values_pass_the_scrubber_unchanged():
    case = {"patient": {"name": "SYNTHETIC, Meenakshi Sundaram", "mrn": "SYN-812345"}}
    for t in ("Allred score 8/8", "T2 N0 M0", "Ki-67 20 %", "HER2 3+", "2.8 x 2.1 cm", "cycle 1 of 4", "pT2 N1a (2/14) M0", "CA-19-9 37 U/mL",
              "Ki-67 20-30 %", "CR after chemotherapy", "ER 90%, PR 10%", "IHC REPORT, Sep 2026", "ECOG 1", "pCR 2026"):
        assert similar.scrub(t, case) == t, t
        assert not similar._carries_id(t, case), t
    for fmt in FORMATS:
        got = similar.scrub(f"seen {fmt} here", case)
        assert got in ("seen [date] here", "seen [id] here"), (fmt, got)
        assert similar._carries_id(fmt, case), fmt
    assert similar.scrub("review on 5 Nov 2026.", case) == "review on [date]." and similar.scrub("IP No. IP/26/01234", case) == "[id]"


def test_late_lines_give_cards_without_reasons_and_the_text_order_note(model, people, monkeypatch):
    source(); past("TB-SIM-401"); past("TB-SIM-402")
    monkeypatch.setattr(similar, "SEARCH_BUDGET_S", 1)
    model.lines_delay = 3
    model.order = lambda lst, k: {"order": ["P9"]}
    out = do_search("TB-SIM-300")
    assert out["ordered_by"] == "text" and out["order_note"] == similar.ORDER_NOTE_TEXT
    cards = out["results"] + out["weaker"]
    assert len(cards) == 2 and all(c["no_reasons"] and c["similar"] == [] for c in cards) and similar.LINES_LATE in out["note"]
    ev = [e for e in store.read_audit("TB-SIM-300") if e["kind"] == "similar_search"][-1]
    assert ev["ordered_by"] == "text" and "too long" in ev["fallback"] and "no valid model order" in ev["fallback"]


def test_no_advice_word_in_any_fixed_string_or_in_a_response(model, people):
    rx = re.compile(r"\b(" + "|".join(re.escape(w) for w in similar.ADVICE_WORDS) + r")", re.I)
    for mod in (similar, __import__("tumour_board.api.similar", fromlist=["x"])):
        tree = ast.parse(Path(mod.__file__).read_text())
        skip = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ADVICE_WORDS" for t in node.targets):
                skip |= {id(x) for x in ast.walk(node.value)}
        strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip]
        assert strings
        for s in strings:
            assert not rx.search(s), s
            assert chr(0x2014) not in s and chr(0x2013) not in s
    source(); past("TB-SIM-411", her2="Positive (score 3+)"); past("TB-SIM-412")
    out = do_search("TB-SIM-300", "HER2 positive")
    texts = [v for _, v in walk(out) if isinstance(v, str)]
    assert texts and not any(rx.search(t) for t in texts)


# ---- 4. the audit of a search -----------------------------------------------------------------------------------------------------

def test_a_search_is_audited_in_this_file_each_shown_file_and_the_org_log_without_identifiers(model, people):
    source(name="Bhavani Raghavan", uhid="VXH/2026/007711")
    past("TB-SIM-421", name="Lalitha Ramaswamy", uhid="VXH/2026/008822"); past("TB-SIM-422", name="Jayanthi Krishnan")
    out = do_search("TB-SIM-300", "HER2 negative")
    shown = [c["case_id"] for c in out["results"] + out["weaker"]]
    ev = [e for e in store.read_audit("TB-SIM-300") if e["kind"] == "similar_search"]
    assert len(ev) == 1
    e = ev[0]
    assert {"by", "words", "cancer_group", "n_candidates", "n_results", "n_weaker", "ordered_by", "fallback", "shown_hash", "dropped_lines",
            "prompt_version", "seconds"} <= set(e)
    assert e["by"] == RAO and e["words"] == "HER2 negative" and e["cancer_group"] == "breast" and e["n_candidates"] == 2
    assert e["n_results"] + e["n_weaker"] == 2 and e["ordered_by"] == "model" and e["prompt_version"] == similar.PROMPT_VERSION
    assert e["shown_hash"] == hashlib.sha1(",".join(shown).encode()).hexdigest()[:16] and "TB-SIM-421" not in json.dumps(e)
    for sid in shown:
        s = [x for x in store.read_audit(sid) if x["kind"] == "similar_shown"]
        assert len(s) == 1 and s[0]["by"] == RAO and s[0]["from"] == "TB-SIM-300" and "words" not in s[0]
    o = [x for x in org.read_audit() if x.get("kind") == "similar_search"][-1]
    assert o["case_id"] == "TB-SIM-300" and o["shown"] == shown and o["words_hash"] == hashlib.sha1(b"HER2 negative").hexdigest()[:12]
    assert o["n_results"] == len(out["results"]) and "words" not in o
    logs = json.dumps([x for cid in ["TB-SIM-300"] + shown for x in store.read_audit(cid) if str(x.get("kind")).startswith("similar")]
                      + [x for x in org.read_audit() if str(x.get("kind")).startswith("similar")]).lower()
    for bad in ("bhavani", "raghavan", "lalitha", "ramaswamy", "jayanthi", "krishnan", "007711", "008822", "syn-8", "allred", "nottingham"):
        assert bad not in logs, bad


def test_an_empty_or_failed_search_is_audited_and_refused_words_are_never_written(model, people):
    source(name="Bhavani Raghavan")
    out = do_search("TB-SIM-300")
    assert out["results"] == [] and out["weaker"] == [] and out["note"] == "No past Case File of this cancer group has a recorded decision."
    with pytest.raises(published.PublishedError):
        do_search("TB-SIM-300", "bhavani with brain metastases")
    ev = [e for e in store.read_audit("TB-SIM-300") if e["kind"] == "similar_search"]
    assert [e["fallback"] for e in ev] == ["", "bad_words"] and ev[1]["words"] == "" and "bhavani" not in json.dumps(ev).lower()
    assert [x for x in org.read_audit() if x.get("kind") == "similar_search"][-1]["words_hash"] == ""


# ---- 5. the routes ---------------------------------------------------------------------------------------------------------------

def detail(r):
    return r.json()["detail"]


def test_the_router_tuple_holds_similar_and_the_three_paths_exist(full):
    import routes.tumour_board_routes as R
    assert '"similar"' in inspect.getsource(R._include_nik_routers)
    with warnings.catch_warnings():  # the schema build repeats an older route's operation id (not this item's)
        warnings.simplefilter("ignore")
        api_paths = full.tc.app.openapi()["paths"]  # the included routers stay nested in app.routes (FastAPI 0.142)
    assert "get" in api_paths["/api/tb/cases/{case_id}/similar"]
    assert "post" in api_paths["/api/tb/cases/{case_id}/similar/search"] and "post" in api_paths["/api/tb/cases/{case_id}/similar/open"]


def test_the_search_route_answers_and_refuses_words_with_this_patients_name(full, model):
    source(name="Radhika Menon", uhid="VXH/2026/001101"); past("TB-SIM-431"); past("TB-SIM-432")
    api = full.as_(RAO)
    r = api.post("/cases/TB-SIM-300/similar/search", {"words": "HER2 positive"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["ordered_by"] == "model" and b["order_note"] == similar.ORDER_NOTE_MODEL and len(b["results"] + b["weaker"]) == 2
    assert api.post("/cases/TB-SIM-300/similar/search").status_code == 200  # no body: no words
    for w in ("radhika with brain metastases", "VXH/2026/001101", "number 12345678"):
        r = api.post("/cases/TB-SIM-300/similar/search", {"words": w})
        assert r.status_code == 400 and detail(r)["code"] == "bad_words", r.text
    assert api.post("/cases/TB-SIM-300/similar/search", {"words": 12}).status_code == 400


def test_the_search_route_refuses_words_with_a_date_a_phone_an_email_or_an_identifier(full, model):
    source(); past("TB-SIM-433")
    api = full.as_(RAO)
    for w in ("seen on 12/03/2026", "review 5 Nov 2026", "call 98765 43210", "asha.k@example.com", "IP No. IP/26/01234", "RAD-26-0789 report"):
        r = api.post("/cases/TB-SIM-300/similar/search", {"words": w})
        assert r.status_code == 400 and detail(r)["code"] == "bad_words", (w, r.text)
    ev = [e for e in store.read_audit("TB-SIM-300") if e["kind"] == "similar_search"]
    assert ev and all(e["fallback"] == "bad_words" and e["words"] == "" for e in ev)
    assert "98765" not in json.dumps(ev) and "12/03/2026" not in json.dumps(ev) and not model.calls


def test_open_refuses_the_same_patient_a_linked_file_and_another_cancer_group(full, model):
    source(uhid="VXH/2026/007001", linked_cases=[{"case_id": "TB-SIM-472"}])
    past("TB-SIM-471", uhid="VXH/2026/007001", name="Other Name")          # the same patient (UHID in common)
    past("TB-SIM-472")                                                       # linked from this file
    past("TB-SIM-473", linked_cases=[{"case_id": "TB-SIM-300"}])            # links back to this file
    past("TB-SIM-474", protocol="cervix")                                    # another cancer group
    past("TB-SIM-475")                                                       # fine
    rl = org.roles(RAO)
    for pid in ("TB-SIM-471", "TB-SIM-472", "TB-SIM-473", "TB-SIM-474"):
        with pytest.raises(ValueError, match="not_found"):
            similar.open_info(rl, pid, "TB-SIM-300")
        r = full.as_(RAO).post("/cases/TB-SIM-300/similar/open", {"past_case_id": pid})
        assert r.status_code == 404 and pid not in r.text
    assert similar.open_info(rl, "TB-SIM-475", "TB-SIM-300")["how"] == "normal"
    assert not [e for e in store.read_audit("TB-SIM-471") if e["kind"] == "similar_opened"]


def test_the_sixty_first_opening_in_ten_minutes_is_refused(full, model):
    source(); past("TB-SIM-476")
    api = full.as_(RAO)
    for _ in range(60):
        assert api.post("/cases/TB-SIM-300/similar/open", {"past_case_id": "TB-SIM-476"}).status_code == 200
    r = api.post("/cases/TB-SIM-300/similar/open", {"past_case_id": "TB-SIM-476"})
    assert r.status_code == 429 and detail(r)["code"] == "rate_limited"


def test_the_eleventh_search_in_ten_minutes_is_refused(full, model):
    source()
    api = full.as_(RAO)
    for _ in range(10):
        assert api.post("/cases/TB-SIM-300/similar/search", {}).status_code == 200
    r = api.post("/cases/TB-SIM-300/similar/search", {})
    assert r.status_code == 429 and detail(r)["code"] == "rate_limited"


def test_admin_window_and_supporting_department_are_refused(full, model):
    source(); past("TB-SIM-441")
    assert full.as_(VX).post("/cases/TB-SIM-300/similar/search", {}).status_code == 403
    access.open_doctor_window(MEHTA, "TB-SIM-300", "Second opinion on the plan (synthetic)")
    assert access.scope(org.roles(MEHTA), store.get_case("TB-SIM-300")) == access.READ
    r = full.as_(MEHTA).post("/cases/TB-SIM-300/similar/search", {})
    assert r.status_code == 403 and detail(r)["code"] == "break_glass_read_only"
    r = full.as_(MEHTA).post("/cases/TB-SIM-300/similar/open", {"past_case_id": "TB-SIM-441"})
    assert r.status_code == 403
    st = store.get_state("TB-SIM-300")
    st["actions"] = [{"id": "A1", "source": "pre_authorization", "requirement": "breast_imaging", "department": "Radiology",
                      "department_id": "radiology", "status": "pending", "created": store.now_iso(), "history": []}]
    store.save_state("TB-SIM-300", st)
    assert access.scope(org.roles(RAVI), store.get_case("TB-SIM-300")) == access.REQUESTS
    assert full.as_(RAVI).post("/cases/TB-SIM-300/similar/search", {}).status_code == 403
    assert full.as_(RAVI).get("/cases/TB-SIM-300/similar").status_code == 403
    assert not model.calls


def test_a_protected_file_is_refused_without_its_name(full, model, monkeypatch):
    monkeypatch.setattr(config, "PROTECTED_CASES", {"TB-SIM-PROT"})
    mk("TB-SIM-PROT", name="Nirmala Devarajan")
    r = full.as_(RAO).post("/cases/TB-SIM-PROT/similar/search", {})  # its creator passes the Case File guard
    assert r.status_code == 403 and detail(r)["code"] == "protected"
    assert "TB-SIM-PROT" not in r.text and "nirmala" not in r.text.lower()
    g = full.as_(RAO).get("/cases/TB-SIM-PROT/similar")
    assert g.status_code == 200 and g.json()["available"] is False and g.json()["reason"] == similar.PROTECTED_REASON
    r = full.as_(MEHTA).post("/cases/TB-SIM-PROT/similar/search", {})
    assert r.status_code == 403 and "TB-SIM-PROT" not in r.text and "nirmala" not in r.text.lower()
    with pytest.raises(ValueError, match="protected"):
        do_search("TB-SIM-PROT")
    assert not (store.case_dir("TB-SIM-PROT") / "audit.jsonl").exists() or "similar" not in (store.case_dir("TB-SIM-PROT") / "audit.jsonl").read_text()
    assert not model.calls


def test_open_normal_with_reason_refused_and_gone(full, model, people):
    source(participants=[{"department": "medical_oncology"}])  # Dr Mehta's department takes part: full access to this file
    past("TB-SIM-451")
    rao = full.as_(RAO).post("/cases/TB-SIM-300/similar/open", {"past_case_id": "TB-SIM-451"})
    assert rao.status_code == 200 and rao.json() == {"how": "normal", "scope": "full", "reason": "", "via": "", "label": similar.LABEL}
    here = [e for e in store.read_audit("TB-SIM-300") if e["kind"] == "similar_opened"]
    there = [e for e in store.read_audit("TB-SIM-451") if e["kind"] == "similar_opened"]
    assert [(e["by"], e["past"], e["how"]) for e in here] == [(RAO, "TB-SIM-451", "normal")]
    assert [(e["by"], e["from"], e["how"]) for e in there] == [(RAO, "TB-SIM-300", "normal")]
    o = [x for x in org.read_audit() if x.get("kind") == "similar_opened"]
    assert [(x["case_id"], x["past"], x["how"]) for x in o] == [("TB-SIM-300", "TB-SIM-451", "normal")]
    assert access.scope(org.roles(MEHTA), store.get_case("TB-SIM-300")) == access.FULL
    m = full.as_(MEHTA).post("/cases/TB-SIM-300/similar/open", {"past_case_id": "TB-SIM-451"})
    assert m.status_code == 200 and m.json() == {"how": "with_reason", "scope": None, "reason": "similar to Case File TB-SIM-300",
                                                 "via": "similar:TB-SIM-300", "label": similar.LABEL}
    assert len([e for e in store.read_audit("TB-SIM-451") if e["kind"] == "similar_opened"]) == 1  # with_reason audits nothing here
    # the break-glass route opens the window with that via, then open answers normal
    bg = full.as_(MEHTA).post("/break-glass", {"case_id": "TB-SIM-451", "reason": m.json()["reason"], "via": m.json()["via"]})
    assert bg.status_code == 200 and bg.json()["via"] == "similar:TB-SIM-300"
    again = full.as_(MEHTA).post("/cases/TB-SIM-300/similar/open", {"past_case_id": "TB-SIM-451"})
    assert again.json()["how"] == "normal" and again.json()["scope"] == "read"
    # a login with full access here but no scope there and no right to open with a reason
    unplaced = {"user": "x", "known": True, "departments": {}}
    monkey_case = store.get_case("TB-SIM-451")
    assert access.scope(unplaced, monkey_case) is None and not access.may_open_with_reason(unplaced, monkey_case)
    assert similar.open_info(unplaced, "TB-SIM-451", "TB-SIM-300") == {"how": "refused", "scope": None, "reason": "", "via": "", "label": similar.LABEL}
    # archived after the search: not available any more (404, never named)
    c = store.get_case("TB-SIM-451"); c["archived"] = {"by": RAO, "at": store.now_iso(), "reason": "synthetic"}; store.save_case(c)
    r = full.as_(RAO).post("/cases/TB-SIM-300/similar/open", {"past_case_id": "TB-SIM-451"})
    assert r.status_code == 404 and detail(r)["code"] == "not_found" and "TB-SIM-451" not in r.text
    for bad in ("", "TB-NONE", "../x", "TB-SIM-300"):
        assert full.as_(RAO).post("/cases/TB-SIM-300/similar/open", {"past_case_id": bad}).status_code == 404


def test_info_lists_the_last_five_searches_newest_first_and_is_off_inside_a_window(full, model):
    source()
    api = full.as_(RAO)
    g = api.get("/cases/TB-SIM-300/similar").json()
    assert g == {"available": True, "reason": "", "label": similar.LABEL, "order_note": similar.ORDER_NOTE_MODEL, "model_line": similar.MODEL_LINE,
                 "cancer_group": "breast", "group_label": "Breast cancer", "searches": []}
    words = ["HER2 positive", "brain metastases", "triple negative", "lobular", "ER positive", "after surgery"]
    for w in words:
        assert api.post("/cases/TB-SIM-300/similar/search", {"words": w}).status_code == 200
    s = api.get("/cases/TB-SIM-300/similar").json()["searches"]
    assert [x["words"] for x in s] == words[::-1][:5] and all(x["by_name"] == "Dr Rao (synthetic)" and x["at"] for x in s)
    access.open_doctor_window(MEHTA, "TB-SIM-300", "Second opinion on the plan (synthetic)")
    m = full.as_(MEHTA).get("/cases/TB-SIM-300/similar")
    assert m.status_code == 200 and m.json()["available"] is False and m.json()["reason"] == similar.SCOPE_REASON
    mk("TB-SIM-461", protocol="generic")
    n = full.as_(RAO).get("/cases/TB-SIM-461/similar").json()
    assert n["available"] is False and n["reason"] == similar.NO_GROUP_REASON
    assert similar.info("TB-SIM-300", org.roles(VX, vaidyx_admin=True))["reason"] == similar.ADMIN_REASON
    c = store.get_case("TB-SIM-300"); c["archived"] = {"by": RAO, "at": store.now_iso(), "reason": "synthetic"}; store.save_case(c)
    a = similar.info("TB-SIM-300", org.roles(RAO))
    assert a["available"] is False and a["reason"] == "This Case File is archived."
    g = full.as_(RAO).get("/cases/TB-SIM-300/similar")
    assert g.status_code == 200 and g.json()["available"] is False and g.json()["reason"] == "This Case File is archived."
