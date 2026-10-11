"""ingest.extract_pages for office files (plan item 1.4): .xlsx read cell by cell with openpyxl (values exactly as
stored), .pptx through markitdown, one page per sheet or slide; .doc / .rtf / .odt refused at upload unless LibreOffice (soffice) is on PATH, in which case they are converted
to PDF and read the normal way. No GPU, no model calls. Fixtures are SYNTHETIC (see fixtures/office/)."""
import asyncio, shutil, subprocess
from pathlib import Path

import pytest

from tumour_board import extract, ingest, store
from tumour_board.tests.conftest import FIXTURES

OFFICE = FIXTURES / "office"
TB004_XLSX = Path("/data/vaidyx/tb_demo_corpus/cases/TB-004/laboratory_medicine/biochemistry_2026-09-05.xlsx")
MSG = "Save as PDF or DOCX and upload again"
XLS_MSG = "Save as XLSX or PDF and upload again"


def pages(path):
    return asyncio.run(ingest.extract_pages(Path(path)))


def no_soffice(monkeypatch):
    real = shutil.which
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: None if cmd == "soffice" else real(cmd, *a, **k))


def with_soffice(monkeypatch):
    real = shutil.which
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: "/usr/bin/soffice" if cmd == "soffice" else real(cmd, *a, **k))


def _pdf_bytes(line: str) -> bytes:
    """A minimal one-page PDF with a real text layer (Helvetica), xref offsets computed."""
    stream = f"BT /F1 11 Tf 40 760 Td ({line}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % x for x in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


# ---- .xlsx / .pptx ----

def test_xlsx_one_page_per_sheet():
    p = pages(OFFICE / "lab_values.xlsx")
    assert len(p) == 2 and {x["method"] for x in p} == {"office-text"}
    assert p[0]["text"].startswith("## Haematology") and p[1]["text"].startswith("## Biochemistry")
    assert "11.8" in p[0]["text"] and "lakhs/cumm" in p[0]["text"] and "SYN-900001" in p[0]["text"]
    assert "| Haemoglobin | 11.8 | g/dL |" in p[0]["text"].splitlines()  # one table row per line
    assert "Creatinine" in p[1]["text"] and "Creatinine" not in p[0]["text"]
    assert "NaN" not in p[0]["text"]  # empty cells stay empty (no pandas markers)
    assert "| UHID | SYN-900001 |" in p[0]["text"].splitlines()


def test_pptx_one_page_per_slide():
    p = pages(OFFICE / "board_slides.pptx")
    assert len(p) == 2 and {x["method"] for x in p} == {"office-text"}
    assert "Tumour Board Case File SYN-900001 (SYNTHETIC)" in p[0]["text"]
    assert "PD-L1 TPS 60%" in p[1]["text"] and "Histopathology: adenocarcinoma" in p[1]["text"]
    assert "PD-L1" not in p[0]["text"] and "Slide number" not in p[1]["text"]


@pytest.mark.skipif(not TB004_XLSX.exists(), reason="demo corpus not built on this machine")
def test_demo_corpus_tb004_xlsx():
    p = pages(TB004_XLSX)
    assert len(p) == 1 and p[0]["method"] == "office-text"
    t = p[0]["text"]
    lines = t.splitlines()
    assert "| S. Creatinine | 1.1 | mg/dl | 0.7 - 1.3 |" in lines
    assert "| Report status: FINAL |" in lines and "| Blood urea | 31 | mg/dl | 15 - 40 |" in lines  # not "31.0"
    assert "SYN-400118" in t and "NaN" not in t and "Unnamed" not in t


def test_xlsx_values_exactly_as_stored(tmp_path):
    import datetime as dt
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "Renal"
    for row in [("Investigation", "Result", "Units", "Date"),
                ("Blood urea", 31, "mg/dl", dt.date(2026, 9, 5)),
                ("Sample code", "007", None, None),
                ("Platelets", 2.45, "lakhs/cumm", dt.datetime(2026, 9, 6, 10, 30)),
                (None, None, None, None),
                ("Sodium", None, "mmol/L", None),
                ("Note", "SYNTHETIC\nDEMO ONLY", None, None)]:
        ws.append(row)
    wb.create_sheet("Blank")
    wb.save(tmp_path / "renal.xlsx")
    p = pages(tmp_path / "renal.xlsx")
    assert len(p) == 2 and p[1] == {"text": "", "method": "office-text"}  # page N stays sheet N
    assert p[0]["text"].splitlines() == [
        "## Renal",
        "| Investigation | Result | Units | Date |",
        "| Blood urea | 31 | mg/dl | 2026-09-05 |",  # int 31 stays "31", not "31.0"
        "| Sample code | 007 |",  # text "007" stays "007"; trailing empty cells dropped
        "| Platelets | 2.45 | lakhs/cumm | 2026-09-06 10:30:00 |",
        "| Sodium |  | mmol/L |",  # empty row dropped; empty middle cell kept as a blank cell
        "| Note | SYNTHETIC DEMO ONLY |"]  # a line break inside a cell does not split the row


