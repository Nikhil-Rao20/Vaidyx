"""V1-9.1: synthetic oral cavity demo case TB-007 in the demo corpus generator (no GPU, no model calls).

Checks the generator definitions themselves (every answer-key value printed in its document, Word package valid, protocol
oral_cavity, board decision, no dental record in the OPD note), the --only build (only the named case is written), and,
when the generated corpus is present, that TB-007 in it matches the generator and passes check_corpus."""
import json, re, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tumour_board import docstatus, ingest, protocol
from tumour_board.demo_data import check_corpus, india_corpus as ic

CORPUS = Path("/data/vaidyx/tb_demo_corpus")
CID = "TB-007"
CASE = next(c for c in ic.V1_CASES if c[0] == CID)
DOCS, ARRIVALS = CASE[3], CASE[4]
ALL = DOCS + ARRIVALS


def _norm(s):
    return " ".join(str(s).split()).lower()


def source_text(d):
    """Everything a document prints, straight from its generator definition (no rendering)."""
    if d["fmt"] == "docx":
        parts = []
        for kind, c in d["blocks"]:
            parts += [" ".join(map(str, r)) for r in c] if kind == "table" else [c]
        return "\n".join(parts)
    parts = [d.get("hosp", ic.HOSP), d["dept"], d["title"]]
    parts += [f"{k} {v}" for k, v in d.get("id_rows", []) + d.get("meta", []) + d.get("grid", [])]
    for head, c in d.get("sections", []):
        parts.append(head)
        if isinstance(c, list):
            parts += [" ".join(map(str, r)) for r in c]
        elif isinstance(c, dict):
            parts.append(re.sub(r"<[^>]+>", " ", c["html"]))
        else:
            parts.append(c)
    parts += d.get("footer", []) + [d.get("stamp", ""), d.get("nabl", "")]
    return "\n".join(parts)


def _dmy(iso):
    y, m, dd = iso.split("-")
    return f"{dd}/{m}/{y}"


def test_case_registration_and_protocol():
    cid, prot, pat, _, _ = CASE
    assert prot == "oral_cavity"
    assert pat == {"name": "Manjunath Gowda", "mrn": "SYN-700352", "agesex": "54 Y / M"}
    assert ic.V1_PATIENTS[CID] is ic.P7 and ic.P7["abha"] == "91-5512-0846-2271"
    assert "aadhaar" not in ic.P7
    assert len(DOCS) == 6 and len(ARRIVALS) == 1
    assert len({d["path"] for d in ALL}) == len(ALL)


@pytest.mark.parametrize("d", ALL, ids=[d["path"] for d in ALL])
def test_every_truth_value_is_printed(d):
    t, flat = d["truth"], _norm(source_text(d))
    assert "synthetic" in flat
    assert t["doc_type"] in protocol.doc_types()
    want = [v for v in list(t.get("fields", {}).values()) + list(t.get("other_values", {}).values()) if v]
    want += list(t["identity"].values()) + [_dmy(t[k]) for k in ("report_date", "event_date") if t.get(k)]
    want += [x.split(": ", 1)[1] for x in t.get("negated", []) + t.get("not_negations", [])]
    missing = [w for w in want if _norm(w) not in flat]
    assert not missing, missing


def test_names_printed_as_planned():
    """Only the dental Word file prints the title Sri; every other document prints the registered name."""
    for d in ALL:
        name = d["truth"]["identity"]["name"]
        assert name == ("Sri Manjunath Gowda" if d["fmt"] == "docx" else "Manjunath Gowda"), d["path"]


def test_opd_note_has_no_dental_record():
    opd = next(d for d in DOCS if d["path"] == "surgical_oncology/head_neck_opd_2026-09-14.pdf")
    flat = _norm(source_text(opd))
    for w in ("dental", "opg", "orthopantomogram", "sent for", "extraction"):
        assert w not in flat, w
    assert opd["truth"]["fields"]["ecog"] == "1" and "ecog performance status: 1" in flat
    holders = [d["path"] for d in ALL if "dental_evaluation" in d["truth"].get("fields", {})]
    assert holders == ["surgical_oncology/dental_evaluation_2026-09-17.docx"]


def test_board_decision():
    rec = ARRIVALS[0]
    assert rec["truth"]["board_decision"] is ic.BOARD_DECISION_7
    assert ic.BOARD_DECISIONS["TB-005"] is ic.BOARD_DECISION and ic.BOARD_DECISIONS["TB-007"] is ic.BOARD_DECISION_7
    bd = ic.BOARD_DECISION_7
    assert bd["text"] == ic.DECISION_TEXT_7 and bd["document"] == rec["path"] and bd["board_date"] == rec["truth"]["event_date"]
    assert set(ic.BOARD_DECISION) <= set(bd) and bd["dose_slips"] == [] and bd["absent_specialties"] == []
    for w in ("Cisplatin 40 mg/m2 IV weekly", "60 Gy in 30 fractions", "Stage as recorded: cT4a N1 M0"):
        assert w in bd["text"]
    flat = _norm(source_text(rec))
    assert _norm(ic.DECISION_TEXT_7) in flat
    for w in ("radiation oncology", "medical oncology", "surgical oncology"):
        assert w in flat


def test_no_em_or_en_dash_in_tb007():
    blob = json.dumps([ic.P7, ic.BOARD_DECISION_7, [{k: v for k, v in d.items()} for d in ALL]], ensure_ascii=False, default=str)
    assert "\u2014" not in blob and "\u2013" not in blob


