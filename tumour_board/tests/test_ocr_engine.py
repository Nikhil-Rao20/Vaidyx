"""Independent OCR engine for numbers (V1 item 8.3): the number check on strings, the word format, Aadhaar masking of the
engine's words, ocr_page with the engine absent / mocked, and (only when Tesseract is installed) the Done-when fixture: one
wrong digit that both model reads share is flagged by the engine. Synthetic text only."""
import asyncio, io, json

import pytest

from tumour_board import ingest, ocr_engine

ENGINE = "the independent OCR engine reads a different number"


def spans(full, eng):
    return [(s["line"], s["numbers"]) for s in ocr_engine.engine_spans(full, eng)]


# ---- engine_spans on strings ----------------------------------------------------------------------------------------
def test_one_wrong_digit_is_flagged():
    full = "IHC REPORT\nPD-L1 (22C3) Tumour Proportion Score: 80%\nKi-67 index: 35%"
    (s,) = ocr_engine.engine_spans(full, "IHC REPORT\nPD-L1 (22C3) Tumour Proportion Score: 60%\nKi-67 index: 35%")
    assert s["line"] == "PD-L1 (22C3) Tumour Proportion Score: 80%" and s["numbers"] == ["60", "80"]
    assert s["reason"] == ENGINE and s["source"] == "engine" and full[s["start"]:s["end"]] == s["line"]


def test_equal_numbers_are_not_flagged():
    t = "Hb 11.8 g/dL 13.0 - 17.0\nECOG 1\nPlatelets 2,45,000 /cumm"
    assert spans(t, t) == []
    assert spans(t, "Hb 11.8 g/dl. 13.0-17.0\nECOG 1\nPlatelets 245000 /cumm") == []


@pytest.mark.parametrize("full,eng", [
    ("Haemoglobin 11.8 g/dL 13.0 - 17.0", "Haemoglobin 118 g/dl. 13.0-17.0"),           # decimal point lost by the engine
    ("S. Creatinine 0.8 mg/dl 0.5 - 1.1", "S. Creatinine 08 mg/dl 05-11"),
    ("22:00 97.8 84 121/71 17 MK", "22:00 97.8 84 121/71 7 MK"),                       # leading digit cut
    ("Platelet count 198 x10^3/uL 150 - 410", "Platelet count 198 x103/uL 150 - 410"),  # merged
    ("cT2b N2 M0, Stage IIIA (AJCC 8th edition)", "€12b NZ MO, Stage IIIA (ACC 8th edition)"),  # letters, missed digits
    ("Mr. RAMESH KUMAR SYN-400118 58 Y / M", "Mr. RAMESH KUMAR SYN-400118 Es EERE"),     # number not read at all
    ("05/09/2026 12:40 Dr. Anand Kulkarni LAB/26/118392", "05/09/2026 12:40 _Dr. Anand Kulkarni _1AB/26/118392"),  # extra number
])
def test_engine_slips_that_are_not_evidence(full, eng):
    assert spans(full, eng) == []


def test_table_rows_with_pipes():
    full = "| Test | Result | Unit |\n| Hb | 11.8 | g/dL |\n| Platelets | 2,46,000 | /cumm |\n| Creatinine | 0.9 | mg/dL |"
    eng = "Test Result Unit\nHb 11.8 g/dL\nPlatelets 2,45,000 /cumm\nCreatinine 0.9 mg/dL"
    assert spans(full, eng) == [("| Platelets | 2,46,000 | /cumm |", ["245000", "246000"])]
    assert spans(full.replace("2,46,000", "2,45,000"), eng) == []


@pytest.mark.parametrize("eng", [
    "1, | have been explained the nature of the procedure, its risks",
    "8.1 have been explained the nature of the procedure, its risks",
    "(1) I have been explained the nature of the procedure, its risks",
])
def test_list_markers_are_not_compared(eng):
    assert spans("1. I have been explained the nature of the procedure, its risks", eng) == []


def test_page_markers_and_blank_form_fields():
    full = "Case record, scanned copy. Page 35 of 100\nItem 4: ______________________ Amount: ________"
    assert spans(full, "Case record, scanned copy. Page 36 of 100\nitem 4: Amount:") == []
    assert spans(full.replace("Item 4", "Item 7"), "Case record, scanned copy. Page 35 of 100\nitem 4: Amount:") == [
        ("Item 7: ______________________ Amount: ________", ["4", "7"])]  # underscores dropped by the engine: still partners


