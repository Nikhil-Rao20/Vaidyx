"""Guideline search eval (V1 item 5.3): hit rule, metrics and the gold file. Fast: no embedding model, no index build.

Evidence snippets on PDF pages are checked by `python -m tumour_board.eval.guideline_eval --check-gold` (about 45 s for
the whole library, about 4 s even reading only the listed pages, so outside the unit suite); here only the .docx / .txt
snippets are checked against the guideline text."""
import json

import pytest

from tumour_board import config, guidelines
from tumour_board.eval import guideline_eval as ge

EXP = [{"file": "ncg_india/a.pdf", "pages": [4], "evidence": "x"}, {"file": "icmr/b.pdf", "pages": [9, 10], "evidence": "y"}]


def H(file, page, page_end=None, region="India", text="Guideline text about staging work-up."):
    h = {"file": file, "page": page, "region": region, "text": text, "score": 0.1}
    if page_end is not None:
        h["page_end"] = page_end
    return h


# hit rule

def test_hit_missing_page_end_is_single_page():
    assert ge.is_hit(H("ncg_india/a.pdf", 4), EXP)
    assert not ge.is_hit(H("ncg_india/a.pdf", 5), EXP)
    assert ge.span(H("ncg_india/a.pdf", 4)) == (4, 4)
    assert ge.span({"file": "f", "page": 4, "page_end": None}) == (4, 4)


def test_hit_page_end_overlap():
    assert ge.is_hit(H("ncg_india/a.pdf", 2, 4), EXP)  # span 2-4 reaches page 4
    assert ge.is_hit(H("ncg_india/a.pdf", 3, 6), EXP)
    assert not ge.is_hit(H("ncg_india/a.pdf", 5, 8), EXP)
    assert not ge.is_hit(H("ncg_india/a.pdf", 1, 3), EXP)


def test_hit_needs_the_same_file():
    assert not ge.is_hit(H("ncg_india/other.pdf", 4), EXP)
    assert not ge.is_hit(H("icmr/b.pdf", 4), EXP)  # page 4 is expected only in a.pdf


def test_any_acceptable_answer_counts_and_first_hit_rank():
    top = [H("esmo/c.pdf", 1, region="International"), H("icmr/b.pdf", 10), H("ncg_india/a.pdf", 4)]
    assert ge.first_hit_rank(top, EXP) == 2
    assert ge.first_hit_rank(top[:1], EXP) is None
    assert ge.first_hit_rank([], EXP) is None


# metrics

def test_india_share_divides_by_k():
    top = [H("a", 1), H("b", 1, region="International"), H("c", 1), H("d", 1, region="UK"), H("e", 1)]
    assert ge.india_share(top, 5) == pytest.approx(0.6)
    assert ge.india_share(top[:2], 5) == pytest.approx(0.2)  # fewer results than k still count against k
    assert ge.india_share(top + [H("f", 1)], 5) == pytest.approx(0.6)  # only the top k