def test_xlsx_wrong_dimension_tag_reads_everything(tmp_path):
    """Lab systems often write a stale <dimension>; read-only openpyxl would trust it and cut rows and columns."""
    import re, zipfile
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "Lab"
    for row in [("Investigation", "Result", "Units", "Ref"), ("Haemoglobin", "11.8", "g/dL", "13 - 17"), ("Platelets", "2.45", "lakhs/cumm", "1.5 - 4.1")]:
        ws.append(row)
    good = tmp_path / "good.xlsx"; wb.save(good)
    bad = tmp_path / "bad.xlsx"
    with zipfile.ZipFile(good) as zin, zipfile.ZipFile(bad, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data, n = re.subn(rb'<dimension ref="[^"]+"', b'<dimension ref="A1:B2"', data)
                assert n == 1
            zout.writestr(item, data)
    assert b'<dimension ref="A1:B2"' in zipfile.ZipFile(bad).read("xl/worksheets/sheet1.xml")
    assert pages(bad)[0]["text"].splitlines() == [
        "## Lab",
        "| Investigation | Result | Units | Ref |",
        "| Haemoglobin | 11.8 | g/dL | 13 - 17 |",
        "| Platelets | 2.45 | lakhs/cumm | 1.5 - 4.1 |"]


def test_xlsx_percent_cells_as_shown(tmp_path):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "IHC"
    ws.append(("Marker", "Result"))
    for name, v, fmt in [("Ki-67", 0.45, "0%"), ("PD-L1 TPS", 0.6, "0.0%"), ("ER", 0.955, "0.00%"), ("HER2", 0.125, "0%"), ("Count", 0.45, "General")]:
        ws.append((name, v)); ws.cell(ws.max_row, 2).number_format = fmt
    wb.save(tmp_path / "ihc.xlsx")
    lines = pages(tmp_path / "ihc.xlsx")[0]["text"].splitlines()
    assert lines[2:] == ["| Ki-67 | 45% |", "| PD-L1 TPS | 60.0% |", "| ER | 95.50% |", "| HER2 | 13% |", "| Count | 0.45 |"]


def test_percent_text():
    assert ingest._percent_text(0.45, "0%") == "45%" and ingest._percent_text(0.45, "0.0%") == "45.0%"
    assert ingest._percent_text(1, "0%") == "100%" and ingest._percent_text(-0.005, "0%") == "-1%"
    assert ingest._percent_text(0.45, "General") is None and ingest._percent_text("45%", "0%") is None
    assert ingest._percent_text(True, "0%") is None


def test_xlsx_formula_without_saved_value_is_marked(tmp_path):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "Calc"
    ws.append(("Investigation", "Result")); ws.append(("eGFR", "=186*2")); ws.append(("Creatinine", 0.9))
    wb.create_sheet("Plain").append(("UHID", "SYN-900001"))
    wb.save(tmp_path / "calc.xlsx")  # openpyxl saves formulas without a cached value
    p = pages(tmp_path / "calc.xlsx")
    assert p[0]["text"].splitlines() == ["## Calc", "| Investigation | Result |", f"| eGFR | {ingest.FORMULA_NO_VALUE} |", "| Creatinine | 0.9 |"]
    assert ingest.FORMULA_NO_VALUE == "[formula, no saved value]"
    assert p[0]["needs_review"] == "a formula cell has no saved value; open the file to check"
    assert "needs_review" not in p[1] and p[1]["text"] == "## Plain\n| UHID | SYN-900001 |"


def test_xlsx_formula_with_saved_value_uses_the_value(tmp_path):
    import re, zipfile
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(("eGFR", "=186*2"))
    src = tmp_path / "src.xlsx"; wb.save(src)
    dst = tmp_path / "saved.xlsx"  # add a cached value as Excel would: <f>186*2</f><v>372</v>
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data, n = re.subn(rb"<f>186\*2</f>(?:<v>\s*</v>|<v\s*/>)?", b"<f>186*2</f><v>372</v>", data)
                assert n == 1
            zout.writestr(item, data)
    p = pages(dst)
    assert p[0]["text"].splitlines()[1] == "| eGFR | 372 |" and "needs_review" not in p[0]


def test_cell_text():
    import datetime as dt
    assert [ingest._cell_text(v) for v in (None, 31, "007", 2.45, 11.8, True, dt.date(2026, 1, 2), dt.datetime(2026, 1, 2))] == \
        ["", "31", "007", "2.45", "11.8", "True", "2026-01-02", "2026-01-02"]


def test_pptx_split_fallback_single_page():
    assert ingest._pptx_pages("plain text, no markers") == [{"text": "plain text, no markers", "method": "office-text"}]


def test_pptx_split_keeps_blank_slides_and_preamble():
    md = "Deck\n<!-- Slide number: 1 -->\n# A\n\n<!-- Slide number: 2 -->\n\n<!-- Slide number: 3 -->\n# C"
    assert [x["text"] for x in ingest._pptx_pages(md)] == ["Deck\n# A", "", "# C"]  # page N == slide N


def test_xlsx_does_not_use_markitdown(monkeypatch):
    import markitdown
    def boom(*a, **k):
        raise AssertionError("xlsx must not go through markitdown / pandas")
    monkeypatch.setattr(markitdown.MarkItDown, "convert", boom)
    assert len(pages(OFFICE / "lab_values.xlsx")) == 2


def test_unreadable_xlsx_reports_plainly(tmp_path):
    f = tmp_path / "broken.xlsx"; f.write_bytes(b"not a zip, synthetic")
    p = pages(f)
    assert p[0]["text"] == "" and p[0]["method"].startswith("unsupported (could not read .xlsx file")


@pytest.mark.parametrize("ext", [".pptx", ".xlsx"])
def test_empty_office_file_keeps_no_readable_text_path(unit_case, tmp_path, ext):
    f = tmp_path / f"blank{ext}"
    if ext == ".pptx":
        from pptx import Presentation
        Presentation().save(f)
    else:
        from openpyxl import Workbook
        Workbook().save(f)
    p = pages(f)
    assert "".join(x["text"] for x in p).strip() == ""
    doc = store.add_document_file(unit_case, f.name, f.read_bytes())
    d = asyncio.run(extract.process_document(unit_case, doc["doc_id"], "lung_nsclc", {"mrn": "SYN-900001", "name": "SYNTHETIC, Test Patient"}))
    assert (d["state"], d["error"]) == ("error", "no readable text")


# ---- .doc / .rtf / .odt ----

@pytest.mark.parametrize("name", ["x.doc", "Report.RTF", "notes.odt", Path("a/b/c.doc")])
def test_reject_reason_without_soffice(monkeypatch, name):
    no_soffice(monkeypatch)
    assert ingest.reject_reason(name) == MSG


@pytest.mark.parametrize("name", ["labs.xls", "LABS.XLS", Path("a/b.xls")])
def test_reject_reason_xls(monkeypatch, name):
    no_soffice(monkeypatch)
    assert ingest.reject_reason(name) == XLS_MSG
    with_soffice(monkeypatch)
    assert ingest.reject_reason(name) is None


def test_xls_without_soffice_reads_nothing(monkeypatch, tmp_path):
    no_soffice(monkeypatch)
    f = tmp_path / "labs.xls"; f.write_bytes(b"\xd0\xcf\x11\xe0 synthetic")
    assert pages(f) == [{"text": "", "method": f"unsupported ({XLS_MSG})"}]


def test_xls_with_soffice_goes_through_conversion(monkeypatch, tmp_path):
    with_soffice(monkeypatch)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 1, b"", b""))
    f = tmp_path / "labs.xls"; f.write_bytes(b"\xd0\xcf\x11\xe0 synthetic")
    assert pages(f) == [{"text": "", "method": "unsupported (conversion to PDF failed)"}]
    assert len(calls) == 1 and calls[0][-1] == str(f) and "--convert-to" in calls[0]