def test_dental_docx_is_a_valid_word_package(tmp_path):
    d = next(x for x in DOCS if x["fmt"] == "docx")
    p = tmp_path / "dental.docx"
    ic.write_docx(p, d["blocks"])
    with zipfile.ZipFile(p) as z:
        assert z.testzip() is None
        assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= set(z.namelist())
        for n in z.namelist():
            ET.fromstring(z.read(n))  # well-formed XML
    txt = ingest._docx_text(p)
    assert "Sri Manjunath Gowda" in txt and "SYN-700352" in txt and "grossly carious 36 and 37" in txt
    assert docstatus.detect_status(txt)[0] == "UNSTATED" and docstatus.detect_signature(txt)[0] == "yes"


def test_fact_ids_in_catalogue_when_protocol_present():
    if not (Path(protocol.__file__).parent / "protocols" / "oral_cavity.json").exists():
        pytest.skip("protocols/oral_cavity.json not written yet")
    cat = protocol.facts()
    ids = {f for d in ALL for f in d["truth"].get("fields", {})}
    assert not ids - set(cat), sorted(ids - set(cat))


def _fake_build(out, monkeypatch, only):
    """build_v1 without weasyprint: every PDF is a small placeholder file, the reference text is the HTML."""
    class _Html:
        def __init__(self, string):
            self.s = string

        def write_pdf(self, target):
            Path(target).write_text(self.s)

    class _Weasy:
        HTML = _Html
    monkeypatch.setattr(ic, "pdf_text", lambda p: Path(p).read_text())
    monkeypatch.setattr(ic, "fix_known_lines", lambda ref, known: ref)
    monkeypatch.setattr(ic, "to_photo", lambda pdf, png, seed: Path(png).write_bytes(b"photo"))
    monkeypatch.setattr(ic, "to_big_scan", lambda pdf, out_pdf, seed: Path(out_pdf).write_bytes(b"scan"))
    ic.build_v1(out, _Weasy, lambda pdf, png, seed: Path(png).write_bytes(b"png"), only=only)


def test_only_builds_just_the_named_case(tmp_path, monkeypatch):
    out = tmp_path / "corpus"
    keep = {out / "cases" / "TB-004" / "x.pdf": "a", out / "arrivals" / "TB-005" / "y.pdf": "b", out / "truth" / "TB-006.json": "{}",
            out / "truth" / "intake.json": '{"files": {}}', out / "intake" / "pathology" / "z.pdf": "c",
            out / "truth" / "reference_text" / "TB-004" / "r.txt": "d"}
    stale = [out / "cases" / CID / "old.pdf", out / "arrivals" / CID / "old.pdf", out / "truth" / "reference_text" / CID / "old.txt"]
    for p, s in list(keep.items()) + [(p, "old") for p in stale]:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(s)
    _fake_build(out, monkeypatch, {CID})
    for p, s in keep.items():
        assert p.read_text() == s, p
    assert not any(p.exists() for p in stale)
    assert sorted(p.name for p in (out / "truth").glob("*.json")) == ["TB-006.json", "TB-007.json", "intake.json"]
    assert sorted(p.name for p in (out / "cases").iterdir()) == ["TB-004", CID]
    truth = json.loads((out / "truth" / f"{CID}.json").read_text())
    assert truth["protocol"] == "oral_cavity" and truth["board_decision"]["text"] == ic.DECISION_TEXT_7
    assert set(truth["documents"]) == {d["path"] for d in DOCS} and set(truth["arrivals"]) == {d["path"] for d in ARRIVALS}
    assert all((out / "cases" / CID / d["path"]).exists() for d in DOCS)
    assert (out / "truth" / "reference_text" / CID / "radio_diagnosis" / "xray_chest_pa_2026-09-15.png.txt").exists()
    assert json.loads((out / "cases" / CID / "case.json").read_text())["protocol"] == "oral_cavity"


def test_full_build_writes_board_decisions_and_intake_patient(tmp_path, monkeypatch):
    out = tmp_path / "corpus"
    _fake_build(out, monkeypatch, None)
    assert json.loads((out / "truth" / "TB-005.json").read_text())["board_decision"]["text"] == ic.DECISION_TEXT
    assert json.loads((out / "truth" / "TB-007.json").read_text())["board_decision"]["text"] == ic.DECISION_TEXT_7
    assert "board_decision" not in json.loads((out / "truth" / "TB-004.json").read_text())
    assert json.loads((out / "truth" / "intake.json").read_text())["patients"]["TB-007"]["uhid"] == "SYN-700352"


needs_corpus = pytest.mark.skipif(not (CORPUS / "truth" / f"{CID}.json").exists(), reason="demo corpus with TB-007 not generated here")


@needs_corpus
def test_corpus_tb007_matches_generator():
    truth = json.loads((CORPUS / "truth" / f"{CID}.json").read_text())
    want = json.loads(json.dumps({d["path"]: d["truth"] for d in DOCS}, ensure_ascii=False))
    assert truth["documents"] == want and truth["protocol"] == "oral_cavity"
    assert truth["board_decision"] == json.loads(json.dumps(ic.BOARD_DECISION_7))
    for d in DOCS:
        assert (CORPUS / "cases" / CID / d["path"]).stat().st_size > 0
    for d in ARRIVALS:
        assert (CORPUS / "arrivals" / CID / d["path"]).stat().st_size > 0


@needs_corpus
def test_corpus_tb007_passes_check_corpus():
    _, problems = check_corpus.check(CORPUS)
    assert not [p for p in problems if p.startswith(CID)], problems
