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