@pytest.mark.parametrize("name", ["x.pdf", "x.docx", "x.xlsx", "x.pptx", "x.txt", "x.png"])
def test_reject_reason_none_for_supported(monkeypatch, name):
    no_soffice(monkeypatch)
    assert ingest.reject_reason(name) is None


def test_reject_reason_none_with_soffice(monkeypatch):
    with_soffice(monkeypatch)
    assert ingest.reject_reason("x.doc") is None and ingest.reject_reason("x.odt") is None


def test_rejected_types_stay_in_supported():
    assert ingest.REJECTED_EXT <= ingest.OFFICE_EXT <= ingest.SUPPORTED


def test_messages_plain_no_em_dash():
    src = Path(ingest.__file__).read_text()
    assert "\u2014" not in src and "\u2013" not in src
    assert MSG == ingest.REJECT_MESSAGE and XLS_MSG == ingest.REJECT_MESSAGES[".xls"]


def test_doc_without_soffice_reads_nothing(monkeypatch, tmp_path):
    no_soffice(monkeypatch)
    f = tmp_path / "old.doc"; f.write_bytes(b"\xd0\xcf\x11\xe0 synthetic")
    p = pages(f)
    assert p == [{"text": "", "method": f"unsupported ({MSG})"}]


def test_doc_with_soffice_converts_to_pdf(monkeypatch, tmp_path):
    with_soffice(monkeypatch)
    calls = []
    line = "SYNTHETIC referral letter for patient SYN-900001: histopathology shows adenocarcinoma of the right upper lobe"

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        out = Path(cmd[cmd.index("--outdir") + 1])
        (out / (Path(cmd[-1]).stem + ".pdf")).write_bytes(_pdf_bytes(line))
        return subprocess.CompletedProcess(cmd, 0, b"", b"")
    monkeypatch.setattr(subprocess, "run", fake_run)

    async def no_ocr(*a, **k):
        raise AssertionError("text-layer PDF must not be sent to OCR")
    monkeypatch.setattr(ingest, "ocr_page", no_ocr)
    f = tmp_path / "referral.doc"; f.write_bytes(b"\xd0\xcf\x11\xe0 synthetic")
    p = pages(f)
    assert len(calls) == 1
    cmd, kw = calls[0]
    outdir = cmd[cmd.index("--outdir") + 1]
    assert cmd[0] == "/usr/bin/soffice" and cmd[-1] == str(f)
    assert cmd[1] == "-env:UserInstallation=" + (Path(outdir) / "profile").as_uri()  # own profile per conversion
    assert cmd[2:6] == ["--headless", "--convert-to", "pdf", "--outdir"]
    assert kw["timeout"] == 120
    assert len(p) == 1 and p[0]["method"] == "text-layer" and "adenocarcinoma" in p[0]["text"] and "SYN-900001" in p[0]["text"]
    assert not Path(outdir).exists()  # temporary output directory cleaned up


