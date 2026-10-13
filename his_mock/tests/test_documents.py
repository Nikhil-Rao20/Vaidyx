"""Unit tests for the mock hospital's report documents (plan item V2-1.2): every report version is a PDF in an Indian layout
whose text layer holds every value of the record, signed versions carry the demo-CA block verbatim, one signature fails
verification by design, outside reports keep their own laboratory and the masked Aadhaar only. SYNTHETIC data only; builds
into a temporary directory (the pdf venv renders the PDFs)."""
import hashlib
import json
import re
import time

import pytest

from his_mock import documents, generator, scenarios
from his_mock.model import Store
from his_mock.paths import layout

TAMPERED = "p03-r10"          # P03-R10, the discharge summary whose signature fails verification (scenarios.json)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("his_mock_docs")
    store = generator.build(out, documents=True, dicom=False, hl7=False)
    return store, layout(out)


@pytest.fixture(scope="module")
def store(built):
    return built[0]


@pytest.fixture(scope="module")
def files(built):
    return built[1]


def _pdf(files, report_id, n):
    return files["documents"] / f"{report_id}-v{n}.pdf"


def _text(files, report_id, n=1):
    return documents.norm(documents.text_of(_pdf(files, report_id, n)))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ one PDF per version, everything printed
def test_a_pdf_for_every_version(store, files):
    want = sum(len(r["versions"]) for r in store.reports.values())
    pdfs = sorted(p.name for p in files["documents"].glob("*.pdf"))
    assert len(pdfs) == want and want > 100
    for r in store.reports.values():
        for v in r["versions"]:
            doc = v["document"]
            assert doc["path"] == f"documents/{r['id']}-v{v['version']}.pdf"
            assert doc["sha256"] == _sha(files["data_dir"] / doc["path"])


def test_check_finds_no_problem(store, files):
    assert documents.check(store, files) == []


def test_check_cli_on_the_built_directory(files, capsys):
    assert documents.main(["--check", "--data", str(files["data_dir"])]) == 0
    assert "0 problem(s)" in capsys.readouterr().out


def test_store_saved_with_the_documents(store, files):
    saved = json.loads(files["store"].read_text(encoding="utf-8"))
    r = saved["reports"]["p01-r02"]["versions"][0]
    assert r["document"] == store.reports["p01-r02"]["versions"][0]["document"] and r["document"]["sha256"]


def test_signature_block_verbatim(store, files):
    sig = store.signatures["sig-p01-r02-v1"]
    text = _text(files, "p01-r02")
    assert sig["block"] in text
    assert sig["block"].startswith("Digitally signed by Dr Sanjay Joshi, MD (Radiodiagnosis), Reg. No. VXREG-20201, ")
    assert "Report status: FINAL" in text and "Vaidyx Demo CA" in text
    for w in ("unsigned", "signature pending", "awaiting verification", "draft"):
        assert w not in text.lower()
    # Reg. No. only in the footer signature block, never in the identity header
    assert text.count("Reg. No.") == 1 and text.index("Reg. No.") > text.index("Report status:")


def test_preliminary_report(files):
    text = _text(files, "p12-r02")
    assert "Report status: PRELIMINARY" in text and "Digitally signed" not in text
    assert "(preliminary, verification awaited)" in text and "4.8 x 3.6 cm right upper lobe mass" in text


def test_unsigned_final_reads_unsigned(files):
    text = _text(files, "p11-r02")
    assert "Report status: FINAL" in text and "Signature pending" in text and "Digitally signed" not in text
    assert "Squamous cell carcinoma, non-keratinising" in text


def test_amended_report_keeps_both_versions(store, files):
    v1, v2 = _text(files, "p02-r05", 1), _text(files, "p02-r05", 2)
    assert "Report status: FINAL" in v1 and "2+ (Equivocal)" in v1 and "3+ (Positive)" not in v1
    assert "Report status: AMENDED" in v2 and "3+ (Positive)" in v2
    note = store.reports["p02-r05"]["versions"][1]["amendment_note"]
    assert f"Amends version 1 of 03/09/2026: {note}" in v2
    assert store.signatures["sig-p02-r05-v2"]["block"] in v2 and store.signatures["sig-p02-r05-v1"]["block"] in v1