def test_lines_without_partner_compared_with_the_engine_stretch():
    full = "Patient SYNTHETIC\nHb 11.8 | WBC 7200 | Platelets 245000\nReport status: FINAL"
    eng = "Patient SYNTHETIC\nPlatelets 245000\nWBC 7200\nHb 11.8\nReport status: FINAL"  # columns read in another order
    assert spans(full, eng) == []


def test_offsets_with_leading_spaces():
    full = "Patient: Test Patient\n  PD-L1 TPS 6%  \nECOG 1"
    (s,) = ocr_engine.engine_spans(full, "Patient: Test Patient\nPD-L1 TPS 8%\nECOG 1")
    assert full[s["start"]:s["end"]] == "PD-L1 TPS 6%"


def test_confirm_needs_the_same_number_in_doubt():
    full = "10:00 97.9 89 131/72 14 MK"
    first = ocr_engine.engine_spans(full, "10:00 97.9 89 134/72 14 MK")
    assert first and first[0]["numbers"] == ["131", "134"]
    assert ocr_engine.confirm_spans(first, full, "10:00 37.9 89 131/72 14 MK") == []  # another slip on the same row
    assert ocr_engine.confirm_spans(first, full, "10:00 97.9 89 131/72 14 MK") == []  # the re-read agrees
    assert ocr_engine.confirm_spans(first, full, "10:00 97.9 89 134/72 14 MK") == first


# ---- word format, Aadhaar --------------------------------------------------------------------------------------------
TSV_HEAD = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


def _tsv(rows):
    return TSV_HEAD + "".join(f"5\t1\t{b}\t1\t{ln}\t{k + 1}\t{x}\t{y}\t{w}\t{h}\t{c}\t{t}\n" for k, (b, ln, x, y, w, h, c, t) in enumerate(rows))


def test_parse_tsv_normalises_boxes_and_lines():
    tsv = _tsv([(1, 1, 100, 50, 200, 40, 96.4, "Ki-67"), (1, 1, 320, 50, 100, 40, 91.0, "35%"),
                (1, 2, 100, 120, 300, 40, 88.25, "FINAL"), (2, 1, 100, 300, 50, 40, -1, " ")])
    text, words = ocr_engine.parse_tsv(tsv, 1000, 2000)
    assert text == "Ki-67 35%\nFINAL"
    assert words[0] == ["Ki-67", 0.1, 0.025, 0.3, 0.045, 96.4, 0]
    assert words[2] == ["FINAL", 0.1, 0.06, 0.4, 0.08, 88.2, 1] and len(words) == 3


def test_aadhaar_masked_in_text_and_words():
    tsv = _tsv([(1, 1, 10, 10, 90, 20, 95, "Aadhaar"), (1, 1, 110, 10, 40, 20, 95, "No."), (1, 1, 160, 10, 60, 20, 95, "6043"),
                (1, 1, 230, 10, 60, 20, 95, "1187"), (1, 1, 300, 10, 60, 20, 95, "2200"), (1, 2, 10, 40, 40, 20, 95, "Hb"),
                (1, 2, 60, 40, 50, 20, 95, "11.8")])
    text, words = ocr_engine.parse_tsv(tsv, 1000, 1000)
    masked, mw, n = ocr_engine.mask_words(text, words)
    assert n == 1 and masked == "Aadhaar No. XXXX XXXX 2200\nHb 11.8"
    assert [w[0] for w in mw] == ["Aadhaar", "No.", "XXXX", "XXXX", "2200", "Hb", "11.8"]
    assert [w[1:] for w in mw] == [w[1:] for w in words]  # boxes kept for masking the preview
    assert "6043" not in json.dumps([masked, mw]) and "1187" not in json.dumps([masked, mw])


def test_aadhaar_ungrouped_word_on_a_labelled_line():
    tsv = _tsv([(1, 1, 10, 10, 60, 20, 95, "UID:"), (1, 1, 80, 10, 150, 20, 95, "604311872200")])
    text, words = ocr_engine.parse_tsv(tsv, 1000, 1000)
    masked, mw, n = ocr_engine.mask_words(text, words)
    assert n == 1 and "604311872200" not in json.dumps([masked, mw]) and mw[1][0].endswith("2200") and "XXXX" in mw[1][0]


def test_no_aadhaar_words_unchanged():
    text, words = "Hb 11.8", [["Hb", 0.1, 0.1, 0.2, 0.2, 95.0, 0], ["11.8", 0.3, 0.1, 0.4, 0.2, 95.0, 0]]
    assert ocr_engine.mask_words(text, words) == (text, words, 0)