def test_doc_with_soffice_conversion_fails(monkeypatch, tmp_path):
    with_soffice(monkeypatch)

    def failing_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
    monkeypatch.setattr(subprocess, "run", failing_run)
    f = tmp_path / "slow.rtf"; f.write_text("{\\rtf1 synthetic}")
    p = pages(f)
    assert p[0]["text"] == "" and p[0]["method"].startswith("unsupported (conversion to PDF failed")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"", b""))
    assert pages(f) == [{"text": "", "method": "unsupported (conversion to PDF failed)"}]


# ---- two-read OCR check, line by line (V1 item 3.3) -----------------------------------------------------------
def _two_reads(monkeypatch, full, second, events=None):
    monkeypatch.setenv("TB_OCR_ENGINE", "off")  # the two-read check alone (the independent engine: test_ocr_engine.py)

    async def fake(png, audit=None, max_side=None):
        return second if max_side else full
    monkeypatch.setattr(ingest, "ocr_image", fake)
    return asyncio.run(ingest.ocr_page(b"png", audit=events.append if events is not None else None))


def _span_text_ok(p):
    return all(p["text"][s["start"]:s["end"]] == s["line"] for s in p.get("ocr_uncertain_spans", []) if s.get("read") != "second")


def test_ocr_single_digit_slip_is_flagged(monkeypatch):
    p = _two_reads(monkeypatch, "PD-L1 TPS 6%\nECOG 1", "PD-L1 TPS 8%\nECOG 2")
    assert {"6", "8"} <= set(p["ocr_uncertain_numbers"])
    spans = p["ocr_uncertain_spans"]
    assert [(s["line"], s["numbers"], s["reason"]) for s in spans] == [
        ("PD-L1 TPS 6%", ["6", "8"], "the two OCR reads disagree on a number"),
        ("ECOG 1", ["1", "2"], "the two OCR reads disagree on a number")]
    assert _span_text_ok(p)


def test_ocr_keeps_both_reads(monkeypatch):
    p = _two_reads(monkeypatch, "ECOG 1", "ECOG 2")
    assert p["text"] == "ECOG 1" and p["second_read"] == "ECOG 2" and p["ocr_reads"] == 2 and p["method"] == "vision-transcription"


def test_ocr_number_found_elsewhere_still_flags_its_line(monkeypatch):
    full = "Hb 11.8 g/dL\nWBC 7200 /cumm\nPlatelets 2.45 lakh/cumm"
    second = "Hb 11.3 g/dL\nWBC 7200 /cumm\nMCV 11.8 fL"
    p = _two_reads(monkeypatch, full, second)
    hb = ingest.uncertain_overlap(p, full.index("11.8"), full.index("11.8") + 4)
    assert hb and hb["line"] == "Hb 11.8 g/dL" and hb["numbers"] == ["11.3", "11.8"]
    assert ingest.uncertain_overlap(p, full.index("7200"), full.index("7200") + 4) is None  # agreeing line is never a span
    assert _span_text_ok(p)


def test_ocr_shifted_table_rows_flag_only_the_missing_row(monkeypatch):
    rows = ["| Hb | 11.8 | g/dL |", "| WBC | 7200 | /cumm |", "| Platelets | 2,45,000 | /cumm |",
            "| Creatinine | 0.9 | mg/dL |", "| ALT | 32 | U/L |", "| AST | 28 | U/L |"]
    p = _two_reads(monkeypatch, "\n".join(rows), "\n".join(rows[:2] + rows[3:]))
    spans = p["ocr_uncertain_spans"]
    assert [(s["line"], s["reason"]) for s in spans] == [(rows[2], "this line with numbers appears in one read only")]
    assert p["ocr_uncertain_numbers"] == ["245000"] and _span_text_ok(p)