def test_omitted_value_is_absent(store, files):
    r = store.reports["p03-r05"]
    assert r["omitted_values"] == ["her2"]
    text = _text(files, "p03-r05")
    assert documents.label("her2") not in text
    for v in r["versions"][0]["values"].values():
        assert v in text
    assert "Digitally signed by" in text


def test_observation_value_never_printed(files):
    text = _text(files, "p15-r03")
    assert "12.1 gm%" in text and "11.2 gm%" not in text


def test_lab_report_is_nabl_style(files):
    text = _text(files, "p03-r09")
    assert "Investigation Result Units Biological reference interval" in text
    assert "10.9 gm%" in text and "2.2 lakhs/cumm" in text and "9,800 /cumm" in text
    assert "12.0-15.0" in text          # female haemoglobin range
    assert documents.NABL_LINE in text
    assert "Ward / Bed : High Dependency Unit / HDU-04" in text   # drawn in the HDU, same IP No.


def test_every_page_marked_synthetic(store, files):
    for rid in ("p01-r01", "p14-r01", "p03-r10"):
        text = _text(files, rid)
        assert documents.WATERMARK in text and documents.PAGE_FOOTER in text
        assert not re.search(r"Sahyadri|SYN-|\u2014", text)


# ------------------------------------------------------------------ tamper: a signature that fails verification
def test_tampered_signature_hash_differs(store, files):
    fx = scenarios.load()
    rec = next(r for p in fx["patients"] for r in p["records"] if r["id"] == "P03-R10")
    assert rec["signature"]["verification_status"] == "failed" and rec["signature"]["document_hash"] is None
    assert "signature_fails_verification" in {s["id"] for s in fx["scenarios"]}
    for sig in store.signatures.values():
        rep = store.reports[sig["report_id"]]
        v = next(x for x in rep["versions"] if x["version"] == sig["version"])
        pdf = files["data_dir"] / v["document"]["path"]
        if sig["report_id"] == TAMPERED:
            assert sig["verification_status"] == "failed"
            assert sig["document_hash"] != _sha(pdf) == v["document"]["sha256"]
            assert sig["document_hash"] == documents.tampered_hash(pdf.read_bytes())
        else:
            assert sig["verification_status"] == "verified" and sig["document_hash"] == _sha(pdf), sig["id"]
    # the PDF itself is untouched: it still prints the signature block
    assert store.signatures[f"sig-{TAMPERED}-v1"]["block"] in _text(files, TAMPERED)


# ------------------------------------------------------------------ outside reports
def test_outside_reports(files):
    index = json.loads(files["fixture_index"].read_text(encoding="utf-8"))
    recs = {o["record"]["id"]: o["record"] for o in index["outside_reports"]}
    assert set(recs) == {"P06-R06", "P17-R10"}
    for rid, rec in recs.items():
        pdf, png = documents.outside_paths(files, rec)
        text = documents.norm(documents.text_of(pdf))
        assert rec["outside_source"]["name"] in text and rec["printed_status"] in text and rec["printed_signature"] in text
        assert "Vaidyx Demo CA" not in text and "Digitally signed" not in text and "Vaidyx Demo Hospital (SYNTHETIC)" not in text
        assert not scenarios.AADHAAR_LIKE.search(text)
        for v in rec["values"].values():
            assert v in text
        if rid == "P06-R06":
            assert "Aadhaar No. : XXXX XXXX 1234" in text
            assert png.exists() and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        else:
            assert "Aadhaar" not in text and png is None