# ---- settings -----------------------------------------------------------------------------------------------------
def test_turned_off_and_not_installed(monkeypatch):
    monkeypatch.setenv("TB_OCR_ENGINE", "off")
    assert not ocr_engine.available() and ocr_engine.unavailable_note() == "independent OCR engine turned off"
    assert asyncio.run(ocr_engine.read_page(b"png")) is None and ocr_engine.engine_info() is None
    monkeypatch.delenv("TB_OCR_ENGINE")
    monkeypatch.setenv("TB_TESSERACT", "/nonexistent/tesseract")
    assert ocr_engine.binary() is None and ocr_engine.unavailable_note() == "independent OCR engine not installed"
    events = []
    assert asyncio.run(ocr_engine.read_page(b"png", events.append)) is None and events == []


def test_recheck_scale():
    assert ocr_engine.recheck_scale([1198, 1693]) == 1.5
    assert ocr_engine.recheck_scale([3000, 2000]) == pytest.approx(1.333, abs=1e-3)
    assert ocr_engine.recheck_scale([4000, 3000]) == 0.75


# ---- ocr_page -----------------------------------------------------------------------------------------------------
def _reader(monkeypatch, full, second=None):
    async def fake(png, audit=None, max_side=None):
        return (second if second is not None else full) if max_side else full
    monkeypatch.setattr(ingest, "ocr_image", fake)


def test_ocr_page_without_the_engine_is_unchanged(monkeypatch):
    monkeypatch.setenv("TB_TESSERACT", "/nonexistent/tesseract")
    _reader(monkeypatch, "PD-L1 TPS 6%\nECOG 1", "PD-L1 TPS 8%\nECOG 1")
    events = []
    p = asyncio.run(ingest.ocr_page(b"png", audit=events.append))
    assert p["ocr_engine_note"] == "independent OCR engine not installed" and "ocr_engine" not in p
    assert [s["reason"] for s in p["ocr_uncertain_spans"]] == ["the two OCR reads disagree on a number"]
    assert events == [{"kind": "ocr_disagreement", "numbers": ["6", "8"], "lines": 1}]


def _fake_engine(monkeypatch, *texts):
    """read_page returns these texts in turn (first read, then the confirming re-read)."""
    calls, it = [], iter(texts)

    async def read(png, audit=None, scale=1.0):
        calls.append(scale)
        return {"engine": "tesseract", "version": "5.5.3", "lang": "eng", "size": [1000, 1400], "text": next(it), "words": []}
    monkeypatch.setattr(ocr_engine, "read_page", read)
    return calls


def test_ocr_page_merges_engine_spans(monkeypatch):
    t = "IHC REPORT\nPD-L1 TPS 80%\nKi-67 35%"
    _reader(monkeypatch, t)
    calls = _fake_engine(monkeypatch, t.replace("80%", "60%"), t.replace("80%", "60%"))
    events = []
    p = asyncio.run(ingest.ocr_page(b"png", audit=events.append))
    (s,) = p["ocr_uncertain_spans"]
    assert s["reason"] == ENGINE and s["source"] == "engine" and p["ocr_uncertain_numbers"] == ["60", "80"]
    assert calls == [1.0, 1.5] and p["ocr_engine"]["recheck"]["confirmed"] == 1 and p["text"] == t  # transcription untouched
    assert events == [{"kind": "ocr_engine_disagreement", "numbers": ["60", "80"], "lines": 1}]
    loc = p["text"].index("80%")
    assert ingest.uncertain_overlap(p, loc, loc + 3)["reason"] == ENGINE


def test_ocr_page_engine_agrees_no_reread(monkeypatch):
    t = "IHC REPORT\nPD-L1 TPS 80%"
    _reader(monkeypatch, t)
    calls = _fake_engine(monkeypatch, t)
    p = asyncio.run(ingest.ocr_page(b"png"))
    assert "ocr_uncertain_spans" not in p and calls == [1.0] and p["ocr_engine"]["text"] == t and "ocr_engine_note" not in p


def test_ocr_page_unconfirmed_engine_slip_is_dropped(monkeypatch):
    t = "10:00 97.9 89 131/72 14 MK"
    _reader(monkeypatch, t)
    _fake_engine(monkeypatch, "10:00 97.9 89 134/72 14 MK", "10:00 97.9 89 131/72 14 MK")
    p = asyncio.run(ingest.ocr_page(b"png"))
    assert "ocr_uncertain_spans" not in p and p["ocr_engine"]["recheck"] == {
        "scale": 1.5, "text": t, "candidates": 1, "confirmed": 0}


