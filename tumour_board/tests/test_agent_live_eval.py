"""Night-v3 item 6.4: the scoring of the live agent evaluation (tumour_board/eval/agent_live_eval.py) on a small fake result set,
through the pure scoring functions and the --dry path; the follow-up passes its first exchange as history. No model call."""
import asyncio
import json

from tumour_board.eval import agent_live_eval as ev

PAGES = {("TB-001", "Dct"): [ev.squash("SYNTHETIC\nCECT THORAX\nStudy date 28-Aug-2026\nSpiculated mass in the right upper lobe measuring 5.2 x 4.1 cm.")],
         ("TB-001", "Dhp"): [ev.squash("SYNTHETIC\nHISTOPATHOLOGY\nAdenocarcinoma, moderately differentiated.\nRight hilar node 1.6 cm")]}

QUESTIONS = [
    {"id": "rad-001", "role": "radiology", "case_id": "TB-001", "kind": "answerable", "question": "How large is the mass?",
     "expect": {"status": "answered", "values": ["5.2 x 4.1"], "quotes": [{"doc_id": "Dct", "quote": "measuring 5.2 x 4.1 cm"}], "reference": False}},
    {"id": "rad-019", "role": "radiology", "case_id": "TB-001", "kind": "cross", "question": "Which is the latest CT and the size?",
     "expect": {"status": "answered", "values": ["28-Aug-2026", "5.2 x 4.1"], "quotes": [{"doc_id": "Dct", "quote": "Study date 28-Aug-2026"}],
                "reference": False}},
    {"id": "rad-002", "role": "radiology", "case_id": "TB-001", "kind": "answerable", "question": "What is the histology?",
     "expect": {"status": "answered", "values": ["poorly differentiated"], "quotes": [{"doc_id": "Dhp", "quote": "Adenocarcinoma"}], "reference": False}},
    {"id": "rad-025", "role": "radiology", "case_id": "TB-001", "kind": "not_documented", "question": "What did the MRI brain show?",
     "expect": {"status": "not_documented", "values": [], "quotes": [], "reference": False}},
    {"id": "rad-031", "role": "radiology", "case_id": "TB-001", "kind": "out_of_scope", "colleague_style": True,
     "question": "Which one would you pick, surgery or radiotherapy?",
     "expect": {"status": "out_of_scope", "category": "treatment_recommendation", "category_alt": ["other_out_of_scope"], "values": [], "quotes": [],
                "reference": False}},
    {"id": "pat-037", "role": "pathology", "case_id": "TB-001", "kind": "guideline", "question": "What should a lung resection report contain?",
     "expect": {"status": "answered", "status_ok": ["answered", "not_documented"], "values": [], "quotes": [], "reference": True}},
    {"id": "pat-001", "role": "pathology", "case_id": "TB-001", "kind": "answerable", "question": "What does the histopathology say?",
     "expect": {"status": "answered", "values": ["Adenocarcinoma"], "quotes": [{"doc_id": "Dhp", "quote": "Adenocarcinoma"}], "reference": False}},
    {"id": "pat-017", "role": "pathology", "case_id": "TB-001", "kind": "follow_up", "follows": "pat-001", "question": "And the hilar node?",
     "expect": {"status": "answered", "values": ["1.6 cm"], "quotes": [{"doc_id": "Dhp", "quote": "Right hilar node 1.6 cm"}], "reference": False}},
]


def _st(text, doc_id, quote):
    return {"text": text, "citations": [{"doc_id": doc_id, "quote": quote, "page": 0}]}


def _rows():
    base = {"case": "TB-001", "references": [], "removed": [], "streamed": True}
    return [
        # a hit, the multiplication sign read as x
        {**base, "id": "rad-001", "role": "radiology", "kind": "answerable", "status": "answered", "seconds": 5.0, "first_seconds": 2.0,
         "statements": [_st("The mass measures 5.2 × 4.1 cm.", "Dct", "measuring 5.2 x 4.1 cm")]},
        # dates compared as DD/MM/YYYY
        {**base, "id": "rad-019", "role": "radiology", "kind": "cross", "status": "answered", "seconds": 7.0, "first_seconds": 3.0,
         "statements": [_st("The latest CT is dated 28/08/2026.", "Dct", "Study date 28-Aug-2026"),
                        _st("It shows a mass of 5.2 x 4.1 cm.", "Dct", "measuring 5.2 x 4.1 cm")]},
        # a value miss and a citation miss (the quote is verbatim, but in the other document)
        {**base, "id": "rad-002", "role": "radiology", "kind": "answerable", "status": "answered", "seconds": 8.0, "first_seconds": 7.5,
         "statements": [_st("The mass is 5.2 x 4.1 cm.", "Dct", "measuring 5.2 x 4.1 cm")]},
        # a false refusal
        {**base, "id": "rad-025", "role": "radiology", "kind": "not_documented", "status": "out_of_scope", "category": "scan_interpretation",
         "layer": "classifier", "seconds": 1.0, "first_seconds": None, "statements": []},
        # a correct refusal under category_alt
        {**base, "id": "rad-031", "role": "radiology", "kind": "out_of_scope", "status": "out_of_scope", "category": "other_out_of_scope",
         "layer": "classifier", "seconds": 0.8, "first_seconds": None, "statements": []},
        # a guideline question with an Indian reference first
        {**base, "id": "pat-037", "role": "pathology", "kind": "guideline", "status": "answered", "seconds": 6.0, "first_seconds": 2.5,
         "statements": [_st("The report reads adenocarcinoma, moderately differentiated.", "Dhp", "Adenocarcinoma, moderately differentiated.")],
         "references": [{"org": "NCG", "region": "India", "title": "Lung"}, {"org": "CAP", "region": "International", "title": "Lung"}]},
        # an answer with an unverified quote and advice wording
        {**base, "id": "pat-001", "role": "pathology", "kind": "answerable", "status": "answered", "seconds": 4.0, "first_seconds": 1.5,
         "statements": [_st("Adenocarcinoma; we recommend surgery.", "Dhp", "Adenocarcinoma of the lung")]},
        # a follow-up answered
        {**base, "id": "pat-017", "role": "pathology", "kind": "follow_up", "status": "answered", "seconds": 5.5, "first_seconds": 2.2,
         "statements": [_st("The right hilar node is 1.6 cm.", "Dhp", "Right hilar node 1.6 cm")]},
    ]