def test_score_query_and_summary():
    qa = {"id": "G01", "query": "q1", "cancer": "lung_nsclc", "kind": "case", "indian_expected": True, "expected": EXP}
    qb = {"id": "G02", "query": "q2", "cancer": None, "kind": "board", "indian_expected": True, "expected": EXP}
    qc = {"id": "G03", "query": "q3", "cancer": None, "kind": "board", "indian_expected": False,
          "expected": [{"file": "recist/r.pdf", "pages": [5], "evidence": "z"}]}
    ra = ge.score_query(qa, [H("ncg_india/a.pdf", 4), H("x", 1)], 5)  # rank 1, India first
    rb = ge.score_query(qb, [H("esmo/c.pdf", 1, region="International"), H("icmr/b.pdf", 9, 11)], 5)  # rank 2, rank 1 foreign
    rc = ge.score_query(qc, [H("recist/r.pdf", 6, region="International")], 5)  # miss
    assert (ra["rank"], ra["hit"], ra["rr"], ra["rank1_india"]) == (1, True, 1.0, True)
    assert (rb["rank"], rb["rr"], rb["rank1_india"]) == (2, 0.5, False)
    assert (rc["rank"], rc["hit"], rc["rr"]) == (None, False, 0.0)
    assert rb["top"][1]["page_end"] == 11 and rb["top"][1]["hit"] and ra["top"][1]["page_end"] == 1
    s = ge.summarise([ra, rb, rc], 5)
    assert s["n"] == 3 and s["hit@5"] == pytest.approx(2 / 3, abs=1e-4)
    assert s["hit@5_by_kind"] == {"case": 1.0, "board": 0.5}
    assert s["mrr"] == pytest.approx(0.5, abs=1e-4)  # (1 + 0.5 + 0) / 3
    assert s["india_share"] == pytest.approx((0.4 + 0.2 + 0.0) / 3, abs=1e-4)
    assert s["india_share_indian_expected"] == pytest.approx(0.3, abs=1e-4)
    assert s["n_indian_expected"] == 2 and s["india_first"] == pytest.approx(0.5)  # only the India-expected queries


def test_score_query_cuts_to_k():
    q = {"id": "G01", "query": "q", "cancer": None, "kind": "board", "indian_expected": True, "expected": EXP}
    r = ge.score_query(q, [H("x", 1)] * 5 + [H("ncg_india/a.pdf", 4)], 5)
    assert not r["hit"] and len(r["top"]) == 5


class FakeIndex:
    """Stands in for GuidelineIndex: fixed results, records the calls."""
    def __init__(self, hits):
        self.hits, self.calls, self.chunks = hits, [], [{}] * 7

    def search(self, q, k=8, cancer=None):
        self.calls.append((q, k, cancer))
        return self.hits[:k]


def test_run_ranks_like_search_grouped_and_writes_reports(tmp_path):
    bib = "Lee HJ, Chung WS, Kim YS, et al. J Clin Oncol 2011;29:1261-70. doi 10.1200/x. Park SK, Choi JH."
    assert guidelines._is_reference_list(bib)
    gold = {"version": "t", "judged_by": None, "queries": [
        {"id": "G01", "query": "rectal MRI", "cancer": "colorectal_rectum", "kind": "case", "indian_expected": True, "expected": EXP},
        {"id": "G02", "query": "RECIST", "cancer": None, "kind": "board", "indian_expected": False,
         "expected": [{"file": "recist/r.pdf", "pages": [5], "evidence": "z"}]}]}
    gp = tmp_path / "gold.json"; gp.write_text(json.dumps(gold))
    idx = FakeIndex([H("ncg_india/a.pdf", 4, text=bib), H("esmo/c.pdf", 2, region="International"), H("icmr/b.pdf", 9)])
    res = ge.run(gp, tmp_path / "out", k=5, idx=idx, verbose=False)
    assert idx.calls == [("rectal MRI", ge.CANDIDATES, "colorectal_rectum"), ("RECIST", ge.CANDIDATES, None)]
    r1 = res["queries"][0]
    assert r1["rank"] == 2 and [t["file"] for t in r1["top"]] == ["esmo/c.pdf", "icmr/b.pdf"]  # bibliography chunk dropped
    assert res["summary"]["hit@5"] == 0.5 and res["meta"]["chunks"] == 7
    d = json.loads((tmp_path / "out" / "guideline_eval.json").read_text())
    assert d["summary"]["mrr"] == 0.25 and len(d["queries"]) == 2
    md = (tmp_path / "out" / "guideline_eval.md").read_text()
    assert "| hit@5 | 50.0% (1 / 2) |" in md and "**icmr/b.pdf p.9**" in md and "G02" in md
    assert "—" not in md  # no em dashes in reports


