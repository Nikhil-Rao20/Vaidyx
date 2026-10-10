"""search: value finder patterns (oncology synonyms) and line hits with source offsets. No embeddings are loaded."""
import re

import pytest

from tumour_board import search, store
from tumour_board.tests.util import add, make_doc

PDL1 = [r"\bpd\-l1\b", r"\bpdl1\b", r"\bpd\ l1\b", r"\btps\b", r"\b22c3\b", r"\bsp263\b", r"\bcps\b"]
HB = ["haemoglobin", "hemoglobin", r"\bhb\b", r"\bhgb\b"]


@pytest.mark.parametrize("q", ["What is the PD-L1 TPS?", "PDL1", "tps", "22C3", "SP263 score"])
def test_pdl1_synonyms(q):
    assert search._patterns(q) == PDL1


@pytest.mark.parametrize("q", ["haemoglobin", "Hb", "hemoglobin level", "HGB?"])
def test_haemoglobin_synonyms(q):
    assert search._patterns(q) == HB


def test_other_synonyms():
    assert search._patterns("KPS") == [r"\becog\b", r"performance\ status", r"\bkps\b", "karnofsky"]
    assert search._patterns("mib-1 index")[:2] == [r"\bki\-67\b", r"\bki67\b"]
    assert r"\btlc\b" in search._patterns("WBC")


def test_plain_words_drop_filler():
    assert search._patterns("what is the smoking history") == [r"\bsmoking\b", r"\bhistory\b"]
    assert search._patterns("what is the") == []


@pytest.mark.parametrize("line,q", [("PD-L1 (22C3) TPS: 60%", "TPS"), ("Tumour Proportion Score (TPS) 60%", "PD-L1"),
                                     ("22C3 clone: 60%", "pd-l1"), ("Hb 11.8 g/dL", "haemoglobin"), ("HAEMOGLOBIN 11.8", "Hb")])
def test_patterns_match_report_lines(line, q):
    rx = re.compile("|".join(f"(?:{p})" for p in search._patterns(q)), re.I)
    assert rx.search(line)


def test_patterns_respect_word_boundaries():
    rx = re.compile("|".join(f"(?:{p})" for p in search._patterns("Hb")), re.I)
    assert not rx.search("Hbs Ag negative") and not rx.search("thb")


def test_find_values_on_demo_case(demo_cases):
    r = search.find_values("TB-001", "PD-L1")
    assert r["patterns"] == PDL1
    assert [(h["doc_id"], h["text"], h["match"]) for h in r["hits"]] == [("D67977cf8", "PD-L1 (22C3) TPS Pending", "PD-L1")]
    h = r["hits"][0]
    page = store.get_doc("TB-001", h["doc_id"])["pages"][h["page"]]["text"]
    assert page[h["start"]:h["end"]] == h["text"]
    assert (h["status"], h["date"], h["doc_type"]) == ("DRAFT", "2026-09-08", "histopathology")


def test_find_values_haemoglobin_line_text(demo_cases):
    hits = search.find_values("TB-001", "Hb")["hits"]
    assert [(h["doc_id"], h["text"]) for h in hits] == [("Dedaf7100", "Haemoglobin 11.8 g/dL 13.0 - 17.0")]


def test_find_values_sorted_newest_first_and_skips_unready(unit_case):
    add(unit_case, make_doc("Dold", "lab", date="2026-08-01", text="SYNTHETIC\nHb 12.5 g/dL"),
        make_doc("Dnew", "lab", date="2026-09-04", text="SYNTHETIC\nHaemoglobin 11.2 g/dL"),
        make_doc("Dbusy", "lab", date="2026-09-10", text="SYNTHETIC\nHb 9.0 g/dL", state="reading"))
    hits = search.find_values(unit_case, "haemoglobin")["hits"]
    assert [(h["doc_id"], h["text"]) for h in hits] == [("Dnew", "Haemoglobin 11.2 g/dL"), ("Dold", "Hb 12.5 g/dL")]


def test_find_values_no_patterns(unit_case):
    assert search.find_values(unit_case, "what is the") == {"patterns": [], "hits": []}


def test_tokenize():
    assert search.tokenize("PD-L1 (22C3) TPS: 60%, Hb 11.8 g/dL") == ["pd-l1", "22c3", "tps", "60", "hb", "11.8", "g/dl"]


def test_chunks_cover_the_page_with_offsets():
    text = "".join(f"line {i} " + "x" * 50 + "\n" for i in range(40))
    d = make_doc("Dlong", "other", text=text)
    ch = search.chunks_for(d, size=300)
    assert len(ch) > 1 and ch[0]["start"] == 0
    for c in ch:
        assert text[c["start"]:c["end"]].strip() == c["text"]
    assert ch[-1]["end"] == len(text)