def test_ocr_dropped_row_and_a_slip_further_down(monkeypatch):
    rows = ["| Hb | 11.8 |", "| WBC | 7200 |", "| Platelets | 245000 |", "| ALT | 32 |", "| AST | 28 |", "| ALP | 96 |"]
    second = rows[:2] + ["| ALT | 32 |", "| AST | 23 |", "| ALP | 96 |"]
    p = _two_reads(monkeypatch, "\n".join(rows), "\n".join(second))
    assert [(s["line"], s["numbers"]) for s in p["ocr_uncertain_spans"]] == [(rows[2], ["245000"]), (rows[4], ["23", "28"])]


def test_ocr_merged_rows_flag_only_those_rows(monkeypatch):
    rows = ["Hb 11.8 g/dL", "WBC 7200 /cumm", "Platelets 245000 /cumm", "Creatinine 0.9 mg/dL", "Urea 24 mg/dL"]
    second = rows[:2] + ["Platelets 245000 /cumm Creatinine 0.9 mg/dL", rows[4]]
    p = _two_reads(monkeypatch, "\n".join(rows), "\n".join(second))
    flagged = {s["line"] for s in p["ocr_uncertain_spans"]}
    assert flagged == {rows[2], rows[3]} and _span_text_ok(p)  # the rows either side still align


def test_ocr_line_in_second_read_only(monkeypatch):
    p = _two_reads(monkeypatch, "Hb 11.8 g/dL\nUrea 24 mg/dL", "Hb 11.8 g/dL\nWBC 7200 /cumm\nUrea 24 mg/dL")
    (s,) = p["ocr_uncertain_spans"]
    assert s["read"] == "second" and s["line"] == "WBC 7200 /cumm" and s["numbers"] == ["7200"] and s["start"] == s["end"]
    assert s["start"] == p["text"].index("Urea") and p["ocr_uncertain_numbers"] == ["7200"]
    assert ingest.uncertain_overlap(p, 0, len("Hb 11.8 g/dL")) is None and ingest.uncertain_overlap(p, s["start"], s["start"] + 4) is None


def test_ocr_numbers_in_a_different_order_or_count(monkeypatch):
    p = _two_reads(monkeypatch, "BP 120/80 mmHg\nSize 3.2 x 2.1 cm", "BP 80/120 mmHg\nSize 3.2 cm")
    assert [(s["line"], s["numbers"]) for s in p["ocr_uncertain_spans"]] == [("BP 120/80 mmHg", ["120", "80"]), ("Size 3.2 x 2.1 cm", ["2.1"])]


def test_ocr_identical_reads_have_no_spans(monkeypatch):
    events = []
    p = _two_reads(monkeypatch, "Hb 11.8 g/dL\nECOG 1", "Hb 11.8 g/dL\nECOG 1", events)
    assert "ocr_uncertain_spans" not in p and "ocr_uncertain_numbers" not in p and events == []


@pytest.mark.parametrize("full,second", [
    ("1. Chest CT\n2. Biopsy", "1) Chest CT\n2) Biopsy"),
    ("(1) Chest CT", "a) Chest CT"),
    ("- 1 -\nHb 11.8", "- 2 -\nHb 11.8"),
    ("Page 1 of 2\nHb 11.8", "Page 2 of 2\nHb 11.8"),
    ("| Hb | 11.8 |", "Hb | 11.8"),
    ("Platelets 2,45,000", "Platelets  245000"),
    ("Hb 11.8\n\n\nECOG 1", "  Hb   11.8\nECOG 1  "),
])
def test_ocr_markers_pipes_and_spacing_are_not_disagreements(monkeypatch, full, second):
    assert "ocr_uncertain_spans" not in _two_reads(monkeypatch, full, second)


def test_ocr_engine_off_changes_nothing_but_a_note(monkeypatch):
    p = _two_reads(monkeypatch, "Hb 11.8 g/dL\nECOG 1", "Hb 11.8 g/dL\nECOG 2")
    assert p.pop("ocr_engine_note") == "independent OCR engine turned off" and "ocr_engine" not in p
    assert set(p) == {"text", "second_read", "method", "ocr_reads", "ocr_uncertain_spans", "ocr_uncertain_numbers"}
    assert all("source" not in s for s in p["ocr_uncertain_spans"])


def test_ocr_disagreement_audit_event(monkeypatch):
    events = []
    _two_reads(monkeypatch, "PD-L1 TPS 6%\nECOG 1\nHb 11.8", "PD-L1 TPS 8%\nECOG 1\nHb 11.8", events)
    assert events == [{"kind": "ocr_disagreement", "numbers": ["6", "8"], "lines": 1}]