# ------------------------------------------------------------------ determinism
def test_rendering_is_deterministic(store, files, tmp_path):
    picks = [("p02-r05", 2), ("p03-r09", 1), ("p14-r01", 1)]
    jobs = []
    for rid, n in picks:
        r = store.reports[rid]
        v = next(x for x in r["versions"] if x["version"] == n)
        jobs.append({"html": documents.html_for(store, r, v), "out": str(tmp_path / f"{rid}-v{n}.pdf")})
    documents.run_jobs(jobs)
    for rid, n in picks:
        assert (tmp_path / f"{rid}-v{n}.pdf").read_bytes() == _pdf(files, rid, n).read_bytes()


# ------------------------------------------------------------------ layouts
def _first(store, doc_types):
    return next(r for r in sorted(store.reports.values(), key=lambda r: r["id"]) if r["doc_type"] in doc_types)


@pytest.mark.parametrize("doc_types, headings", [
    (("ct", "mri"), ("Technique", "Findings", "Impression", "Accession No.", "Ref. by")),
    (("pet_ct",), ("Technique", "Findings", "Impression")),
    (("histopathology",), ("Specimen", "Block No.", "Gross", "Microscopy", "Diagnosis", "Lab No.", "Sample ID")),
    (("ihc",), ("Block No.", "Marker", "Result")),
    (("molecular",), ("Block No.", "Test", "Method", "Result")),
    (("cytology",), ("Specimen", "Microscopy", "Diagnosis")),
    (("lab",), ("Investigation", "Biological reference interval", "Units", "NABL-style", "Sample ID")),
    (("endoscopy",), ("Procedure", "Findings", "Impression")),
    (("clinical_note",), ("Presenting complaint", "Examination", "Clinical question / Plan", "Unit", "Consultant")),
    (("referral",), ("Referral", "Referred from", "Unit")),
    (("discharge_summary",), ("Admission", "Referrals", "Diagnosis", "Course", "Advice", "IP No.", "Transferred to")),
])
def test_layout_headings(store, doc_types, headings):
    r = _first(store, doc_types) if doc_types != ("discharge_summary",) else store.reports["p03-r10"]
    if doc_types == ("referral",):
        r = next(x for x in store.reports.values() if x["doc_type"] == "referral"
                 and store.encounters[x["encounter_id"]]["referrals"])
    page = documents.html_for(store, r, r["versions"][-1])
    for h in headings:
        assert h in page, (r["id"], h)
    assert ("IP No." in page) or ("OP No." in page)
    assert "SYNTHETIC - DEMO ONLY" in page and "\u2014" not in page


def test_opd_note_header(store):
    r = store.reports["p01-r01"]
    page = documents.html_for(store, r, r["versions"][0])
    assert "OPD CONSULTATION NOTE" in page and "OP/26/118701" in page and "Breast Surgery, Unit I" in page
    assert "Dr Kavitha Raghunathan" in page and "99-2600-0000-0101" in page


# ------------------------------------------------------------------ the reporting desk path (1.5): one pair only
def test_render_versions_single_pair(files, tmp_path):
    s = Store.load(files["store"])
    r = s.sign_final("p12-r02", "VXREG-20201", when="2026-09-03T10:05:00+05:30")
    v = s.current_version(r)
    assert v["version"] == 2 and v["signature_id"]
    desk = layout(tmp_path)
    t0 = time.monotonic()
    written = documents.render_versions(s, desk, [(r, v)])
    assert time.monotonic() - t0 < 10
    assert written == [tmp_path / "documents" / "p12-r02-v2.pdf"]
    pdf = written[0]
    assert v["document"] == {"path": "documents/p12-r02-v2.pdf", "sha256": _sha(pdf)}
    assert s.signatures[v["signature_id"]]["document_hash"] == _sha(pdf)
    text = documents.norm(documents.text_of(pdf))
    assert "Report status: FINAL" in text and s.signatures[v["signature_id"]]["block"] in text
    assert "4.8 x 3.6 cm right upper lobe mass" in text and "preliminary" not in text.lower()
    assert sorted(p.name for p in (tmp_path / "documents").iterdir()) == ["p12-r02-v2.pdf"]   # nothing else rendered