def test_check_evidence_with_a_fake_library(tmp_path):
    (tmp_path / "ncg_india").mkdir()
    (tmp_path / "ncg_india" / "a.pdf").write_text("")
    pages = {"a.pdf": [(0, "cover"), (1, "x"), (2, "y"), (3, "MRI   brain\n(b) is  optimal")]}
    gold = {"queries": [
        {"id": "G01", "expected": [{"file": "ncg_india/a.pdf", "pages": [4], "evidence": "MRI brain (b) is optimal"}]},
        {"id": "G02", "expected": [{"file": "ncg_india/a.pdf", "pages": [3], "evidence": "MRI brain"},
                                   {"file": "ncg_india/a.pdf", "pages": [9], "evidence": "x"},
                                   {"file": "icmr/missing.pdf", "pages": [1], "evidence": "x"}]}]}
    probs = ge.check_evidence(gold, root=tmp_path, reader=lambda p: pages[p.name])
    assert not [p for p in probs if p.startswith("G01")]  # whitespace-normalised match on page 4 (index 3)
    assert any("G02" in p and "evidence not on" in p and "[3]" in p for p in probs)
    assert any("G02" in p and "no page [9]" in p for p in probs)
    assert any("G02" in p and "missing file icmr/missing.pdf" in p for p in probs)


def test_validate_schema_flags_problems():
    q = {"id": "G01", "query": "q", "cancer": "lung_nsclc", "kind": "case", "indian_expected": True, "expected": EXP}
    good = {"queries": [dict(q, id=f"G{i:02d}") for i in range(1, 21)]}
    assert ge.validate_schema(good) == []
    bad = {"queries": [dict(q, id="G01"), dict(q, id="G01", kind="trivia", cancer="liver", indian_expected="yes", expected=[])]}
    probs = ge.validate_schema(bad)
    for frag in ("2 queries", "duplicate id G01", "kind 'trivia'", "cancer 'liver'", "indian_expected", "no expected"):
        assert any(frag in p for p in probs), frag


# the gold file

@pytest.fixture(scope="module")
def gold():
    return ge.load_gold()


def test_gold_schema(gold):
    assert ge.validate_schema(gold) == []
    qs = gold["queries"]
    assert gold["judged_by"] is None and all(q["judged"] is False for q in qs)  # awaiting Eswar's judgement
    assert {q["kind"] for q in qs} == {"case", "board"}
    assert 0.6 <= sum(q["indian_expected"] for q in qs) / len(qs) <= 0.8  # India-first, some international-only
    assert [q["id"] for q in qs] == [f"G{i:02d}" for i in range(1, len(qs) + 1)]
    assert all(q["cancer"] in guidelines.CANCER_WORDS or q["cancer"] is None for q in qs)


def test_gold_india_expected_queries_list_an_indian_source(gold):
    india = {f for f, (_, region, _) in guidelines.SOURCES.items() if region == "India"} | {"tmc"}
    for q in gold["queries"]:
        has_indian = any(e["file"].split("/")[0] in india for e in q["expected"])
        assert has_indian == q["indian_expected"], q["id"]


def test_gold_has_no_patient_data_or_em_dashes(gold):
    raw = json.dumps(gold)
    assert "cases/" not in raw and "TB-2026" not in raw
    assert all("—" not in (q["query"] + q.get("note", "")) for q in gold["queries"])


def test_gold_expected_files_exist(gold):
    if not config.GUIDELINE_DIR.is_dir():
        pytest.skip("guideline library not present")
    missing = sorted({e["file"] for q in gold["queries"] for e in q["expected"] if not (config.GUIDELINE_DIR / e["file"]).is_file()})
    assert not missing


def test_gold_docx_and_text_evidence_on_listed_pages(gold):
    if not config.GUIDELINE_DIR.is_dir():
        pytest.skip("guideline library not present")
    sub = {"queries": [{"id": q["id"], "expected": [e for e in q["expected"] if not e["file"].lower().endswith(".pdf")]}
                       for q in gold["queries"]]}
    assert sum(len(q["expected"]) for q in sub["queries"]) >= 5
    assert ge.check_evidence(sub) == []