def test_uncertain_overlap_by_offsets(monkeypatch):
    full = "Patient: Test Patient\n  PD-L1 TPS 6%  \nECOG 1"
    p = _two_reads(monkeypatch, full, "Patient: Test Patient\nPD-L1 TPS 8%\nECOG 1")
    (s,) = p["ocr_uncertain_spans"]
    assert p["text"][s["start"]:s["end"]] == s["line"] == "PD-L1 TPS 6%"
    at = full.index("6%")
    assert ingest.uncertain_overlap(p, at, at + 2) is s
    assert ingest.uncertain_overlap(p, 0, full.index("\n")) is None
    assert ingest.uncertain_overlap(p, full.index("ECOG"), len(full)) is None
    assert ingest.uncertain_overlap({"text": "x"}, 0, 1) is None


def test_ocr_aadhaar_masked_before_the_line_check(monkeypatch):
    events = []
    p = _two_reads(monkeypatch, "Aadhaar No. 6043 1187 2200\nHb 11.8", "Aadhaar No. 6043 1187 2209\nHb 11.8", events)
    blob = __import__("json").dumps([p, events])
    assert "6043" not in blob and "1187" not in blob and p["aadhaar_masked"] == 1
    assert p["second_read"].startswith("Aadhaar No. XXXX XXXX 2209")


# ---- Hindi / regional text and handwriting flags (V1 item 3.6) ------------------------------------------------
TB005_OPD = Path("/data/vaidyx/tb_demo_corpus/truth/reference_text/TB-005/surgical_oncology/surgical_oncology_opd_2026-09-03.png.txt")
HINDI_LINE = "मरीज़ ने बताया कि बाएँ स्तन में गांठ चार महीने से है।"
DEVANAGARI_FLAG = "contains Hindi / regional text (Devanagari)"
SYNTHETIC_OPD = ("Sahyadri Cancer Institute (SYNTHETIC)\nUHID SYN-500263\nHypothyroidism on thyroxine 50 mcg once daily.\n"
                 + HINDI_LINE + "\nECOG performance status: 0\n")


def _flag_offsets_ok(text, flags):
    return all(text[x["start"]:x["end"]] == x["line"] for x in flags["flagged_lines"])


@pytest.mark.skipif(not TB005_OPD.exists(), reason="demo corpus not present")
def test_tb005_opd_hindi_line_is_flagged(tmp_path):
    f = tmp_path / "opd.txt"; f.write_bytes(TB005_OPD.read_bytes())
    (p,) = pages(f)
    assert p["text"] == TB005_OPD.read_text()  # never translated or removed
    assert p["flags"] == [DEVANAGARI_FLAG]
    assert [(x["line"], x["flag"]) for x in p["flagged_lines"]] == [(HINDI_LINE, DEVANAGARI_FLAG)] and _flag_offsets_ok(p["text"], p)


def test_page_flags_devanagari_lines_and_offsets():
    fl = ingest.page_flags(SYNTHETIC_OPD)
    assert fl["flags"] == [DEVANAGARI_FLAG] and [x["line"] for x in fl["flagged_lines"]] == [HINDI_LINE] and _flag_offsets_ok(SYNTHETIC_OPD, fl)


@pytest.mark.parametrize("line,script", [("நோயாளி வலி இல்லை", "Tamil"), ("রোগীর ব্যথা নেই", "Bengali"), ("ರೋಗಿ ನೋವು ಇಲ್ಲ", "Kannada"),
                                         ("రోగికి నొప్పి లేదు", "Telugu"), ("രോഗിക്ക് വേദനയില്ല", "Malayalam"), ("ਮਰੀਜ਼ ਨੂੰ ਦਰਦ ਨਹੀਂ", "Gurmukhi"),
                                         ("દર્દીને દુખાવો નથી", "Gujarati"), ("ରୋଗୀଙ୍କୁ ଯନ୍ତ୍ରଣା ନାହିଁ", "Odia")])
def test_page_flags_names_each_indic_script(line, script):
    fl = ingest.page_flags("Hb 11.8 g/dL\n" + line)
    assert fl["flags"] == [f"contains Hindi / regional text ({script})"] and fl["flagged_lines"][0]["line"] == line


def test_page_flags_two_scripts_and_illegible_in_one_page():
    text = "Hb 11.8 g/dL\nमरीज़ ठीक है\nநோயாளி நலம்\nDiagnosis: [illegible] carcinoma"
    fl = ingest.page_flags(text)
    assert fl["flags"] == ["contains Hindi / regional text (Devanagari, Tamil)", "handwriting / illegible parts: verify"]
    assert [x["flag"] for x in fl["flagged_lines"]] == ["contains Hindi / regional text (Devanagari)", "contains Hindi / regional text (Tamil)",
                                                         "handwriting / illegible parts: verify"]
    assert _flag_offsets_ok(text, fl)


@pytest.mark.parametrize("marker", ["[illegible]", "[Illegible]", "(illegible)", "[unreadable]", "[UNCLEAR]", "[handwritten note]",
                                    "[handwritten: signature]", "???", "?????", "[illegible word]"])