def test_ocr_page_keeps_both_reasons_on_one_line(monkeypatch):
    _reader(monkeypatch, "PD-L1 TPS 80%\nECOG 1", "PD-L1 TPS 30%\nECOG 1")
    _fake_engine(monkeypatch, "PD-L1 TPS 60%\nECOG 1", "PD-L1 TPS 60%\nECOG 1")
    p = asyncio.run(ingest.ocr_page(b"png"))
    assert [s["reason"] for s in p["ocr_uncertain_spans"]] == ["the two OCR reads disagree on a number", ENGINE]
    assert p["ocr_uncertain_numbers"] == ["30", "60", "80"]


def test_ocr_page_engine_failure_is_a_note(monkeypatch):
    async def none(png, audit=None, scale=1.0):
        return None
    monkeypatch.setattr(ocr_engine, "read_page", none)
    monkeypatch.setattr(ocr_engine, "binary", lambda: "/usr/bin/tesseract")
    _reader(monkeypatch, "ECOG 1")
    p = asyncio.run(ingest.ocr_page(b"png"))
    assert p["ocr_engine_note"] == "independent OCR engine could not read this page" and "ocr_uncertain_spans" not in p


# ---- with the real binary -------------------------------------------------------------------------------------------
IHC_LINES = ["Sahyadri Cancer Institute (SYNTHETIC)", "IHC REPORT", "UHID SYN-400118",
             "PD-L1 (22C3) Tumour Proportion Score: 60%", "Ki-67 index: 35%", "Report status: FINAL"]


def _png(lines) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.load_default(size=28)
    im = Image.new("L", (1100, 60 + 50 * len(lines)), 255)
    d = ImageDraw.Draw(im)
    for k, line in enumerate(lines):
        d.text((40, 30 + 50 * k), line, fill=0, font=font)
    buf = io.BytesIO(); im.save(buf, "PNG")
    return buf.getvalue()


needs_binary = pytest.mark.skipif(not ocr_engine.available(), reason="Tesseract not installed")


@needs_binary
def test_done_when_one_wrong_digit_both_reads_share_is_flagged(monkeypatch):
    """V1 8.3 Done when: both model reads say 80% (the two-read check cannot see it); the engine reads 60% on the image."""
    wrong = "\n".join(IHC_LINES).replace("60%", "80%")
    _reader(monkeypatch, wrong, wrong)
    events = []
    p = asyncio.run(ingest.ocr_page(_png(IHC_LINES), audit=events.append))
    (s,) = p["ocr_uncertain_spans"]
    assert s["line"] == "PD-L1 (22C3) Tumour Proportion Score: 80%" and s["reason"] == ENGINE and s["numbers"] == ["60", "80"]
    assert p["text"] == wrong and p["ocr_engine"]["engine"] == "tesseract" and p["ocr_engine"]["version"].startswith("5.")
    assert {"kind": "ocr_engine_disagreement", "numbers": ["60", "80"], "lines": 1} in events
    loc = p["text"].index("80%")
    assert ingest.uncertain_overlap(p, loc, loc + 3) is s


@needs_binary
def test_real_read_word_format(monkeypatch):
    r = asyncio.run(ocr_engine.read_page(_png(IHC_LINES)))
    assert r["engine"] == "tesseract" and r["lang"] == "eng" and r["size"] == [1100, 360]
    assert "PD-L1 (22C3) Tumour Proportion Score: 60%" in r["text"]
    lines = r["text"].split("\n")
    for t, x0, y0, x1, y1, conf, n in r["words"]:
        assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1 and isinstance(conf, float) and t in lines[n].split(" ")
    w = next(w for w in r["words"] if w[0] == "60%")
    assert w[6] == lines.index("PD-L1 (22C3) Tumour Proportion Score: 60%")


@needs_binary
def test_real_read_masks_aadhaar():
    r = asyncio.run(ocr_engine.read_page(_png(["Aadhaar No. 6043 1187 2200", "Hb 11.8 g/dL"])))
    blob = json.dumps(r)
    assert "6043" not in blob and "1187" not in blob and "XXXX XXXX 2200" in r["text"] and r["aadhaar_masked"] == 1


@needs_binary
def test_real_read_error_is_audited_never_raised():
    events = []
    assert asyncio.run(ocr_engine.read_page(b"not an image", events.append)) is None
    assert events and events[0]["kind"] == "ocr_engine_error"