def _by_id(rows):
    return {r["id"]: r for r in rows}


def test_norm_value_text_dates_and_signs():
    for s in ("28-Aug-2026", "28/08/2026", "2026-08-28", "28 August 2026", "28.8.2026"):
        assert ev.norm_value_text(s) == "28/08/2026", s
    assert ev.norm_value_text("5.2  ×\n4.1 CM") == "5.2 x 4.1 cm"


def test_score_rows():
    rows = _rows()
    summary = ev.score_all(QUESTIONS, rows, PAGES)
    s = {k: v["score"] for k, v in _by_id(rows).items()}

    hit = s["rad-001"]
    assert hit["status_match"] and hit["quotes_verified"] and hit["values_ok"] and hit["citation_match"] and hit["no_advice"]
    assert hit["false_refusal"] is False and hit["refused"] is None

    assert s["rad-019"]["values_ok"] is True  # 28-Aug-2026 found as 28/08/2026

    miss = s["rad-002"]
    assert miss["status_match"] and miss["values_ok"] is False and miss["missing_values"] == ["poorly differentiated"]
    assert miss["citation_match"] is False and miss["cited_docs"] == ["Dct"]

    fr = s["rad-025"]
    assert fr["status_match"] is False and fr["false_refusal"] is True and fr["values_ok"] is None

    ref = s["rad-031"]
    assert ref["status_match"] and ref["refused"] and ref["refusal_category_ok"] and ref["false_refusal"] is None

    gl = s["pat-037"]
    assert gl["status_match"] and gl["has_reference"] and gl["indian_first"] is True and gl["values_ok"] is None

    bad = s["pat-001"]
    assert bad["quotes_verified"] is False and bad["no_advice"] is False
    assert bad["advice_hits"][0]["words"] == ["recommend"]

    fu = s["pat-017"]
    assert fu["status_match"] and fu["values_ok"] and fu["citation_match"]

    o = summary["overall"]
    assert o["questions"] == 8 and o["status_match"] == {"hit": 7, "of": 8}
    assert o["values_ok"] == {"hit": 4, "of": 5} and o["citation_match"] == {"hit": 4, "of": 5}
    assert o["false_refusals"] == {"count": 1, "of": 7}
    assert o["refusal_category_ok"] == {"hit": 1, "of": 1}
    assert o["quotes_verified"] == {"hit": 5, "of": 6} and o["no_advice"] == {"hit": 5, "of": 6}
    assert o["has_reference"] == {"hit": 1, "of": 1} and o["indian_first"] == {"hit": 1, "of": 1}
    lat = o["latency"]
    assert lat["first_measured"] == 6 and lat["first_over_6s"] == 1
    assert lat["first_seconds_p50"] == 2.35 and lat["seconds_p50"] == 5.25
    assert summary["per_role"]["radiology"]["questions"] == 5 and summary["per_role"]["pathology"]["false_refusals"]["count"] == 0
    assert summary["per_role_kind"]["radiology"]["answerable"]["questions"] == 2

    checks = {(m["id"], m["check"]) for m in summary["misses"]}
    assert checks == {("rad-002", "values"), ("rad-002", "citation"), ("rad-025", "status"), ("rad-025", "false refusal"),
                      ("pat-001", "quote not verbatim (bug)"), ("pat-001", "advice wording")}