def test_page_flags_illegible_markers(marker):
    text = f"Clinical notes\nBiopsy from {marker} lesion\nECOG 1"
    fl = ingest.page_flags(text)
    assert fl["flags"] == ["handwriting / illegible parts: verify"]
    assert [x["line"] for x in fl["flagged_lines"]] == [f"Biopsy from {marker} lesion"] and _flag_offsets_ok(text, fl)


@pytest.mark.parametrize("text", ["Package rate ₹ 1,20,000 under PM-JAY", "Is this the right side?", "Clear margins (R0)",
                                  "Résumé of café visit, naïve", "", "Handwritten consent attached", "Question?? Please confirm"])
def test_page_flags_plain_text_is_not_flagged(text):
    assert ingest.page_flags(text) == {}


def test_english_only_pages_have_no_flags(tmp_path):
    import json
    for doc in (FIXTURES / "cases").glob("*/docs/*/doc.json"):
        for pg in json.loads(doc.read_text()).get("pages") or []:
            assert ingest.page_flags(pg.get("text") or "") == {}, doc
    for f in [OFFICE / "lab_values.xlsx", OFFICE / "board_slides.pptx", FIXTURES / "long_discharge_summary.txt"]:
        if f.exists():
            assert all("flags" not in p and "flagged_lines" not in p for p in pages(f)), f


def test_text_layer_pdf_hindi_line_is_flagged(monkeypatch, tmp_path):
    text = SYNTHETIC_OPD + "Hindi note above kept as written in the record for the clinician to read."

    class FakePage:
        def extract_text(self):
            return text

    class FakeReader:
        def __init__(self, path):
            self.pages = [FakePage()]
    import pypdf
    monkeypatch.setattr(pypdf, "PdfReader", FakeReader)
    f = tmp_path / "referral.pdf"; f.write_bytes(b"%PDF-1.4 synthetic")
    (p,) = pages(f)
    assert p["method"] == "text-layer" and p["text"] == text and p["flags"] == [DEVANAGARI_FLAG]


def test_flagged_overlap():
    fl = ingest.page_flags(SYNTHETIC_OPD)
    page = {"text": SYNTHETIC_OPD, **fl}
    at = SYNTHETIC_OPD.index("स्तन")
    assert ingest.flagged_overlap(page, at, at + 4)["line"] == HINDI_LINE
    at = SYNTHETIC_OPD.index("50 mcg")
    assert ingest.flagged_overlap(page, at, at + 6) is None
    assert ingest.flagged_overlap({"text": "x"}, 0, 1) is None


def test_ocr_page_carries_the_flags(monkeypatch):
    p = _two_reads(monkeypatch, SYNTHETIC_OPD + "Signed [illegible]", SYNTHETIC_OPD + "Signed [illegible]")
    assert p["text"] == SYNTHETIC_OPD + "Signed [illegible]"
    assert p["flags"] == [DEVANAGARI_FLAG, "handwriting / illegible parts: verify"] and _flag_offsets_ok(p["text"], p)
    assert "flags" not in _two_reads(monkeypatch, "Hb 11.8 g/dL", "Hb 11.8 g/dL")


# ---- big scans: batches + warning (V1 item 3.7) --------------------------------------------------------------
DECCAN_SCAN = Path("/data/vaidyx/tb_demo_corpus/cases/TB-006/outside_records/deccan_general_hospital_records_scan.pdf")
ENGLISH_LINE = "Patient reviewed in the clinic today and the biopsy report was discussed with the family"


def _blank_pdf(path, n):
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(n):
        w.add_blank_page(width=36, height=36)  # tiny pages: cheap to render
    with open(path, "wb") as f:
        w.write(f)
    return path


def _fake_reader(monkeypatch, text_pages=()):
    """Fake ocr_page and _img_bytes: images are numbered in render order; each read records how many images had been
    rendered when it ran (its batch boundary)."""
    rendered, calls = [], []

    def img(im):
        rendered.append(1); return f"img{len(rendered) - 1}".encode()

    async def read(b, audit=None):
        calls.append(len(rendered)); return {"text": "read of " + b.decode(), "method": "vision-transcription"}
    monkeypatch.setattr(ingest, "_img_bytes", img)
    monkeypatch.setattr(ingest, "ocr_page", read)
    if text_pages:
        import pypdf
        real = pypdf.PdfReader

        class Reader:
            def __init__(self, p):
                self.pages = [type("P", (), {"extract_text": (lambda self, i=i: ENGLISH_LINE if i in text_pages else "")})()
                              for i in range(len(real(p).pages))]
        monkeypatch.setattr(pypdf, "PdfReader", Reader)
    return calls


def test_scanned_pdf_read_in_batches_of_20(monkeypatch, tmp_path):
    calls = _fake_reader(monkeypatch)
    p = pages(_blank_pdf(tmp_path / "scan.pdf", 45))
    from collections import Counter
    assert Counter(calls) == {20: 20, 40: 20, 45: 5}  # 20 rendered and read, then the next 20, then 5
    assert [x["text"] for x in p] == [f"read of img{i}" for i in range(45)]


def test_batches_keep_page_order_with_text_layer_pages(monkeypatch, tmp_path):
    text_pages = {0, 7, 14, 21, 28}
    calls = _fake_reader(monkeypatch, text_pages)
    p = pages(_blank_pdf(tmp_path / "mixed.pdf", 30))
    image_pages = [i for i in range(30) if i not in text_pages]
    assert len(calls) == 25 and sorted(set(calls)) == [20, 25]
    assert [x["method"] for x in p] == ["text-layer" if i in text_pages else "vision-transcription" for i in range(30)]
    assert [p[i]["text"] for i in image_pages] == [f"read of img{k}" for k in range(25)]


def test_small_scan_is_one_batch(monkeypatch, tmp_path):
    calls = _fake_reader(monkeypatch)
    assert len(pages(_blank_pdf(tmp_path / "small.pdf", 3))) == 3 and calls == [3, 3, 3]


def test_scan_batch_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TB_SCAN_BATCH", "4")
    calls = _fake_reader(monkeypatch)
    pages(_blank_pdf(tmp_path / "scan.pdf", 10))
    assert calls == [4] * 4 + [8] * 4 + [10] * 2


def test_multiframe_tiff_read_in_batches(monkeypatch, tmp_path):
    from PIL import Image
    f = tmp_path / "scan.tiff"
    frames = [Image.new("RGB", (8, 8), (i, i, i)) for i in range(25)]
    frames[0].save(f, save_all=True, append_images=frames[1:])
    calls = _fake_reader(monkeypatch)
    p = pages(f)
    assert calls == [20] * 20 + [25] * 5 and [x["text"] for x in p] == [f"read of img{i}" for i in range(25)]


@pytest.mark.skipif(not DECCAN_SCAN.exists(), reason="demo corpus not present")
def test_scan_estimate_and_warning_on_the_100_page_demo_scan(monkeypatch):
    for k in ("TB_SCAN_SECONDS_PER_PAGE", "TB_SCAN_WARN_PAGES"):
        monkeypatch.delenv(k, raising=False)
    assert ingest.scan_estimate(DECCAN_SCAN) == {"pages": 100, "image_pages": 100, "seconds": 120}
    w = ingest.scan_warning(DECCAN_SCAN, DECCAN_SCAN.name)
    assert w == "deccan_general_hospital_records_scan.pdf has 100 scanned pages: reading it will take about 2 minutes"
    assert "—" not in w and "–" not in w


def test_text_pdf_has_no_image_pages_and_no_warning(tmp_path):
    f = tmp_path / "note.pdf"; f.write_bytes(_pdf_bytes(ENGLISH_LINE))
    assert ingest.scan_estimate(f) == {"pages": 1, "image_pages": 0, "seconds": 0}
    assert ingest.scan_warning(f, "note.pdf") is None


def test_scan_estimate_counts_blank_pages_and_frames(tmp_path):
    from PIL import Image
    assert ingest.scan_estimate(_blank_pdf(tmp_path / "b.pdf", 3)) == {"pages": 3, "image_pages": 3, "seconds": 4}  # 3.6 s rounded up
    png = tmp_path / "photo.png"; Image.new("RGB", (8, 8)).save(png)
    assert ingest.scan_estimate(png) == {"pages": 1, "image_pages": 1, "seconds": 2}
    assert ingest.scan_estimate(tmp_path / "notes.txt") is None and ingest.scan_estimate(OFFICE / "lab_values.xlsx") is None
    bad = tmp_path / "broken.pdf"; bad.write_bytes(b"not a pdf")
    assert ingest.scan_estimate(bad) is None and ingest.scan_warning(bad, "broken.pdf") is None


def test_scan_warning_threshold_and_env_overrides(monkeypatch, tmp_path):
    f = _blank_pdf(tmp_path / "scan.pdf", 51)
    assert ingest.scan_warning(f, "scan.pdf") == "scan.pdf has 51 scanned pages: reading it will take about 2 minutes"  # 61.2 s
    assert ingest.scan_warning(_blank_pdf(tmp_path / "fifty.pdf", 50), "fifty.pdf") is None  # warns only above 50
    monkeypatch.setenv("TB_SCAN_WARN_PAGES", "100")
    assert ingest.scan_warning(f, "scan.pdf") is None
    monkeypatch.setenv("TB_SCAN_WARN_PAGES", "10")
    monkeypatch.setenv("TB_SCAN_SECONDS_PER_PAGE", "0.5")
    assert ingest.scan_estimate(f)["seconds"] == 26
    assert ingest.scan_warning(f) == "scan.pdf has 51 scanned pages: reading it will take about 26 seconds"  # filename defaults to the file's name
    monkeypatch.setenv("TB_SCAN_SECONDS_PER_PAGE", "not a number")
    assert ingest.scan_estimate(f)["seconds"] == 62