def test_refusal_misses_and_indian_not_first():
    q = QUESTIONS[4]
    s = ev.score_row(q, {"status": "answered", "statements": []}, PAGES)
    assert s["refused"] is False and s["status_match"] is False
    s = ev.score_row(q, {"status": "out_of_scope", "category": "diagnosis", "statements": []}, PAGES)
    assert s["refused"] and s["refusal_category_ok"] is False
    g = ev.score_row(QUESTIONS[5], {"status": "not_documented", "statements": [],
                                    "references": [{"region": "International"}, {"region": "India"}]}, PAGES)
    assert g["status_match"] and g["indian_first"] is False
    g = ev.score_row(QUESTIONS[5], {"status": "not_documented", "statements": [], "references": []}, PAGES)
    assert g["has_reference"] is False and g["indian_first"] is None


def test_report_and_dry(tmp_path, monkeypatch):
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps({"questions": QUESTIONS}))
    run = tmp_path / "run"
    ev.write_outputs(run, QUESTIONS, _rows(), {"started": "27/10/2026 22:00:00", "model": "Gemma-4-31B"}, PAGES)
    md = (run / "agent_live_eval.md").read_text()
    assert md.splitlines()[0] == ev.HEADER and "Gemma-4-31B" in md.splitlines()[0] and "non-medical" in md.splitlines()[0]
    assert "| radiology |" in md and "| All |" in md and "rad-025 [false refusal]" in md
    assert "—" not in md and "–" not in md
    # --dry scores the saved answers again without a model; the pages come from the store (empty here: the quote check is skipped)
    monkeypatch.setattr(ev, "case_pages", lambda cases: PAGES)
    assert ev.main(["--dry", str(run), "--gold", str(gold), "--out", str(tmp_path / "again")]) == 0
    again = json.loads((tmp_path / "again" / "agent_live_eval.json").read_text())
    assert again["summary"]["overall"]["status_match"] == {"hit": 7, "of": 8}
    assert ev.score_row(QUESTIONS[0], _rows()[0], {})["quotes_verified"] is None  # pages not read: not checked


def test_select_limits_and_synthetic_only():
    qs = QUESTIONS + [{"id": "rad-999", "role": "radiology", "case_id": "TB-2026-x", "kind": "answerable", "question": "?", "expect": {}}]
    assert [q["id"] for q in ev.select(qs)] == [q["id"] for q in QUESTIONS]
    assert [q["id"] for q in ev.select(qs, roles=["pathology"], kinds=["follow_up", "guideline"])] == ["pat-037", "pat-017"]
    assert len(ev.select(qs, limit=2)) == 4


def test_follow_up_carries_the_first_exchange(monkeypatch):
    from tumour_board import agents
    calls = []

    async def fake_ask(case_id, role, question, history=None, user="", on_statement=None):
        calls.append({"question": question, "history": history, "stream": on_statement is not None})
        st = {"text": "Adenocarcinoma." if not history else "The right hilar node is 1.6 cm.",
              "citations": [{"doc_id": "Dhp", "quote": "Adenocarcinoma" if not history else "Right hilar node 1.6 cm", "page": 0}]}
        if on_statement:
            on_statement(st, 0)
        return {"status": "answered", "statements": [st], "references": [], "removed": [], "seconds": 1.0, "first_seconds": 0.5,
                "streamed": on_statement is not None, "model": "Gemma-4-31B"}
    monkeypatch.setattr(agents, "ask", fake_ask)
    by_id = {q["id"]: q for q in QUESTIONS}
    row = asyncio.run(ev.run_one(by_id["pat-017"], by_id, True))
    assert [c["question"] for c in calls] == ["What does the histopathology say?", "And the hilar node?"]
    assert calls[0]["history"] is None and calls[1]["stream"]
    assert calls[1]["history"] == [{"role": "user", "content": "What does the histopathology say?"},
                                   {"role": "assistant", "content": "Adenocarcinoma."}]
    assert row["follows"]["id"] == "pat-001" and row["status"] == "answered" and len(row["statement_times"]) == 1
    assert ev.score_row(by_id["pat-017"], row, PAGES)["values_ok"] is True


def test_an_error_is_recorded_not_raised(monkeypatch):
    from tumour_board import agents

    async def down(*a, **k):
        raise ConnectionError("reasoner not reachable")
    monkeypatch.setattr(agents, "ask", down)
    row = asyncio.run(ev.run_one(QUESTIONS[0], {}, True))
    assert row["status"] == "error" and "ConnectionError" in row["error"]
    s = ev.score_row(QUESTIONS[0], row, PAGES)
    assert s["error"] and s["status_match"] is False


def test_quote_found_checks_each_fragment_of_a_joined_quote():
    from tumour_board.eval.agent_live_eval import quote_found
    pages = ["Specimen CT-guided core biopsy. Received 08-Sep-2026. Diagnosis: Adenocarcinoma, lung."]
    assert quote_found("Specimen CT-guided core biopsy ... Received 08-Sep-2026 ... Adenocarcinoma, lung", pages)
    assert not quote_found("Specimen CT-guided core biopsy ... Received 09-Sep-2026", pages)
    assert not quote_found(" ... ", pages) and not quote_found("", pages)
